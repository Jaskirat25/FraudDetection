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

from core.types import RiskReport, FieldCrop, RiskLevel
from modules.register import register_card
from modules.qr import decode_and_verify_qr
from modules.ocr import extract_fields
from modules.validate import validate_rules
from modules.tamper import detect_tamper
from modules.face import verify_face
from modules.scoring import compute_risk_report
from modules.validate.verhoeff import validate_verhoeff

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
        {
            "id": "combined-image.jpg",
            "title": "Jaskirat Singh (Front + Back Combined)",
            "description": "Complete card with front photo & V5 Secure QR (Authentic match)",
            "tag": "Authentic Full Card",
            "tag_color": "green"
        },
        {
            "id": "WhatsApp Image 2026-09-27 at 5.05.50 PM.jpeg",
            "title": "Jaskirat Singh (Card Back + V5 QR)",
            "description": "High-density V5 BigInt QR code with RSA-2048 signature",
            "tag": "Secure QR Back",
            "tag_color": "blue"
        },
        {
            "id": "aadhar_front.jpeg",
            "title": "Jaskirat Singh (Card Front Photo & Text)",
            "description": "Front card scan with clear photo crop, name, and DOB",
            "tag": "Card Front",
            "tag_color": "indigo"
        },
        {
            "id": "WhatsApp Image 2026-09-25 at 10.32.28 AM.jpeg",
            "title": "Dhruv (Different Person / Impostor Test)",
            "description": "Use as live selfie or card to test biometric mismatch & photo-swap",
            "tag": "Impostor Test Subject",
            "tag_color": "amber"
        }
    ]
    # Filter to existing files
    available = [s for s in sample_files if (PROJECT_ROOT / s["id"]).exists()]
    return {"samples": available}


@app.get("/api/sample/{filename}")
async def get_sample_file(filename: str):
    """Returns sample image file content."""
    file_path = PROJECT_ROOT / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Sample image not found")
    return FileResponse(file_path)


@app.post("/api/screen")
async def screen_document(
    card_file: Optional[UploadFile] = File(None),
    card_sample: Optional[str] = Form(None),
    card_data: Optional[str] = Form(None),
    live_file: Optional[UploadFile] = File(None),
    live_data: Optional[str] = Form(None),
):
    """
    Executes the full 5-Layer Authenticity Screening Pipeline.
    Accepts uploaded file, sample identifier, or webcam base64 stream.
    """
    t_start = time.time()
    
    # 1. Resolve Card Image
    card_bgr = None
    card_path_for_model = None
    temp_card_file = None

    if card_sample and (PROJECT_ROOT / card_sample).exists():
        card_path_for_model = str(PROJECT_ROOT / card_sample)
        card_bgr = cv2.imread(card_path_for_model)
    elif card_file and card_file.filename:
        content = await card_file.read()
        nparr = np.frombuffer(content, np.uint8)
        card_bgr = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        # Write to temporary file so offline YOLO engine can read it if needed
        temp_card_file = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
        temp_card_file.write(content)
        temp_card_file.close()
        card_path_for_model = temp_card_file.name
    elif card_data:
        card_bgr = _decode_base64_image(card_data)
        if card_bgr is not None:
            temp_card_file = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
            cv2.imwrite(temp_card_file.name, card_bgr)
            temp_card_file.close()
            card_path_for_model = temp_card_file.name

    if card_bgr is None:
        raise HTTPException(status_code=400, detail="No valid card image provided.")

    # 2. Resolve Live Selfie Image (Webcam or Upload)
    live_bgr = None
    if live_file and live_file.filename:
        content_live = await live_file.read()
        nparr_live = np.frombuffer(content_live, np.uint8)
        live_bgr = cv2.imdecode(nparr_live, cv2.IMREAD_COLOR)
    elif live_data:
        live_bgr = _decode_base64_image(live_data)

    try:
        # Layer 3: Field Localization (YOLO offline + fallback)
        rectified_card, crops, reg_quality = register_card(card_bgr, image_path=card_path_for_model)

        # Layer 1: Secure QR Decode & RSA-2048 Cryptographic Verification
        qr_crop = next((c.image for c in crops if c.name == "qr_code"), None)
        qr_res = decode_and_verify_qr(rectified_card, qr_crop)

        # Layer 4: Targeted OCR Text Extraction
        ocr_fields = extract_fields(crops)

        # Layer 2: Deterministic Rules & Verhoeff Checksum
        rule_res = validate_rules(ocr_fields, qr_res)

        # Layer 4: Forensic Anomaly & Tamper Detection
        tamper_res = detect_tamper(crops)

        # Layer 5: 3-Way Face Biometric Matching
        photo_crop = next((c.image for c in crops if c.name == "photo"), None)
        face_res = verify_face(card_photo=photo_crop, live_photo=live_bgr, qr_photo=qr_res.photo)

        # Risk Fusion & Scoring Engine (M8 - Fail-Closed Decision Engine)
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
        # Clean up temporary uploaded file if created
        if temp_card_file and os.path.exists(temp_card_file.name):
            try:
                os.remove(temp_card_file.name)
            except Exception:
                pass


if __name__ == "__main__":
    import uvicorn
    print("\n==================================================")
    print("  Starting Aadhaar Screening Dashboard (M9)")
    print("  URL: http://127.0.0.1:8000")
    print("==================================================\n")
    uvicorn.run("api.main:app", host="127.0.0.1", port=8000, reload=True)
