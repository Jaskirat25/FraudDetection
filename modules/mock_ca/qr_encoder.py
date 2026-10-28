"""
modules/mock_ca/qr_encoder.py - Synthetic V5 Secure QR Generator.
Builds, signs, zlib-compresses, and BigInt-encodes authentic UIDAI V5 Secure QR codes
that decode and verify 100% cleanly against the Mock-UIDAI CA.
"""

import sys
import zlib
import datetime
from typing import Dict, Any, Optional, Tuple
import numpy as np
import cv2
import qrcode
from qrcode.constants import ERROR_CORRECT_L

if hasattr(sys, "set_int_max_str_digits"):
    sys.set_int_max_str_digits(50000)

from modules.mock_ca.ca_authority import sign_qr_payload, get_or_create_mock_ca


def create_synthetic_qr_payload(
    demographics: Dict[str, str],
    photo_bgr: Optional[np.ndarray] = None,
    issue_datetime: Optional[datetime.datetime] = None,
    corrupt_signature: bool = False
) -> Tuple[bytes, str, np.ndarray]:
    """
    Constructs a complete UIDAI V5 Secure QR payload:
    1. Delimited text fields (0xFF).
    2. Embedded JPEG photo.
    3. RSA-2048 PKCS#1 v1.5 / SHA-256 digital signature (256 bytes).
    4. zlib compression.
    5. BigInteger decimal string encoding.
    6. High-density QR code image matrix.

    Returns:
        (compressed_bytes, decimal_string, qr_image_bgr)
    """
    if issue_datetime is not None:
        now = issue_datetime
    elif "issue_datetime" in demographics and isinstance(demographics["issue_datetime"], datetime.datetime):
        now = demographics["issue_datetime"]
    elif "issue_date" in demographics and demographics["issue_date"]:
        raw_ts = str(demographics["issue_date"]).replace("/", "-")
        try:
            now = datetime.datetime.fromisoformat(raw_ts)
        except Exception:
            now = datetime.datetime.strptime(raw_ts, "%Y-%m-%d %H:%M:%S")
    else:
        now = datetime.datetime.now(datetime.timezone.utc)
    ts_str = now.strftime("%Y%m%d%H%M%S")
    
    last4 = demographics.get("last4") or demographics.get("aadhaar_last4") or "1234"
    ref_id = f"{last4}{ts_str}999"

    name = demographics.get("name", "Aarav Sharma")
    dob = demographics.get("dob", "15/08/1995")
    gender = demographics.get("gender", "M")[0].upper()
    care_of = demographics.get("care_of", "S/O Rajesh Sharma")
    state = demographics.get("state", "Punjab")
    district = demographics.get("district", "Kapurthala")
    landmark = demographics.get("landmark", "Main Road")
    house = demographics.get("house", "H.No 102")
    location = demographics.get("location", "Sector 4")
    pincode = demographics.get("pincode", "144622")
    post_office = demographics.get("post_office", "Central PO")
    state = demographics.get("state", "Punjab")
    subdistrict = demographics.get("subdistrict", district)

    # Prepare photo bytes
    if photo_bgr is not None and photo_bgr.size > 0:
        # Resize photo to standard compact Aadhaar QR thumbnail (64x64, ~900 bytes)
        thumb = cv2.resize(photo_bgr, (64, 64), interpolation=cv2.INTER_AREA)
        success, photo_bytes = cv2.imencode(".jpg", thumb, [cv2.IMWRITE_JPEG_QUALITY, 45])
        if not success:
            photo_bytes = b""
        else:
            photo_bytes = bytes(photo_bytes)
    else:
        # Dummy small 1x1 JPEG
        dummy = np.zeros((32, 32, 3), dtype=np.uint8)
        _, photo_bytes = cv2.imencode(".jpg", dummy)
        photo_bytes = bytes(photo_bytes)

    # Construct V5 parts array (separated by 0xFF)
    parts = [
        b"V5",                                  # 0: Format
        b"3",                                   # 1: Email/Mobile code
        ref_id.encode("latin-1"),               # 2: Ref ID
        name.encode("latin-1"),                 # 3: Name
        dob.encode("latin-1"),                  # 4: DOB
        gender.encode("latin-1"),               # 5: Gender
        care_of.encode("latin-1"),              # 6: Care Of
        district.encode("latin-1"),             # 7: District
        landmark.encode("latin-1"),             # 8: Landmark
        house.encode("latin-1"),                # 9: House
        location.encode("latin-1"),             # 10: Location
        pincode.encode("latin-1"),              # 11: PIN
        post_office.encode("latin-1"),          # 12: Post Office
        state.encode("latin-1"),                # 13: State
        subdistrict.encode("latin-1"),          # 14: Sub-district
        photo_bytes                             # 15: JPEG photo codestream
    ]

    data_payload = b"\xff".join(parts)

    # Generate RSA-2048 Digital Signature
    priv_key, _, _ = get_or_create_mock_ca()
    signature_bytes = sign_qr_payload(data_payload, private_key=priv_key)

    if corrupt_signature:
        # Corrupt last 4 bytes to simulate signature forgery
        sig_list = bytearray(signature_bytes)
        sig_list[-1] ^= 0xFF
        sig_list[-2] ^= 0xAA
        signature_bytes = bytes(sig_list)

    # Combine data payload and 256-byte signature
    decompressed = data_payload + signature_bytes

    # zlib compress
    compressed_bytes = zlib.compress(decompressed, level=9)

    # Convert to BigInteger decimal string
    big_int = int.from_bytes(compressed_bytes, "big")
    decimal_str = str(big_int)

    # Render QR code image
    qr = qrcode.QRCode(
        version=None,                           # Auto-detect minimum version
        error_correction=ERROR_CORRECT_L,       # Level L for maximum data capacity
        box_size=4,
        border=2,
    )
    qr.add_data(decimal_str)
    qr.make(fit=True)
    qr_pil = qr.make_image(fill_color="black", back_color="white")
    qr_bgr = cv2.cvtColor(np.array(qr_pil.convert("RGB")), cv2.COLOR_RGB2BGR)

    return compressed_bytes, decimal_str, qr_bgr
