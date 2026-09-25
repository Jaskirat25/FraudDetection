"""
core/config.py - Centralized configuration, paths, and bounding boxes.
"""

import os
from pathlib import Path

# Base Paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
TEMPLATES_DIR = DATA_DIR / "templates"
CERTS_DIR = DATA_DIR / "certs"
SYNTHETIC_DIR = DATA_DIR / "synthetic"
FORGED_DIR = DATA_DIR / "forged"

# Canonical Card Dimensions in standard reference coordinate space (width x height)
CANONICAL_WIDTH = 1000
CANONICAL_HEIGHT = 630

# Canonical Field Bounding Boxes (x, y, w, h) based on standard Aadhaar card layout
CANONICAL_FIELDS = {
    "header_logo": (40, 20, 100, 70),
    "header_text": (160, 25, 700, 60),
    "photo": (50, 120, 200, 250),
    "name_hi": (280, 120, 420, 45),
    "name_en": (280, 175, 420, 45),
    "dob": (280, 230, 420, 40),
    "gender": (280, 280, 420, 40),
    "aadhaar_no": (280, 430, 440, 60),
    "qr_code": (730, 120, 230, 230),
    "emblem": (850, 25, 100, 80),
}

# Risk Scoring Weights (Tier 2 Additive Points)
RISK_WEIGHTS = {
    "unreadable_mandatory_field": 25.0,
    "tamper_photo_high": 30.0,
    "tamper_dob_or_num_high": 25.0,
    "tamper_general_high": 15.0,
    "face_mismatch_live": 30.0,
    "pin_state_mismatch": 15.0,
    "hindi_english_divergence": 20.0,
    "poor_registration": 10.0,
    "qr_missing": 10.0,
}

# Risk Score Bands
SCORE_BANDS = {
    "LOW_MAX": 29.0,      # 0 to 29 -> LOW
    "MEDIUM_MAX": 59.0,   # 30 to 59 -> MEDIUM
                          # 60+ -> HIGH
}
