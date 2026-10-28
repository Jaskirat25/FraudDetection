"""
api/main.py - FastAPI Backend for Aadhaar Authenticity Screening System Dashboard (M9).
Exposes REST endpoints for document screening, live webcam biometric matching, and audit reporting.
"""

import os
import sys
import time
import base64
import tempfile
from pathlib import Path
from typing import Optional, Dict, Any, List

import numpy as np
import cv2
from fastapi import FastAPI, UploadFile, File, Form, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.types import RiskReport, FieldCrop, RiskLevel, ModuleResult
from modules.register import register_card
from modules.qr import decode_and_verify_qr
from modules.ocr import extract_fields
from modules.validate import validate_rules
from modules.tamper import detect_tamper
from modules.face import verify_face
from modules.scoring import compute_risk_report
from modules.validate.verhoeff import validate_verhoeff
from modules.passport.pipeline import screen_passport
from modules.passport.fusion import PassportDecision, PassportPriority

app = FastAPI(
    title="Layered Aadhaar Authenticity Screening System",
    description="5-Layer Defense-in-Depth Pipeline for Aadhaar Verification",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _to_base64_uri(img: Optional[np.ndarray], format: str = ".jpg") -> Optional[str]:
    """Encodes a NumPy image array into a base64 data URI string."""
    if img is None or img.size == 0:
        return None
    success, buffer = cv2.imencode(format, img)
    if not success:
        return None
    b64_str = base64.b64encode(buffer).decode("utf-8")
    mime = "image/jpeg" if format.lower() in (".jpg", ".jpeg") else "image/png"
    return f"data:{mime};base64,{b64_str}"


def _decode_base64_image(data_uri: str) -> Optional[np.ndarray]:
    """Decodes a base64 data URI (e.g. data:image/jpeg;base64,...) to a NumPy array."""
    try:
        if "," in data_uri:
            data_uri = data_uri.split(",", 1)[1]
        raw_bytes = base64.b64decode(data_uri)
        nparr = np.frombuffer(raw_bytes, np.uint8)
        return cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    except Exception:
        return None


@app.get("/", response_class=HTMLResponse)
async def serve_dashboard(request: Request):
    """Serves the interactive screening dashboard."""
    return templates.TemplateResponse(request=request, name="index.html")


@app.get("/api/samples")
async def list_sample_images():
    """Lists pre-packaged sample documents in the workspace for rapid testing."""
    sample_files = [
        # Aadhaar Samples
        {
            "id": "sample_pair_jaskirat",
            "doc_type": "aadhaar",
            "title": "Jaskirat Singh (Front + Back Separate Pair)",
            "description": "Two separate photos: Front portrait & back V5 Secure QR (Authentic match)",
            "tag": "Dual-Sided Pair",
            "tag_color": "emerald",
            "is_pair": True,
            "front_file": "aadhar_front.jpeg",
            "back_file": "WhatsApp Image 2026-09-27 at 5.05.50 PM.jpeg"
        },
        {
            "id": "combined-image.jpg",
            "doc_type": "aadhaar",
            "title": "Jaskirat Singh (Front + Back Combined)",
            "description": "Complete card with front photo & V5 Secure QR (Authentic match)",
            "tag": "Authentic Full Card",
            "tag_color": "green"
        },
        {
            "id": "WhatsApp Image 2026-09-27 at 5.05.50 PM.jpeg",
            "doc_type": "aadhaar",
            "title": "Jaskirat Singh (Card Back + V5 QR)",
            "description": "High-density V5 BigInt QR code with RSA-2048 signature",
            "tag": "Secure QR Back",
            "tag_color": "blue"
        },
        {
            "id": "aadhar_front.jpeg",
            "doc_type": "aadhaar",
            "title": "Jaskirat Singh (Card Front Photo & Text)",
            "description": "Front card scan with clear photo crop, name, and DOB",
            "tag": "Card Front",
            "tag_color": "indigo"
        },
        {
            "id": "WhatsApp Image 2026-09-25 at 10.32.28 AM.jpeg",
            "doc_type": "aadhaar",
            "title": "Dhruv (Different Person / Impostor Test)",
            "description": "Use as live selfie or card to test biometric mismatch & photo-swap",
            "tag": "Impostor Test Subject",
            "tag_color": "amber"
        },
        # Passport Samples
        {
            "id": "data/samples/sample_passport_authentic.jpg",
            "doc_type": "passport",
            "title": "Jaskirat Singh (Authentic Indian Passport)",
            "description": "Genuine ICAO Doc 9303 TD3 booklet: 7-3-1 modulo-10 verified & VIZ matched",
            "tag": "Authentic Doc 9303",
            "tag_color": "emerald"
        },
        {
            "id": "data/samples/sample_passport_tampered.jpg",
            "doc_type": "passport",
            "title": "Jaskirat Singh (Tampered Passport Number)",
            "description": "VIZ printed number altered to Z9876543 (MRZ / VIZ mismatch detected)",
            "tag": "Tampered VIZ Number",
            "tag_color": "red"
        },
        {
            "id": "data/samples/sample_passport_expired.jpg",
            "doc_type": "passport",
            "title": "Jaskirat Singh (Expired Passport - 2022)",
            "description": "Valid format & checksums, but expired document validity (Rule D-7)",
            "tag": "Expired Document",
            "tag_color": "amber"
        },
        {
            "id": "data/samples/sample_passport_repair.jpg",
            "doc_type": "passport",
            "title": "Jaskirat Singh (OCR Confusion Auto-Repair)",
            "description": "OCR misread 'O' in place of '0'; safely repaired via VIZ corroboration (Rule C-11)",
            "tag": "C-11 Auto-Repair",
            "tag_color": "blue"
        }
    ]
    # Filter to existing files
    available = [
        s for s in sample_files 
        if (s.get("is_pair") and (PROJECT_ROOT / s["front_file"]).exists() and (PROJECT_ROOT / s["back_file"]).exists())
        or (not s.get("is_pair") and (PROJECT_ROOT / s["id"]).exists())
    ]
    return {"samples": available}


@app.get("/api/sample/{filename:path}")
async def get_sample_file(filename: str):
    """Returns sample image file content."""
    file_path = PROJECT_ROOT / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Sample image not found")
    return FileResponse(file_path)


@app.post("/api/screen")
async def screen_document(
    front_file: Optional[UploadFile] = File(None),
    front_data: Optional[str] = Form(None),
    back_file: Optional[UploadFile] = File(None),
    back_data: Optional[str] = Form(None),
    card_file: Optional[UploadFile] = File(None),
    card_sample: Optional[str] = Form(None),
    card_data: Optional[str] = Form(None),
    live_file: Optional[UploadFile] = File(None),
    live_data: Optional[str] = Form(None),
    live_frames_data: Optional[str] = Form(None),
):
    """
    Executes the full 5-Layer Authenticity Screening Pipeline.
    Supports:
    1. Dual-Sided Mode: Upload front and back photos separately.
    2. Single Canvas Mode: Upload a single combined card photo or select sample.
    3. Optional live selfie for 3-way biometric face verification.
    """
    t_start = time.time()
    temp_files = []

    async def _resolve_img(upload: Optional[UploadFile], b64: Optional[str], sample_path: Optional[str]):
        if sample_path and (PROJECT_ROOT / sample_path).exists():
            p = str(PROJECT_ROOT / sample_path)
            return cv2.imread(p), p
        if upload and upload.filename:
            content = await upload.read()
            nparr = np.frombuffer(content, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            tf = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
            tf.write(content)
            tf.close()
            temp_files.append(tf.name)
            return img, tf.name
        if b64:
            img = _decode_base64_image(b64)
            if img is not None:
                tf = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
                cv2.imwrite(tf.name, img)
                tf.close()
                temp_files.append(tf.name)
                return img, tf.name
        return None, None

    # Resolve Sample Pair if selected
    front_sample = None
    back_sample = None
    single_sample = card_sample
    if card_sample == "sample_pair_jaskirat":
        front_sample = "aadhar_front.jpeg"
        back_sample = "WhatsApp Image 2026-09-27 at 5.05.50 PM.jpeg"
        single_sample = None

    front_bgr, front_path = await _resolve_img(front_file, front_data, front_sample)
    back_bgr, back_path = await _resolve_img(back_file, back_data, back_sample)
    card_bgr, card_path = await _resolve_img(card_file, card_data, single_sample)
    live_bgr, _ = await _resolve_img(live_file, live_data, None)

    # Resolve multi-frame live burst if provided
    live_frames = []
    if live_frames_data:
        try:
            import json
            raw_list = json.loads(live_frames_data)
            if isinstance(raw_list, list):
                for item in raw_list:
                    dec = _decode_base64_image(item)
                    if dec is not None:
                        live_frames.append(dec)
        except Exception:
            pass

    if not live_frames and live_bgr is not None:
        live_frames = [live_bgr]
    elif live_frames and live_bgr is None:
        live_bgr = live_frames[-1]

    try:
        # Branch A: Dual-Sided Intake (Front & Back provided separately)
        if front_bgr is not None and back_bgr is not None:
            rect_front, crops_front, qual_front = register_card(front_bgr, image_path=front_path)
            rect_back, crops_back, qual_back = register_card(back_bgr, image_path=back_path)
            crops = crops_front + crops_back
            reg_quality = min(qual_front, qual_back)

            qr_crop = next((c.image for c in crops_back if c.name == "qr_code"), None)
            if qr_crop is None:
                qr_crop = next((c.image for c in crops_front if c.name == "qr_code"), None)
            qr_res = decode_and_verify_qr(rect_back, qr_crop)
            if not qr_res.present and rect_front is not None:
                qr_res_f = decode_and_verify_qr(rect_front, qr_crop)
                if qr_res_f.present:
                    qr_res = qr_res_f

            ocr_fields = extract_fields(crops)
            rule_res = validate_rules(ocr_fields, qr_res)

            tamper_front = detect_tamper(crops_front, full_image=rect_front)
            tamper_back = detect_tamper(crops_back, full_image=rect_back)
            tamper_res = ModuleResult(module_name="tamper_detection")
            tamper_res.scores = {**tamper_front.scores, **tamper_back.scores}
            tamper_res.flags = tamper_front.flags + tamper_back.flags
            tamper_res.evidence = {**tamper_front.evidence, **tamper_back.evidence}
            tamper_res.hard_fail = tamper_front.hard_fail or tamper_back.hard_fail

            photo_crop = next((c.image for c in crops if c.name == "photo"), None)
            face_res = verify_face(
                card_photo=photo_crop,
                live_photo=live_bgr,
                qr_photo=qr_res.photo,
                live_frames=live_frames if len(live_frames) > 0 else None
            )

            has_qr_crop = any(c.name == "qr_code" for c in crops)
            all_results = [rule_res, tamper_res, face_res]
            report = compute_risk_report(
                all_results,
                field_data=ocr_fields,
                qr_payload=qr_res.payload,
                qr_result=qr_res,
                has_qr_crop=has_qr_crop,
                card_quality_score=reg_quality
            )

        # Branch B: Single Combined Card Intake
        else:
            active_bgr = card_bgr if card_bgr is not None else (front_bgr if front_bgr is not None else back_bgr)
            active_path = card_path or front_path or back_path
            if active_bgr is None:
                raise HTTPException(status_code=400, detail="No card image provided. Please upload front and back images, or a combined card scan.")

            rectified_card, crops, reg_quality = register_card(active_bgr, image_path=active_path)
            qr_crop = next((c.image for c in crops if c.name == "qr_code"), None)
            qr_res = decode_and_verify_qr(rectified_card, qr_crop)
            ocr_fields = extract_fields(crops)
            rule_res = validate_rules(ocr_fields, qr_res)
            tamper_res = detect_tamper(crops, full_image=rectified_card)
            photo_crop = next((c.image for c in crops if c.name == "photo"), None)
            face_res = verify_face(
                card_photo=photo_crop,
                live_photo=live_bgr,
                qr_photo=qr_res.photo,
                live_frames=live_frames if len(live_frames) > 0 else None
            )

            has_qr_crop = any(c.name == "qr_code" for c in crops)
            all_results = [rule_res, tamper_res, face_res]
            report = compute_risk_report(
                all_results,
                field_data=ocr_fields,
                qr_payload=qr_res.payload,
                qr_result=qr_res,
                has_qr_crop=has_qr_crop,
                card_quality_score=reg_quality
            )

        # Prepare UI Visual Crops (Base64)
        crops_b64 = {}
        for c in crops:
            if c.name in ("photo", "qr_code", "aadhaar_no", "dob", "name_en", "gender", "aadhar-address"):
                crops_b64[c.name] = _to_base64_uri(c.image)

        # Prepare OCR vs QR Cross-Check Comparison Table
        cross_checks = []
        raw_num = ocr_fields.get("aadhaar_no", ("", 0.0))[0]
        qr_last4 = qr_res.payload.get("last4", "")
        if raw_num or qr_last4:
            clean_digits = "".join(filter(str.isdigit, raw_num))
            matches_last4 = clean_digits.endswith(qr_last4) if (clean_digits and qr_last4) else None
            cross_checks.append({
                "field": "Aadhaar Number",
                "ocr_value": raw_num or "Not Detected",
                "qr_value": f"XXXX XXXX {qr_last4}" if qr_last4 else "Not Present",
                "status": "MATCH" if matches_last4 is True else ("MISMATCH" if matches_last4 is False else "N/A"),
                "status_color": "green" if matches_last4 is True else ("red" if matches_last4 is False else "gray")
            })

        name_ocr = ocr_fields.get("name_en", ("", 0.0))[0]
        name_qr = qr_res.payload.get("name", "")
        if name_ocr or name_qr:
            matches_name = (name_ocr.strip().lower() in name_qr.strip().lower()) if (name_ocr and name_qr) else None
            cross_checks.append({
                "field": "Cardholder Name",
                "ocr_value": name_ocr or "Not Detected",
                "qr_value": name_qr or "Not Present",
                "status": "MATCH" if matches_name else ("MISMATCH" if matches_name is False else "N/A"),
                "status_color": "green" if matches_name else ("red" if matches_name is False else "gray")
            })

        dob_ocr = ocr_fields.get("dob", ("", 0.0))[0]
        dob_qr = qr_res.payload.get("dob", "")
        if dob_ocr or dob_qr:
            matches_dob = (dob_ocr.strip() == dob_qr.strip()) if (dob_ocr and dob_qr) else None
            cross_checks.append({
                "field": "Date of Birth",
                "ocr_value": dob_ocr or "Not Detected",
                "qr_value": dob_qr or "Not Present",
                "status": "MATCH" if matches_dob else ("MISMATCH" if matches_dob is False else "N/A"),
                "status_color": "green" if matches_dob else ("red" if matches_dob is False else "gray")
            })

        gender_ocr = ocr_fields.get("gender", ("", 0.0))[0]
        gender_qr = qr_res.payload.get("gender", "")
        if gender_ocr or gender_qr:
            matches_gender = (gender_ocr.upper() == gender_qr.upper()) if (gender_ocr and gender_qr) else None
            cross_checks.append({
                "field": "Gender",
                "ocr_value": gender_ocr or "Not Detected",
                "qr_value": gender_qr or "Not Present",
                "status": "MATCH" if matches_gender else ("MISMATCH" if matches_gender is False else "N/A"),
                "status_color": "green" if matches_gender else ("red" if matches_gender is False else "gray")
            })

        # Back-side PIN code cross check
        pin_ocr = ocr_fields.get("pincode", ("", 0.0))[0]
        pin_qr = qr_res.payload.get("pincode", "")
        if pin_ocr or pin_qr:
            matches_pin = (pin_ocr == pin_qr) if (pin_ocr and pin_qr) else None
            cross_checks.append({
                "field": "Postal PIN Code",
                "ocr_value": pin_ocr or "Not Detected",
                "qr_value": pin_qr or "Not Present",
                "status": "MATCH" if matches_pin else ("MISMATCH" if matches_pin is False else "N/A"),
                "status_color": "green" if matches_pin else ("red" if matches_pin is False else "gray")
            })

        # Back-side State cross check
        state_qr = qr_res.payload.get("state", "")
        addr_ocr = ocr_fields.get("address", ("", 0.0))[0]
        if state_qr and addr_ocr:
            matches_state = (state_qr.upper() in addr_ocr.upper())
            cross_checks.append({
                "field": "State / Jurisdiction",
                "ocr_value": state_qr if matches_state else "Discrepancy / Other",
                "qr_value": state_qr,
                "status": "MATCH" if matches_state else "MISMATCH",
                "status_color": "green" if matches_state else "yellow"
            })

        # Verhoeff math check
        verhoeff_valid = None
        digits_12 = "".join(filter(str.isdigit, raw_num))
        if len(digits_12) == 12:
            verhoeff_valid = validate_verhoeff(digits_12)

        execution_time = time.time() - t_start

        response_payload = {
            "success": True,
            "verdict": report.verdict.value,
            "verdict_reason": report.verdict_reason,
            "overall_risk": report.overall_risk.value,
            "risk_score": round(report.risk_score, 1),
            "hard_reject": report.hard_reject,
            "tier1_violations": report.tier1_violations,
            "tier2_contributions": report.tier2_contributions,
            "flags": report.flags,
            "qr": {
                "present": qr_res.present,
                "is_secure_qr": qr_res.is_secure_qr,
                "signature_valid": qr_res.signature_valid,
                "cert_name": qr_res.payload.get("verified_by_cert", None),
                "cert_timeline": qr_res.payload.get("cert_timeline_status", None),
                "issue_timestamp": qr_res.payload.get("issue_timestamp", None),
                "version": qr_res.payload.get("version", "Legacy/Standard"),
                "demographics": {k: v for k, v in qr_res.payload.items() if k not in ("raw", "verified_by_cert", "cert_timeline_status")},
                "photo_base64": _to_base64_uri(qr_res.photo)
            },
            "card": {
                "photo_base64": _to_base64_uri(photo_crop),
                "qr_base64": _to_base64_uri(qr_crop),
                "crops": crops_b64
            },
            "live": {
                "provided": live_bgr is not None,
                "photo_base64": _to_base64_uri(live_bgr)
            },
            "biometrics": {
                "card_face_detected": face_res.evidence.get("card_face_detected", False),
                "qr_face_detected": face_res.evidence.get("qr_face_detected", False),
                "live_face_detected": face_res.evidence.get("live_face_detected", False),
                "card_qr_cosine_sim": face_res.evidence.get("card_qr_cosine_sim"),
                "card_qr_distance": face_res.evidence.get("card_qr_distance"),
                "card_qr_match": (
                    face_res.evidence.get("card_qr_cosine_sim") is not None and 
                    face_res.evidence.get("card_qr_cosine_sim") >= face_res.evidence.get("threshold_cosine", 0.363)
                ),
                "card_live_cosine_sim": face_res.evidence.get("card_live_cosine_sim"),
                "card_live_distance": face_res.evidence.get("card_live_distance"),
                "card_live_match": (
                    face_res.evidence.get("card_live_cosine_sim") is not None and 
                    face_res.evidence.get("card_live_cosine_sim") >= face_res.evidence.get("threshold_cosine", 0.363)
                ),
                "qr_live_cosine_sim": face_res.evidence.get("qr_live_cosine_sim"),
                "qr_live_distance": face_res.evidence.get("qr_live_distance"),
                "qr_live_match": (
                    face_res.evidence.get("qr_live_cosine_sim") is not None and 
                    face_res.evidence.get("qr_live_cosine_sim") >= face_res.evidence.get("threshold_cosine", 0.363)
                ),
                "threshold_cosine": face_res.evidence.get("threshold_cosine", 0.363)
            },
            "liveness": face_res.evidence.get("liveness", {
                "is_live": True if live_bgr is None else False,
                "liveness_score": 1.0 if live_bgr is None else 0.0,
                "attack_type": "NOT_PROVIDED" if live_bgr is None else "UNKNOWN",
                "apcer_risk": "LOW" if live_bgr is None else "HIGH",
                "scores": {},
                "details": {}
            }),
            "cross_checks": cross_checks,
            "verhoeff": {
                "checked": len(digits_12) == 12,
                "valid": verhoeff_valid,
                "digits": digits_12 if len(digits_12) == 12 else None
            },
            "execution_time_seconds": round(execution_time, 2)
        }

        return JSONResponse(response_payload)

    finally:
        # Clean up temporary uploaded files if created
        for tf_path in temp_files:
            if tf_path and os.path.exists(tf_path):
                try:
                    os.remove(tf_path)
                except Exception:
                    pass


@app.post("/api/screen/passport")
async def screen_passport_endpoint(
    passport_file: Optional[UploadFile] = File(None),
    passport_data: Optional[str] = Form(None),
    passport_sample: Optional[str] = Form(None),
    live_file: Optional[UploadFile] = File(None),
    live_data: Optional[str] = Form(None),
    live_frames_data: Optional[str] = Form(None),
):
    """
    Executes the ICAO Doc 9303 Indian Passport Screening Pipeline with optional biometric verification.
    """
    t_start = time.time()
    temp_files = []

    async def _resolve_img(upload: Optional[UploadFile], b64: Optional[str], sample_path: Optional[str]):
        if sample_path and (PROJECT_ROOT / sample_path).exists():
            p = str(PROJECT_ROOT / sample_path)
            return cv2.imread(p), p
        if upload and upload.filename:
            content = await upload.read()
            nparr = np.frombuffer(content, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            tf = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
            tf.write(content)
            tf.close()
            temp_files.append(tf.name)
            return img, tf.name
        if b64:
            img = _decode_base64_image(b64)
            if img is not None:
                tf = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
                cv2.imwrite(tf.name, img)
                tf.close()
                temp_files.append(tf.name)
                return img, tf.name
        return None, None

    passport_bgr, passport_path = await _resolve_img(passport_file, passport_data, passport_sample)
    live_bgr, _ = await _resolve_img(live_file, live_data, None)

    # Multi-frame live burst
    live_frames = []
    if live_frames_data:
        try:
            import json
            raw_list = json.loads(live_frames_data)
            if isinstance(raw_list, list):
                for item in raw_list:
                    dec = _decode_base64_image(item)
                    if dec is not None:
                        live_frames.append(dec)
        except Exception:
            pass

    if not live_frames and live_bgr is not None:
        live_frames = [live_bgr]
    elif live_frames and live_bgr is None:
        live_bgr = live_frames[-1]

    if passport_bgr is None:
        raise HTTPException(status_code=400, detail="No passport image provided. Please upload a passport image or select an instant demo sample.")

    try:
        report, artifacts = screen_passport(passport_bgr, return_artifacts=True)

        crops = artifacts.get("crops", {})
        photo_crop = crops.get("photo").image if "photo" in crops else None
        mrz_crop = crops.get("mrz").image if "mrz" in crops else None
        rect_img = artifacts.get("rectified_image")
        mrz_res = artifacts.get("mrz_res")
        viz_data = artifacts.get("viz_data", {})
        raw_mrz = artifacts.get("raw_mrz", ("", ""))

        # Biometrics if live selfie provided and passport face detected
        face_res = None
        if photo_crop is not None and live_bgr is not None:
            try:
                face_res = verify_face(
                    card_photo=photo_crop,
                    live_photo=live_bgr,
                    qr_photo=None,
                    live_frames=live_frames if len(live_frames) > 0 else None,
                )
            except Exception:
                face_res = None

        # Build VIZ <-> MRZ Cross Checks Comparison Table
        cross_checks = []
        if mrz_res:
            # 1. Passport Number
            p_mrz = mrz_res.passport_number or ""
            p_viz = viz_data.get("passport_no", "")
            if p_mrz or p_viz:
                match_p = (p_mrz.strip() == p_viz.strip()) if (p_mrz and p_viz) else None
                cross_checks.append({
                    "field": "Passport Number",
                    "viz_value": p_viz or "Not Detected",
                    "mrz_value": p_mrz or "Not Detected",
                    "status": "MATCH" if match_p else ("MISMATCH" if match_p is False else "N/A"),
                    "status_color": "green" if match_p else ("red" if match_p is False else "gray")
                })

            # 2. Surname
            s_mrz = mrz_res.surname or ""
            s_viz = viz_data.get("surname", "")
            if s_mrz or s_viz:
                match_s = (s_mrz.lower() in s_viz.lower() or s_viz.lower() in s_mrz.lower()) if (s_mrz and s_viz) else None
                cross_checks.append({
                    "field": "Surname",
                    "viz_value": s_viz or "Not Detected",
                    "mrz_value": s_mrz or "Not Detected",
                    "status": "MATCH" if match_s else ("MISMATCH" if match_s is False else "N/A"),
                    "status_color": "green" if match_s else ("red" if match_s is False else "gray")
                })

            # 3. Given Names
            g_mrz = mrz_res.given_names or ""
            g_viz = viz_data.get("given_names", "")
            if g_mrz or g_viz:
                match_g = (g_mrz.lower() in g_viz.lower() or g_viz.lower() in g_mrz.lower()) if (g_mrz and g_viz) else None
                cross_checks.append({
                    "field": "Given Name(s)",
                    "viz_value": g_viz or "Not Detected",
                    "mrz_value": g_mrz or "Not Detected",
                    "status": "MATCH" if match_g else ("MISMATCH" if match_g is False else "N/A"),
                    "status_color": "green" if match_g else ("red" if match_g is False else "gray")
                })

            # 4. Nationality
            n_mrz = mrz_res.nationality or ""
            n_viz = viz_data.get("nationality", "")
            if n_mrz or n_viz:
                match_n = (n_mrz == "IND" and "IND" in n_viz.upper()) if (n_mrz and n_viz) else None
                cross_checks.append({
                    "field": "Nationality",
                    "viz_value": n_viz or "Not Detected",
                    "mrz_value": n_mrz or "Not Detected",
                    "status": "MATCH" if match_n else ("MISMATCH" if match_n is False else "N/A"),
                    "status_color": "green" if match_n else ("red" if match_n is False else "gray")
                })

            # 5. Date of Birth
            d_mrz = mrz_res.dob or ""
            d_viz = viz_data.get("dob", "")
            if d_mrz or d_viz:
                match_d = None
                if d_mrz and d_viz:
                    try:
                        d_parts = d_viz.split("/")
                        if len(d_parts) == 3:
                            viz_iso = f"{d_parts[2]}-{d_parts[1]}-{d_parts[0]}"
                            match_d = (viz_iso == d_mrz)
                    except Exception:
                        pass
                cross_checks.append({
                    "field": "Date of Birth",
                    "viz_value": d_viz or "Not Detected",
                    "mrz_value": d_mrz or "Not Detected",
                    "status": "MATCH" if match_d else ("MISMATCH" if match_d is False else "N/A"),
                    "status_color": "green" if match_d else ("red" if match_d is False else "gray")
                })

            # 6. Sex
            sx_mrz = mrz_res.sex or ""
            sx_viz = viz_data.get("sex", "")
            if sx_mrz or sx_viz:
                match_sx = (sx_mrz.upper() == sx_viz.upper()) if (sx_mrz and sx_viz) else None
                cross_checks.append({
                    "field": "Sex",
                    "viz_value": sx_viz or "Not Detected",
                    "mrz_value": sx_mrz or "Not Detected",
                    "status": "MATCH" if match_sx else ("MISMATCH" if match_sx is False else "N/A"),
                    "status_color": "green" if match_sx else ("red" if match_sx is False else "gray")
                })

            # 7. Expiry Date
            e_mrz = mrz_res.expiry_date or ""
            e_viz = viz_data.get("doe", "")
            if e_mrz or e_viz:
                match_e = None
                if e_mrz and e_viz:
                    try:
                        e_parts = e_viz.split("/")
                        if len(e_parts) == 3:
                            viz_e_iso = f"{e_parts[2]}-{e_parts[1]}-{e_parts[0]}"
                            match_e = (viz_e_iso == e_mrz)
                    except Exception:
                        pass
                cross_checks.append({
                    "field": "Date of Expiry",
                    "viz_value": e_viz or "Not Detected",
                    "mrz_value": e_mrz or "Not Detected",
                    "status": "MATCH" if match_e else ("MISMATCH" if match_e is False else "N/A"),
                    "status_color": "green" if match_e else ("red" if match_e is False else "gray")
                })

        execution_time = time.time() - t_start

        response_payload = {
            "success": True,
            "document": "indian_passport",
            "verdict": report.decision.value,
            "priority": report.priority.value if report.priority else None,
            "document_status": report.document_status,
            "risk_index": round(report.risk_index, 1),
            "risk_band": report.risk_band,
            "coverage": round(report.coverage * 100, 1),
            "findings": report.findings,
            "recommended_action": report.recommended_action.value,
            "image_quality": report.image_quality,
            "mrz": {
                "line1": raw_mrz[0],
                "line2": raw_mrz[1],
                "valid_structure": mrz_res.valid_structure if mrz_res else False,
                "check_digits": mrz_res.check_digits if mrz_res else {},
                "decoded": {
                    "document_type": mrz_res.document_type if mrz_res else None,
                    "issuing_country": mrz_res.issuing_country if mrz_res else None,
                    "passport_number": mrz_res.passport_number if mrz_res else None,
                    "surname": mrz_res.surname if mrz_res else None,
                    "given_names": mrz_res.given_names if mrz_res else None,
                    "nationality": mrz_res.nationality if mrz_res else None,
                    "dob": mrz_res.dob if mrz_res else None,
                    "sex": mrz_res.sex if mrz_res else None,
                    "expiry_date": mrz_res.expiry_date if mrz_res else None,
                } if mrz_res else {}
            },
            "viz": viz_data,
            "cross_checks": cross_checks,
            "crops": {
                "rectified_base64": _to_base64_uri(rect_img),
                "photo_base64": _to_base64_uri(photo_crop),
                "mrz_base64": _to_base64_uri(mrz_crop),
            },
            "live": {
                "provided": live_bgr is not None,
                "photo_base64": _to_base64_uri(live_bgr)
            },
            "biometrics": {
                "passport_face_detected": (face_res.evidence.get("card_face_detected", False) if face_res else (photo_crop is not None)),
                "live_face_detected": (face_res.evidence.get("live_face_detected", False) if face_res else False),
                "passport_live_cosine_sim": (face_res.evidence.get("card_live_cosine_sim") if face_res else None),
                "passport_live_match": (
                    face_res is not None and
                    face_res.evidence.get("card_live_cosine_sim") is not None and
                    face_res.evidence.get("card_live_cosine_sim") >= face_res.evidence.get("threshold_cosine", 0.363)
                ),
                "threshold_cosine": (face_res.evidence.get("threshold_cosine", 0.363) if face_res else 0.363),
                "liveness": (face_res.evidence.get("liveness", {}) if face_res else None)
            },
            "execution_time_seconds": round(execution_time, 2)
        }

        return JSONResponse(response_payload)

    finally:
        for tf_path in temp_files:
            if tf_path and os.path.exists(tf_path):
                try:
                    os.remove(tf_path)
                except Exception:
                    pass


if __name__ == "__main__":
    import uvicorn
    print("\n==================================================")
    print("  Starting Aadhaar Screening Dashboard (M9)")
    print("  URL: http://127.0.0.1:8000")
    print("==================================================\n")
    uvicorn.run("api.main:app", host="127.0.0.1", port=8000, reload=True)
