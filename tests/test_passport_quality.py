"""
tests/test_passport_quality.py - Unit tests for Quality Gate (Checks A-1, A-2).
"""

import sys
from pathlib import Path
import numpy as np
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from modules.passport.quality import assess_passport_image_quality
from modules.passport.types import CheckStatus, RecommendedAction


def test_quality_gate_clean():
    # Create high-contrast, sharp synthetic image (800x600)
    img = np.zeros((600, 800, 3), dtype=np.uint8)
    # Add checkerboard pattern to give high Laplacian variance (sharp edges)
    img[::20, :, :] = 200
    img[:, ::20, :] = 200

    res = assess_passport_image_quality(img)
    assert res.passed is True
    assert res.status == CheckStatus.PASS
    assert res.recommended_action == RecommendedAction.CONTINUE
    assert len(res.hints) == 0


def test_quality_gate_blur():
    # Uniform smooth image (very low Laplacian variance)
    img_blur = np.full((600, 800, 3), 128, dtype=np.uint8)
    res = assess_passport_image_quality(img_blur)
    assert res.passed is False
    assert res.status == CheckStatus.FAIL
    assert res.recommended_action == RecommendedAction.RECAPTURE_REQUIRED
    assert any("blur" in h.lower() for h in res.hints)


def test_quality_gate_glare():
    # 800x600 image with a large saturated white hotspot (> 10% of pixels = 255)
    img = np.full((600, 800, 3), 100, dtype=np.uint8)
    img[100:400, 100:400, :] = 255  # 300x300 = 90,000 pixels / 480,000 = 18.75% glare

    res = assess_passport_image_quality(img, glare_threshold_ratio=0.08)
    assert res.passed is False
    assert res.status == CheckStatus.FAIL
    assert res.recommended_action == RecommendedAction.RECAPTURE_REQUIRED
    assert any("glare" in h.lower() for h in res.hints)


def test_quality_gate_low_resolution():
    # 400x300 image (below 600x400 minimum)
    img_small = np.zeros((300, 400, 3), dtype=np.uint8)
    res = assess_passport_image_quality(img_small)
    assert res.passed is False
    assert any("resolution" in h.lower() for h in res.hints)


def test_quality_gate_invalid_input():
    res_none = assess_passport_image_quality(None)
    assert res_none.passed is False
    assert res_none.status == CheckStatus.FAIL
    assert res_none.recommended_action == RecommendedAction.RECAPTURE_REQUIRED
