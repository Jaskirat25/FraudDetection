"""
modules/validate/rules.py - Calibrated Deterministic Rule Engine & Two-Tier Validation (L2).
"""

import re
from typing import Dict, Tuple, Optional, Any
from core.types import ModuleResult, QRResult
from difflib import SequenceMatcher
from .verhoeff import validate_verhoeff, repair_aadhaar_verhoeff

# Comprehensive Postal Circle Prefix mappings (first 2 digits -> State)
PIN_PREFIX_STATE = {
    "11": "DELHI",
    "12": "HARYANA", "13": "HARYANA",
    "14": "PUNJAB", "15": "PUNJAB",
    "16": "CHANDIGARH",
    "17": "HIMACHAL PRADESH",
    "18": "JAMMU AND KASHMIR", "19": "JAMMU AND KASHMIR",
    "20": "UTTAR PRADESH", "21": "UTTAR PRADESH", "22": "UTTAR PRADESH", "23": "UTTAR PRADESH",
    "24": "UTTAR PRADESH", "25": "UTTAR PRADESH", "26": "UTTAR PRADESH", "27": "UTTAR PRADESH",
    "28": "UTTAR PRADESH",
    "30": "RAJASTHAN", "31": "RAJASTHAN", "32": "RAJASTHAN", "33": "RAJASTHAN", "34": "RAJASTHAN",
    "36": "GUJARAT", "37": "GUJARAT", "38": "GUJARAT", "39": "GUJARAT",
    "40": "MAHARASHTRA", "41": "MAHARASHTRA", "42": "MAHARASHTRA", "43": "MAHARASHTRA", "44": "MAHARASHTRA",
    "45": "MADHYA PRADESH", "46": "MADHYA PRADESH", "47": "MADHYA PRADESH", "48": "MADHYA PRADESH",
    "49": "CHHATTISGARH",
    "50": "TELANGANA", "51": "ANDHRA PRADESH", "52": "ANDHRA PRADESH", "53": "ANDHRA PRADESH",
    "56": "KARNATAKA", "57": "KARNATAKA", "58": "KARNATAKA", "59": "KARNATAKA",
    "60": "TAMIL NADU", "61": "TAMIL NADU", "62": "TAMIL NADU", "63": "TAMIL NADU", "64": "TAMIL NADU",
    "67": "KERALA", "68": "KERALA", "69": "KERALA",
    "70": "WEST BENGAL", "71": "WEST BENGAL", "72": "WEST BENGAL", "73": "WEST BENGAL", "74": "WEST BENGAL",
    "75": "ODISHA", "76": "ODISHA", "77": "ODISHA",
    "78": "ASSAM",
    "79": "NORTH EAST",
    "80": "BIHAR", "81": "BIHAR", "82": "BIHAR", "83": "JHARKHAND", "84": "BIHAR", "85": "BIHAR",
}


def validate_rules(fields: Dict[str, Tuple[str, float]], qr: Optional[QRResult] = None) -> ModuleResult:
    """
    Executes calibrated deterministic rules with Verhoeff-assisted OCR error repair
    and confidence-aware cross-checking against the signed QR payload.
    """
    result = ModuleResult(module_name="rule_validation")
    
    # Extract QR metadata upfront
    qr_present = qr is not None and qr.present
    is_secure = qr is not None and qr.is_secure_qr
    sig_valid = qr is not None and qr.signature_valid
    qr_last4 = qr.payload.get("last4", "") if (qr and qr.payload) else None

    result.evidence["qr_present"] = qr_present
    result.evidence["is_secure_qr"] = is_secure
    result.evidence["qr_signature_valid"] = sig_valid

    # 1. Aadhaar Number Validation (Verhoeff Checksum with Mathematical OCR Repair)
    raw_num, num_conf = fields.get("aadhaar_no", ("", 0.0))
    digits_num = re.sub(r"\D", "", raw_num)

    if digits_num:
        is_valid, repaired_num, explanation = repair_aadhaar_verhoeff(digits_num, qr_last4=qr_last4)
        result.evidence["repaired_aadhaar_no"] = repaired_num
        result.evidence["verhoeff_valid"] = is_valid

        if is_valid:
            result.scores["aadhaar_no"] = 0.0
            result.flags.append(explanation)
        else:
            # Check if this failure is trustworthy or simply low-confidence capture noise
            if num_conf >= 0.75 or digits_num[0] in ('0', '1'):
                # Confident failure: Number is legitimately fabricated or starts with 0/1
                result.flags.append(f"Verhoeff Checksum FAILED: {explanation}")
                result.scores["aadhaar_no"] = 1.0
                result.hard_fail = True
            else:
                # Low confidence capture noise: Avoid false hard reject; flag for retake/review
                result.flags.append(f"Aadhaar Number Unresolvable: OCR confidence low ({num_conf*100:.1f}%). {explanation}")
                result.scores["aadhaar_no"] = 0.40

    # 2. QR Cryptographic & Cross-check Validation (L1 & L7)
    if qr_present and qr.payload:
        sig_status = getattr(qr, "signature_status", "VALID" if sig_valid else "INVALID_SIGNATURE")
        cert_name = getattr(qr, "cert_name", None)

        if is_secure:
            if sig_status == "VALID":
                result.scores["qr_signature"] = 0.0
                cert_desc = f" ({cert_name})" if cert_name else ""
                result.flags.append(f"QR Signature Verified: Authenticated against pinned UIDAI certificate{cert_desc}.")
            elif sig_status == "UNKNOWN_KEY":
                result.scores["qr_signature"] = 0.40
                result.flags.append("Unknown Signing Key: QR issue timestamp or key identifier falls outside known UIDAI CA epochs. Flagged for manual review.")
            else:
                # Conclusive Forgery: Secure QR signature failed verification against active pinned certificate
                result.scores["qr_signature"] = 1.0
                result.flags.append("FORGERY ALERT: UIDAI Secure QR RSA-2048 digital signature verification FAILED!")
                result.hard_fail = True
        else:
            # Legacy XML QR without digital signature -> Cannot be cryptographically verified
            result.scores["qr_signature"] = 0.30
            result.flags.append("Legacy XML QR detected: Unsigned format lacking UIDAI RSA-2048 cryptographic signature.")

        # 3. Temporal Plausibility & Freshness Checks (L8)
        temporal_valid = getattr(qr, "temporal_valid", True)
        temporal_issues = getattr(qr, "temporal_issues", [])
        if not temporal_valid:
            for issue in temporal_issues:
                result.flags.append(f"Temporal Anomaly: {issue}")
                if "FUTURE TIMESTAMP" in issue or "CHRONOLOGICAL INVERSION" in issue:
                    result.scores["temporal_anomaly"] = 1.0
                    result.hard_fail = True
                else:
                    result.scores["temporal_anomaly"] = max(result.scores.get("temporal_anomaly", 0.0), 0.40)
        elif qr.payload.get("issue_timestamp"):
            result.scores["temporal_anomaly"] = 0.0
            result.flags.append(f"Temporal Integrity Verified: Issue timestamp ({qr.payload.get('issue_timestamp')}) is chronologically plausible.")


        # Cross-check printed DOB vs QR payload (Confidence-Aware)
        qr_dob = qr.payload.get("dob", "").replace("-", "/").strip()
        ocr_dob_raw, ocr_dob_conf = fields.get("dob", ("", 0.0))
        ocr_dob = ocr_dob_raw.replace("-", "/").strip()

        if qr_dob and ocr_dob:
            if qr_dob == ocr_dob:
                result.scores["dob_mismatch"] = 0.0
            else:
                qr_year = qr_dob[-4:] if len(qr_dob) >= 4 else ""
                ocr_year = ocr_dob[-4:] if len(ocr_dob) >= 4 else ""
                year_diff = sum(1 for a, b in zip(qr_year, ocr_year) if a != b)

                if qr_year != ocr_year and year_diff > 1 and ocr_dob_conf >= 0.70:
                    # Conclusive tamper on birth year
                    result.flags.append(f"CONCLUSIVE TAMPER: Printed birth year shows '{ocr_year}', but signed QR contains '{qr_year}'.")
                    result.scores["dob_mismatch"] = 1.0
                    result.hard_fail = True
                elif qr_dob != ocr_dob and ocr_dob_conf >= 0.85:
                    result.flags.append(f"CONCLUSIVE TAMPER: Printed DOB shows '{ocr_dob}', but signed QR contains '{qr_dob}'.")
                    result.scores["dob_mismatch"] = 1.0
                    result.hard_fail = True
                else:
                    result.flags.append(f"DOB Optical Ambiguity: Printed reads '{ocr_dob}' (conf {ocr_dob_conf*100:.1f}%), signed QR contains '{qr_dob}'.")
                    result.scores["dob_mismatch"] = 0.15

        # Cross-check printed Name vs QR payload (Levenshtein Fuzzy Matching)
        qr_name = qr.payload.get("name", "").strip().lower()
        ocr_name_raw, ocr_name_conf = fields.get("name_en", ("", 0.0))
        ocr_name = ocr_name_raw.strip().lower()

        if qr_name and ocr_name:
            ratio = SequenceMatcher(None, qr_name, ocr_name).ratio()
            if ratio >= 0.70 or ocr_name in qr_name or qr_name in ocr_name:
                result.scores["name_mismatch"] = 0.0
            elif ocr_name_conf >= 0.75:
                result.flags.append(f"CONCLUSIVE TAMPER: Printed name '{ocr_name_raw}' does not match signed QR name '{qr.payload.get('name')}'.")
                result.scores["name_mismatch"] = 1.0
                result.hard_fail = True
            else:
                result.flags.append(f"Name Optical Ambiguity: Printed reads '{ocr_name_raw}' (conf {ocr_name_conf*100:.1f}%), signed QR contains '{qr.payload.get('name')}'.")
                result.scores["name_mismatch"] = 0.20

        # 4. Back-Side Address Proof Cross-Check (L6)
        printed_address_raw, addr_conf = fields.get("address", ("", 0.0))
        printed_pin_raw, pin_conf = fields.get("pincode", ("", 0.0))
        printed_addr_upper = printed_address_raw.upper()

        qr_pin = qr.payload.get("pincode", "").strip()
        qr_state = qr.payload.get("state", "").upper().strip()
        qr_district = qr.payload.get("district", "").upper().strip()

        # (a) PIN Code Cross-Check
        if printed_pin_raw and qr_pin:
            if printed_pin_raw == qr_pin:
                result.scores["pin_mismatch"] = 0.0
                result.flags.append(f"PIN Code Verified: Printed PIN ({printed_pin_raw}) matches signed QR PIN ({qr_pin}).")
            else:
                pin_diff = sum(1 for a, b in zip(printed_pin_raw, qr_pin) if a != b)
                if pin_conf >= 0.75 and pin_diff > 1:
                    result.flags.append(f"CONCLUSIVE ADDRESS TAMPER: Printed PIN '{printed_pin_raw}' contradicts signed QR PIN '{qr_pin}'!")
                    result.scores["pin_mismatch"] = 1.0
                    result.hard_fail = True
                else:
                    result.flags.append(f"PIN Optical Ambiguity: Printed reads '{printed_pin_raw}' (conf {pin_conf*100:.1f}%), signed QR contains '{qr_pin}'.")
                    result.scores["pin_mismatch"] = 0.25

        # (b) State Cross-Check
        if qr_state and printed_addr_upper:
            if qr_state in printed_addr_upper:
                result.scores["state_mismatch"] = 0.0
                result.flags.append(f"State Verified: Printed address confirms state ({qr_state.title()}).")
            elif addr_conf >= 0.70:
                conflicting_states = [s for s in set(PIN_PREFIX_STATE.values()) if s != qr_state and s in printed_addr_upper and len(s) > 4]
                if conflicting_states:
                    result.flags.append(f"State Discrepancy: Signed QR specifies state '{qr_state.title()}', but printed address indicates '{conflicting_states[0].title()}'.")
                    result.scores["state_mismatch"] = 0.50
                else:
                    result.scores["state_mismatch"] = 0.15

        # (c) District Cross-Check
        if qr_district and printed_addr_upper:
            if qr_district in printed_addr_upper:
                result.scores["district_mismatch"] = 0.0
                result.flags.append(f"District Verified: Printed address confirms district ({qr_district.title()}).")

        # (d) PIN Prefix to State Geographic Consistency
        effective_pin = printed_pin_raw if printed_pin_raw else qr_pin
        effective_state = qr_state
        if effective_pin and len(effective_pin) >= 2 and effective_state:
            prefix = effective_pin[:2]
            expected_state = PIN_PREFIX_STATE.get(prefix)
            if expected_state and expected_state not in effective_state:
                result.flags.append(f"Geographic Anomaly: Postal circle prefix '{prefix}' belongs to {expected_state.title()}, but state is registered as {effective_state.title()}.")
                result.scores["pin_state_mismatch"] = 0.35
            elif expected_state:
                result.scores["pin_state_mismatch"] = 0.0

    else:
        result.flags.append("Cryptographic Anchor Missing: No readable QR code detected on card.")
        result.scores["qr_missing"] = 0.50

    return result
