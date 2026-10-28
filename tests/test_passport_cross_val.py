"""
tests/test_passport_cross_val.py - Unit tests for VIZ <-> MRZ Cross-Validation (E-1..E-7) & Dependency Suppression.
"""

import sys
from pathlib import Path
from datetime import date
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from modules.passport.mrz import TD3MRZParser
from modules.passport.viz import VIZLogicValidator
from modules.passport.cross_val import CrossValidator, transliterate_viz_text
from modules.passport.types import CheckStatus, CheckClass
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


def test_transliteration():
    # Diacritics and accents
    assert transliterate_viz_text("Renée") == "RENEE"
    # Apostrophes removed
    assert transliterate_viz_text("D'SOUZA") == "DSOUZA"
    # Hyphens converted to space
    assert transliterate_viz_text("SINGH-ROY") == "SINGH ROY"


def test_xval_full_match(parser, viz_validator, cross_validator):
    ref_date = date(2026, 10, 28)
    l1, l2 = build_sample_mrz(
        surname="SHARMA",
        given_names="RAHUL",
        passport_no="L1234567<",
        dob="980514",
        sex="M",
        expiry="280513",
    )
    mrz_res = parser.parse(l1, l2, viz_dob_year=1998, viz_expiry_year=2028, reference_date=ref_date)

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

    x_res = cross_validator.cross_validate(viz_res, mrz_res)
    assert x_res.valid_crosscheck is True
    assert x_res.overall_status == CheckStatus.PASS

    # Verify individual checks passed
    e_checks = ["E-1", "E-2", "E-3", "E-4", "E-5", "E-6", "E-7"]
    for ec in e_checks:
        f = next(finding for finding in x_res.findings if finding.check_id == ec)
        assert f.status == CheckStatus.PASS


def test_xval_given_names_truncation(parser, viz_validator, cross_validator):
    """
    Very long given name that gets truncated at the 39-character boundary in MRZ line 1.
    """
    long_given_viz = "VENKATESHWARAN RAMAKRISHNAN"
    mrz_truncated = "VENKATESHWARAN<R"
    l1, l2 = build_sample_mrz(
        surname="SUBRAMANIAN",
        given_names=mrz_truncated,
    )
    mrz_res = parser.parse(l1, l2)

    viz_fields = {
        "surname": "SUBRAMANIAN",
        "given_names": long_given_viz,
    }
    viz_res = viz_validator.validate(viz_fields)

    x_res = cross_validator.cross_validate(viz_res, mrz_res)
    e3 = next(f for f in x_res.findings if f.check_id == "E-3")
    assert e3.status == CheckStatus.PASS
    assert "Truncated match" in e3.evidence.get("detail", "")


def test_xval_passport_number_mismatch(parser, viz_validator, cross_validator):
    l1, l2 = build_sample_mrz(passport_no="L1234567<")
    mrz_res = parser.parse(l1, l2)

    # VIZ has different passport number
    viz_fields = {
        "passport_no": "Z9876543",
    }
    viz_res = viz_validator.validate(viz_fields)

    x_res = cross_validator.cross_validate(viz_res, mrz_res)
    e1 = next(f for f in x_res.findings if f.check_id == "E-1")
    assert e1.status == CheckStatus.FAIL
    assert e1.check_class == CheckClass.T1
    assert x_res.overall_status == CheckStatus.FAIL


def test_confidence_gating_unreliable_input(parser, viz_validator, cross_validator):
    """
    If an input was UNKNOWN (not reliable), a mismatch should be marked UNKNOWN,
    NEVER a false T1 fraud escalation.
    """
    l1, l2 = build_sample_mrz()
    mrz_res = parser.parse(l1, l2)

    viz_fields = {
        "passport_no": "L1234567",
        "surname": "WRONGNAME",
    }
    viz_res = viz_validator.validate(viz_fields)
    # Simulate low OCR confidence / UNKNOWN status on VIZ surname
    viz_res.fields["surname"].status = CheckStatus.UNKNOWN

    x_res = cross_validator.cross_validate(viz_res, mrz_res)
    e2 = next(f for f in x_res.findings if f.check_id == "E-2")
    # Must NOT be FAIL (T1); must be UNKNOWN
    assert e2.status == CheckStatus.UNKNOWN


def test_dependency_suppression_corrupt_mrz(parser, viz_validator, cross_validator):
    """
    If MRZ line length or structure is invalid, downstream checks should be suppressed
    and emit a single finding rather than cascading failures.
    """
    l1, l2 = build_sample_mrz()
    # Make MRZ invalid length
    mrz_res = parser.parse(l1[:35], l2)
    assert mrz_res.valid_structure is False

    viz_fields = {
        "passport_no": "L1234567",
        "surname": "SHARMA",
    }
    viz_res = viz_validator.validate(viz_fields)

    x_res = cross_validator.cross_validate(viz_res, mrz_res)
    # All E-checks suppressed, single gate finding emitted
    assert len(x_res.findings) == 1
    assert x_res.findings[0].code == "PP-GATE-001"
    assert x_res.findings[0].status == CheckStatus.UNKNOWN
