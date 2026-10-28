"""
test_crypto_temporal.py - Comprehensive verification for Trust Store Pinning (L7)
and Temporal Plausibility & Freshness (L8).
"""

import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta
import cv2

# Ensure project root in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from modules.qr import decode_and_verify_qr
from modules.qr.trust_store import (
    load_pinned_trust_store,
    verify_uidai_signature_pinned,
    validate_temporal_plausibility,
    PINNED_UIDAI_CERTIFICATES
)
from modules.validate.rules import validate_rules
from core.types import QRResult, Verdict
from modules.scoring.fusion import compute_risk_report


def run_tests():
    print("=" * 60)
    print("  Testing UIDAI Trust Store Pinning & Temporal Integrity")
    print("=" * 60)

    # Test 1: Trust Store Loading & Pinning
    print("\n[Test 1] Trust Store Pinning Verification:")
    keys = load_pinned_trust_store()
    assert len(keys) == 8, f"Expected 8 pinned certificates, found {len(keys)}"
    print(f"  ✅ All {len(keys)} pinned UIDAI certificates loaded and SHA-256 verified.")

    # Test 2: Real Card Decode & Verified Signature
    print("\n[Test 2] Real Card Cryptographic Anchor Verification:")
    img = cv2.imread("combined-image.jpg")
    qr_res = decode_and_verify_qr(img)
    assert qr_res.present, "QR should be present on combined-image.jpg"
    assert qr_res.is_secure_qr, "QR should be recognized as Secure QR"
    assert qr_res.signature_valid, "Signature should be cryptographically VALID"
    assert qr_res.signature_status == "VALID", f"Expected VALID status, got {qr_res.signature_status}"
    assert qr_res.cert_name == "uidai_offline_publickey_2026.cer", f"Expected 2026 cert, got {qr_res.cert_name}"
    assert qr_res.temporal_valid, f"Temporal checks should pass: {qr_res.temporal_issues}"
    print(f"  ✅ Real QR Signature Status: {qr_res.signature_status}")
    print(f"  ✅ Verified Against Pinned Cert: {qr_res.cert_name}")
    print(f"  ✅ Pinned SHA-256: {qr_res.cert_fingerprint[:16]}...")
    print(f"  ✅ Issue Timestamp: {qr_res.payload.get('issue_timestamp')}")

    # Test 3: INVALID_SIGNATURE (Corrupted signature / Forged payload)
    print("\n[Test 3] Tampered Signature / Forged Payload Test:")
    tampered_sig_res = QRResult(
        present=True,
        is_secure_qr=True,
        signature_valid=False,
        signature_status="INVALID_SIGNATURE",
        payload={"name": "Attacker", "dob": "01/01/1990", "last4": "1096"},
        temporal_valid=True
    )
    rule_res_tampered = validate_rules({"aadhaar_no": ("9876 5432 1096", 0.95)}, tampered_sig_res)
    assert rule_res_tampered.hard_fail, "Tampered signature MUST cause hard_fail!"
    report_tampered = compute_risk_report([rule_res_tampered], qr_result=tampered_sig_res)
    assert report_tampered.verdict == Verdict.REJECT, f"Expected REJECT, got {report_tampered.verdict}"
    print(f"  ✅ Correctly flagged hard reject: Verdict = {report_tampered.verdict.value}")

    # Test 4: UNKNOWN_KEY (Future epoch or unpinned certificate)
    print("\n[Test 4] Unknown Signing Key / Unmapped Epoch Test:")
    unknown_key_res = QRResult(
        present=True,
        is_secure_qr=True,
        signature_valid=False,
        signature_status="UNKNOWN_KEY",
        payload={"name": "Legitimate User", "dob": "01/01/1990", "last4": "1096"},
        temporal_valid=True
    )
    rule_res_unknown = validate_rules({"aadhaar_no": ("9876 5432 1096", 0.95)}, unknown_key_res)
    assert not rule_res_unknown.hard_fail, "UNKNOWN_KEY must NOT trigger an aggressive hard reject!"
    report_unknown = compute_risk_report([rule_res_unknown], qr_result=unknown_key_res)
    assert report_unknown.verdict == Verdict.REVIEW, f"Expected REVIEW, got {report_unknown.verdict}"
    print(f"  ✅ Correctly routes to REVIEW: Verdict = {report_unknown.verdict.value} (Reason: {report_unknown.verdict_reason[:60]}...)")

    # Test 5: Temporal Chronological Inversion (DOB > Issue Date)
    print("\n[Test 5] Chronological Inversion Attack Test (Issued before Birth):")
    inversion_res = QRResult(
        present=True,
        is_secure_qr=True,
        signature_valid=True,
        signature_status="VALID",
        payload={"name": "Time Traveler", "dob": "15/08/2025", "issue_timestamp": "2020-01-01 12:00:00", "last4": "1096"},
        temporal_valid=False,
        temporal_issues=["CHRONOLOGICAL INVERSION: Card issue date (2020-01-01) precedes holder's date of birth (15/08/2025)."]
    )
    rule_res_inv = validate_rules({"aadhaar_no": ("9876 5432 1096", 0.95)}, inversion_res)
    assert rule_res_inv.hard_fail, "Chronological inversion MUST cause hard_fail!"
    report_inv = compute_risk_report([rule_res_inv], qr_result=inversion_res)
    assert report_inv.verdict == Verdict.REJECT, f"Expected REJECT, got {report_inv.verdict}"
    print(f"  ✅ Correctly caught chronological inversion: Verdict = {report_inv.verdict.value}")

    # Test 6: Future-dated Card Attack
    print("\n[Test 6] Future-dated Card Attack Test:")
    future_res = QRResult(
        present=True,
        is_secure_qr=True,
        signature_valid=True,
        signature_status="VALID",
        payload={"name": "Future Citizen", "dob": "01/01/2000", "issue_timestamp": "2030-01-01 12:00:00", "last4": "1096"},
        temporal_valid=False,
        temporal_issues=["FUTURE TIMESTAMP: Card claims issuance in the future (2030-01-01 12:00:00 UTC)."]
    )
    rule_res_fut = validate_rules({"aadhaar_no": ("9876 5432 1096", 0.95)}, future_res)
    assert rule_res_fut.hard_fail, "Future dated card MUST cause hard_fail!"
    report_fut = compute_risk_report([rule_res_fut], qr_result=future_res)
    assert report_fut.verdict == Verdict.REJECT, f"Expected REJECT, got {report_fut.verdict}"
    print(f"  ✅ Correctly caught future dated card: Verdict = {report_fut.verdict.value}")

    print("\n" + "=" * 60)
    print("  ALL 6 TRUST STORE PINNING & TEMPORAL TESTS PASSED! 🎉")
    print("=" * 60)


if __name__ == "__main__":
    run_tests()
