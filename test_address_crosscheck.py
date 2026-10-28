"""
test_address_crosscheck.py - Comprehensive verification for Back-Side Address Proof Cross-Check (L6).
"""

import sys
from pathlib import Path
import cv2

# Ensure project root in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from modules.register import register_card
from modules.qr import decode_and_verify_qr
from modules.ocr import extract_fields
from modules.validate.rules import validate_rules
from modules.scoring.fusion import compute_risk_report
from core.types import QRResult, Verdict


def test_address_pipeline():
    print("=" * 60)
    print("  Testing Back-Side Address Proof Cross-Check (L6)")
    print("=" * 60)

    # Test 1: Real Card Combined End-to-End Address Extraction & Verification
    print("\n[Test 1] Real Card Combined (combined-image.jpg):")
    img = cv2.imread("combined-image.jpg")
    _, crops, _ = register_card(img, "combined-image.jpg")
    ocr_fields = extract_fields(crops)
    qr_res = decode_and_verify_qr(img)

    print(f"  OCR Extracted PIN: {ocr_fields.get('pincode')}")
    print(f"  OCR Extracted Address: {ocr_fields.get('address', ('', 0.0))[0][:60]}...")
    print(f"  Signed QR PIN: {qr_res.payload.get('pincode')}")
    print(f"  Signed QR State: {qr_res.payload.get('state')}")
    print(f"  Signed QR District: {qr_res.payload.get('district')}")

    rule_res = validate_rules(ocr_fields, qr_res)
    assert not rule_res.hard_fail, "Real card must NOT hard fail on address checks!"
    assert rule_res.scores.get("pin_mismatch", 0.0) == 0.0, "PIN mismatch score must be 0.0"
    assert rule_res.scores.get("state_mismatch", 0.0) == 0.0, "State mismatch score must be 0.0"
    assert rule_res.scores.get("district_mismatch", 0.0) == 0.0, "District mismatch score must be 0.0"

    matching_flags = [f for f in rule_res.flags if any(k in f for k in ("PIN Code Verified", "State Verified", "District Verified"))]
    print(f"  ✅ Verified Address Match Flags: {matching_flags}")

    # Test 2: Fabricated Card with Tampered Printed PIN
    print("\n[Test 2] Tampered Printed PIN Attack (e.g., 144622 altered to 110001):")
    fake_ocr = {
        "aadhaar_no": ("9876 5432 1096", 0.95),
        "address": ("Address: House 12, Main Street, Delhi - 110001", 0.85),
        "pincode": ("110001", 0.90)
    }
    fake_qr = QRResult(
        present=True,
        is_secure_qr=True,
        signature_valid=True,
        signature_status="VALID",
        payload={
            "name": "Jaskirat Singh",
            "last4": "1096",
            "pincode": "144622",
            "state": "Punjab",
            "district": "Kapurthala",
            "issue_timestamp": "2026-07-24 21:19:43"
        },
        temporal_valid=True
    )
    tampered_res = validate_rules(fake_ocr, fake_qr)
    assert tampered_res.hard_fail, "Tampered PIN code MUST trigger hard fail!"
    assert tampered_res.scores.get("pin_mismatch") == 1.0, "PIN mismatch score must be 1.0"
    report_tampered = compute_risk_report([tampered_res], qr_result=fake_qr)
    assert report_tampered.verdict == Verdict.REJECT, f"Expected REJECT, got {report_tampered.verdict}"
    print(f"  ✅ Tampered PIN caught: Verdict = {report_tampered.verdict.value}")

    # Test 3: Conflicting State Attack (Card printed address claims Maharashtra, QR says Punjab)
    print("\n[Test 3] Conflicting State Jurisdiction Attack:")
    state_tamper_ocr = {
        "aadhaar_no": ("9876 5432 1096", 0.95),
        "address": ("Address: Flat 402, Mumbai, Maharashtra - 144622", 0.85),
        "pincode": ("144622", 0.85)
    }
    state_tamper_res = validate_rules(state_tamper_ocr, fake_qr)
    assert state_tamper_res.scores.get("state_mismatch", 0.0) >= 0.50, "State mismatch score must be >= 0.50"
    discrepancy_flags = [f for f in state_tamper_res.flags if "State Discrepancy" in f]
    print(f"  ✅ Conflicting state caught: {discrepancy_flags}")

    # Test 4: Geographic Inconsistency (PIN prefix 11 belongs to Delhi, but card claims Punjab)
    print("\n[Test 4] Geographic Inconsistency Check:")
    geo_anomaly_ocr = {
        "aadhaar_no": ("9876 5432 1096", 0.95),
        "address": ("Address: Sector 4, Punjab", 0.80),
        "pincode": ("110001", 0.80)
    }
    geo_qr = QRResult(
        present=True,
        is_secure_qr=True,
        signature_valid=True,
        signature_status="VALID",
        payload={
            "name": "User",
            "last4": "1096",
            "pincode": "110001",
            "state": "Punjab",  # Delhi PIN prefix with Punjab state
            "issue_timestamp": "2026-07-24 21:19:43"
        },
        temporal_valid=True
    )
    geo_res = validate_rules(geo_anomaly_ocr, geo_qr)
    assert geo_res.scores.get("pin_state_mismatch", 0.0) > 0.0, "Postal circle mismatch must be scored"
    geo_flags = [f for f in geo_res.flags if "Geographic Anomaly" in f]
    print(f"  ✅ Geographic anomaly caught: {geo_flags}")

    print("\n" + "=" * 60)
    print("  ALL 4 BACK-SIDE ADDRESS CROSS-CHECK TESTS PASSED! 🎉")
    print("=" * 60)


if __name__ == "__main__":
    test_address_pipeline()
