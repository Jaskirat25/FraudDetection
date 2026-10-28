import sys
from pathlib import Path
import pytest
from datetime import date

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from modules.passport.mrz import (
    TD3MRZParser,
    calculate_icao_check_digit,
    is_valid_calendar_date,
)
from modules.passport.types import CheckStatus, RecommendedAction, CheckClass


@pytest.fixture
def parser():
    return TD3MRZParser()


# Sample valid Indian Passport TD3 MRZ vectors
# L1: P<INDSURNAME<<GIVEN<NAME<<<<<<<<<<<<<<<<<<< (44)
# L2: L1234567<3IND9805149M2805139<<<<<<<<<<<<<<<2 (44)
def build_sample_mrz(
    surname="SURNAME",
    given_names="GIVEN<NAME",
    passport_no="L1234567<",
    nationality="IND",
    dob="980514",
    sex="M",
    expiry="280513",
    personal_no="<<<<<<<<<<<<<<",
    personal_no_cd="<",
):
    # Calculate check digits dynamically for pristine sample
    pass_cd = str(calculate_icao_check_digit(passport_no))
    dob_cd = str(calculate_icao_check_digit(dob))
    exp_cd = str(calculate_icao_check_digit(expiry))
    
    # Line 1:
    name_payload = f"{surname}<<{given_names}"
    l1 = f"P<IND{name_payload}".ljust(44, "<")

    # Line 2 components:
    comp1 = f"{passport_no}{pass_cd}"          # 10 chars
    comp2 = f"{nationality}"                    # 3 chars
    comp3 = f"{dob}{dob_cd}"                    # 7 chars
    comp4 = f"{sex}"                            # 1 char
    comp5 = f"{expiry}{exp_cd}"                 # 7 chars
    comp6 = f"{personal_no}{personal_no_cd}"    # 15 chars
    
    # Composite payload (1-10, 14-20, 22-43):
    composite_payload = comp1 + comp3 + comp5 + comp6
    composite_cd = str(calculate_icao_check_digit(composite_payload))

    l2 = comp1 + comp2 + comp3 + comp4 + comp5 + comp6 + composite_cd
    return l1, l2


# =============================================================================
# Checksum Calculator Unit Tests
# =============================================================================

def test_icao_check_digit_calculation():
    # Test vector:
    # "HA672242<":
    # H=17*7=119, A=10*3=30, 6=6*1=6, 7=7*7=49, 2=2*3=6, 2=2*1=2, 4=4*7=28, 2=2*3=6, <=0*1=0
    # Sum: 119+30+6+49+6+2+28+6+0 = 246 -> mod 10 = 6
    assert calculate_icao_check_digit("HA672242<") == 6

    # Digits only: "650225" -> 6*7+5*3+0*1+2*7+2*3+5*1 = 42+15+0+14+6+5 = 82 -> 2
    assert calculate_icao_check_digit("650225") == 2

    # All filler: "<" evaluates to 0
    assert calculate_icao_check_digit("<<<<<<<<") == 0


def test_icao_check_digit_invalid_char():
    with pytest.raises(ValueError, match="Invalid ICAO MRZ character"):
        calculate_icao_check_digit("A123#456")


# =============================================================================
# C-1: Structure & Charset Tests
# =============================================================================

def test_mrz_structure_valid(parser):
    l1, l2 = build_sample_mrz()
    res = parser.parse(l1, l2)
    assert res.valid_structure is True
    assert res.overall_status == CheckStatus.PASS
    c1 = next(f for f in res.findings if f.check_id == "C-1")
    assert c1.status == CheckStatus.PASS


def test_mrz_structure_invalid(parser):
    l1, l2 = build_sample_mrz()
    # Bad line length (43 instead of 44)
    res_len = parser.parse(l1[:43], l2)
    assert res_len.valid_structure is False
    assert res_len.overall_status == CheckStatus.FAIL
    assert res_len.recommended_action == RecommendedAction.RECAPTURE_REQUIRED

    # Invalid lowercase / punctuation characters
    res_char = parser.parse(l1.replace("IND", "ind"), l2)
    c1 = next(f for f in res_char.findings if f.check_id == "C-1")
    assert c1.status == CheckStatus.FAIL

    # Invalid document prefix (must start with P)
    res_prefix = parser.parse("V" + l1[1:], l2)
    c1_pref = next(f for f in res_prefix.findings if f.check_id == "C-1")
    assert c1_pref.status == CheckStatus.FAIL


# =============================================================================
# C-2: State & Nationality Tests
# =============================================================================

def test_state_nationality_valid(parser):
    l1, l2 = build_sample_mrz()
    res = parser.parse(l1, l2)
    c2 = next(f for f in res.findings if f.check_id == "C-2")
    assert c2.status == CheckStatus.PASS


def test_state_nationality_invalid(parser):
    # Foreign issuing state e.g. GBR
    l1, l2 = build_sample_mrz()
    l1_bad = l1[:2] + "GBR" + l1[5:]
    res = parser.parse(l1_bad, l2)
    c2 = next(f for f in res.findings if f.check_id == "C-2")
    assert c2.status == CheckStatus.FAIL
    assert c2.check_class == CheckClass.T1


# =============================================================================
# C-3, C-4, C-5, C-6, C-7: Check Digits & Checksums
# =============================================================================

def test_passport_number_check_digit(parser):
    l1, l2 = build_sample_mrz()
    res = parser.parse(l1, l2)
    c3 = next(f for f in res.findings if f.check_id == "C-3")
    assert c3.status == CheckStatus.PASS
    assert res.check_digits["passport_no"] is True

    # Mutate passport number check digit (pos 10 -> index 9)
    bad_cd = "0" if l2[9] != "0" else "1"
    l2_bad = l2[:9] + bad_cd + l2[10:]
    res_bad = parser.parse(l1, l2_bad)
    c3_bad = next(f for f in res_bad.findings if f.check_id == "C-3")
    assert c3_bad.status == CheckStatus.FAIL
    assert c3_bad.check_class == CheckClass.T1


def test_dob_check_digit(parser):
    l1, l2 = build_sample_mrz()
    res = parser.parse(l1, l2)
    c4 = next(f for f in res.findings if f.check_id == "C-4")
    assert c4.status == CheckStatus.PASS

    # Mutate DOB check digit (pos 20 -> index 19)
    bad_cd = "0" if l2[19] != "0" else "1"
    l2_bad = l2[:19] + bad_cd + l2[20:]
    res_bad = parser.parse(l1, l2_bad)
    c4_bad = next(f for f in res_bad.findings if f.check_id == "C-4")
    assert c4_bad.status == CheckStatus.FAIL


def test_expiry_check_digit(parser):
    l1, l2 = build_sample_mrz()
    res = parser.parse(l1, l2)
    c5 = next(f for f in res.findings if f.check_id == "C-5")
    assert c5.status == CheckStatus.PASS

    # Mutate Expiry check digit (pos 28 -> index 27)
    bad_cd = "0" if l2[27] != "0" else "1"
    l2_bad = l2[:27] + bad_cd + l2[28:]
    res_bad = parser.parse(l1, l2_bad)
    c5_bad = next(f for f in res_bad.findings if f.check_id == "C-5")
    assert c5_bad.status == CheckStatus.FAIL


def test_personal_number_blank(parser):
    # Indian passport with blank personal number '<'
    l1, l2 = build_sample_mrz(personal_no="<<<<<<<<<<<<<<", personal_no_cd="<")
    res = parser.parse(l1, l2)
    c6 = next(f for f in res.findings if f.check_id == "C-6")
    assert c6.status == CheckStatus.PASS

    # Indian passport with blank personal number and '0' check digit
    l1_0, l2_0 = build_sample_mrz(personal_no="<<<<<<<<<<<<<<", personal_no_cd="0")
    res_0 = parser.parse(l1_0, l2_0)
    c6_0 = next(f for f in res_0.findings if f.check_id == "C-6")
    assert c6_0.status == CheckStatus.PASS


def test_composite_check_digit(parser):
    l1, l2 = build_sample_mrz()
    res = parser.parse(l1, l2)
    c7 = next(f for f in res.findings if f.check_id == "C-7")
    assert c7.status == CheckStatus.PASS
    assert res.check_digits["composite"] is True

    # Mutate composite check digit (pos 44 -> index 43)
    bad_cd = "0" if l2[43] != "0" else "1"
    l2_bad = l2[:43] + bad_cd
    res_bad = parser.parse(l1, l2_bad)
    c7_bad = next(f for f in res_bad.findings if f.check_id == "C-7")
    assert c7_bad.status == CheckStatus.FAIL
    assert c7_bad.check_class == CheckClass.T1


# =============================================================================
# C-8: Name Parsing Tests
# =============================================================================

def test_name_parsing(parser):
    # 1. Standard: Surname + Multiple Given Names
    l1, l2 = build_sample_mrz(surname="SHARMA", given_names="RAHUL<KUMAR")
    res = parser.parse(l1, l2)
    assert res.surname == "SHARMA"
    assert res.given_names == "RAHUL KUMAR"
    c8 = next(f for f in res.findings if f.check_id == "C-8")
    assert c8.status == CheckStatus.PASS

    # 2. Hyphenated / Compound surname (transliterated to single '<' in MRZ)
    l1, l2 = build_sample_mrz(surname="SINGH<ROY", given_names="JASKIRAT")
    res = parser.parse(l1, l2)
    assert res.surname == "SINGH ROY"
    assert res.given_names == "JASKIRAT"

    # 3. Single-name holder (no given names)
    l1, l2 = build_sample_mrz(surname="KUMAR", given_names="")
    res = parser.parse(l1, l2)
    assert res.surname == "KUMAR"
    assert res.given_names == ""
    assert res.overall_status == CheckStatus.PASS

    # 4. Heavy trailing filler
    l1, l2 = build_sample_mrz(surname="DAS", given_names="A")
    res = parser.parse(l1, l2)
    assert res.surname == "DAS"
    assert res.given_names == "A"

    # 5. Anomalous secondary '<<' inside given names
    l1_bad = "P<INDVERMA<<ANIL<<KUMAR<<<<<<<<<<<<<<<<<<<<<"
    res_bad = parser.parse(l1_bad, l2)
    c8_bad = next(f for f in res_bad.findings if f.check_id == "C-8")
    assert c8_bad.status == CheckStatus.FAIL
    assert c8_bad.check_class == CheckClass.T2


# =============================================================================
# C-9: Sex Field Validation Tests
# =============================================================================

def test_sex_field(parser):
    # 'M' Male
    l1, l2_m = build_sample_mrz(sex="M")
    assert parser.parse(l1, l2_m).sex == "M"

    # 'F' Female
    l1, l2_f = build_sample_mrz(sex="F")
    assert parser.parse(l1, l2_f).sex == "F"

    # '<' Unspecified
    l1, l2_u = build_sample_mrz(sex="<")
    assert parser.parse(l1, l2_u).sex == ""

    # Invalid character 'X'
    l1, l2_x = build_sample_mrz(sex="X")
    res_x = parser.parse(l1, l2_x)
    c9_bad = next(f for f in res_x.findings if f.check_id == "C-9")
    assert c9_bad.status == CheckStatus.FAIL
    assert c9_bad.check_class == CheckClass.T1


# =============================================================================
# C-10: Date Validity & Century Logic Tests
# =============================================================================

def test_date_validity_and_century(parser):
    ref_date = date(2026, 10, 27)

    # 1. Valid dates with century resolution (DOB 980514 -> 1998-05-14; Expiry 280513 -> 2028-05-13)
    l1, l2 = build_sample_mrz(dob="980514", expiry="280513")
    res = parser.parse(l1, l2, reference_date=ref_date)
    assert res.dob == "1998-05-14"
    assert res.expiry_date == "2028-05-13"

    # 2. Leap year date: Feb 29, 2000 (000229) is a valid calendar date
    assert is_valid_calendar_date(2000, 2, 29) is True
    l1_lp, l2_lp = build_sample_mrz(dob="000229", expiry="280513")
    res_lp = parser.parse(l1_lp, l2_lp, viz_dob_year=2000, reference_date=ref_date)
    assert res_lp.dob == "2000-02-29"

    # 3. Non-leap year date: Feb 29, 2023 (230229) is impossible
    assert is_valid_calendar_date(2023, 2, 29) is False
    l1_nlp, l2_nlp = build_sample_mrz(dob="230229", expiry="280513")
    res_nlp = parser.parse(l1_nlp, l2_nlp, reference_date=ref_date)
    c10 = next(f for f in res_nlp.findings if f.check_id == "C-10")
    assert c10.status == CheckStatus.FAIL

    # 4. Out of bounds month/day: 981332 (Month 13, Day 32)
    l1_oob, l2_oob = build_sample_mrz(dob="981332", expiry="280513")
    res_oob = parser.parse(l1_oob, l2_oob, reference_date=ref_date)
    c10_oob = next(f for f in res_oob.findings if f.check_id == "C-10")
    assert c10_oob.status == CheckStatus.FAIL

    # 5. VIZ-assisted century corroboration (1998 vs 2098)
    l1_viz, l2_viz = build_sample_mrz(dob="980514", expiry="280513")
    res_viz = parser.parse(l1_viz, l2_viz, viz_dob_year=1998, viz_expiry_year=2028, reference_date=ref_date)
    assert res_viz.dob == "1998-05-14"
    assert res_viz.expiry_date == "2028-05-13"

    # VIZ mismatch: VIZ says 1997 but MRZ says 98
    res_viz_mismatch = parser.parse(l1_viz, l2_viz, viz_dob_year=1997, reference_date=ref_date)
    c10_mm = next(f for f in res_viz_mismatch.findings if f.check_id == "C-10")
    assert c10_mm.status == CheckStatus.FAIL
