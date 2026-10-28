"""
tests/test_passport_viz.py - Unit tests for VIZ Document-Logic Rules (Checks D-2..D-7, D-10).
"""

import sys
from pathlib import Path
from datetime import date
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from modules.passport.viz import VIZLogicValidator, parse_viz_date
from modules.passport.types import CheckStatus, CheckClass


@pytest.fixture
def validator():
    return VIZLogicValidator()


def test_viz_date_format_valid():
    dt, err = parse_viz_date("14/05/1998")
    assert err is None
    assert dt == date(1998, 5, 14)

    # Leap day on leap year
    dt_lp, err_lp = parse_viz_date("29/02/2000")
    assert err_lp is None
    assert dt_lp == date(2000, 2, 29)


def test_viz_date_format_invalid():
    # Impossible month
    _, err_m = parse_viz_date("14/13/1998")
    assert err_m is not None

    # Leap day on non-leap year
    _, err_lp = parse_viz_date("29/02/2023")
    assert err_lp is not None


def test_viz_logic_all_valid(validator):
    ref_date = date(2026, 10, 28)
    fields = {
        "passport_no": "L1234567",
        "surname": "SHARMA",
        "given_names": "RAHUL",
        "dob": "14/05/1998",
        "doi": "15/05/2018",
        "doe": "14/05/2028",
        "sex": "M",
        "nationality": "INDIAN",
    }
    result = validator.validate(fields, reference_date=ref_date)
    assert result.valid_logic is True
    assert result.overall_status == CheckStatus.PASS
    assert "EXPIRED" not in result.document_status


def test_dob_plausibility(validator):
    ref_date = date(2026, 10, 28)

    # Future DOB
    fields_future = {
        "dob": "14/05/2027",
        "doi": "15/05/2018",
        "doe": "14/05/2028",
        "nationality": "INDIAN",
    }
    res_f = validator.validate(fields_future, reference_date=ref_date)
    d3 = next(f for f in res_f.findings if f.check_id == "D-3")
    assert d3.status == CheckStatus.FAIL
    assert d3.check_class == CheckClass.T1

    # Implausible age (>115)
    fields_old = {
        "dob": "14/05/1850",
        "doi": "15/05/2018",
        "doe": "14/05/2028",
        "nationality": "INDIAN",
    }
    res_old = validator.validate(fields_old, reference_date=ref_date)
    d3_old = next(f for f in res_old.findings if f.check_id == "D-3")
    assert d3_old.status == CheckStatus.FAIL


def test_date_ordering(validator):
    ref_date = date(2026, 10, 28)

    # DOI before DOB
    fields_bad_order = {
        "dob": "14/05/1998",
        "doi": "14/05/1990",  # Issued before birth!
        "doe": "14/05/2028",
        "nationality": "INDIAN",
    }
    res = validator.validate(fields_bad_order, reference_date=ref_date)
    d4 = next(f for f in res.findings if f.check_id == "D-4")
    assert d4.status == CheckStatus.FAIL
    assert d4.check_class == CheckClass.T1


def test_issue_date_not_in_future(validator):
    ref_date = date(2026, 10, 28)
    fields_future_doi = {
        "dob": "14/05/1998",
        "doi": "01/01/2027",  # In the future!
        "doe": "01/01/2037",
        "nationality": "INDIAN",
    }
    res = validator.validate(fields_future_doi, reference_date=ref_date)
    d5 = next(f for f in res.findings if f.check_id == "D-5")
    assert d5.status == CheckStatus.FAIL
    assert d5.check_class == CheckClass.T1


def test_expiry_status_flag(validator):
    ref_date = date(2026, 10, 28)
    # Expired passport (DOE in 2024 < 2026)
    fields_expired = {
        "dob": "14/05/1998",
        "doi": "15/05/2014",
        "doe": "14/05/2024",
        "nationality": "INDIAN",
    }
    res = validator.validate(fields_expired, reference_date=ref_date)
    assert "EXPIRED" in result_status_flags(res)
    # Administrative flag should NOT fail overall logic or trigger T1 fraud
    assert res.valid_logic is True
    assert res.overall_status == CheckStatus.PASS


def test_nationality_literal(validator):
    fields_foreign = {
        "dob": "14/05/1998",
        "nationality": "BRITISH",
    }
    res = validator.validate(fields_foreign)
    d10 = next(f for f in res.findings if f.check_id == "D-10")
    assert d10.status == CheckStatus.FAIL
    assert d10.check_class == CheckClass.T1


def result_status_flags(res):
    return res.document_status
