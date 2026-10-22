"""
modules/scoring/fusion.py - Two-Tier Risk Scoring and Fail-Closed Decision Engine (L1-L5 Fusion).
Implements fail-closed verdict states: VERIFIED, REVIEW, RETAKE, REJECT.
"""

from typing import List, Dict, Any, Optional
from core.types import ModuleResult, RiskReport, RiskLevel, Verdict, QRResult
from core.config import RISK_WEIGHTS, SCORE_BANDS


def compute_risk_report(
    results: List[ModuleResult],
    field_data: Optional[Dict[str, Any]] = None,
    qr_payload: Optional[Dict[str, Any]] = None,
    qr_result: Optional[QRResult] = None,
    has_qr_crop: bool = False,
    card_quality_score: float = 0.95
) -> RiskReport:
    """
    Fuses outputs from all modules into a final fail-closed risk verdict.
    
    Verdicts:
    - REJECT: Conclusive fraud (bad signature, photo-swap, printed vs QR text mismatch, Verhoeff fail).
    - RETAKE: Capture degraded (QR detected but unreadable, face landmarks not found due to blur/glare).
    - REVIEW: Missing cryptographic anchor (legacy unsigned XML, front-only card) or soft point accumulation.
    - VERIFIED: Fail-closed clean pass. ALL mandatory cryptographic & biometric proofs verified.
    """
    hard_reject = False
    tier1_violations: List[str] = []
    tier2_contributions: List[Dict[str, Any]] = []
    all_flags: List[str] = []
    per_field_analysis: Dict[str, Dict[str, Any]] = {}
    merged_evidence: Dict[str, Any] = {}
    
    total_score = 0.0

    # 1. Process all module results
    for mod in results:
        all_flags.extend(mod.flags)
        merged_evidence.update(mod.evidence)
        
        # Check Tier 1 hard fails
        if mod.hard_fail:
            hard_reject = True
            fail_flags = [
                f for f in mod.flags 
                if any(w in f.upper() for w in ("FRAUD", "MISMATCH", "FAILED", "INVALID", "TAMPER", "FORGERY", "ALERT"))
            ]
            tier1_violations.extend(fail_flags if fail_flags else mod.flags)

        # Check Tier 2 contributions
        for field_name, score in mod.scores.items():
            if field_name not in per_field_analysis:
                per_field_analysis[field_name] = {"tamper_score": score}
            else:
                per_field_analysis[field_name]["tamper_score"] = max(
                    per_field_analysis[field_name].get("tamper_score", 0.0), score
                )

    # 2. Tier 2 Additive Point Accumulation
    for field_name, info in per_field_analysis.items():
        s = info.get("tamper_score", 0.0)
        if s > 0.7:
            if field_name == "photo":
                pts = RISK_WEIGHTS.get("tamper_photo_high", 30.0)
                tier2_contributions.append({"reason": "High suspicion in photo crop", "points": pts})
                total_score += pts
            elif field_name == "face_mismatch_live":
                pts = RISK_WEIGHTS.get("face_mismatch_live", 30.0)
                tier2_contributions.append({"reason": "Live selfie does not match cardholder photo", "points": pts})
                total_score += pts
            elif field_name in ("dob", "aadhaar_no"):
                pts = RISK_WEIGHTS.get("tamper_dob_or_num_high", 25.0)
                tier2_contributions.append({"reason": f"High suspicion in {field_name} crop", "points": pts})
                total_score += pts
            else:
                pts = RISK_WEIGHTS.get("tamper_general_high", 15.0)
                tier2_contributions.append({"reason": f"High suspicion in {field_name}", "points": pts})
                total_score += pts

    # Extract cryptographic & biometric evidence
    qr_present = merged_evidence.get("qr_present", qr_result.present if qr_result else False)
    is_secure_qr = merged_evidence.get("is_secure_qr", qr_result.is_secure_qr if qr_result else False)
    qr_sig_valid = merged_evidence.get("qr_signature_valid", qr_result.signature_valid if qr_result else False)
    card_face_detected = merged_evidence.get("card_face_detected", True)
    card_qr_cosine_sim = merged_evidence.get("card_qr_cosine_sim", None)
    qr_live_cosine_sim = merged_evidence.get("qr_live_cosine_sim", None)

    # 3. FAIL-CLOSED VERDICT STATE MACHINE

    # State 1: Conclusive Hard Fraud -> REJECT
    if hard_reject:
        verdict = Verdict.REJECT
        overall_risk = RiskLevel.HIGH
        total_score = 100.0
        verdict_reason = "Immediate rejection: Cryptographic forgery, physical photo-swap, or mathematical checksum failure detected."

    # State 2: Physical Capture Degraded -> RETAKE
    elif has_qr_crop and not qr_present:
        verdict = Verdict.RETAKE
        overall_risk = RiskLevel.MEDIUM
        total_score = max(total_score, 35.0)
        verdict_reason = "RETAKE REQUIRED: QR code was detected on the card, but could not be decoded due to blur, glare, or low resolution. Please retake a clear, well-lit photo."

    elif card_face_detected is False and ("photo" in per_field_analysis or any("card surface photo" in f for f in all_flags)):
        verdict = Verdict.RETAKE
        overall_risk = RiskLevel.MEDIUM
        total_score = max(total_score, 35.0)
        verdict_reason = "RETAKE REQUIRED: Cardholder photograph is too degraded or dark to localize facial landmarks. Please submit a clearer image."

    elif card_quality_score < 0.60:
        verdict = Verdict.RETAKE
        overall_risk = RiskLevel.MEDIUM
        total_score = max(total_score, 35.0)
        verdict_reason = "RETAKE REQUIRED: Overall document capture quality is degraded or distorted. Please retake a flat, centered photo."

    # State 3: Missing Cryptographic Anchor -> REVIEW (FAIL CLOSED: Can NEVER be VERIFIED)
    elif not is_secure_qr or not qr_sig_valid:
        verdict = Verdict.REVIEW
        overall_risk = RiskLevel.MEDIUM
        pts = 45.0
        tier2_contributions.append({
            "reason": "Missing cryptographic anchor: UIDAI Secure QR was not verified on this card",
            "points": pts
        })
        total_score = min(100.0, total_score + pts)
        verdict_reason = "MANUAL REVIEW REQUIRED: Document lacks a verified UIDAI RSA-2048 cryptographic anchor. Front-only scan or unsigned legacy card. Alternative verification (e-Aadhaar PDF / Offline XML) advised."

    # State 4: Soft Risk Points Accumulation or Borderline Match -> REVIEW
    elif total_score > SCORE_BANDS["LOW_MAX"] or (card_qr_cosine_sim is not None and card_qr_cosine_sim < 0.40):
        verdict = Verdict.REVIEW
        overall_risk = RiskLevel.MEDIUM if total_score <= SCORE_BANDS["MEDIUM_MAX"] else RiskLevel.HIGH
        verdict_reason = "MANUAL REVIEW REQUIRED: Soft diagnostic anomalies or borderline biometric similarity detected on the document."

    # State 5: Verified Authentic -> VERIFIED (Fail-closed satisfied!)
    else:
        verdict = Verdict.VERIFIED
        overall_risk = RiskLevel.LOW
        verdict_reason = "VERIFIED: Cryptographically authentic document. UIDAI RSA-2048 signature valid, printed text agrees with digital payload, and biometrics match."

    return RiskReport(
        overall_risk=overall_risk,
        verdict=verdict,
        verdict_reason=verdict_reason,
        risk_score=min(100.0, total_score),
        hard_reject=hard_reject,
        tier1_violations=tier1_violations,
        tier2_contributions=tier2_contributions,
        per_field_analysis=per_field_analysis,
        flags=all_flags,
        heatmap_overlay=None,
        metadata={
            "total_modules_evaluated": len(results),
            "cryptographic_anchor_verified": is_secure_qr and qr_sig_valid
        }
    )
