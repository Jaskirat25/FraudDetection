"""
modules/validate/rules.py - Calibrated Deterministic Rule Engine & Two-Tier Validation (L2).
"""

import re
from typing import Dict, Tuple, Optional, Any
from core.types import ModuleResult, QRResult
from .verhoeff import validate_verhoeff

# Standard Postal Circle Prefix mappings (first 2 digits -> State)
PIN_PREFIX_STATE = {
    "11": "DELHI",
    "12": "HARYANA",
    "13": "HARYANA",
    "14": "PUNJAB",
    "15": "PUNJAB",
    "16": "CHANDIGARH",
    "17": "HIMACHAL PRADESH",
    "18": "JAMMU AND KASHMIR",
    "19": "JAMMU AND KASHMIR",
    "20": "UTTAR PRADESH",
    "30": "RAJASTHAN",
    "38": "GUJARAT",
    "40": "MAHARASHTRA",
    "41": "MAHARASHTRA",
    "50": "TELANGANA",
    "56": "KARNATAKA",
    "60": "TAMIL NADU",
    "68": "KERALA",
    "70": "WEST BENGAL",
}


def validate_rules(fields: Dict[str, Tuple[str, float]], qr: Optional[QRResult] = None) -> ModuleResult:
    """
    Executes calibrated deterministic rules against extracted fields and QR payload.
    Tier 1 (Hard Fail): Verhoeff failure, QR-to-print field mismatch.
    Tier 2 (Points): Unverified signature, missing QR, PIN-to-state discrepancy.
    """
    result = ModuleResult(module_name="rule_validation")
    
    # 1. Aadhaar Number Validation (Verhoeff Checksum)
    raw_num = fields.get("aadhaar_no", ("", 0.0))[0]
    digits_num = re.sub(r"\D", "", raw_num)
    
    if len(digits_num) == 12:
        if digits_num[0] in ('0', '1'):
            result.flags.append(f"Invalid Aadhaar prefix: Real numbers never start with {digits_num[0]}")
            result.scores["aadhaar_no"] = 1.0
            result.hard_fail = True
        elif not validate_verhoeff(digits_num):
            result.flags.append(f"Verhoeff Checksum FAILED: The 12-digit number ({raw_num}) is mathematically invalid!")
            result.scores["aadhaar_no"] = 1.0
            result.hard_fail = True
        else:
            result.scores["aadhaar_no"] = 0.0
    elif len(digits_num) >= 4:
        # Masked Aadhaar
        result.scores["aadhaar_no"] = 0.0

    # 2. QR Cryptographic & Cross-check Validation (L1)
    qr_present = qr is not None and qr.present
    is_secure = qr is not None and qr.is_secure_qr
    sig_valid = qr is not None and qr.signature_valid
    
    result.evidence["qr_present"] = qr_present
    result.evidence["is_secure_qr"] = is_secure
    result.evidence["qr_signature_valid"] = sig_valid

    if qr_present and qr.payload:
        # Check Signature Status
        if is_secure:
            if sig_valid:
                result.scores["qr_signature"] = 0.0
                result.flags.append("QR Signature Verified: Authenticated against UIDAI certificate.")
            else:
                # Conclusive Forgery: Secure QR signature failed verification
                result.scores["qr_signature"] = 1.0
                result.flags.append("FORGERY ALERT: UIDAI Secure QR RSA-2048 digital signature verification FAILED!")
                result.hard_fail = True
        else:
            # Legacy XML QR without digital signature -> Cannot be cryptographically verified
            result.scores["qr_signature"] = 0.30
            result.flags.append("Legacy XML QR detected: Unsigned format lacking UIDAI RSA-2048 cryptographic signature.")

        # Cross-check printed fields vs QR payload (Conclusive Tamper Check)
        qr_dob = qr.payload.get("dob", "")
        ocr_dob = fields.get("dob", ("", 0.0))[0]
        if qr_dob and ocr_dob:
            if qr_dob.strip() != ocr_dob.strip() and qr_dob[-4:] != ocr_dob[-4:]:
                result.flags.append(f"CONCLUSIVE TAMPER: Printed DOB shows '{ocr_dob}', but signed QR contains '{qr_dob}'.")
                result.scores["dob_mismatch"] = 1.0
                result.hard_fail = True
            else:
                result.scores["dob_mismatch"] = 0.0

        # Cross-check last 4 digits
        qr_last4 = qr.payload.get("last4", "")
        if qr_last4 and len(digits_num) >= 4:
            card_last4 = digits_num[-4:]
            if qr_last4 != card_last4:
                result.flags.append(f"CONCLUSIVE TAMPER: Card ends in '{card_last4}', but signed QR belongs to ID ending in '{qr_last4}'.")
                result.scores["aadhaar_no_mismatch"] = 1.0
                result.hard_fail = True
            else:
                result.scores["aadhaar_no_mismatch"] = 0.0

        # Cross-check PIN prefix to State if available
        qr_pin = qr.payload.get("pincode", "")
        qr_state = qr.payload.get("state", "").upper()
        if qr_pin and len(qr_pin) >= 2 and qr_state:
            prefix = qr_pin[:2]
            expected_state = PIN_PREFIX_STATE.get(prefix)
            if expected_state and expected_state not in qr_state:
                result.flags.append(f"Geographic Anomaly: PIN prefix {prefix} belongs to {expected_state}, but state reads {qr_state}.")
                result.scores["pin_state_mismatch"] = 0.15

    else:
        result.flags.append("Cryptographic Anchor Missing: No readable QR code detected on card.")
        result.scores["qr_missing"] = 0.50

    return result
