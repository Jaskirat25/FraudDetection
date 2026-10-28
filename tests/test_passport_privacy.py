"""
tests/test_passport_privacy.py - Unit tests for Keyed-HMAC and Reuse Index (Check I-6).
"""

import sys
from pathlib import Path
import hashlib
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from modules.passport.privacy import compute_keyed_hmac, PassportReuseIndex
from modules.passport.types import CheckStatus, CheckClass


@pytest.fixture
def reuse_index():
    idx = PassportReuseIndex(secret_key=b"test-secret-salt")
    idx.clear()
    return idx


def test_keyed_hmac_computation():
    pass_no = "L1234567"
    hmac1 = compute_keyed_hmac(pass_no, secret_key=b"salt-1")
    hmac2 = compute_keyed_hmac(pass_no, secret_key=b"salt-2")
    
    # Keyed HMAC must differ with different keys
    assert hmac1 != hmac2
    # Keyed HMAC must differ from plain SHA-256
    plain_sha = hashlib.sha256(pass_no.encode("utf-8")).hexdigest()
    assert hmac1 != plain_sha

    # Normalization check: padding '<' or lower case produces same HMAC
    assert compute_keyed_hmac("l1234567<", secret_key=b"salt-1") == hmac1


def test_reuse_index_initial_submission(reuse_index):
    res = reuse_index.check_and_record(
        passport_no="L1234567",
        full_name="RAHUL SHARMA",
        dob="1998-05-14",
        submission_id="sub_001",
    )
    assert res.status == CheckStatus.PASS
    assert res.is_duplicate is False


def test_reuse_index_repeat_clean_submission(reuse_index):
    # First submission
    reuse_index.check_and_record(
        passport_no="L1234567",
        full_name="RAHUL SHARMA",
        dob="1998-05-14",
    )

    # Identical repeat submission
    res_repeat = reuse_index.check_and_record(
        passport_no="L1234567",
        full_name="RAHUL SHARMA",
        dob="1998-05-14",
    )
    assert res_repeat.status == CheckStatus.PASS
    assert res_repeat.is_duplicate is True


def test_reuse_index_demographic_mismatch(reuse_index):
    """
    T1 Contradiction: Same passport number submitted under a DIFFERENT person's name or DOB!
    """
    reuse_index.check_and_record(
        passport_no="L1234567",
        full_name="RAHUL SHARMA",
        dob="1998-05-14",
        submission_id="sub_original",
    )

    # Impersonation attempt: Same passport number, completely different name
    res_clash = reuse_index.check_and_record(
        passport_no="L1234567",
        full_name="VIKRAM VERMA",
        dob="1998-05-14",
        submission_id="sub_forged",
    )
    assert res_clash.status == CheckStatus.FAIL
    assert res_clash.is_duplicate is True
    clash_finding = next(f for f in res_clash.findings if f.check_id == "I-6")
    assert clash_finding.status == CheckStatus.FAIL
    assert clash_finding.check_class == CheckClass.T1
    assert "Identity Clash" in clash_finding.message


def test_reuse_index_photo_reuse_alert(reuse_index):
    """
    T2 Signal: Same photo embedding/hash appears on two DIFFERENT passport numbers.
    """
    photo_signature = "perceptual_hash_abc123"

    # Submission 1
    reuse_index.check_and_record(
        passport_no="L1234567",
        full_name="RAHUL SHARMA",
        dob="1998-05-14",
        photo_hash=photo_signature,
    )

    # Submission 2: Different passport number, but reused the exact same photo
    res_photo_reuse = reuse_index.check_and_record(
        passport_no="Z9876543",
        full_name="AJAY SINGH",
        dob="1995-02-10",
        photo_hash=photo_signature,
    )
    assert res_photo_reuse.status == CheckStatus.FAIL
    photo_finding = next(f for f in res_photo_reuse.findings if f.field == "photo")
    assert photo_finding.status == CheckStatus.FAIL
    assert photo_finding.check_class == CheckClass.T2
