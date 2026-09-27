"""
modules/qr/qr_verifier.py - Secure QR Decoding, Decompression & Cryptographic Cross-Checking (L1).
Supports:
1. UIDAI V4 & V5 Secure QR Codes (Big-Int Byte Stream + RSA-2048 Signed).
2. High-Density decoding via zxing-cpp, PyZbar, and OpenCV.
3. Legacy XML QR (<PrintLetterBarcodeData ... />).
4. Cryptographic cross-check against printed OCR text.
"""

import zlib
import re
import xml.etree.ElementTree as ET
from typing import Optional, Dict, Tuple, List, Any
import numpy as np
import cv2
from core.types import QRResult, FieldCrop


def _decode_qr_image(qr_img: np.ndarray) -> Optional[Tuple[bytes, str]]:
    """
    Decodes QR code from image array using zxing-cpp as primary engine,
    with pyzbar and OpenCV fallbacks.
    Returns: (raw_bytes, text_data)
    """
    if qr_img is None or qr_img.size == 0:
        return None

    # 1. Primary Engine: zxing-cpp (Handles high-density V4/V5 Secure QR codes effortlessly)
    try:
        import zxingcpp
        results = zxingcpp.read_barcodes(qr_img)
        if results:
            return results[0].bytes, results[0].text
    except Exception:
        pass

    # 2. Convert to grayscale and test with zxing-cpp
    if len(qr_img.shape) == 3:
        gray = cv2.cvtColor(qr_img, cv2.COLOR_BGR2GRAY)
    else:
        gray = qr_img.copy()

    try:
        import zxingcpp
        results = zxingcpp.read_barcodes(gray)
        if results:
            return results[0].bytes, results[0].text
    except Exception:
        pass

    # 3. Fallback: PyZbar
    try:
        from pyzbar import pyzbar
        decoded_objs = pyzbar.decode(gray)
        if decoded_objs:
            return decoded_objs[0].data, decoded_objs[0].data.decode("latin-1", errors="ignore")
    except Exception:
        pass

    # 4. Fallback: Multi-scale contrast enhancement
    for scale in [1.5, 2.0]:
        scaled = cv2.resize(gray, (0, 0), fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
        enhanced = clahe.apply(scaled)
        try:
            import zxingcpp
            results = zxingcpp.read_barcodes(enhanced)
            if results:
                return results[0].bytes, results[0].text
        except Exception:
            pass

    return None


# Cached Public Keys Trust Store
_TRUSTED_PUBLIC_KEYS = None


def _get_trusted_public_keys():
    """Loads all UIDAI certificates (.cer / .pem) from data/certs/ with their validity windows."""
    global _TRUSTED_PUBLIC_KEYS
    if _TRUSTED_PUBLIC_KEYS is None:
        _TRUSTED_PUBLIC_KEYS = []
        from pathlib import Path
        from datetime import datetime, timezone
        cert_dir = Path(__file__).resolve().parent.parent.parent / "data" / "certs"
        
        if cert_dir.exists():
            from cryptography.x509 import load_der_x509_certificate, load_pem_x509_certificate
            candidate_files = list(cert_dir.glob("*.cer")) + list(cert_dir.glob("*.pem")) + list(cert_dir.glob("*.crt"))
            for cert_file in candidate_files:
                try:
                    data = cert_file.read_bytes()
                    try:
                        cert = load_der_x509_certificate(data)
                    except Exception:
                        cert = load_pem_x509_certificate(data)
                    
                    # Extract UTC validity window
                    valid_from = cert.not_valid_before_utc if hasattr(cert, 'not_valid_before_utc') else cert.not_valid_before.replace(tzinfo=timezone.utc)
                    valid_to = cert.not_valid_after_utc if hasattr(cert, 'not_valid_after_utc') else cert.not_valid_after.replace(tzinfo=timezone.utc)

                    _TRUSTED_PUBLIC_KEYS.append({
                        "name": cert_file.name,
                        "pub_key": cert.public_key(),
                        "valid_from": valid_from,
                        "valid_to": valid_to
                    })
                except Exception as e:
                    print(f"[Crypto] Notice: Could not load {cert_file.name}: {e}")
    return _TRUSTED_PUBLIC_KEYS


def _parse_issue_timestamp_from_ref_id(ref_id: str):
    """
    Extracts the issue date/time from Reference ID string.
    Format: <last4><YYYYMMDDHHMMSS><subseconds> (e.g., 301920260724211943730 -> 2026-07-24 21:19:43)
    """
    from datetime import datetime, timezone
    if len(ref_id) >= 18:
        # Digits 4 to 18 contain YYYYMMDDHHMMSS
        ts_str = ref_id[4:18]
        try:
            dt = datetime.strptime(ts_str, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
            return dt, dt.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            pass
    return None, None


def _verify_uidai_rsa_signature(
    payload_bytes: bytes,
    signature_bytes: bytes,
    issue_dt=None
) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Deterministic Key Selection:
    1. Filters for certificates whose active window covers the card's issue timestamp.
    2. Verifies RSA-2048 signature against the matched certificate.
    Returns: (is_valid, matching_cert_name, anomaly_note)
    """
    keys = _get_trusted_public_keys()
    if not keys:
        return False, None, "No certificates found in data/certs trust store."

    from cryptography.hazmat.primitives.asymmetric import padding
    from cryptography.hazmat.primitives import hashes

    # Step A: Filter by timestamp if issue date is present
    target_keys = []
    if issue_dt is not None:
        for k in keys:
            if k["valid_from"] <= issue_dt <= k["valid_to"]:
                target_keys.append(k)

        if not target_keys:
            note = f"Temporal Anomaly: Card claims issue date {issue_dt.strftime('%Y-%m-%d')}, but no UIDAI certificate in trust store was active on that date."
            # Fall back to testing all keys just in case clock drift or unparsed timezone
            target_keys = keys
        else:
            note = f"Active Certificate Matched for Issue Date {issue_dt.strftime('%Y-%m-%d')}."
    else:
        target_keys = keys
        note = None

    # Step B: Cryptographic RSA Verification
    for k in target_keys:
        try:
            k["pub_key"].verify(
                signature_bytes,
                payload_bytes,
                padding.PKCS1v15(),
                hashes.SHA256()
            )
            return True, k["name"], f"Verified by active cert: {k['name']}"
        except Exception:
            continue

    return False, None, note


def _parse_xml_qr(xml_text: str) -> Dict[str, str]:
    """Parses pre-2019 unsigned XML QR format."""
    payload: Dict[str, str] = {}
    try:
        root = ET.fromstring(xml_text)
        attribs = root.attrib
        payload["name"] = attribs.get("name", "")
        payload["dob"] = attribs.get("dob", attribs.get("yob", ""))
        payload["gender"] = "MALE" if attribs.get("gender", "") == "M" else "FEMALE" if attribs.get("gender", "") == "F" else attribs.get("gender", "")
        payload["last4"] = attribs.get("uid", "")[-4:] if attribs.get("uid") else ""
        payload["pincode"] = attribs.get("pc", "")
        payload["state"] = attribs.get("state", "")
        payload["address"] = f"{attribs.get('house', '')} {attribs.get('street', '')} {attribs.get('dist', '')} {attribs.get('state', '')}".strip()
    except Exception as e:
        print(f"[QR] XML parsing fallback: {e}")
    return payload


def _parse_secure_qr(raw_bytes: bytes, text_data: str) -> Tuple[Dict[str, str], Optional[np.ndarray], bool]:
    """
    Parses UIDAI V4 & V5 Secure QR Codes.
    Extracts demographics, face photo, issue timestamp, and performs Temporal Certificate Verification.
    """
    payload: Dict[str, str] = {}
    photo_np = None
    sig_valid = False

    # 1. Convert Big-Integer decimal string to bytes if applicable
    if text_data and text_data.strip().isdigit():
        big_int = int(text_data.strip())
        byte_len = (big_int.bit_length() + 7) // 8
        working_bytes = big_int.to_bytes(byte_len, "big")
    else:
        working_bytes = raw_bytes

    # 2. Decompress zlib stream
    decompressed = None
    for wbits in [16 + zlib.MAX_WBITS, -15, 0, zlib.MAX_WBITS]:
        try:
            decompressed = zlib.decompress(working_bytes, wbits)
            break
        except Exception:
            continue

    if decompressed is None:
        decompressed = working_bytes

    # 3. Split by delimiter 255 (0xFF)
    parts = decompressed.split(b"\xff")
    
    def decode_part(idx):
        return parts[idx].decode("latin-1", errors="ignore").strip() if idx < len(parts) else ""

    # Detect V5 format (Starts with V5) vs Standard V4 format
    is_v5 = len(parts) > 0 and decode_part(0).upper().startswith("V5")
    ref_id = ""

    if is_v5 and len(parts) >= 15:
        ref_id = decode_part(2)
        payload["version"] = "V5"
        payload["last4"] = ref_id[:4] if len(ref_id) >= 4 else ""
        payload["name"] = decode_part(3)
        payload["dob"] = decode_part(4).replace("-", "/")
        
        raw_g = decode_part(5).upper()
        payload["gender"] = "MALE" if raw_g == "M" else "FEMALE" if raw_g == "F" else raw_g
        
        payload["care_of"] = decode_part(6)
        payload["district"] = decode_part(7)
        payload["pincode"] = decode_part(11)
        payload["state"] = decode_part(13)
        payload["address"] = f"{payload.get('care_of', '')}, {payload.get('district', '')}, {payload.get('state', '')} - {payload.get('pincode', '')}".strip(", -")

    elif len(parts) >= 15:
        ref_id = decode_part(1)
        payload["version"] = "V4"
        payload["last4"] = ref_id[:4] if len(ref_id) >= 4 else ""
        payload["name"] = decode_part(2)
        payload["dob"] = decode_part(3).replace("-", "/")
        
        raw_g = decode_part(4).upper()
        payload["gender"] = "MALE" if raw_g == "M" else "FEMALE" if raw_g == "F" else raw_g
        
        payload["care_of"] = decode_part(5)
        payload["district"] = decode_part(6)
        payload["house"] = decode_part(8)
        payload["pincode"] = decode_part(10)
        payload["state"] = decode_part(12)
        payload["address"] = f"{payload.get('house', '')} {decode_part(13)} {payload.get('district', '')} {payload.get('state', '')}".strip()

    # 4. Extract Issue Timestamp from Reference ID for Temporal Cert Selection
    issue_dt, issue_str = _parse_issue_timestamp_from_ref_id(ref_id)
    if issue_str:
        payload["issue_timestamp"] = issue_str

    # 5. Check RSA-2048 digital signature with Temporal Key Matching
    if len(decompressed) > 256:
        data_payload = decompressed[:-256]
        signature_bytes = decompressed[-256:]
        sig_valid, matching_cert, note = _verify_uidai_rsa_signature(data_payload, signature_bytes, issue_dt=issue_dt)
        if matching_cert:
            payload["verified_by_cert"] = matching_cert
        if note:
            payload["cert_timeline_status"] = note

    # Extract Face Photo if present (JPEG2000 bytes)
    for p in parts:
        # Check JPEG or JPEG2000 signatures
        if len(p) > 200:
            if p.startswith(b"\xff\xd8") or p.startswith(b"\x00\x00\x00\x0c\x6a\x50\x20\x20"):
                nparr = np.frombuffer(p, np.uint8)
                decoded_pic = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                if decoded_pic is not None:
                    photo_np = decoded_pic
                    break

    return payload, photo_np, sig_valid


def decode_and_verify_qr(
    image: np.ndarray,
    qr_crop: Optional[np.ndarray] = None
) -> QRResult:
    """
    Decodes QR code from either the whole card or the cropped QR region.
    Unpacks demographics, face photo, and signature validity.
    """
    decoded = None

    # 1. Try decoding from dedicated QR crop first
    if qr_crop is not None and qr_crop.size > 0:
        decoded = _decode_qr_image(qr_crop)

    # 2. Fallback to whole card image
    if decoded is None and image is not None:
        decoded = _decode_qr_image(image)

    if decoded is None:
        return QRResult(
            present=False,
            signature_valid=False,
            is_secure_qr=False,
            payload={},
            photo=None,
            flags=["No readable QR code found in card scan."]
        )

    raw_bytes, text_data = decoded

    # Branch 1: Legacy XML QR
    if "<PrintLetterBarcodeData" in text_data or "<?xml" in text_data:
        payload = _parse_xml_qr(text_data)
        return QRResult(
            present=True,
            signature_valid=False,
            is_secure_qr=False,
            payload=payload,
            photo=None,
            raw_text=text_data[:80],
            flags=["Legacy XML QR Code (Pre-2019, Unsigned)."]
        )

    # Branch 2: Secure QR (V4 / V5)
    payload, photo_np, sig_valid = _parse_secure_qr(raw_bytes, text_data)
    if payload and payload.get("name"):
        return QRResult(
            present=True,
            signature_valid=sig_valid,
            is_secure_qr=True,
            payload=payload,
            photo=photo_np,
            raw_text=text_data[:40] + "...",
            flags=[f"Secure QR Code ({payload.get('version', '2019+')} RSA Signed)."]
        )

    return QRResult(
        present=True,
        signature_valid=False,
        is_secure_qr=False,
        payload={"raw": text_data[:100]},
        photo=None,
        raw_text=text_data[:60],
        flags=["Unrecognized QR payload format."]
    )


def cross_check_qr_with_ocr(
    qr_payload: Dict[str, str],
    ocr_fields: Dict[str, Tuple[str, float]]
) -> Tuple[bool, List[str], Dict[str, float]]:
    """
    Performs deterministic cross-check comparison between QR payload and OCR extracted fields.
    """
    violations = []
    scores = {}
    is_fraud = False

    # 1. DOB Cross-Check
    qr_dob = qr_payload.get("dob", "").strip()
    ocr_dob = ocr_fields.get("dob", ("", 0.0))[0].strip()
    if qr_dob and ocr_dob:
        if qr_dob != ocr_dob and qr_dob[-4:] != ocr_dob[-4:]:
            is_fraud = True
            violations.append(f"DOB TAMPER DETECTED: Printed card shows '{ocr_dob}', but signed QR contains '{qr_dob}'.")
            scores["dob_mismatch"] = 1.0
        else:
            scores["dob_mismatch"] = 0.0

    # 2. Gender Cross-Check
    qr_gender = qr_payload.get("gender", "").upper().strip()
    ocr_gender = ocr_fields.get("gender", ("", 0.0))[0].upper().strip()
    if qr_gender and ocr_gender:
        if qr_gender != ocr_gender and qr_gender[0] != ocr_gender[0]:
            is_fraud = True
            violations.append(f"GENDER MISMATCH: Card shows '{ocr_gender}', but signed QR contains '{qr_gender}'.")
            scores["gender_mismatch"] = 1.0
        else:
            scores["gender_mismatch"] = 0.0

    # 3. Last 4 Digits Cross-Check
    qr_last4 = qr_payload.get("last4", "").strip()
    ocr_aadhaar = ocr_fields.get("aadhaar_no", ("", 0.0))[0].strip()
    ocr_digits = "".join(filter(str.isdigit, ocr_aadhaar))
    if qr_last4 and len(ocr_digits) >= 4:
        ocr_last4 = ocr_digits[-4:]
        if qr_last4 != ocr_last4:
            is_fraud = True
            violations.append(f"AADHAAR NUMBER MISMATCH: Card ends in '{ocr_last4}', but signed QR belongs to ID ending in '{qr_last4}'.")
            scores["aadhaar_no_mismatch"] = 1.0
        else:
            scores["aadhaar_no_mismatch"] = 0.0

    # 4. Name Cross-Check (Fuzzy string similarity)
    qr_name = qr_payload.get("name", "").lower().strip()
    ocr_name = ocr_fields.get("name_en", ("", 0.0))[0].lower().strip()
    if qr_name and ocr_name:
        common_chars = sum(1 for c in set(qr_name) if c in ocr_name)
        total_unique = len(set(qr_name) | set(ocr_name))
        sim = common_chars / max(1, total_unique)
        if sim < 0.5:
            is_fraud = True
            violations.append(f"NAME TAMPER DETECTED: Printed name '{ocr_name.title()}' differs from signed QR name '{qr_name.title()}'.")
            scores["name_mismatch"] = 1.0
        else:
            scores["name_mismatch"] = round(1.0 - sim, 2)

    return is_fraud, violations, scores
