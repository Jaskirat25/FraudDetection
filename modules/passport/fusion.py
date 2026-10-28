"""
modules/passport/fusion.py - Evidence Groups & Decision Fusion Engine.
Implements Section 6 of passport_module_plan_v2.md:
Aggregates findings into evidence groups, computes calibrated risk_index and coverage,
and generates standardized explainable screening verdicts.
"""

from enum import Enum
from dataclasses import dataclass, field as dc_field
from typing import Optional, Dict, List, Any

from modules.passport.types import (
    CheckStatus,
    RecommendedAction,
    CheckClass,
    Finding,
    MRZParseResult,
)
from modules.passport.quality import QualityGateResult
from modules.passport.viz import VIZLogicResult
from modules.passport.cross_val import CrossValidationResult
from modules.passport.privacy import ReuseCheckResult
from modules.passport.rules import default_registry, PassportRulesRegistry


class PassportDecision(str, Enum):
    LOW_RISK_SCREEN = "LOW_RISK_SCREEN"
    MANUAL_REVIEW = "MANUAL_REVIEW"
    RECAPTURE_REQUIRED = "RECAPTURE_REQUIRED"
    UNSUPPORTED = "UNSUPPORTED"


class PassportPriority(str, Enum):
    HIGH = "HIGH"
    NORMAL = "NORMAL"
    LOW = "LOW"


@dataclass
class PassportScreeningReport:
    """Standardized Section 6.4 Output Schema."""
    document: str = "indian_passport"
    decision: PassportDecision = PassportDecision.LOW_RISK_SCREEN
    priority: Optional[PassportPriority] = None
    document_status: List[str] = dc_field(default_factory=list)
    risk_index: float = 0.0
    risk_band: Optional[str] = None
    extraction_confidence: float = 1.0
    image_quality: Dict[str, Any] = dc_field(default_factory=dict)
    coverage: float = 1.0
    findings: List[Dict[str, Any]] = dc_field(default_factory=list)
    not_evaluated: List[str] = dc_field(default_factory=list)
    rules_version: str = "ruleset-2026-10"
    recommended_action: RecommendedAction = RecommendedAction.CONTINUE

    def to_dict(self) -> Dict[str, Any]:
        return {
            "document": self.document,
            "decision": self.decision.value,
            "priority": self.priority.value if self.priority else None,
            "document_status": self.document_status,
            "risk_index": round(self.risk_index, 1),
            "risk_band": self.risk_band,
            "extraction_confidence": round(self.extraction_confidence, 2),
            "image_quality": self.image_quality,
            "coverage": round(self.coverage, 2),
            "findings": self.findings,
            "not_evaluated": self.not_evaluated,
            "rules_version": self.rules_version,
            "recommended_action": self.recommended_action.value,
        }


class PassportDecisionEngine:
    """
    Orchestrates evidence fusion across Quality, MRZ, VIZ, Cross-Val, and History.
    """

    def __init__(self, registry: Optional[PassportRulesRegistry] = None):
        self.registry = registry or default_registry

    def fuse(
        self,
        quality_res: Optional[QualityGateResult] = None,
        mrz_res: Optional[MRZParseResult] = None,
        viz_res: Optional[VIZLogicResult] = None,
        xval_res: Optional[CrossValidationResult] = None,
        reuse_res: Optional[ReuseCheckResult] = None,
        planned_check_ids: Optional[List[str]] = None,
    ) -> PassportScreeningReport:
        report = PassportScreeningReport()
        report.rules_version = self.registry.ruleset_version

        all_findings: List[Finding] = []

        # 1. Collect findings from all executed stages
        if quality_res and quality_res.finding:
            all_findings.append(quality_res.finding)
            report.image_quality = quality_res.metrics

        if mrz_res:
            all_findings.extend(mrz_res.findings)

        if viz_res:
            all_findings.extend(viz_res.findings)
            report.document_status.extend(viz_res.document_status)

        if xval_res:
            all_findings.extend(xval_res.findings)

        if reuse_res:
            all_findings.extend(reuse_res.findings)

        report.document_status = sorted(list(set(report.document_status)))
        report.findings = [f.to_dict() for f in all_findings]

        # 2. Compute Coverage Metric (Section 6.4)
        # Coverage = (PASS + FAIL) / total_applicable_checks
        planned_checks = planned_check_ids or [
            "A-2", "C-1", "C-2", "C-3", "C-4", "C-5", "C-6", "C-7", "C-8", "C-9", "C-10",
            "D-2", "D-3", "D-4", "D-5", "D-7", "D-10",
            "E-1", "E-2", "E-3", "E-4", "E-5", "E-6", "E-7",
            "I-6",
        ]

        evaluated_ids = set()
        decisive_ids = set()
        for f in all_findings:
            evaluated_ids.add(f.check_id)
            if f.status in (CheckStatus.PASS, CheckStatus.FAIL):
                decisive_ids.add(f.check_id)

        not_evaluated_list = [cid for cid in planned_checks if cid not in evaluated_ids]
        report.not_evaluated = not_evaluated_list

        total_applicable = len(planned_checks)
        report.coverage = len(decisive_ids) / total_applicable if total_applicable > 0 else 1.0

        # 3. Calculate Extraction Confidence (Group G1)
        mrz_pass_count = sum(1 for f in all_findings if f.check_id.startswith("C-") and f.status == CheckStatus.PASS)
        mrz_total_count = sum(1 for f in all_findings if f.check_id.startswith("C-"))
        report.extraction_confidence = mrz_pass_count / mrz_total_count if mrz_total_count > 0 else 0.5

        # 4. Check for Hard Contradictions (T1 FAIL on reliable inputs)
        t1_fails = [f for f in all_findings if f.status == CheckStatus.FAIL and f.check_class == CheckClass.T1]
        t2_fails = [f for f in all_findings if f.status == CheckStatus.FAIL and f.check_class == CheckClass.T2]

        # 5. Weighted Risk Index Calculation (Section 6.3)
        # Starting weights: T2 signals contribute 20 points each (capped at 100)
        risk_score = 0.0
        if t1_fails:
            risk_score = 80.0 + min(len(t1_fails) * 5.0, 20.0)
        else:
            risk_score = min(len(t2_fails) * 20.0, 100.0)
        report.risk_index = risk_score

        # 6. Calibrated Decision Logic (Section 6.2)
        # Gate 1: Quality Gate failure
        if quality_res and not quality_res.passed:
            report.decision = PassportDecision.RECAPTURE_REQUIRED
            report.priority = None
            report.recommended_action = RecommendedAction.RECAPTURE_REQUIRED
            return report

        # Gate 2: Critical field UNKNOWN due to scan quality
        has_critical_unknown = any(
            f.status == CheckStatus.UNKNOWN and f.check_id in ("C-1", "A-2")
            for f in all_findings
        )
        if has_critical_unknown:
            report.decision = PassportDecision.RECAPTURE_REQUIRED
            report.priority = None
            report.recommended_action = RecommendedAction.RECAPTURE_REQUIRED
            return report

        # Gate 3: T1 Conclusive Contradiction -> MANUAL_REVIEW with priority=HIGH
        if t1_fails:
            report.decision = PassportDecision.MANUAL_REVIEW
            report.priority = PassportPriority.HIGH
            report.recommended_action = RecommendedAction.MANUAL_REVIEW
            return report

        # Gate 4: Elevated Risk or Unresolved T2 Contradictions
        if risk_score >= 40.0:
            report.decision = PassportDecision.MANUAL_REVIEW
            report.priority = PassportPriority.NORMAL
            report.recommended_action = RecommendedAction.MANUAL_REVIEW
            return report

        # Gate 5: Clean screening -> LOW_RISK_SCREEN
        report.decision = PassportDecision.LOW_RISK_SCREEN
        report.priority = None
        report.recommended_action = RecommendedAction.CONTINUE
        return report
