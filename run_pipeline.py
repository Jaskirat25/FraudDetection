"""
run_pipeline.py - End-to-End Aadhaar Authenticity Screening Pipeline.
Accepts an image path (and optional live photo), executes L1-L5 layers, and prints structured JSON report.
"""

import sys
import os
import json
import argparse
from pathlib import Path
import numpy as np
import cv2
from typing import Optional, List

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")
if hasattr(sys, "set_int_max_str_digits"):
    sys.set_int_max_str_digits(50000)

from core.types import RiskReport, ModuleResult
from modules.register import register_card
from modules.qr import decode_and_verify_qr
from modules.ocr import extract_fields
from modules.validate import validate_rules
from modules.tamper import detect_tamper
from modules.face import verify_face
from modules.scoring import compute_risk_report


def screen_aadhaar(
    card_img_path: Optional[str] = None,
    front_img_path: Optional[str] = None,
    back_img_path: Optional[str] = None,
    live_img_path: Optional[str] = None
) -> RiskReport:
    """
    Executes the full screening pipeline on either:
    1. A single combined card image (front + back on one canvas)
    2. Two individual images (front_img_path and back_img_path processed separately & fused)
    """
    live_image = cv2.imread(live_img_path) if live_img_path and os.path.exists(live_img_path) else None

    # Branch A: Dual-Intake Mode (Separate Front and Back Images)
    if front_img_path and back_img_path:
        front_img = cv2.imread(front_img_path)
        back_img = cv2.imread(back_img_path)
        if front_img is None:
            raise ValueError(f"Failed to load front image from {front_img_path}")
        if back_img is None:
            raise ValueError(f"Failed to load back image from {back_img_path}")

        # Layer 3: Independent Field Localization on Front & Back
        rect_front, crops_front, qual_front = register_card(front_img, image_path=front_img_path)
        rect_back, crops_back, qual_back = register_card(back_img, image_path=back_img_path)

        # Merge crops into unified evaluation pool
        crops = crops_front + crops_back
        reg_quality = min(qual_front, qual_back)

        # Layer 1: Secure QR Decode & Verification (Search back crops first, then back image)
        qr_crop = next((c.image for c in crops_back if c.name == "qr_code"), None)
        if qr_crop is None:
            qr_crop = next((c.image for c in crops_front if c.name == "qr_code"), None)
        
        qr_res = decode_and_verify_qr(rect_back, qr_crop)
        if not qr_res.present and rect_front is not None:
            # Fallback check in case user inverted front and back files
            qr_res_front = decode_and_verify_qr(rect_front, qr_crop)
            if qr_res_front.present:
                qr_res = qr_res_front

        # Layer 4: Targeted OCR Text Extraction
        ocr_fields = extract_fields(crops)

        # Layer 2: Deterministic Rules & Verhoeff Checksum
        rule_res = validate_rules(ocr_fields, qr_res)

        # Layer 4: Forensic Anomaly & Screen PAD on Both Surfaces
        tamper_front = detect_tamper(crops_front, full_image=rect_front)
        tamper_back = detect_tamper(crops_back, full_image=rect_back)

        tamper_res = ModuleResult(module_name="tamper_detection")
        tamper_res.scores = {**tamper_front.scores, **tamper_back.scores}
        tamper_res.flags = tamper_front.flags + tamper_back.flags
        tamper_res.evidence = {**tamper_front.evidence, **tamper_back.evidence}
        tamper_res.hard_fail = tamper_front.hard_fail or tamper_back.hard_fail

        # Layer 5: 3-Way Face Verification
        photo_crop = next((c.image for c in crops if c.name == "photo"), None)
        face_res = verify_face(card_photo=photo_crop, live_photo=live_image, qr_photo=qr_res.photo)

        # Fail-Closed Fusion Engine
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
        return report

    # Branch B: Single Image Mode (Combined Canvas or Single Side)
    target_path = card_img_path or front_img_path or back_img_path
    if not target_path or not os.path.exists(target_path):
        dummy_img = np.full((630, 1000, 3), 245, dtype=np.uint8)
        cv2.putText(dummy_img, "AADHAAR MOCK CARD", (300, 300), cv2.FONT_HERSHEY_SIMPLEX, 1, (50, 50, 50), 2)
        card_image = dummy_img
        target_path = "mock.jpg"
    else:
        card_image = cv2.imread(target_path)
        if card_image is None:
            raise ValueError(f"Failed to load image from {target_path}")

    # Layer 3: Field Localization
    rectified_card, crops, reg_quality = register_card(card_image, image_path=target_path)

    # Layer 1: QR Decode & Signature Verification
    qr_crop = next((c.image for c in crops if c.name == "qr_code"), None)
    qr_res = decode_and_verify_qr(rectified_card, qr_crop)

    # Layer 4: Dual-Engine OCR Text Extraction
    ocr_fields = extract_fields(crops)

    # Layer 2: Deterministic Rules & Verhoeff Checksum
    rule_res = validate_rules(ocr_fields, qr_res)

    # Layer 4: Per-Crop Tamper Detection & PAD Anti-Spoofing
    tamper_res = detect_tamper(crops, full_image=rectified_card)

    # Layer 5: 3-Way Face Verification
    photo_crop = next((c.image for c in crops if c.name == "photo"), None)
    face_res = verify_face(card_photo=photo_crop, live_photo=live_image, qr_photo=qr_res.photo)

    # Layer 5: Risk Scoring & Fusion
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
    return report


def main():
    parser = argparse.ArgumentParser(description="Aadhaar Authenticity Screening System")
    parser.add_argument("image_path", nargs="?", default=None, help="Path to single card photo (combined front+back)")
    parser.add_argument("--front", default=None, help="Path to separate card front photo")
    parser.add_argument("--back", default=None, help="Path to separate card back photo")
    parser.add_argument("--live", default=None, help="Path to optional live webcam selfie")
    args = parser.parse_args()

    print(f"\n==================================================")
    print(f"  Aadhaar Authenticity Screening Pipeline (v1)")
    print(f"==================================================")

    if args.front and args.back:
        print(f"Intake Mode: DUAL-SIDED (Front + Back Separate)")
        print(f"  Front: {args.front}")
        print(f"  Back:  {args.back}")
        report = screen_aadhaar(front_img_path=args.front, back_img_path=args.back, live_img_path=args.live)
    else:
        path = args.image_path or args.front or args.back or "combined-image.jpg"
        print(f"Intake Mode: SINGLE IMAGE")
        print(f"  Analyzing: {path}")
        report = screen_aadhaar(card_img_path=path, live_img_path=args.live)

    # Pretty-print report summary
    print(f"\n[VERDICT]:       {report.verdict.value}")
    print(f"[VERDICT REASON]: {report.verdict_reason}")
    print(f"[RISK SCORE]:    {report.risk_score:.1f} / 100.0 (Risk Band: {report.overall_risk.value})")
    print(f"[HARD REJECT]:   {report.hard_reject}")
    
    if report.tier1_violations:
        print(f"\n--- Conclusive Tier-1 Violations (Immediate Fraud) ---")
        for v in report.tier1_violations:
            print(f"  🚨 {v}")

    if report.tier2_contributions:
        print(f"\n--- Tier-2 Risk Contributions ---")
        for c in report.tier2_contributions:
            print(f"  * +{c['points']} pts: {c['reason']}")

    print(f"\n--- Diagnostic Findings ---")
    for flag in report.flags:
        print(f"  - {flag}")

    print("\n--- Per-Field Analysis ---")
    for f_name, f_info in report.per_field_analysis.items():
        print(f"  * {f_name:12s}: Tamper Suspicion = {f_info.get('tamper_score', 0.0):.2f}")

    print(f"\n==================================================\n")


if __name__ == "__main__":
    main()
