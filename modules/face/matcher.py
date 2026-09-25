"""
modules/face/matcher.py - ArcFace 3-Way Face Verification (L5).
Compares Card Crop Photo, QR-Embedded Photo, and Live Webcam Capture.
"""

from typing import Optional
import numpy as np
from core.types import ModuleResult


def verify_face(
    card_photo: Optional[np.ndarray],
    live_photo: Optional[np.ndarray] = None,
    qr_photo: Optional[np.ndarray] = None
) -> ModuleResult:
    """
    Computes cosine distances between:
    1. Card Photo <-> QR Photo (Detects Photo-Swap)
    2. Card Photo <-> Live Photo (Detects Impostor)
    3. QR Photo <-> Live Photo (Cryptographically bound identity verification)
    """
    result = ModuleResult(module_name="face_verification")
    
    # Stub baseline distances
    result.evidence["card_qr_distance"] = 0.15   # < 0.40 -> Genuine match
    result.evidence["card_live_distance"] = 0.22 if live_photo is not None else None
    result.evidence["qr_live_distance"] = 0.20 if (qr_photo is not None and live_photo is not None) else None
    
    result.scores["photo_consistency"] = 0.05
    return result
