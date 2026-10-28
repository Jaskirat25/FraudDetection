"""
tests/test_passport_fusion.py - Unit tests for Evidence Fusion & Decision Engine.
"""

import sys
from pathlib import Path
from datetime import date
import pytest
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from modules.passport.mrz import TD3MRZParser
from modules.passport.viz import VIZLogicValidator
from modules.passport.cross_val import CrossValidator
from modules.passport.quality import assess_passport_image_quality
from modules.passport.privacy import PassportReuseIndex
from modules.passport.fusion import (
    PassportDecisionEngine,
    PassportDecision,
    PassportPriority,
)
from modules.passport.types import RecommendedAction
from tests.test_passport_mrz import build_sample_mrz


@pytest.fixture
def parser():
    return TD3MRZParser()


@pytest.fixture
def viz_validator():
    return VIZLogicValidator()


@pytest.fixture
def cross_validator():
    return CrossValidator()


@pytest.fixture
def decision_engine():
    return PassportDecisionEngine()


def test_fusion_clean_pass_low_risk_screen(parser, viz_validator, cross_validator, decision_engine):
    ref_date = date(2026, 10, 28)

    # 1. Clean synthetic image
    img = np.zeros((600, 800, 3), dtype=np.uint8)
    img[::20, :, :] = 200
    img[:, ::20, :] = 200
    q_res = assess_passport_image_quality(img)

    # 2. Clean MRZ
    l1, l2 = build_sample_mrz(
        surname="SHARMA",
        given_names="RAHUL",
        passport_no="L1234567<",
        dob="980514",
        expiry="280513",
    )
    mrz_res = parser.parse(l1, l2, viz_dob_year=1998, viz_expiry_year=2028, reference_date=ref_date)

    # 3. Clean VIZ
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
    viz_res = viz_validator.validate(viz_fields, reference_date=ref_date)

    # 4. Clean Cross-Val
    x_res = cross_validator.cross_validate(viz_res, mrz_res)

    # 5. Fusion
    report = decision_engine.fuse(
        quality_res=q_res,
        mrz_res=mrz_res,
        viz_res=viz_res,
        xval_res=x_res,
    )

    assert report.decision == PassportDecision.LOW_RISK_SCREEN
    assert report.priority is None
    assert report.recommended_action == RecommendedAction.CONTINUE
    assert report.risk_index == 0.0
    assert report.coverage >= 0.80
    assert report.extraction_confidence == 1.0


def test_fusion_quality_gate_triggers_recapture(parser, viz_validator, cross_validator, decision_engine):
    # Blurry image
    img_blur = np.full((600, 800, 3), 128, dtype=np.uint8)
    q_res = assess_passport_image_quality(img_blur)

    report = decision_engine.fuse(quality_res=q_res)

    assert report.decision == PassportDecision.RECAPTURE_REQUIRED
    assert report.priority is None
    assert report.recommended_action == RecommendedAction.RECAPTURE_REQUIRED


def test_fusion_t1_contradiction_triggers_high_priority_review(parser, viz_validator, cross_validator, decision_engine):
    ref_date = date(2026, 10, 28)

    l1, l2 = build_sample_mrz(passport_no="L1234567<")
    mrz_res = parser.parse(l1, l2, reference_date=ref_date)

    # Contradicting passport number in VIZ
    viz_fields = {
        "passport_no": "Z9999999",
        "dob": "14/05/1998",
        "nationality": "INDIAN",
    }
    viz_res = viz_validator.validate(viz_fields, reference_date=ref_date)
    x_res = cross_validator.cross_validate(viz_res, mrz_res)

    report = decision_engine.fuse(
        mrz_res=mrz_res,
        viz_res=viz_res,
        xval_res=x_res,
    )

    assert report.decision == PassportDecision.MANUAL_REVIEW
    assert report.priority == PassportPriority.HIGH
    assert report.recommended_action == RecommendedAction.MANUAL_REVIEW
    assert report.risk_index >= 80.0


def test_fusion_expired_status_preserved(parser, viz_validator, cross_validator, decision_engine):
    ref_date = date(2026, 10, 28)

    l1, l2 = build_sample_mrz(dob="980514", expiry="220513")  # Expired in 2022
    mrz_res = parser.parse(l1, l2, reference_date=ref_date)

    viz_fields = {
        "dob": "14/05/1998",
        "doi": "14/05/2012",
        "doe": "13/05/2022",
        "nationality": "INDIAN",
    }
    viz_res = viz_validator.validate(viz_fields, reference_date=ref_date)

    report = decision_engine.fuse(
        mrz_res=mrz_res,
        viz_res=viz_res,
    )

    assert "EXPIRED" in report.document_status
