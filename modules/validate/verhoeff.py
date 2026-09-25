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
