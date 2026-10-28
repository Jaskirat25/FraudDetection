"""
tests/test_passport_pipeline.py - Unit & Integration tests for Passport Vision & End-to-End Pipeline.
"""

import sys
from pathlib import Path
from datetime import date
import numpy as np
import cv2
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from modules.passport.register import (
    rectify_passport_perspective,
    locate_mrz_strip_morphological,
    register_passport_page,
    PASSPORT_CANONICAL_WIDTH,
    PASSPORT_CANONICAL_HEIGHT,
)
from modules.passport.pipeline import screen_passport
from modules.passport.fusion import PassportDecision, PassportPriority
from modules.passport.privacy import PassportReuseIndex
from tests.test_passport_mrz import build_sample_mrz


@pytest.fixture
def fresh_reuse_index():
    idx = PassportReuseIndex(secret_key=b"test-secret-salt-pipeline")
    idx.clear()
    return idx


def create_synthetic_passport_image():
    """Generates a sharp 1000x700 synthetic image with passport page layout."""
    img = np.full((PASSPORT_CANONICAL_HEIGHT, PASSPORT_CANONICAL_WIDTH, 3), 240, dtype=np.uint8)
    
    # Header & decorative elements
    cv2.rectangle(img, (20, 20), (980, 80), (220, 220, 220), -1)
    cv2.putText(img, "REPUBLIC OF INDIA", (320, 55), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 2)
    
    # Photo region
    cv2.rectangle(img, (40, 140), (280, 460), (180, 180, 180), -1)
    cv2.putText(img, "PHOTO", (120, 300), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (50, 50, 50), 2)
    
    # MRZ bottom strip (high contrast dark monospace characters)
    mrz_l1 = "P<INDSHARMA<<RAHUL<<<<<<<<<<<<<<<<<<<<<<<<<<"
    mrz_l2 = "L1234567<3IND9805149M2805139<<<<<<<<<<<<<<<2"
    cv2.putText(img, mrz_l1, (35, 570), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 0, 0), 2)
    cv2.putText(img, mrz_l2, (35, 630), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 0, 0), 2)
    
    return img


def test_passport_perspective_rectification():
    # Synthetic canvas (1200x900) containing a quadrilateral passport page
    canvas = np.zeros((900, 1200, 3), dtype=np.uint8)
    
    # Create white polygon (tilted passport booklet)
    pts = np.array([[150, 100], [1050, 120], [1020, 820], [120, 790]], dtype=np.int32)
    cv2.fillPoly(canvas, [pts], (230, 230, 230))
    cv2.putText(canvas, "PASSPORT", (300, 300), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 2)

    rectified, quality = rectify_passport_perspective(canvas)
    assert rectified.shape == (PASSPORT_CANONICAL_HEIGHT, PASSPORT_CANONICAL_WIDTH, 3)
    assert quality >= 0.80


def test_locate_mrz_strip_morphological():
    img = create_synthetic_passport_image()
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    x, y, w, h = locate_mrz_strip_morphological(gray)
    
    # MRZ strip must be located in the lower portion of the page
    assert y >= 450
    assert w >= 600
    assert h >= 40


def test_register_passport_page():
    img = create_synthetic_passport_image()
    rectified, crops, quality = register_passport_page(img)
    
    assert rectified.shape == (PASSPORT_CANONICAL_HEIGHT, PASSPORT_CANONICAL_WIDTH, 3)
    assert "photo" in crops
    assert "mrz" in crops
    assert "passport_no" in crops
    assert crops["photo"].image.shape[0] > 0


def test_screen_passport_clean_end_to_end(fresh_reuse_index):
    ref_date = date(2026, 10, 28)
    img = create_synthetic_passport_image()

    l1, l2 = build_sample_mrz(
        surname="SHARMA",
        given_names="RAHUL",
        passport_no="L1234567<",
        dob="980514",
        expiry="280513",
    )
    viz_fields = {
        "passport_no": "L1234567",
        "surname": "SHARMA",
        "given_names": "RAHUL",
        "dob": "14/05/1998",
        "doi": "15/05/2018",
        "doe": "13/05/2028",
        "sex": "M",
        "nationality": "INDIAN",
    }

    report = screen_passport(
        image_or_path=img,
        reference_date=ref_date,
        reuse_index=fresh_reuse_index,
        provided_mrz=(l1, l2),
        provided_viz=viz_fields,
    )

    assert report.decision == PassportDecision.LOW_RISK_SCREEN
    assert report.priority is None
    assert report.risk_index == 0.0
    assert report.coverage >= 0.80
    assert "EXPIRED" not in report.document_status


def test_screen_passport_quality_gate_fail_fast():
    # Blurry image
    img_blur = np.full((600, 800, 3), 128, dtype=np.uint8)
    report = screen_passport(image_or_path=img_blur)

    assert report.decision == PassportDecision.RECAPTURE_REQUIRED
    assert report.priority is None
    assert len(report.findings) >= 1
    assert any("blur" in f.get("message", "").lower() for f in report.findings)


def test_screen_passport_tamper_detection(fresh_reuse_index):
    ref_date = date(2026, 10, 28)
    img = create_synthetic_passport_image()

    l1, l2 = build_sample_mrz(passport_no="L1234567<")
    # Forged VIZ with different passport number
    viz_forged = {
        "passport_no": "Z9999999",
        "surname": "SHARMA",
        "given_names": "RAHUL",
        "dob": "14/05/1998",
        "nationality": "INDIAN",
    }

    report = screen_passport(
        image_or_path=img,
        reference_date=ref_date,
        reuse_index=fresh_reuse_index,
        provided_mrz=(l1, l2),
        provided_viz=viz_forged,
    )

    assert report.decision == PassportDecision.MANUAL_REVIEW
    assert report.priority == PassportPriority.HIGH
    assert report.risk_index >= 80.0


def test_screen_passport_with_c11_repair(fresh_reuse_index):
    """
    Simulates OCR misreading 'L1234560' as 'L123456O'.
    Checksum fails, but VIZ corroborates 'L1234560'.
    The pipeline safely repairs it and produces LOW_RISK_SCREEN.
    """
    ref_date = date(2026, 10, 28)
    img = create_synthetic_passport_image()

    real_l1, real_l2 = build_sample_mrz(passport_no="L1234560<")
    # Corrupt passport number in line 2: 'O' instead of '0'
    corrupt_l2 = real_l2[:7] + "O" + real_l2[8:]

    viz_fields = {
        "passport_no": "L1234560",
        "surname": "SURNAME",
        "given_names": "GIVEN NAME",
        "dob": "14/05/1998",
        "doi": "15/05/2018",
        "doe": "13/05/2028",
        "sex": "M",
        "nationality": "INDIAN",
    }

    report = screen_passport(
        image_or_path=img,
        reference_date=ref_date,
        reuse_index=fresh_reuse_index,
        provided_mrz=(real_l1, corrupt_l2),
        provided_viz=viz_fields,
    )

    # Check that repair finding PP-MRZ-011 was emitted and check succeeded
    repair_findings = [f for f in report.findings if f.get("code") == "PP-MRZ-011"]
    assert len(repair_findings) >= 1
    assert report.decision == PassportDecision.LOW_RISK_SCREEN
