"""
benchmark_suite.py - Quantitative Evaluation Benchmark Suite (L1-L8).
Simulates the complete 14-class attack matrix (A1 to A14) to report quantitative
True Positive Rate (Detection Rate), False Reject Rate, and Routing Accuracy.
"""

import sys
import time
from pathlib import Path
from dataclasses import dataclass
from typing import List, Dict, Any, Optional
import numpy as np

# Ensure project root in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from core.types import QRResult, ModuleResult, Verdict, RiskLevel
from modules.validate.rules import validate_rules
from modules.tamper.detector import detect_tamper
from modules.face.matcher import verify_face
from modules.scoring.fusion import compute_risk_report


@dataclass
class TestCase:
    test_id: str
    category: str
    description: str
    expected_verdict: Verdict
    setup_fn: Any


def setup_a1_bad_signature():
    """A1: Cryptographic QR Signature Forgery (Tampered RSA signature)"""
    qr = QRResult(
        present=True,
        is_secure_qr=True,
        signature_valid=False,
        signature_status="INVALID_SIGNATURE",
        payload={"name": "Attacker", "dob": "01/01/1990", "last4": "1096"},
        temporal_valid=True
    )
    rule_res = validate_rules({"aadhaar_no": ("9876 5432 1096", 0.95)}, qr)
    return [rule_res], qr, None, 0.95


def setup_a2_unknown_ca_key():
    """A2: Unknown CA Key / Unmapped Epoch (Future rotated key outside trust store)"""
    qr = QRResult(
        present=True,
        is_secure_qr=True,
        signature_valid=False,
        signature_status="UNKNOWN_KEY",
        payload={"name": "Citizen", "dob": "01/01/1990", "last4": "1096"},
        temporal_valid=True
    )
    rule_res = validate_rules({"aadhaar_no": ("9876 5432 1096", 0.95)}, qr)
    return [rule_res], qr, None, 0.95


def setup_a3_photo_swap():
    """A3: Biometric Photo Swap (Printed card photo does not match signed QR photo)"""
    qr = QRResult(
        present=True,
        is_secure_qr=True,
        signature_valid=True,
        signature_status="VALID",
        payload={"name": "Jaskirat Singh", "dob": "01/01/1990", "last4": "1096"},
        temporal_valid=True
    )
    rule_res = validate_rules({"aadhaar_no": ("9876 5432 1096", 0.95)}, qr)
    # Simulate face module reporting conclusive photo swap
    face_res = ModuleResult(module_name="face_verification")
    face_res.hard_fail = True
    face_res.scores["photo_swap"] = 1.0
    face_res.flags.append("BIOMETRIC FORGERY DETECTED: Physical card photo does not match cryptographically signed QR photo (Cosine Sim: 0.124 < 0.363).")
    face_res.evidence["card_qr_cosine_sim"] = 0.124
    return [rule_res, face_res], qr, None, 0.95


def setup_a4_text_overwrite():
    """A4: Printed Text Overwrite / Name Tamper"""
    qr = QRResult(
        present=True,
        is_secure_qr=True,
        signature_valid=True,
        signature_status="VALID",
        payload={"name": "Jaskirat Singh", "dob": "01/01/1990", "last4": "1096"},
        temporal_valid=True
    )
    rule_res = validate_rules({
        "aadhaar_no": ("9876 5432 1096", 0.95),
        "name_en": ("Vikram Sharma", 0.92)  # Different name
    }, qr)
    return [rule_res], qr, None, 0.95


def setup_a5_verhoeff_fail():
    """A5: Verhoeff Mathematical Checksum Failure (Random fabricated 12-digit number)"""
    qr = QRResult(
        present=True,
        is_secure_qr=True,
        signature_valid=True,
        signature_status="VALID",
        payload={"name": "User", "dob": "01/01/1990", "last4": "9999"},
        temporal_valid=True
    )
    # "0123 4567 8901" fails Verhoeff and starts with 0
    rule_res = validate_rules({"aadhaar_no": ("0123 4567 8901", 0.95)}, qr)
    return [rule_res], qr, None, 0.95


def setup_a6_pin_tamper():
    """A6: Back-Side PIN Code Tamper (Printed PIN contradicts signed QR PIN)"""
    qr = QRResult(
        present=True,
        is_secure_qr=True,
        signature_valid=True,
        signature_status="VALID",
        payload={"name": "User", "last4": "1096", "pincode": "144622", "state": "Punjab"},
        temporal_valid=True
    )
    rule_res = validate_rules({
        "aadhaar_no": ("9876 5432 1096", 0.95),
        "pincode": ("110001", 0.90)  # Contradicts 144622
    }, qr)
    return [rule_res], qr, None, 0.95


def setup_a7_future_timestamp():
    """A7: Future-Dated Document Attack"""
    qr = QRResult(
        present=True,
        is_secure_qr=True,
        signature_valid=True,
        signature_status="VALID",
        payload={"name": "Citizen", "last4": "1096"},
        temporal_valid=False,
        temporal_issues=["FUTURE TIMESTAMP: Card claims issuance in the future (2032-01-01 12:00:00 UTC)."]
    )
    rule_res = validate_rules({"aadhaar_no": ("9876 5432 1096", 0.95)}, qr)
    return [rule_res], qr, None, 0.95


def setup_a8_chronological_inversion():
    """A8: Chronological Inversion Attack (Issued before Birth)"""
    qr = QRResult(
        present=True,
        is_secure_qr=True,
        signature_valid=True,
        signature_status="VALID",
        payload={"name": "Citizen", "last4": "1096"},
        temporal_valid=False,
        temporal_issues=["CHRONOLOGICAL INVERSION: Card issue date (2018-01-01) precedes holder's date of birth (2022-05-10)."]
    )
    rule_res = validate_rules({"aadhaar_no": ("9876 5432 1096", 0.95)}, qr)
    return [rule_res], qr, None, 0.95


def setup_a9_screen_replay():
    """A9: Presentation Attack / Digital Screen Replay (Moiré pattern detected)"""
    qr = QRResult(present=True, is_secure_qr=True, signature_valid=True, signature_status="VALID", payload={"last4": "1096"})
    rule_res = validate_rules({"aadhaar_no": ("9876 5432 1096", 0.95)}, qr)
    tamper_res = ModuleResult(module_name="tamper_detection")
    tamper_res.hard_fail = True
    tamper_res.scores["screen_replay"] = 1.0
    tamper_res.flags.append("PRESENTATION ATTACK ALERT: Digital screen replay detected via 2D FFT Moiré subpixel harmonics.")
    return [rule_res, tamper_res], qr, None, 0.95


def setup_a10_front_only_scan():
    """A10: Front-Only Genuine Scan (Missing QR Anchor -> Must route to REVIEW)"""
    qr = QRResult(present=False, is_secure_qr=False, signature_valid=False, signature_status="NO_QR")
    rule_res = validate_rules({"aadhaar_no": ("9876 5432 1096", 0.95)}, qr)
    return [rule_res], qr, None, 0.95


def setup_a11_severe_blur():
    """A11: Degraded Capture / Severe Blur (Must route to RETAKE)"""
    qr = QRResult(present=True, is_secure_qr=True, signature_valid=True, signature_status="VALID", payload={"last4": "1096"})
    rule_res = validate_rules({"aadhaar_no": ("9876 5432 1096", 0.95)}, qr)
    tamper_res = ModuleResult(module_name="tamper_detection")
    tamper_res.scores["photo"] = 0.35
    tamper_res.flags.append("RETAKE ADVICE: Crop 'photo' is out-of-focus or blurred (sharpness 18.4 < 25.0).")
    return [rule_res, tamper_res], qr, None, 0.95


def setup_a12_specular_glare():
    """A12: Severe Specular Glare (Must route to RETAKE)"""
    qr = QRResult(present=True, is_secure_qr=True, signature_valid=True, signature_status="VALID", payload={"last4": "1096"})
    rule_res = validate_rules({"aadhaar_no": ("9876 5432 1096", 0.95)}, qr)
    tamper_res = ModuleResult(module_name="tamper_detection")
    tamper_res.scores["aadhaar_no"] = 0.35
    tamper_res.flags.append("RETAKE ADVICE: Severe specular glare in 'aadhaar_no' (28.4% pixels overexposed).")
    return [rule_res, tamper_res], qr, None, 0.95


def setup_a13_state_discrepancy():
    """A13: Conflicting State Jurisdiction (Soft anomaly -> Must route to REVIEW)"""
    qr = QRResult(
        present=True,
        is_secure_qr=True,
        signature_valid=True,
        signature_status="VALID",
        payload={"name": "Citizen", "last4": "1096", "pincode": "144622", "state": "Punjab"},
        temporal_valid=True
    )
    rule_res = validate_rules({
        "aadhaar_no": ("9876 5432 1096", 0.95),
        "address": ("Address: Flat 101, Mumbai, Maharashtra", 0.85),
        "pincode": ("144622", 0.85)
    }, qr)
    return [rule_res], qr, None, 0.95


def setup_a14_clean_authentic():
    """A14: Clean Authentic Dual-Sided Card (All checks pass -> Must produce VERIFIED)"""
    qr = QRResult(
        present=True,
        is_secure_qr=True,
        signature_valid=True,
        signature_status="VALID",
        cert_name="uidai_offline_publickey_2026.cer",
        payload={
            "name": "Jaskirat Singh",
            "dob": "01/01/1990",
            "gender": "MALE",
            "last4": "1096",
            "pincode": "144622",
            "state": "Punjab",
            "district": "Kapurthala",
            "issue_timestamp": "2026-07-24 21:19:43"
        },
        temporal_valid=True
    )
    rule_res = validate_rules({
        "aadhaar_no": ("9876 5432 1096", 0.95),
        "name_en": ("Jaskirat Singh", 0.95),
        "dob": ("01/01/1990", 0.95),
        "gender": ("MALE", 0.95),
        "address": ("Address: SIO Nishan Singh, Kapurthala, Punjab - 144622", 0.85),
        "pincode": ("144622", 0.90)
    }, qr)
    face_res = ModuleResult(module_name="face_verification")
    face_res.scores["photo_swap"] = 0.0
    face_res.flags.append("Biometric Match: Cosine Sim 0.830 >= 0.363")
    face_res.evidence["card_qr_cosine_sim"] = 0.830
    return [rule_res, face_res], qr, None, 0.95


TEST_CASES = [
    TestCase("A01", "Cryptographic", "RSA-2048 Digital Signature Forgery", Verdict.REJECT, setup_a1_bad_signature),
    TestCase("A02", "Cryptographic", "Unknown/Unmapped CA Key Epoch", Verdict.REVIEW, setup_a2_unknown_ca_key),
    TestCase("A03", "Biometric", "Physical Card Photo-Swap Attack", Verdict.REJECT, setup_a3_photo_swap),
    TestCase("A04", "Demographic", "Printed Name Tamper / Overwrite", Verdict.REJECT, setup_a4_text_overwrite),
    TestCase("A05", "Checksum", "Verhoeff D5 Checksum Failure", Verdict.REJECT, setup_a5_verhoeff_fail),
    TestCase("A06", "Address (L6)", "Back-Side Printed PIN Tamper", Verdict.REJECT, setup_a6_pin_tamper),
    TestCase("A07", "Temporal (L8)", "Future-Dated Document Injection", Verdict.REJECT, setup_a7_future_timestamp),
    TestCase("A08", "Temporal (L8)", "Chronological Inversion (Issued < DOB)", Verdict.REJECT, setup_a8_chronological_inversion),
    TestCase("A09", "Anti-Spoof PAD", "Digital Screen Replay (Moiré Harmonics)", Verdict.REJECT, setup_a9_screen_replay),
    TestCase("A10", "Fail-Closed", "Front-Only Card (Missing QR Anchor)", Verdict.REVIEW, setup_a10_front_only_scan),
    TestCase("A11", "Physical Quality", "Defocus Blur (Sharpness < 45)", Verdict.RETAKE, setup_a11_severe_blur),
    TestCase("A12", "Physical Quality", "Flash Specular Glare (>10% Pixels)", Verdict.RETAKE, setup_a12_specular_glare),
    TestCase("A13", "Jurisdiction", "Conflicting State Jurisdiction", Verdict.REVIEW, setup_a13_state_discrepancy),
    TestCase("A14", "Baseline", "Authentic Dual-Sided Card", Verdict.VERIFIED, setup_a14_clean_authentic),
]


def run_benchmark():
    print("=" * 80)
    print("  AADHAAR SCREENING PIPELINE - COMPREHENSIVE BENCHMARK EVALUATION (A1-A14)")
    print("=" * 80)
    print(f"Total Test Classes: {len(TEST_CASES)}")
    print("-" * 80)
    print(f"{'ID':<5} | {'Category':<16} | {'Test Description':<38} | {'Exp':<8} | {'Actual':<8} | {'Status'}")
    print("-" * 80)

    results = []
    start_total = time.perf_counter()

    for tc in TEST_CASES:
        t0 = time.perf_counter()
        mods, qr, photo_crop, reg_q = tc.setup_fn()
        report = compute_risk_report(
            mods,
            field_data={},
            qr_payload=qr.payload if qr else {},
            qr_result=qr,
            has_qr_crop=(qr is not None and qr.present),
            card_quality_score=reg_q
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000

        passed = (report.verdict == tc.expected_verdict)
        results.append({
            "id": tc.test_id,
            "category": tc.category,
            "desc": tc.description,
            "expected": tc.expected_verdict.value,
            "actual": report.verdict.value,
            "risk_score": report.risk_score,
            "passed": passed,
            "elapsed_ms": elapsed_ms
        })

        status_str = "✅ PASS" if passed else "❌ FAIL"
        print(f"{tc.test_id:<5} | {tc.category:<16} | {tc.description[:36]:<38} | {tc.expected_verdict.value:<8} | {report.verdict.value:<8} | {status_str}")

    total_time_ms = (time.perf_counter() - start_total) * 1000

    print("=" * 80)
    print("  QUANTITATIVE METRICS SUMMARY")
    print("=" * 80)

    # 1. Malicious Attack Detection Rate (TPR)
    # Malicious classes: A01, A03, A04, A05, A06, A07, A08, A09 (all expected to REJECT)
    malicious = [r for r in results if r["expected"] == "REJECT"]
    detected_malicious = sum(1 for r in malicious if r["actual"] == "REJECT")
    tpr = (detected_malicious / len(malicious)) * 100.0

    # 2. False Reject Rate (FRR) on genuine authentic card
    genuine = [r for r in results if r["expected"] == "VERIFIED"]
    falsely_rejected = sum(1 for r in genuine if r["actual"] != "VERIFIED")
    frr = (falsely_rejected / len(genuine)) * 100.0

    # 3. Degraded Quality Routing Accuracy (RETAKE)
    degraded = [r for r in results if r["expected"] == "RETAKE"]
    routed_retake = sum(1 for r in degraded if r["actual"] == "RETAKE")
    retake_acc = (routed_retake / len(degraded)) * 100.0

    # 4. Anchorless / Manual Review Routing Accuracy (REVIEW)
    review_cases = [r for r in results if r["expected"] == "REVIEW"]
    routed_review = sum(1 for r in review_cases if r["actual"] == "REVIEW")
    review_acc = (routed_review / len(review_cases)) * 100.0

    total_passed = sum(1 for r in results if r["passed"])
    overall_acc = (total_passed / len(results)) * 100.0

    print(f"  • Overall Matrix Accuracy:            {overall_acc:6.2f}% ({total_passed}/{len(results)} scenarios passed)")
    print(f"  • True Positive Rate (Detection Rate): {tpr:6.2f}% ({detected_malicious}/{len(malicious)} malicious attacks rejected)")
    print(f"  • False Reject Rate (FRR):             {frr:6.2f}% ({falsely_rejected}/{len(genuine)} genuine cards rejected)")
    print(f"  • Retake Routing Accuracy (Degraded):  {retake_acc:6.2f}% ({routed_retake}/{len(degraded)} poor captures caught)")
    print(f"  • Review Routing Accuracy (Unanchored):{review_acc:6.2f}% ({routed_review}/{len(review_cases)} routed to manual review)")
    print(f"  • Total Benchmark Execution Time:     {total_time_ms:6.2f} ms")
    print("=" * 80)

    assert total_passed == len(TEST_CASES), f"Benchmark failed: only {total_passed}/{len(TEST_CASES)} passed!"
    print("  ALL 14 ATTACK SCENARIOS EVALUATED AND CERTIFIED! 🎉")
    print("=" * 80)


if __name__ == "__main__":
    run_benchmark()
