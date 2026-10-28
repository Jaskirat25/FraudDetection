"""
tests/test_passport_repair.py - Unit tests for Evidence-Preserving MRZ Repair (Check C-11).
"""

import sys
from pathlib import Path
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from modules.passport.repair import (
    repair_mrz_field,
    generate_candidate_strings,
    CONFUSION_MAP,
)
from modules.passport.mrz import calculate_icao_check_digit
from modules.passport.types import CheckStatus


def test_confusion_candidates_generation():
    # "L123456O<" contains '1', '2', '5', 'O', '<'
    candidates = generate_candidate_strings("L123456O<", max_edits=1)
    cand_texts = [c[0] for c in candidates]
    # 'O' should have candidate '0'
    assert "L1234560<" in cand_texts
    # '5' should have candidate 'S'
    assert "L1234S6O<" in cand_texts


def test_repair_successful_with_viz_corroboration():
    """
    Test scenario: OCR read passport number as 'L123456O<' (letter O instead of zero).
    Real number: 'L1234560<'.
    Expected check digit for 'L1234560<' is calculated.
    With VIZ corroboration = 'L1234560', repair must succeed and auto-accept.
    """
    real_text = "L1234560<"
    corrupt_text = "L123456O<"
    target_cd = str(calculate_icao_check_digit(real_text))
    
    # Check that corrupt text indeed fails the target check digit
    assert str(calculate_icao_check_digit(corrupt_text)) != target_cd

    result = repair_mrz_field(
        field_name="passport_no",
        raw_field_text=corrupt_text,
        expected_check_digit=target_cd,
        viz_value="L1234560",
    )

    assert result.repaired is True
    assert result.repaired_text == real_text
    assert result.viz_corroborated is True
    assert result.post_repair_checksum_valid is True
    assert result.finding is not None
    assert result.finding.status == CheckStatus.PASS
    assert len(result.applied_edits) == 1
    assert result.applied_edits[0] == (7, "O", "0")


def test_repair_rejected_without_viz_corroboration():
    """
    Conservative repair principle: A candidate passing check digit alone
    CANNOT be accepted if VIZ is absent or contradicts.
    """
    real_text = "L1234560<"
    corrupt_text = "L123456O<"
    target_cd = str(calculate_icao_check_digit(real_text))

    # Without VIZ value provided:
    result_no_viz = repair_mrz_field(
        field_name="passport_no",
        raw_field_text=corrupt_text,
        expected_check_digit=target_cd,
        viz_value=None,
    )
    assert result_no_viz.repaired is False
    assert result_no_viz.viz_corroborated is False
    assert result_no_viz.finding.status == CheckStatus.UNKNOWN

    # With contradicting VIZ value:
    result_contra_viz = repair_mrz_field(
        field_name="passport_no",
        raw_field_text=corrupt_text,
        expected_check_digit=target_cd,
        viz_value="Z9999999",
    )
    assert result_contra_viz.repaired is False
    assert result_contra_viz.viz_corroborated is False
    assert result_contra_viz.finding.status == CheckStatus.UNKNOWN


def test_repair_two_edits_max():
    """
    Test scenario: Two OCR errors in DOB: '98O3I4' instead of '980314'.
    """
    real_dob = "980314"
    corrupt_dob = "98O3I4"
    target_cd = str(calculate_icao_check_digit(real_dob))

    result = repair_mrz_field(
        field_name="dob",
        raw_field_text=corrupt_dob,
        expected_check_digit=target_cd,
        viz_value="14/03/1998",
        max_edits=2,
    )

    assert result.repaired is True
    assert result.repaired_text == real_dob
    assert result.viz_corroborated is True
    assert len(result.applied_edits) == 2
