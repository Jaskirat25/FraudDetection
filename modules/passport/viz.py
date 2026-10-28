"""
modules/passport/viz.py - VIZ Document-Logic Rules Engine (Checks D-2 through D-7, D-10).
Implements Section 5 (D) of passport_module_plan_v2.md.
"""

import re
from datetime import datetime, date
from dataclasses import dataclass, field as dc_field
from typing import Optional, Dict, List, Tuple, Any

from modules.passport.mrz import is_valid_calendar_date
from modules.passport.types import (
    CheckStatus,
    RecommendedAction,
    CheckClass,
    FieldObject,
    Finding,
)
from modules.passport.rules import default_registry, PassportRulesRegistry


@dataclass
class VIZLogicResult:
    valid_logic: bool = True
    document_status: List[str] = dc_field(default_factory=list)
    fields: Dict[str, FieldObject] = dc_field(default_factory=dict)
    findings: List[Finding] = dc_field(default_factory=list)
    overall_status: CheckStatus = CheckStatus.PASS
    recommended_action: RecommendedAction = RecommendedAction.CONTINUE


def parse_viz_date(date_str: str) -> Tuple[Optional[date], Optional[str]]:
    """
    Parses a VIZ date string formatted as DD/MM/YYYY with calendar verification.
    Returns (date_obj, None) or (None, error_reason).
    """
    cleaned = date_str.strip()
    match = re.match(r"^(\d{2})[/-](\d{2})[/-](\d{4})$", cleaned)
    if not match:
        return None, f"Invalid date format '{date_str}'; expected DD/MM/YYYY"

    day = int(match.group(1))
    month = int(match.group(2))
    year = int(match.group(3))

    if not is_valid_calendar_date(year, month, day):
        return None, f"Invalid calendar date '{date_str}' (impossible day/month/leap year)"

    return date(year, month, day), None


class VIZLogicValidator:
    """
    Validates visual inspection zone (VIZ) document logic against official rules.
    """

    def __init__(self, registry: Optional[PassportRulesRegistry] = None):
        self.registry = registry or default_registry

    def validate(
        self,
        viz_fields: Dict[str, str],
        reference_date: Optional[date] = None,
    ) -> VIZLogicResult:
        ref_date = reference_date or date.today()
        result = VIZLogicResult()
        findings: List[Finding] = []
        fields: Dict[str, FieldObject] = {}

        raw_dob = viz_fields.get("dob", "")
        raw_doi = viz_fields.get("doi", "")  # Date of Issue
        raw_doe = viz_fields.get("doe", "")  # Date of Expiry
        raw_nat = viz_fields.get("nationality", "")
        raw_pass_no = viz_fields.get("passport_no", "")
        raw_surname = viz_fields.get("surname", "")
        raw_given = viz_fields.get("given_names", "")
        raw_sex = viz_fields.get("sex", "")

        # =====================================================================
        # D-2: Date Formats (DD/MM/YYYY & Calendar Sanity)
        # =====================================================================
        d2_severity = self.registry.get_effective_severity("D-2-date-formats")
        parsed_dates: Dict[str, Optional[date]] = {}
        date_format_errors: List[str] = []

        for d_key, raw_val in [("dob", raw_dob), ("doi", raw_doi), ("doe", raw_doe)]:
            if raw_val:
                dt_obj, err = parse_viz_date(raw_val)
                parsed_dates[d_key] = dt_obj
                if err:
                    date_format_errors.append(f"{d_key.upper()}: {err}")
                    fields[d_key] = FieldObject(
                        field_name=d_key,
                        raw={"viz": raw_val},
                        status=CheckStatus.FAIL,
                    )
                else:
                    fields[d_key] = FieldObject(
                        field_name=d_key,
                        raw={"viz": raw_val},
                        normalized=dt_obj.isoformat(),
                        status=CheckStatus.PASS,
                    )
            else:
                parsed_dates[d_key] = None

        if not date_format_errors:
            findings.append(
                Finding(
                    code="PP-VIZ-002",
                    check_id="D-2",
                    status=CheckStatus.PASS,
                    check_class=d2_severity,
                    message="All present VIZ dates conform to DD/MM/YYYY and valid calendar rules.",
                    evidence={"parsed_dates": {k: v.isoformat() if v else None for k, v in parsed_dates.items()}},
                )
            )
        else:
            findings.append(
                Finding(
                    code="PP-VIZ-002",
                    check_id="D-2",
                    status=CheckStatus.FAIL,
                    check_class=d2_severity,
                    message="VIZ date formatting failure: " + "; ".join(date_format_errors),
                    evidence={"errors": date_format_errors},
                )
            )

        dob_dt = parsed_dates.get("dob")
        doi_dt = parsed_dates.get("doi")
        doe_dt = parsed_dates.get("doe")

        # =====================================================================
        # D-3: DOB Plausibility (Not in Future, Age 0-115)
        # =====================================================================
        d3_severity = self.registry.get_effective_severity("D-3-dob-plausibility")
        if dob_dt:
            if dob_dt > ref_date:
                findings.append(
                    Finding(
                        code="PP-VIZ-003",
                        check_id="D-3",
                        status=CheckStatus.FAIL,
                        check_class=d3_severity,
                        field="dob",
                        message=f"Date of birth ({dob_dt.isoformat()}) is in the future relative to {ref_date.isoformat()}.",
                        evidence={"dob": dob_dt.isoformat(), "reference_date": ref_date.isoformat()},
                    )
                )
                fields["dob"].status = CheckStatus.FAIL
            else:
                age_years = (ref_date - dob_dt).days / 365.25
                if age_years > 115:
                    findings.append(
                        Finding(
                            code="PP-VIZ-003",
                            check_id="D-3",
                            status=CheckStatus.FAIL,
                            check_class=d3_severity,
                            field="dob",
                            message=f"Date of birth implies implausible age: {age_years:.1f} years.",
                            evidence={"dob": dob_dt.isoformat(), "calculated_age": age_years},
                        )
                    )
                    fields["dob"].status = CheckStatus.FAIL
                else:
                    findings.append(
                        Finding(
                            code="PP-VIZ-003",
                            check_id="D-3",
                            status=CheckStatus.PASS,
                            check_class=d3_severity,
                            field="dob",
                            message=f"Date of birth plausible (Holder age: {age_years:.1f} years).",
                            evidence={"dob": dob_dt.isoformat(), "calculated_age": age_years},
                        )
                    )

        # =====================================================================
        # D-4: Date Ordering (DOB < DOI < DOE)
        # =====================================================================
        d4_severity = self.registry.get_effective_severity("D-4-date-ordering")
        ordering_violations = []

        if dob_dt and doi_dt and dob_dt >= doi_dt:
            ordering_violations.append(f"DOB ({dob_dt.isoformat()}) is not strictly before DOI ({doi_dt.isoformat()})")

        if doi_dt and doe_dt and doi_dt >= doe_dt:
            ordering_violations.append(f"DOI ({doi_dt.isoformat()}) is not strictly before DOE ({doe_dt.isoformat()})")

        if dob_dt and doe_dt and dob_dt >= doe_dt:
            ordering_violations.append(f"DOB ({dob_dt.isoformat()}) is not strictly before DOE ({doe_dt.isoformat()})")

        if ordering_violations:
            findings.append(
                Finding(
                    code="PP-VIZ-004",
                    check_id="D-4",
                    status=CheckStatus.FAIL,
                    check_class=d4_severity,
                    message="Chronological ordering violation: " + "; ".join(ordering_violations),
                    evidence={"violations": ordering_violations},
                )
            )
        elif dob_dt or doi_dt or doe_dt:
            findings.append(
                Finding(
                    code="PP-VIZ-004",
                    check_id="D-4",
                    status=CheckStatus.PASS,
                    check_class=d4_severity,
                    message="Chronological date ordering verified (DOB < DOI < DOE).",
                )
            )

        # =====================================================================
        # D-5: Issue Date Plausibility (DOI <= Today)
        # =====================================================================
        d5_severity = self.registry.get_effective_severity("D-5-issue-date-plausibility")
        if doi_dt:
            if doi_dt > ref_date:
                findings.append(
                    Finding(
                        code="PP-VIZ-005",
                        check_id="D-5",
                        status=CheckStatus.FAIL,
                        check_class=d5_severity,
                        field="doi",
                        message=f"Date of Issue ({doi_dt.isoformat()}) is in the future relative to {ref_date.isoformat()}.",
                        evidence={"doi": doi_dt.isoformat(), "reference_date": ref_date.isoformat()},
                    )
                )
                fields["doi"].status = CheckStatus.FAIL
            else:
                findings.append(
                    Finding(
                        code="PP-VIZ-005",
                        check_id="D-5",
                        status=CheckStatus.PASS,
                        check_class=d5_severity,
                        field="doi",
                        message=f"Date of Issue verified ({doi_dt.isoformat()}).",
                    )
                )

        # =====================================================================
        # D-7: Expiry Status (Administrative Flag)
        # =====================================================================
        d7_severity = self.registry.get_effective_severity("D-7-expiry-status")
        if doe_dt:
            if doe_dt < ref_date:
                result.document_status.append("EXPIRED")
                findings.append(
                    Finding(
                        code="PP-DOC-007",
                        check_id="D-7",
                        status=CheckStatus.PASS,
                        check_class=d7_severity,
                        field="doe",
                        message=f"Document is EXPIRED (Expiry: {doe_dt.isoformat()} < Today: {ref_date.isoformat()}).",
                        evidence={"doe": doe_dt.isoformat(), "reference_date": ref_date.isoformat()},
                    )
                )
            else:
                findings.append(
                    Finding(
                        code="PP-DOC-007",
                        check_id="D-7",
                        status=CheckStatus.PASS,
                        check_class=d7_severity,
                        field="doe",
                        message=f"Document is currently valid (Expiry: {doe_dt.isoformat()}).",
                    )
                )

        # =====================================================================
        # D-10: Nationality Literal ('INDIAN')
        # =====================================================================
        d10_severity = self.registry.get_effective_severity("D-10-nationality-literal")
        clean_nat = raw_nat.strip().upper()
        if clean_nat:
            if clean_nat == "INDIAN":
                findings.append(
                    Finding(
                        code="PP-VIZ-010",
                        check_id="D-10",
                        status=CheckStatus.PASS,
                        check_class=d10_severity,
                        field="nationality",
                        message="Printed VIZ nationality verified as 'INDIAN'.",
                    )
                )
                fields["nationality"] = FieldObject(
                    field_name="nationality",
                    raw={"viz": raw_nat},
                    normalized="INDIAN",
                    status=CheckStatus.PASS,
                )
            else:
                findings.append(
                    Finding(
                        code="PP-VIZ-010",
                        check_id="D-10",
                        status=CheckStatus.FAIL,
                        check_class=d10_severity,
                        field="nationality",
                        message=f"Printed nationality is '{clean_nat}'; expected 'INDIAN'.",
                        evidence={"found": clean_nat, "expected": "INDIAN"},
                    )
                )
                fields["nationality"] = FieldObject(
                    field_name="nationality",
                    raw={"viz": raw_nat},
                    normalized=clean_nat,
                    status=CheckStatus.FAIL,
                )

        # Store other present VIZ fields
        for f_name, raw_txt in [("passport_no", raw_pass_no), ("surname", raw_surname), ("given_names", raw_given), ("sex", raw_sex)]:
            if f_name not in fields and raw_txt:
                fields[f_name] = FieldObject(
                    field_name=f_name,
                    raw={"viz": raw_txt},
                    normalized=raw_txt.strip(),
                    status=CheckStatus.PASS,
                )

        result.fields = fields
        result.findings = findings

        has_t1_fail = any(f.status == CheckStatus.FAIL and f.check_class == CheckClass.T1 for f in findings)
        if has_t1_fail:
            result.valid_logic = False
            result.overall_status = CheckStatus.FAIL
            result.recommended_action = RecommendedAction.MANUAL_REVIEW
        else:
            result.valid_logic = True
            result.overall_status = CheckStatus.PASS
            result.recommended_action = RecommendedAction.CONTINUE

        return result
