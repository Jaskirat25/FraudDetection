"""
modules/scoring/fusion.py - Two-Tier Risk Scoring and Explainability Engine (L1-L5 Fusion).
"""

from typing import List, Dict, Any, Optional
from core.types import ModuleResult, RiskReport, RiskLevel
from core.config import RISK_WEIGHTS, SCORE_BANDS


def compute_risk_report(
    results: List[ModuleResult],
    field_data: Optional[Dict[str, Any]] = None,
    qr_payload: Optional[Dict[str, Any]] = None
) -> RiskReport:
    """
    Fuses outputs from all modules into a final risk verdict.
    Tier 1: Conclusive rules (Signature fail, QR-print mismatch, Verhoeff fail) -> Instant HIGH risk.
    Tier 2: Weighted additive points across heuristics and ML scores -> LOW / MEDIUM / HIGH.
    """
    hard_reject = False
    tier1_violations: List[str] = []
    tier2_contributions: List[Dict[str, Any]] = []
    all_flags: List[str] = []
    per_field_analysis: Dict[str, Dict[str, Any]] = {}
    
    total_score = 0.0

    # Process all module results
    for mod in results:
        all_flags.extend(mod.flags)
        
        # Check Tier 1 hard fails
        if mod.hard_fail:
            hard_reject = True
            tier1_violations.extend(mod.flags)

        # Check Tier 2 contributions
        for field_name, score in mod.scores.items():
            if field_name not in per_field_analysis:
                per_field_analysis[field_name] = {"tamper_score": score}
            else:
                per_field_analysis[field_name]["tamper_score"] = max(
                    per_field_analysis[field_name].get("tamper_score", 0.0), score
                )

    if hard_reject:
        overall_risk = RiskLevel.HIGH
        total_score = 100.0
    else:
        # Tier 2 additive calculation
        for field_name, info in per_field_analysis.items():
            s = info.get("tamper_score", 0.0)
            if s > 0.7:
                if field_name == "photo":
                    pts = RISK_WEIGHTS["tamper_photo_high"]
                    tier2_contributions.append({"reason": "High suspicion in photo crop", "points": pts})
                    total_score += pts
                elif field_name in ("dob", "aadhaar_no"):
                    pts = RISK_WEIGHTS["tamper_dob_or_num_high"]
                    tier2_contributions.append({"reason": f"High suspicion in {field_name} crop", "points": pts})
                    total_score += pts
                else:
                    pts = RISK_WEIGHTS["tamper_general_high"]
                    tier2_contributions.append({"reason": f"High suspicion in {field_name}", "points": pts})
                    total_score += pts

        # Determine band
        if total_score <= SCORE_BANDS["LOW_MAX"]:
            overall_risk = RiskLevel.LOW
        elif total_score <= SCORE_BANDS["MEDIUM_MAX"]:
            overall_risk = RiskLevel.MEDIUM
        else:
            overall_risk = RiskLevel.HIGH

    return RiskReport(
        overall_risk=overall_risk,
        risk_score=min(100.0, total_score),
        hard_reject=hard_reject,
        tier1_violations=tier1_violations,
        tier2_contributions=tier2_contributions,
        per_field_analysis=per_field_analysis,
        flags=all_flags,
        heatmap_overlay=None,
        metadata={"total_modules_evaluated": len(results)}
    )
