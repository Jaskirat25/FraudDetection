"""
modules/passport/mrz.py - ICAO Doc 9303 Part 4 TD3 MRZ Parsing & 7-3-1 Checksum Engine.
Implements Checks C-1 through C-10 according to passport_module_plan_v2.md.
"""

import re
import calendar
from datetime import datetime, date
from typing import Optional, Dict, List, Tuple, Any

from modules.passport.types import (
    CheckStatus,
    RecommendedAction,
    CheckClass,
    FieldObject,
    Finding,
    MRZParseResult,
)
from modules.passport.rules import default_registry, PassportRulesRegistry

# ICAO 7-3-1 Character Weights
WEIGHTS = [7, 3, 1]
ICAO_CHARSET = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789<")


def calculate_icao_check_digit(data_str: str) -> int:
    """
    Computes ICAO 9303 check digit using weights [7, 3, 1] repeating mod 10.
    '<' evaluates to 0, '0'-'9' to 0-9, 'A'-'Z' to 10-35.
    """
    total = 0
    for idx, ch in enumerate(data_str):
        weight = WEIGHTS[idx % 3]
        if ch == "<":
            val = 0
        elif "0" <= ch <= "9":
            val = ord(ch) - ord("0")
        elif "A" <= ch <= "Z":
            val = ord(ch) - ord("A") + 10
        else:
            raise ValueError(f"Invalid ICAO MRZ character: '{ch}' in '{data_str}'")
        total += val * weight
    return total % 10


def is_valid_calendar_date(year: int, month: int, day: int) -> bool:
    """Checks if a given year, month, day represents a real calendar date."""
    if not (1 <= month <= 12):
        return False
    if not (1 <= day <= 31):
        return False
    _, max_days = calendar.monthrange(year, month)
    return day <= max_days


class TD3MRZParser:
    """
    Parser and validator for ICAO Doc 9303 Part 4 TD3 Indian Passport MRZs.
    2 lines x 44 characters.
    """

    def __init__(self, registry: Optional[PassportRulesRegistry] = None):
        self.registry = registry or default_registry

    def parse(
        self,
        line1: str,
        line2: str,
        viz_dob_year: Optional[int] = None,
        viz_expiry_year: Optional[int] = None,
        reference_date: Optional[date] = None,
    ) -> MRZParseResult:
        """
        Parses and validates 2 MRZ lines against C-1 through C-10 checks.
        """
        ref_date = reference_date or date.today()
        result = MRZParseResult()
        findings: List[Finding] = []
        fields: Dict[str, FieldObject] = {}
        check_digits: Dict[str, bool] = {}

        # Clean raw strings (strip trailing whitespace / newlines)
        l1 = (line1 or "").strip()
        l2 = (line2 or "").strip()

        # =====================================================================
        # C-1: Structure Check (Length, Charset, Doc Type 'P')
        # =====================================================================
        c1_severity = self.registry.get_effective_severity("C-1-mrz-structure")
        c1_pass = True
        c1_reasons = []

        if len(l1) != 44 or len(l2) != 44:
            c1_pass = False
            c1_reasons.append(f"Invalid line length (Line 1: {len(l1)}, Line 2: {len(l2)}; expected 44 each)")

        invalid_l1_chars = set(l1) - ICAO_CHARSET
        invalid_l2_chars = set(l2) - ICAO_CHARSET
        if invalid_l1_chars or invalid_l2_chars:
            c1_pass = False
            c1_reasons.append(f"Invalid characters present: L1 {sorted(invalid_l1_chars)}, L2 {sorted(invalid_l2_chars)}")

        if len(l1) > 0 and not l1.startswith("P"):
            c1_pass = False
            c1_reasons.append(f"Line 1 does not begin with 'P' (found: '{l1[0]}')")

        if c1_pass:
            result.valid_structure = True
            findings.append(
                Finding(
                    code="PP-MRZ-001",
                    check_id="C-1",
                    status=CheckStatus.PASS,
                    check_class=c1_severity,
                    message="MRZ structure conforms to ICAO 9303 TD3 (2x44, valid charset, prefix P).",
                )
            )
        else:
            result.valid_structure = False
            findings.append(
                Finding(
                    code="PP-MRZ-001",
                    check_id="C-1",
                    status=CheckStatus.FAIL,
                    check_class=c1_severity,
                    message="MRZ structural failure: " + "; ".join(c1_reasons),
                    evidence={"line1_len": len(l1), "line2_len": len(l2), "reasons": c1_reasons},
                )
            )
            # If structure fails critically (wrong length / completely corrupt), downstream checks cannot reliably index
            if len(l1) != 44 or len(l2) != 44:
                result.findings = findings
                result.overall_status = CheckStatus.FAIL
                result.recommended_action = RecommendedAction.RECAPTURE_REQUIRED
                return result

        # Extract fixed-width components (1-indexed mapping to 0-indexed slices):
        # Line 1:
        # 1-2: Document type (e.g. "P<")
        # 3-5: Issuing state ("IND")
        # 6-44: Name field
        doc_type = l1[0:2]
        issuing_country = l1[2:5]
        name_field = l1[5:44]

        # Line 2:
        # 1-9: Passport Number
        # 10: Passport Number Check Digit
        # 11-13: Nationality
        # 14-19: Date of Birth (YYMMDD)
        # 20: DOB Check Digit
        # 21: Sex (M, F, <)
        # 22-27: Expiry Date (YYMMDD)
        # 28: Expiry Check Digit
        # 29-42: Personal / Optional Data
        # 43: Personal Data Check Digit
        # 44: Composite Check Digit
        raw_passport_no = l2[0:9]
        passport_no_cd = l2[9]
        nationality = l2[10:13]
        raw_dob = l2[13:19]
        dob_cd = l2[19]
        raw_sex = l2[20]
        raw_expiry = l2[21:27]
        expiry_cd = l2[27]
        raw_personal_no = l2[28:42]
        personal_no_cd = l2[42]
        composite_cd = l2[43]

        result.document_type = doc_type
        result.issuing_country = issuing_country
        result.nationality = nationality
        clean_passport_no = raw_passport_no.replace("<", "")
        result.passport_number = clean_passport_no

        fields["passport_no"] = FieldObject(
            field_name="passport_no",
            raw={"mrz": raw_passport_no},
            normalized=clean_passport_no,
        )

        # =====================================================================
        # C-2: Issuing State & Nationality Check ('IND')
        # =====================================================================
        c2_severity = self.registry.get_effective_severity("C-2-state-nationality")
        if issuing_country == "IND" and nationality == "IND":
            findings.append(
                Finding(
                    code="PP-MRZ-002",
                    check_id="C-2",
                    status=CheckStatus.PASS,
                    check_class=c2_severity,
                    message="Issuing state and nationality both conform to 'IND'.",
                    evidence={"issuing_country": issuing_country, "nationality": nationality},
                )
            )
            fields["nationality"] = FieldObject(
                field_name="nationality",
                raw={"mrz": nationality},
                normalized="IND",
                status=CheckStatus.PASS,
            )
        else:
            findings.append(
                Finding(
                    code="PP-MRZ-002",
                    check_id="C-2",
                    status=CheckStatus.FAIL,
                    check_class=c2_severity,
                    message=f"Country/Nationality mismatch for Indian passport: Issuing='{issuing_country}', Nationality='{nationality}'.",
                    evidence={"issuing_country": issuing_country, "nationality": nationality},
                )
            )
            fields["nationality"] = FieldObject(
                field_name="nationality",
                raw={"mrz": nationality},
                normalized=nationality,
                status=CheckStatus.FAIL,
            )

        # =====================================================================
        # C-3: Passport Number 7-3-1 Checksum
        # =====================================================================
        c3_severity = self.registry.get_effective_severity("C-3-passport-number-checksum")
        try:
            expected_c3 = str(calculate_icao_check_digit(raw_passport_no))
            c3_pass = (passport_no_cd == expected_c3)
        except ValueError as e:
            c3_pass = False
            expected_c3 = f"ERR: {e}"

        check_digits["passport_no"] = c3_pass
        if c3_pass:
            findings.append(
                Finding(
                    code="PP-MRZ-003",
                    check_id="C-3",
                    status=CheckStatus.PASS,
                    check_class=c3_severity,
                    field="passport_no",
                    message="Passport number 7-3-1 check digit verified.",
                    evidence={"passport_no": raw_passport_no, "check_digit": passport_no_cd},
                )
            )
        else:
            findings.append(
                Finding(
                    code="PP-MRZ-003",
                    check_id="C-3",
                    status=CheckStatus.FAIL,
                    check_class=c3_severity,
                    field="passport_no",
                    message=f"Passport number 7-3-1 check digit mismatch: expected '{expected_c3}', found '{passport_no_cd}'.",
                    evidence={"passport_no": raw_passport_no, "expected": expected_c3, "found": passport_no_cd},
                )
            )
            fields["passport_no"].status = CheckStatus.FAIL

        # =====================================================================
        # C-4: Date of Birth Checksum
        # =====================================================================
        c4_severity = self.registry.get_effective_severity("C-4-dob-checksum")
        try:
            expected_c4 = str(calculate_icao_check_digit(raw_dob))
            c4_pass = (dob_cd == expected_c4)
        except ValueError as e:
            c4_pass = False
            expected_c4 = f"ERR: {e}"

        check_digits["dob"] = c4_pass
        if c4_pass:
            findings.append(
                Finding(
                    code="PP-MRZ-004",
                    check_id="C-4",
                    status=CheckStatus.PASS,
                    check_class=c4_severity,
                    field="dob",
                    message="Date of birth 7-3-1 check digit verified.",
                    evidence={"raw_dob": raw_dob, "check_digit": dob_cd},
                )
            )
        else:
            findings.append(
                Finding(
                    code="PP-MRZ-004",
                    check_id="C-4",
                    status=CheckStatus.FAIL,
                    check_class=c4_severity,
                    field="dob",
                    message=f"DOB check digit mismatch: expected '{expected_c4}', found '{dob_cd}'.",
                    evidence={"raw_dob": raw_dob, "expected": expected_c4, "found": dob_cd},
                )
            )

        # =====================================================================
        # C-5: Expiry Date Checksum
        # =====================================================================
        c5_severity = self.registry.get_effective_severity("C-5-expiry-checksum")
        try:
            expected_c5 = str(calculate_icao_check_digit(raw_expiry))
            c5_pass = (expiry_cd == expected_c5)
        except ValueError as e:
            c5_pass = False
            expected_c5 = f"ERR: {e}"

        check_digits["expiry"] = c5_pass
        if c5_pass:
            findings.append(
                Finding(
                    code="PP-MRZ-005",
                    check_id="C-5",
                    status=CheckStatus.PASS,
                    check_class=c5_severity,
                    field="expiry",
                    message="Expiry date 7-3-1 check digit verified.",
                    evidence={"raw_expiry": raw_expiry, "check_digit": expiry_cd},
                )
            )
        else:
            findings.append(
                Finding(
                    code="PP-MRZ-005",
                    check_id="C-5",
                    status=CheckStatus.FAIL,
                    check_class=c5_severity,
                    field="expiry",
                    message=f"Expiry check digit mismatch: expected '{expected_c5}', found '{expiry_cd}'.",
                    evidence={"raw_expiry": raw_expiry, "expected": expected_c5, "found": expiry_cd},
                )
            )

        # =====================================================================
        # C-6: Personal Number / Optional Field Checksum
        # =====================================================================
        c6_severity = self.registry.get_effective_severity("C-6-personal-number-blank")
        clean_personal_no = raw_personal_no.replace("<", "")
        result.personal_number = clean_personal_no
        c6_rule = self.registry.get_rule("C-6-personal-number-blank") or {}
        allow_zero_or_filler = c6_rule.get("allow_zero_or_filler", True)

        try:
            calculated_c6 = str(calculate_icao_check_digit(raw_personal_no))
            # If completely filler (<), check digit can be '<' or '0'
            if not clean_personal_no and allow_zero_or_filler and personal_no_cd in ("<", "0"):
                c6_pass = True
            else:
                c6_pass = (personal_no_cd == calculated_c6)
            expected_c6 = calculated_c6
        except ValueError as e:
            c6_pass = False
            expected_c6 = f"ERR: {e}"

        check_digits["personal_no"] = c6_pass
        if c6_pass:
            findings.append(
                Finding(
                    code="PP-MRZ-006",
                    check_id="C-6",
                    status=CheckStatus.PASS,
                    check_class=c6_severity,
                    field="personal_no",
                    message="Personal number check digit verified or compliant with blank policy.",
                    evidence={"raw_personal_no": raw_personal_no, "check_digit": personal_no_cd},
                )
            )
        else:
            findings.append(
                Finding(
                    code="PP-MRZ-006",
                    check_id="C-6",
                    status=CheckStatus.FAIL,
                    check_class=c6_severity,
                    field="personal_no",
                    message=f"Personal number check digit mismatch: expected '{expected_c6}', found '{personal_no_cd}'.",
                    evidence={"raw_personal_no": raw_personal_no, "expected": expected_c6, "found": personal_no_cd},
                )
            )

        # =====================================================================
        # C-7: Composite Checksum (Position 44 over 1-10, 14-20, 22-43)
        # =====================================================================
        c7_severity = self.registry.get_effective_severity("C-7-composite-checksum")
        # 1-10: l2[0:10] (passport_no + check_digit)
        # 14-20: l2[13:20] (dob + check_digit)
        # 22-43: l2[21:43] (expiry + cd + personal_no + cd)
        composite_data = l2[0:10] + l2[13:20] + l2[21:43]
        try:
            expected_c7 = str(calculate_icao_check_digit(composite_data))
            c7_pass = (composite_cd == expected_c7)
        except ValueError as e:
            c7_pass = False
            expected_c7 = f"ERR: {e}"

        check_digits["composite"] = c7_pass
        if c7_pass:
            findings.append(
                Finding(
                    code="PP-MRZ-007",
                    check_id="C-7",
                    status=CheckStatus.PASS,
                    check_class=c7_severity,
                    message="Master composite check digit verified.",
                    evidence={"composite_cd": composite_cd},
                )
            )
        else:
            findings.append(
                Finding(
                    code="PP-MRZ-007",
                    check_id="C-7",
                    status=CheckStatus.FAIL,
                    check_class=c7_severity,
                    message=f"Master composite check digit mismatch: expected '{expected_c7}', found '{composite_cd}'.",
                    evidence={"expected": expected_c7, "found": composite_cd},
                )
            )

        # =====================================================================
        # C-8: Name Field Parsing (Surname << Given Names)
        # =====================================================================
        c8_severity = self.registry.get_effective_severity("C-8-name-field-parse")
        surname, given_names, c8_anomalies = self._parse_name(name_field)
        result.surname = surname
        result.given_names = given_names

        fields["surname"] = FieldObject(
            field_name="surname",
            raw={"mrz": name_field},
            normalized=surname,
            status=CheckStatus.PASS if surname or self.registry.get_rule("C-8-name-field-parse", {}).get("allow_single_name") else CheckStatus.UNKNOWN,
        )
        fields["given_names"] = FieldObject(
            field_name="given_names",
            raw={"mrz": name_field},
            normalized=given_names,
            status=CheckStatus.PASS,
        )

        if not c8_anomalies:
            findings.append(
                Finding(
                    code="PP-MRZ-008",
                    check_id="C-8",
                    status=CheckStatus.PASS,
                    check_class=c8_severity,
                    message=f"Name successfully parsed (Surname: '{surname}', Given: '{given_names}').",
                    evidence={"surname": surname, "given_names": given_names},
                )
            )
        else:
            findings.append(
                Finding(
                    code="PP-MRZ-008",
                    check_id="C-8",
                    status=CheckStatus.FAIL,
                    check_class=c8_severity,
                    message="Name structure anomaly detected: " + "; ".join(c8_anomalies),
                    evidence={"anomalies": c8_anomalies, "surname": surname, "given_names": given_names},
                )
            )

        # =====================================================================
        # C-9: Sex Field Validation ('M', 'F', '<')
        # =====================================================================
        c9_severity = self.registry.get_effective_severity("C-9-sex-field")
        c9_rule = self.registry.get_rule("C-9-sex-field") or {}
        allowed_sex = c9_rule.get("allowed_values", ["M", "F", "<"])

        if raw_sex in allowed_sex:
            result.sex = "" if raw_sex == "<" else raw_sex
            fields["sex"] = FieldObject(
                field_name="sex",
                raw={"mrz": raw_sex},
                normalized=result.sex,
                status=CheckStatus.PASS,
            )
            findings.append(
                Finding(
                    code="PP-MRZ-009",
                    check_id="C-9",
                    status=CheckStatus.PASS,
                    check_class=c9_severity,
                    field="sex",
                    message=f"Sex field value '{raw_sex}' conforms to specification.",
                )
            )
        else:
            result.sex = raw_sex
            fields["sex"] = FieldObject(
                field_name="sex",
                raw={"mrz": raw_sex},
                normalized=raw_sex,
                status=CheckStatus.FAIL,
            )
            findings.append(
                Finding(
                    code="PP-MRZ-009",
                    check_id="C-9",
                    status=CheckStatus.FAIL,
                    check_class=c9_severity,
                    field="sex",
                    message=f"Invalid sex field value: '{raw_sex}'. Expected one of {allowed_sex}.",
                    evidence={"found": raw_sex, "allowed": allowed_sex},
                )
            )

        # =====================================================================
        # C-10: Date Validity & Century Logic (DOB & Expiry)
        # =====================================================================
        c10_severity = self.registry.get_effective_severity("C-10-date-validity-century")
        dob_res, dob_err = self._resolve_date(
            raw_dob,
            is_dob=True,
            viz_year=viz_dob_year,
            ref_date=ref_date,
        )
        expiry_res, exp_err = self._resolve_date(
            raw_expiry,
            is_dob=False,
            viz_year=viz_expiry_year,
            ref_date=ref_date,
        )

        result.dob = dob_res
        result.expiry_date = expiry_res

        fields["dob"] = FieldObject(
            field_name="dob",
            raw={"mrz": raw_dob},
            normalized=dob_res,
            status=CheckStatus.PASS if dob_res and not dob_err else (CheckStatus.UNKNOWN if "ambiguous" in dob_err.lower() else CheckStatus.FAIL),
        )
        fields["expiry"] = FieldObject(
            field_name="expiry",
            raw={"mrz": raw_expiry},
            normalized=expiry_res,
            status=CheckStatus.PASS if expiry_res and not exp_err else CheckStatus.FAIL,
        )

        date_issues = []
        if dob_err:
            date_issues.append(f"DOB: {dob_err}")
        if exp_err:
            date_issues.append(f"Expiry: {exp_err}")

        # Logical ordering check: DOB < Expiry (if both resolved)
        if dob_res and expiry_res:
            try:
                dob_dt = datetime.strptime(dob_res, "%Y-%m-%d").date()
                exp_dt = datetime.strptime(expiry_res, "%Y-%m-%d").date()
                if dob_dt >= exp_dt:
                    date_issues.append(f"Ordering violation: DOB ({dob_res}) is not strictly before Expiry ({expiry_res})")
            except ValueError:
                pass

        if not date_issues:
            findings.append(
                Finding(
                    code="PP-MRZ-010",
                    check_id="C-10",
                    status=CheckStatus.PASS,
                    check_class=c10_severity,
                    message=f"Dates validated and century resolved (DOB: {dob_res}, Expiry: {expiry_res}).",
                    evidence={"dob": dob_res, "expiry": expiry_res},
                )
            )
        else:
            status = CheckStatus.UNKNOWN if any("ambiguous" in s.lower() for s in date_issues) else CheckStatus.FAIL
            findings.append(
                Finding(
                    code="PP-MRZ-010",
                    check_id="C-10",
                    status=status,
                    check_class=c10_severity,
                    message="Date validity / ordering anomaly: " + "; ".join(date_issues),
                    evidence={"issues": date_issues},
                )
            )

        # Aggregate Result
        result.findings = findings
        result.fields = fields
        result.check_digits = check_digits

        has_t1_fail = any(f.status == CheckStatus.FAIL and f.check_class == CheckClass.T1 for f in findings)
        has_unknown = any(f.status == CheckStatus.UNKNOWN for f in findings)

        if has_t1_fail:
            result.overall_status = CheckStatus.FAIL
            result.recommended_action = RecommendedAction.MANUAL_REVIEW
        elif has_unknown:
            result.overall_status = CheckStatus.UNKNOWN
            result.recommended_action = RecommendedAction.RECAPTURE_REQUIRED
        else:
            result.overall_status = CheckStatus.PASS
            result.recommended_action = RecommendedAction.CONTINUE

        return result

    def _parse_name(self, name_field: str) -> Tuple[str, str, List[str]]:
        """
        Parses MRZ line 1 name field according to Section 5.1 of plan:
        1. Strip trailing '<' filler.
        2. Split at first '<<' into surname and given names.
        3. Convert inner single '<' to space.
        4. Detect anomalies (e.g., secondary '<<' in given names).
        """
        anomalies = []
        stripped = name_field.rstrip("<")

        if not stripped:
            return "", "", ["Empty name field"]

        parts = stripped.split("<<", 1)
        surname_raw = parts[0]
        given_raw = parts[1] if len(parts) > 1 else ""

        # Check for secondary '<<' inside given names (empty component)
        if "<<" in given_raw:
            anomalies.append("Secondary '<<' delimiter found within given names component")
            # Clean it up by replacing consecutive '<'
            given_raw = re.sub(r"<+", "<", given_raw)

        surname = surname_raw.replace("<", " ").strip()
        given_names = given_raw.replace("<", " ").strip()

        return surname, given_names, anomalies

    def _resolve_date(
        self,
        yymmdd: str,
        is_dob: bool,
        viz_year: Optional[int],
        ref_date: date,
    ) -> Tuple[Optional[str], Optional[str]]:
        """
        Validates calendar date and resolves century (1900 vs 2000 vs 2100).
        Returns (ISO YYYY-MM-DD or None, error_message or None).
        """
        if len(yymmdd) != 6 or not yymmdd.isdigit():
            return None, f"Invalid date string format: '{yymmdd}' (must be 6 digits)"

        yy = int(yymmdd[0:2])
        mm = int(yymmdd[2:4])
        dd = int(yymmdd[4:6])

        if not (1 <= mm <= 12):
            return None, f"Month out of bounds: {mm} in '{yymmdd}'"

        # Check day bounds across centuries
        # Note: Feb 29 leap year depends on the century (2000 is leap, 1900 is not)
        candidate_centuries = [1900, 2000] if is_dob else [2000, 2100, 1900]

        valid_candidates = []
        for c in candidate_centuries:
            full_year = c + yy
            if is_valid_calendar_date(full_year, mm, dd):
                valid_candidates.append(full_year)

        if not valid_candidates:
            return None, f"Impossible calendar date: day {dd} invalid for month {mm} in '{yymmdd}'"

        # If 4-digit VIZ year is provided, compare directly
        if viz_year is not None:
            if viz_year % 100 == yy:
                if is_valid_calendar_date(viz_year, mm, dd):
                    return f"{viz_year:04d}-{mm:02d}-{dd:02d}", None
                else:
                    return None, f"VIZ year {viz_year} yields invalid calendar date for {mm:02d}-{dd:02d}"
            else:
                return None, f"VIZ year ({viz_year}) does not match MRZ YY ({yy})"

        # Century inference heuristic when VIZ year is absent
        filtered_candidates = []
        for y in valid_candidates:
            c_date = date(y, mm, dd)
            if is_dob:
                # DOB cannot be in the future
                if c_date <= ref_date:
                    age = (ref_date - c_date).days // 365
                    # Plausible human age: 0 to 115
                    if 0 <= age <= 115:
                        filtered_candidates.append(y)
            else:
                # Expiry date: typically within [-30 years, +15 years] from reference
                diff_years = (c_date - ref_date).days / 365.25
                if -30 <= diff_years <= 20:
                    filtered_candidates.append(y)

        if len(filtered_candidates) == 1:
            chosen_year = filtered_candidates[0]
            return f"{chosen_year:04d}-{mm:02d}-{dd:02d}", None
        elif len(filtered_candidates) > 1:
            # Ambiguous date candidates
            candidate_strs = [f"{y:04d}-{mm:02d}-{dd:02d}" for y in filtered_candidates]
            return None, f"Ambiguous century candidates without VIZ confirmation: {candidate_strs}"
        else:
            return None, f"No plausible calendar date candidate for '{yymmdd}' relative to {ref_date.isoformat()}"
