"""
modules/validate/rules.py - Deterministic rule engine and QR-Print cross-checking (L2).
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
    "40": "MAHARASHTRA",
    "56": "KARNATAKA",
    "60": "TAMIL NADU",
    "70": "WEST BENGAL",
}


def validate_rules(fields: Dict[str, Tuple[str, float]], qr: Optional[QRResult] = None) -> ModuleResult:
    """
    Executes all deterministic rules against extracted fields and QR payload.
    """
    result = ModuleResult(module_name="rule_validation")
    
    # 1. Aadhaar Number Validation
    raw_num = fields.get("aadhaar_no", ("", 0.0))[0]
    digits_num = re.sub(r"\D", "", raw_num)
    
    if len(digits_num) == 12:
        if digits_num[0] in ('0', '1'):
            result.flags.append(f"Invalid Aadhaar prefix: Cannot start with {digits_num[0]}")
            result.scores["aadhaar_no"] = 1.0
            result.hard_fail = True
        elif not validate_verhoeff(digits_num):
            result.flags.append(f"Verhoeff Checksum Failed on Aadhaar Number ({raw_num})")
            result.scores["aadhaar_no"] = 1.0
            result.hard_fail = True
        else:
            result.scores["aadhaar_no"] = 0.0
    elif raw_num:
        result.flags.append(f"Invalid Aadhaar length: Expected 12 digits, found {len(digits_num)}")
        result.scores["aadhaar_no"] = 0.8

    # 2. QR Cryptographic & Cross-check Validation (L1)
    if qr and qr.present:
        if not qr.signature_valid:
            result.flags.append("QR Signature Invalid: Cryptographic verification failed against UIDAI certificate")
            result.scores["qr_signature"] = 1.0
            result.hard_fail = True
        else:
            # Cross-check printed fields vs QR payload
            qr_dob = qr.payload.get("dob", "")
            ocr_dob = fields.get("dob", ("", 0.0))[0]
            if qr_dob and ocr_dob and qr_dob.strip() != ocr_dob.strip():
                result.flags.append(f"QR vs Printed DOB mismatch: Card reads '{ocr_dob}' but signed QR contains '{qr_dob}'")
                result.scores["dob_mismatch"] = 1.0
                result.hard_fail = True

            qr_name = qr.payload.get("name", "").lower()
            ocr_name = fields.get("name_en", ("", 0.0))[0].lower()
            if qr_name and ocr_name and qr_name.strip() != ocr_name.strip():
                result.flags.append(f"QR vs Printed Name mismatch: Card reads '{ocr_name}' but signed QR contains '{qr_name}'")
                result.scores["name_mismatch"] = 1.0
                result.hard_fail = True
    else:
        result.flags.append("No Secure QR Code detected; relying strictly on heuristic and ML layers")
        result.scores["qr_present"] = 0.5

    return result
