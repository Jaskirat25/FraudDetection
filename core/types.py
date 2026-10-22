"""
core/types.py - Standard data contracts and interfaces for Aadhaar Authenticity Screening System.
All modules MUST conform to these dataclasses and function signatures.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Dict, List, Tuple, Any
import numpy as np


class Verdict(str, Enum):
    VERIFIED = "VERIFIED"   # Cryptographically anchored & biometrically authenticated
    REVIEW = "REVIEW"       # Unverifiable (legacy/no QR, cert unknown, or requires manual check)
    RETAKE = "RETAKE"       # Capture degraded (unreadable QR, blur, face landmarks not found)
    REJECT = "REJECT"       # Hard fraud detected (forged signature, photo swap, text mismatch)


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class ForgeryFamily(str, Enum):
    GENUINE = "GENUINE"
    F1_PHOTO_SWAP = "F1_PHOTO_SWAP"
    F2_TEXT_OVERWRITE = "F2_TEXT_OVERWRITE"
    F3_COPY_MOVE = "F3_COPY_MOVE"
    F4_FULL_RERENDER = "F4_FULL_RERENDER"


@dataclass
class FieldCrop:
    """Cropped image corresponding to a registered card field."""
    name: str                           # e.g., "dob", "name_en", "name_hi", "photo", "aadhaar_no", "address", "qr"
    image: np.ndarray                   # BGR / Grayscale image crop
    bbox: Tuple[int, int, int, int]     # (x, y, width, height) in canonical reference coordinates


@dataclass
class QRResult:
    """Output from Secure QR decoding and verification module (L1)."""
    present: bool = False
    signature_valid: bool = False
    is_secure_qr: bool = False          # True if 2019+ Secure QR with RSA signature
    payload: Dict[str, str] = field(default_factory=dict)  # Demographics (name, dob, gender, address, last4, etc.)
    photo: Optional[np.ndarray] = None  # Extracted compressed face photo (JPEG2000)
    raw_text: Optional[str] = None
    flags: List[str] = field(default_factory=list)


@dataclass
class ModuleResult:
    """Standard result structure returned by individual pipeline modules."""
    module_name: str
    scores: Dict[str, float] = field(default_factory=dict)  # field_name -> 0.0 (clean) to 1.0 (highly suspicious)
    flags: List[str] = field(default_factory=list)          # Human-readable risk explanations / findings
    evidence: Dict[str, Any] = field(default_factory=dict)  # Supplementary diagnostic data (heatmaps, metrics)
    hard_fail: bool = False                                 # If True, bypasses tier-2 scoring and flags HIGH risk immediately


@dataclass
class RiskReport:
    """Final aggregated risk verdict and explainable report (L1-L5)."""
    overall_risk: RiskLevel
    verdict: Verdict = Verdict.REVIEW                      # VERIFIED, REVIEW, RETAKE, REJECT
    verdict_reason: str = ""                               # Plain-language verdict summary
    risk_score: float = 0.0                                # 0 to 100 aggregate points
    hard_reject: bool = False                              # True if triggered by conclusive cryptographic/checksum rule
    tier1_violations: List[str] = field(default_factory=list) # Conclusive reasons (e.g., "Invalid RSA signature")
    tier2_contributions: List[Dict[str, Any]] = field(default_factory=list) # Weighted point breakdown
    per_field_analysis: Dict[str, Dict[str, Any]] = field(default_factory=dict) # Value, QR match, Tamper score per field
    flags: List[str] = field(default_factory=list)          # All plain-language findings
    heatmap_overlay: Optional[np.ndarray] = None           # Visual heatmap representation
    metadata: Dict[str, Any] = field(default_factory=dict) # Processing time, timestamps, masked id
