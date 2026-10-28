"""
modules/validate/verhoeff.py - Verhoeff Checksum Algorithm Implementation.
Used by UIDAI for the 12th digit of Aadhaar numbers.
Aadhaar numbers must satisfy the Verhoeff checksum and must never begin with '0' or '1'.
"""

# Multiplication table (d)
_d = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
    [1, 2, 3, 4, 0, 6, 7, 8, 9, 5],
    [2, 3, 4, 0, 1, 7, 8, 9, 5, 6],
    [3, 4, 0, 1, 2, 8, 9, 5, 6, 7],
    [4, 0, 1, 2, 3, 9, 5, 6, 7, 8],
    [5, 9, 8, 7, 6, 0, 4, 3, 2, 1],
    [6, 5, 9, 8, 7, 1, 0, 4, 3, 2],
    [7, 6, 5, 9, 8, 2, 1, 0, 4, 3],
    [8, 7, 6, 5, 9, 3, 2, 1, 0, 4],
    [9, 8, 7, 6, 5, 4, 3, 2, 1, 0]
]

# Permutation table (p)
_p = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
    [1, 5, 7, 6, 2, 8, 3, 0, 9, 4],
    [5, 8, 0, 3, 7, 9, 6, 1, 4, 2],
    [8, 9, 1, 6, 0, 4, 3, 5, 2, 7],
    [9, 4, 5, 3, 1, 2, 6, 8, 7, 0],
    [4, 2, 8, 6, 5, 7, 3, 9, 0, 1],
    [2, 7, 9, 3, 8, 0, 6, 4, 1, 5],
    [7, 0, 4, 6, 9, 1, 3, 2, 5, 8]
]

# Inverse table (inv)
_inv = [0, 4, 3, 2, 1, 5, 6, 7, 8, 9]


def validate_verhoeff(number_str: str) -> bool:
    """
    Validates whether a numeric string satisfies the Verhoeff checksum.
    Returns True if valid, False otherwise.
    """
    cleaned = "".join(filter(str.isdigit, number_str))
    if not cleaned:
        return False
    
    c = 0
    reversed_digits = [int(x) for x in reversed(cleaned)]
    
    for i, digit in enumerate(reversed_digits):
        c = _d[c][_p[i % 8][digit]]
        
    return c == 0


def generate_verhoeff(number_str: str) -> str:
    """
    Generates the Verhoeff check digit for a numeric string.
    """
    cleaned = "".join(filter(str.isdigit, number_str))
    c = 0
    reversed_digits = [int(x) for x in reversed(cleaned)]
    
    for i, digit in enumerate(reversed_digits):
        c = _d[c][_p[(i + 1) % 8][digit]]
        
    return str(_inv[c])


# Weighted OCR glyph confusion pairs (lower weight = more frequent natural OCR optical error)
_OCR_CONFUSION_WEIGHTS = {
    ('5', '6'): 1.0, ('6', '5'): 1.0,
    ('3', '8'): 1.0, ('8', '3'): 1.0,
    ('0', '8'): 1.2, ('8', '0'): 1.2,
    ('1', '7'): 1.0, ('7', '1'): 1.0,
    ('2', '7'): 1.4, ('7', '2'): 1.4,
    ('4', '9'): 1.4, ('9', '4'): 1.4,
    ('0', '6'): 1.5, ('6', '0'): 1.5,
    ('1', '4'): 1.5, ('4', '1'): 1.5,
    ('8', '9'): 1.4, ('9', '8'): 1.4,
    ('3', '9'): 1.4, ('9', '3'): 1.4,
}


def repair_aadhaar_verhoeff(
    number_str: str,
    qr_last4: str = None
) -> tuple:
    """
    Validates and attempts mathematical repair of an OCR-extracted Aadhaar number
    using the Verhoeff D5 group constraint and cryptographically signed QR anchor.

    Returns:
        (is_valid: bool, formatted_number: Optional[str], explanation: str)
    """
    cleaned = "".join(filter(str.isdigit, number_str))
    
    # Handle masked Aadhaar (e.g. XXXX XXXX 1234)
    if len(cleaned) < 12 and len(cleaned) >= 4:
        if qr_last4 and not cleaned.endswith(qr_last4):
            return False, cleaned, f"Masked card ending ({cleaned[-4:]}) contradicts signed QR ({qr_last4})."
        return True, f"XXXX XXXX {cleaned[-4:]}", "Masked Aadhaar format: Verhoeff check bypassed on masked digits."

    if len(cleaned) != 12:
        return False, cleaned, f"Invalid length: Expected 12 digits, found {len(cleaned)}."

    # Check 1: Aadhaar numbers can never begin with '0' or '1'
    if cleaned[0] in ('0', '1'):
        return False, cleaned, f"Invalid prefix: Real Aadhaar numbers never begin with '{cleaned[0]}'."

    # Check 2: Last 4 digits cross-check with signed QR payload
    last4_differs = False
    if qr_last4 and len(qr_last4) == 4:
        if cleaned[-4:] != qr_last4:
            # Check if last 4 differs by a simple single OCR glyph confusion
            char_diffs = sum(1 for a, b in zip(cleaned[-4:], qr_last4) if a != b)
            if char_diffs == 1:
                last4_differs = True
            else:
                return False, cleaned, f"Conclusive mismatch: Card ends in '{cleaned[-4:]}', but signed QR ends in '{qr_last4}'."

    # Check 3: If already satisfies Verhoeff and last 4 matches
    if validate_verhoeff(cleaned) and not last4_differs:
        formatted = f"{cleaned[0:4]} {cleaned[4:8]} {cleaned[8:12]}"
        return True, formatted, "Verhoeff Checksum VALID: Mathematical D5 group constraint satisfied."

    # Check 4: Attempt mathematical repair using Verhoeff and QR anchor
    working_digits = cleaned[:8] + (qr_last4 if (qr_last4 and len(qr_last4) == 4) else cleaned[8:])
    if working_digits != cleaned and validate_verhoeff(working_digits):
        formatted = f"{working_digits[0:4]} {working_digits[4:8]} {working_digits[8:12]}"
        return True, formatted, f"Repaired OCR reading in last 4 digits using cryptographically signed QR anchor ('{cleaned[-4:]}' -> '{qr_last4}')."

    # Search single-digit substitutions across the first 8 digits
    candidates = []
    for pos in range(8):
        orig_char = working_digits[pos]
        for rep in "0123456789":
            if rep == orig_char:
                continue
            if pos == 0 and rep in ('0', '1'):
                continue
            test_num = working_digits[:pos] + rep + working_digits[pos + 1:]
            if validate_verhoeff(test_num):
                cost = _OCR_CONFUSION_WEIGHTS.get((orig_char, rep), 2.5)
                candidates.append((cost, pos, orig_char, rep, test_num))

    # Search adjacent digit transpositions across the first 8 digits (e.g. 2684 -> 2864)
    for pos in range(7):
        if working_digits[pos] != working_digits[pos + 1]:
            transposed = working_digits[:pos] + working_digits[pos + 1] + working_digits[pos] + working_digits[pos + 2:]
            if validate_verhoeff(transposed):
                candidates.append((1.3, pos, working_digits[pos:pos + 2], working_digits[pos + 1] + working_digits[pos], transposed))

    if candidates:
        candidates.sort(key=lambda x: x[0])
        best = candidates[0]
        if best[0] <= 2.0:
            repaired_digits = best[4]
            formatted = f"{repaired_digits[0:4]} {repaired_digits[4:8]} {repaired_digits[8:12]}"
            return True, formatted, f"Mathematically repaired OCR glyph confusion at digit {best[1] + 1} ('{best[2]}' -> '{best[3]}') via Verhoeff D5 group constraint."

    return False, cleaned, "Verhoeff Checksum FAILED: The 12-digit number is mathematically invalid and could not be resolved to any plausible Aadhaar number."
