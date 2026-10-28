"""
modules/passport/cross_val.py - VIZ ↔ MRZ Cross-Validation (Checks E-1 through E-7) & Dependency Suppression.
Implements Section 5 (E) and Section 3.5 of passport_module_plan_v2.md.
"""

import re
import unicodedata
from dataclasses import dataclass, field as dc_field
from typing import Optional, Dict, List, Tuple, Any

from modules.passport.types import (
    CheckStatus,
    RecommendedAction,
    CheckClass,
    FieldObject,
    Finding,
    MRZParseResult,
)
from modules.passport.viz import VIZLogicResult, parse_viz_date
from modules.passport.rules import default_registry, PassportRulesRegistry


def transliterate_viz_text(text: str) -> str:
    """
    Standard ICAO 9303 transliteration:
    1. Unicode decomposition to remove accents / diacritics.
    2. Uppercase conversion.
    3. Removal of apostrophes.
    4. Conversion of hyphens and multiple spaces into single '<'.
    """
    if not text:
        return ""
    # Remove accents/diacritics
    nfkd = unicodedata.normalize("NFKD", text)
    ascii_text = "".join(c for c in nfkd if not unicodedata.combining(c))
    
    # Uppercase
    upper_text = ascii_text.upper()
    
    # Remove apostrophes
    clean = re.sub(r"['’`\"]", "", upper_text)
    
    # Replace hyphens with space
    clean = clean.replace("-", " ")
    
    # Collapse whitespace
    tokens = clean.split()
    return " ".join(tokens)


@dataclass
class CrossValidationResult:
    valid_crosscheck: bool = True
    findings: List[Finding] = dc_field(default_factory=list)
    fields: Dict[str, FieldObject] = dc_field(default_factory=dict)
    overall_status: CheckStatus = CheckStatus.PASS
    recommended_action: RecommendedAction = RecommendedAction.CONTINUE


class CrossValidator:
    """
    Cross-checks visual fields (VIZ) against parsed MRZ fields with confidence gating.
    """

    def __init__(self, registry: Optional[PassportRulesRegistry] = None):
        self.registry = registry or default_registry

    def cross_validate(
        self,
        viz_result: VIZLogicResult,
        mrz_result: MRZParseResult,
    ) -> CrossValidationResult:
        result = CrossValidationResult()
        findings: List[Finding] = []

        # =====================================================================
        # Dependency Suppression (Section 3.5):
        # If MRZ extraction failed structurally or is UNKNOWN, suppress E-1..E-7
        # =====================================================================
        if not mrz_result.valid_structure or mrz_result.overall_status == CheckStatus.UNKNOWN:
            findings.append(
                Finding(
                    code="PP-GATE-001",
                    check_id="DEP-SUPPRESSION",
                    status=CheckStatus.UNKNOWN,
                    check_class=CheckClass.INFO,
                    message="MRZ extraction is unreliable or structurally invalid. Downstream VIZ<->MRZ checks suppressed.",
                    evidence={"mrz_status": mrz_result.overall_status.value},
                )
            )
            result.valid_crosscheck = False
            result.findings = findings
            result.overall_status = CheckStatus.UNKNOWN
            result.recommended_action = RecommendedAction.RECAPTURE_REQUIRED
            return result

        # ---------------------------------------------------------------------
        # Helper for Confidence Gating:
        # A mismatch is T1 FAIL ONLY if both sides are CheckStatus.PASS.
        # If either side is UNKNOWN or NOT_EVALUATED, the pair becomes UNKNOWN.
        # ---------------------------------------------------------------------
        def evaluate_pair(
            code: str,
            check_id: str,
            rule_id: str,
            field_name: str,
            viz_val: Optional[str],
            mrz_val: Optional[str],
            comparator,
            success_msg: str,
            fail_msg: str,
        ):
            viz_obj = viz_result.fields.get(field_name)
            mrz_obj = mrz_result.fields.get(field_name)

            viz_status = viz_obj.status if viz_obj else CheckStatus.NOT_EVALUATED
            mrz_status = mrz_obj.status if mrz_obj else CheckStatus.NOT_EVALUATED
            severity = self.registry.get_effective_severity(rule_id)

            # Check if both sides are present
            if viz_val is None or mrz_val is None:
                findings.append(
                    Finding(
                        code=code,
                        check_id=check_id,
                        status=CheckStatus.NOT_EVALUATED,
                        check_class=severity,
                        field=field_name,
                        message=f"{field_name.upper()} cross-check not evaluated (missing on one or both sides).",
                        evidence={"viz": viz_val, "mrz": mrz_val},
                    )
                )
                return

            # Gating check: if either input is UNKNOWN / FAIL at extraction level, don't trigger T1 fraud
            is_reliable = (viz_status == CheckStatus.PASS and mrz_status == CheckStatus.PASS)

            matches, detail = comparator(viz_val, mrz_val)
            if matches:
                findings.append(
                    Finding(
                        code=code,
                        check_id=check_id,
                        status=CheckStatus.PASS,
                        check_class=severity,
                        field=field_name,
                        message=success_msg,
                        evidence={"viz": viz_val, "mrz": mrz_val, "detail": detail},
                    )
                )
            else:
                status = CheckStatus.FAIL if is_reliable else CheckStatus.UNKNOWN
                findings.append(
                    Finding(
                        code=code,
                        check_id=check_id,
                        status=status,
                        check_class=severity,
                        field=field_name,
                        message=fail_msg,
                        evidence={"viz": viz_val, "mrz": mrz_val, "detail": detail, "reliable_inputs": is_reliable},
                    )
                )

        # =====================================================================
        # E-1: Passport Number Match
        # =====================================================================
        def comp_pass_no(viz, mrz):
            v_clean = viz.strip().upper().replace(" ", "").replace("<", "")
            m_clean = mrz.strip().upper().replace(" ", "").replace("<", "")
            return (v_clean == m_clean), f"VIZ '{v_clean}' vs MRZ '{m_clean}'"

        v_pass = viz_result.fields.get("passport_no", FieldObject("passport_no")).normalized
        m_pass = mrz_result.passport_number
        evaluate_pair(
            code="PP-XVAL-001",
            check_id="E-1",
            rule_id="E-1-xval-passport-no",
            field_name="passport_no",
            viz_val=v_pass,
            mrz_val=m_pass,
            comparator=comp_pass_no,
            success_msg="Passport number in VIZ matches MRZ exactly.",
            fail_msg="Passport number mismatch between VIZ and MRZ.",
        )

        # =====================================================================
        # E-2: Surname Match (Transliterated)
        # =====================================================================
        def comp_surname(viz, mrz):
            v_trans = transliterate_viz_text(viz)
            m_clean = transliterate_viz_text(mrz)
            return (v_trans == m_clean), f"VIZ '{v_trans}' vs MRZ '{m_clean}'"

        v_sur = viz_result.fields.get("surname", FieldObject("surname")).normalized
        m_sur = mrz_result.surname
        evaluate_pair(
            code="PP-XVAL-002",
            check_id="E-2",
            rule_id="E-2-xval-surname",
            field_name="surname",
            viz_val=v_sur,
            mrz_val=m_sur,
            comparator=comp_surname,
            success_msg="Surname in VIZ matches MRZ primary identifier.",
            fail_msg="Surname mismatch between VIZ and MRZ.",
        )

        # =====================================================================
        # E-3: Given Names Match (Transliterated + Field-Length Truncation)
        # =====================================================================
        def comp_given(viz, mrz):
            v_trans = transliterate_viz_text(viz)
            m_clean = transliterate_viz_text(mrz)
            if v_trans == m_clean:
                return True, "Exact match"
            # Truncation tolerance: MRZ line 1 may truncate long names at field boundary
            if len(m_clean) > 5 and v_trans.startswith(m_clean):
                return True, f"Truncated match at field boundary: VIZ '{v_trans}' truncated to MRZ '{m_clean}'"
            return False, f"VIZ '{v_trans}' vs MRZ '{m_clean}'"

        v_given = viz_result.fields.get("given_names", FieldObject("given_names")).normalized
        m_given = mrz_result.given_names
        evaluate_pair(
            code="PP-XVAL-003",
            check_id="E-3",
            rule_id="E-3-xval-given-names",
            field_name="given_names",
            viz_val=v_given,
            mrz_val=m_given,
            comparator=comp_given,
            success_msg="Given name(s) in VIZ match MRZ secondary identifier.",
            fail_msg="Given name(s) mismatch between VIZ and MRZ.",
        )

        # =====================================================================
        # E-4: Date of Birth Match (DD/MM/YYYY vs YYMMDD + century)
        # =====================================================================
        def comp_dob(viz, mrz):
            # viz is normalized ISO YYYY-MM-DD or raw DD/MM/YYYY
            dt_obj, _ = parse_viz_date(viz) if "/" in viz else (None, None)
            if dt_obj:
                iso_viz = dt_obj.isoformat()
            else:
                iso_viz = viz
            # mrz_result.dob is ISO YYYY-MM-DD if resolved
            mrz_dob = mrz_result.dob or ""
            return (iso_viz == mrz_dob), f"VIZ '{iso_viz}' vs MRZ '{mrz_dob}'"

        v_dob = viz_result.fields.get("dob", FieldObject("dob")).raw.get("viz")
        m_dob = mrz_result.dob
        evaluate_pair(
            code="PP-XVAL-004",
            check_id="E-4",
            rule_id="E-4-xval-dob",
            field_name="dob",
            viz_val=v_dob,
            mrz_val=m_dob,
            comparator=comp_dob,
            success_msg="Date of birth in VIZ matches MRZ DOB and century.",
            fail_msg="Date of birth mismatch between VIZ and MRZ.",
        )

        # =====================================================================
        # E-5: Expiry Date Match (DD/MM/YYYY vs YYMMDD)
        # =====================================================================
        def comp_expiry(viz, mrz):
            dt_obj, _ = parse_viz_date(viz) if "/" in viz else (None, None)
            if dt_obj:
                iso_viz = dt_obj.isoformat()
            else:
                iso_viz = viz
            mrz_exp = mrz_result.expiry_date or ""
            return (iso_viz == mrz_exp), f"VIZ '{iso_viz}' vs MRZ '{mrz_exp}'"

        v_doe = viz_result.fields.get("doe", FieldObject("doe")).raw.get("viz")
        m_doe = mrz_result.expiry_date
        evaluate_pair(
            code="PP-XVAL-005",
            check_id="E-5",
            rule_id="E-5-xval-expiry",
            field_name="doe",
            viz_val=v_doe,
            mrz_val=m_doe,
            comparator=comp_expiry,
            success_msg="Expiry date in VIZ matches MRZ expiry date.",
            fail_msg="Expiry date mismatch between VIZ and MRZ.",
        )

        # =====================================================================
        # E-6: Sex Field Match
        # =====================================================================
        def comp_sex(viz, mrz):
            v_s = viz.strip().upper()[0] if viz else ""
            m_s = mrz.strip().upper()
            return (v_s == m_s), f"VIZ '{v_s}' vs MRZ '{m_s}'"

        v_sex = viz_result.fields.get("sex", FieldObject("sex")).normalized
        m_sex = mrz_result.sex
        evaluate_pair(
            code="PP-XVAL-006",
            check_id="E-6",
            rule_id="E-6-xval-sex",
            field_name="sex",
            viz_val=v_sex,
            mrz_val=m_sex,
            comparator=comp_sex,
            success_msg="Sex field matches between VIZ and MRZ.",
            fail_msg="Sex field mismatch between VIZ and MRZ.",
        )

        # =====================================================================
        # E-7: Nationality Match ('INDIAN' vs 'IND')
        # =====================================================================
        def comp_nat(viz, mrz):
            v_n = viz.strip().upper()
            m_n = mrz.strip().upper()
            matches = (v_n == "INDIAN" and m_n == "IND")
            return matches, f"VIZ '{v_n}' vs MRZ '{m_n}'"

        v_nat = viz_result.fields.get("nationality", FieldObject("nationality")).normalized
        m_nat = mrz_result.nationality
        evaluate_pair(
            code="PP-XVAL-007",
            check_id="E-7",
            rule_id="E-7-xval-nationality",
            field_name="nationality",
            viz_val=v_nat,
            mrz_val=m_nat,
            comparator=comp_nat,
            success_msg="Nationality matches specification (VIZ 'INDIAN' <-> MRZ 'IND').",
            fail_msg="Nationality mismatch between VIZ and MRZ.",
        )

        result.findings = findings
        has_t1_fail = any(f.status == CheckStatus.FAIL and f.check_class == CheckClass.T1 for f in findings)
        has_unknown = any(f.status == CheckStatus.UNKNOWN for f in findings)

        if has_t1_fail:
            result.valid_crosscheck = False
            result.overall_status = CheckStatus.FAIL
            result.recommended_action = RecommendedAction.MANUAL_REVIEW
        elif has_unknown:
            result.valid_crosscheck = False
            result.overall_status = CheckStatus.UNKNOWN
            result.recommended_action = RecommendedAction.RECAPTURE_REQUIRED
        else:
            result.valid_crosscheck = True
            result.overall_status = CheckStatus.PASS
            result.recommended_action = RecommendedAction.CONTINUE

        return result
