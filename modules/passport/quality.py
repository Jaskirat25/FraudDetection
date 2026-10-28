"""
modules/passport/quality.py - Image Quality Gate & Capture Integrity (Checks A-1, A-2).
Implements Section 5 (A) of passport_module_plan_v2.md:
Quality gate runs first. Failures lead directly to RECAPTURE_REQUIRED with actionable hints,
NOT false fraud risk.
"""

from dataclasses import dataclass, field as dc_field
from typing import Optional, Dict, List, Any
import numpy as np
import cv2

from modules.passport.types import (
    CheckStatus,
    RecommendedAction,
    CheckClass,
    Finding,
)


@dataclass
class QualityGateResult:
    passed: bool = True
    status: CheckStatus = CheckStatus.PASS
    recommended_action: RecommendedAction = RecommendedAction.CONTINUE
    hints: List[str] = dc_field(default_factory=list)
    metrics: Dict[str, Any] = dc_field(default_factory=dict)
    finding: Optional[Finding] = None


def assess_passport_image_quality(
    image: np.ndarray,
    blur_threshold: float = 80.0,
    glare_threshold_ratio: float = 0.08,
    min_width: int = 600,
    min_height: int = 400,
) -> QualityGateResult:
    """
    Evaluates image quality: blur (Laplacian variance), glare (specular saturation),
    and minimum resolution required for reliable ICAO TD3 MRZ and VIZ OCR.
    """
    if image is None or not isinstance(image, np.ndarray) or image.size == 0:
        return QualityGateResult(
            passed=False,
            status=CheckStatus.FAIL,
            recommended_action=RecommendedAction.RECAPTURE_REQUIRED,
            hints=["Image is missing, corrupt, or unreadable."],
            metrics={"valid_image": False},
            finding=Finding(
                code="PP-GATE-002",
                check_id="A-2",
                status=CheckStatus.FAIL,
                check_class=CheckClass.INFO,
                message="Quality Gate failed: Image data is empty or invalid.",
                evidence={"valid_image": False},
            ),
        )

    h, w = image.shape[:2]
    hints = []
    issues = []

    # 1. Resolution Check
    if w < min_width or h < min_height:
        issues.append(f"Resolution too low ({w}x{h}; minimum required is {min_width}x{min_height})")
        hints.append("Increase camera resolution or capture closer to the passport (minimum 600x400).")

    # Convert to grayscale for blur and luminosity
    if len(image.shape) == 3:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    else:
        gray = image

    # 2. Blur Check (Laplacian Variance)
    blur_score = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    if blur_score < blur_threshold:
        issues.append(f"Image is blurred (Laplacian variance {blur_score:.1f} < threshold {blur_threshold})")
        hints.append("Hold the camera steady or increase lighting to reduce motion blur.")

    # 3. Glare Check (Specular Highlight Pixel Ratio)
    glare_pixels = int(np.sum(gray >= 250))
    total_pixels = gray.size
    glare_ratio = float(glare_pixels / total_pixels) if total_pixels > 0 else 0.0

    if glare_ratio > glare_threshold_ratio:
        issues.append(f"Excessive specular glare ({glare_ratio * 100:.1f}% > threshold {glare_threshold_ratio * 100:.1f}%)")
        hints.append("Reduce direct lighting glare or angle the camera slightly to avoid reflections.")

    metrics = {
        "width": w,
        "height": h,
        "blur_score": blur_score,
        "blur_threshold": blur_threshold,
        "glare_ratio": glare_ratio,
        "glare_threshold_ratio": glare_threshold_ratio,
    }

    if not issues:
        return QualityGateResult(
            passed=True,
            status=CheckStatus.PASS,
            recommended_action=RecommendedAction.CONTINUE,
            hints=[],
            metrics=metrics,
            finding=Finding(
                code="PP-GATE-002",
                check_id="A-2",
                status=CheckStatus.PASS,
                check_class=CheckClass.INFO,
                message="Quality Gate passed (sharpness, lighting, and resolution adequate for screening).",
                evidence=metrics,
            ),
        )
    else:
        return QualityGateResult(
            passed=False,
            status=CheckStatus.FAIL,
            recommended_action=RecommendedAction.RECAPTURE_REQUIRED,
            hints=hints,
            metrics=metrics,
            finding=Finding(
                code="PP-GATE-002",
                check_id="A-2",
                status=CheckStatus.FAIL,
                check_class=CheckClass.INFO,
                message="Quality Gate failed: " + "; ".join(issues),
                evidence={"issues": issues, "hints": hints, **metrics},
            ),
        )
