"""
modules/passport/types.py - Standard data contracts and interfaces for Passport Screening Module.
Conforms to Check-Status and Evidence architecture in passport_module_plan_v2.md.
"""

from dataclasses import dataclass, field as dc_field
from enum import Enum
from typing import Optional, Dict, List, Any


class CheckStatus(str, Enum):
    PASS = "PASS"                     # Ran and passed
    FAIL = "FAIL"                     # Ran on reliable inputs and found a contradiction
    UNKNOWN = "UNKNOWN"               # Evidence insufficient or ambiguous (low OCR conf, ambiguous date)
    NOT_EVALUATED = "NOT_EVALUATED"   # Could not run (missing input, dependency UNKNOWN)
    NOT_APPLICABLE = "NOT_APPLICABLE" # Does not apply to this page or mode


class RecommendedAction(str, Enum):
    CONTINUE = "CONTINUE"
    RECAPTURE_REQUIRED = "RECAPTURE_REQUIRED"
    MANUAL_REVIEW = "MANUAL_REVIEW"


class CheckClass(str, Enum):
    T1 = "T1"       # Contradiction: FAIL on reliable input forces review
    T2 = "T2"       # Signal: contributes to weighted score
    INFO = "INFO"   # Logged only; default for unverified rules


@dataclass
class FieldObject:
    """Represents an extracted or parsed field with full provenance and confidence."""
    field_name: str
    raw: Dict[str, Any] = dc_field(default_factory=dict)
    normalized: Optional[str] = None
    confidence: float = 1.0
    reader_agreement: bool = True
    repaired: bool = False
    repair_evidence: Optional[Dict[str, Any]] = None
    status: CheckStatus = CheckStatus.PASS

    def to_dict(self) -> Dict[str, Any]:
        return {
            "field": self.field_name,
            "raw": self.raw,
            "normalized": self.normalized,
            "confidence": self.confidence,
            "reader_agreement": self.reader_agreement,
            "repaired": self.repaired,
            "repair_evidence": self.repair_evidence,
            "status": self.status.value,
        }


@dataclass
class Finding:
    """Individual diagnostic finding emitted by a check."""
    code: str                      # e.g., "PP-MRZ-001"
    check_id: str                  # e.g., "C-1"
    status: CheckStatus            # PASS, FAIL, UNKNOWN, NOT_EVALUATED, NOT_APPLICABLE
    check_class: CheckClass        # T1, T2, INFO
    message: str                   # Human-readable explanation
    field: Optional[str] = None    # Affected field name (e.g., "dob", "passport_no")
    evidence: Dict[str, Any] = dc_field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        res = {
            "code": self.code,
            "check": self.check_id,
            "status": self.status.value,
            "class": self.check_class.value,
            "message": self.message,
        }
        if self.field:
            res["field"] = self.field
        if self.evidence:
            res["evidence"] = self.evidence
        return res


@dataclass
class MRZParseResult:
    """Output from MRZ Parsing & Checksum Engine (Checks C-1 through C-10)."""
    valid_structure: bool = False
    document_type: str = ""
    issuing_country: str = ""
    nationality: str = ""
    passport_number: str = ""
    surname: str = ""
    given_names: str = ""
    dob: Optional[str] = None          # ISO YYYY-MM-DD if resolvable, else YYMMDD
    sex: str = ""
    expiry_date: Optional[str] = None  # ISO YYYY-MM-DD if resolvable, else YYMMDD
    personal_number: str = ""
    check_digits: Dict[str, bool] = dc_field(default_factory=dict) # e.g., {"passport_no": True, "dob": True...}
    fields: Dict[str, FieldObject] = dc_field(default_factory=dict)
    findings: List[Finding] = dc_field(default_factory=list)
    overall_status: CheckStatus = CheckStatus.PASS
    recommended_action: RecommendedAction = RecommendedAction.CONTINUE
