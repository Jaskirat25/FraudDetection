"""
modules/passport/privacy.py - Privacy Controls & Keyed-HMAC Reuse Index (Check I-6).
Implements Section 8 and Check I-6 of passport_module_plan_v2.md:
Uses keyed HMAC-SHA256 to index passport numbers safely without storing plain text
or rainbow-table-vulnerable plain SHA-256 hashes.
"""

import os
import hmac
import hashlib
from datetime import datetime, timezone
from dataclasses import dataclass, field as dc_field
from typing import Optional, Dict, List, Tuple, Any

from modules.passport.types import (
    CheckStatus,
    CheckClass,
    Finding,
)

# Application salt for keyed HMAC indexing
DEFAULT_SECRET = b"idshield-passport-screening-hmac-salt-2026"


def compute_keyed_hmac(value: str, secret_key: Optional[bytes] = None) -> str:
    """
    Computes a keyed HMAC-SHA256 digest of a normalized identifier string.
    Ensures passport numbers cannot be enumerated offline via precomputed dictionaries.
    """
    key = secret_key or os.environ.get("PASSPORT_HMAC_SECRET", "").encode("utf-8") or DEFAULT_SECRET
    norm_val = value.strip().upper().replace(" ", "").replace("<", "")
    return hmac.new(key, norm_val.encode("utf-8"), hashlib.sha256).hexdigest()


@dataclass
class ReuseCheckResult:
    status: CheckStatus = CheckStatus.PASS
    findings: List[Finding] = dc_field(default_factory=list)
    is_duplicate: bool = False
    evidence: Dict[str, Any] = dc_field(default_factory=dict)


class PassportReuseIndex:
    """
    In-memory privacy-preserving index for cross-submission duplicate and reuse detection.
    Can be backed by persistent storage (e.g., Redis or SQLite) in production.
    """

    def __init__(self, secret_key: Optional[bytes] = None):
        self.secret_key = secret_key
        # Maps hmac(passport_no) -> record dict
        self._number_index: Dict[str, Dict[str, Any]] = {}
        # Maps photo_hash -> hmac(passport_no)
        self._photo_index: Dict[str, str] = {}

    def check_and_record(
        self,
        passport_no: str,
        full_name: str,
        dob: str,
        photo_hash: Optional[str] = None,
        submission_id: Optional[str] = None,
    ) -> ReuseCheckResult:
        """
        Cross-checks submission against historical index using keyed HMACs:
        - Flags T1 if same passport number is presented under a different identity (name or DOB).
        - Flags T2 if the same photo hash appears under a different passport number.
        - Records new submission if no clashes found.
        """
        result = ReuseCheckResult()
        findings: List[Finding] = []

        clean_num = passport_no.strip().upper().replace("<", "")
        if not clean_num:
            return result

        num_hmac = compute_keyed_hmac(clean_num, self.secret_key)
        norm_name = " ".join(full_name.strip().upper().split())
        norm_dob = dob.strip().replace("/", "-")

        # 1. Check Passport Number HMAC Clash
        if num_hmac in self._number_index:
            existing = self._number_index[num_hmac]
            result.is_duplicate = True

            stored_name = existing["name"]
            stored_dob = existing["dob"]

            name_differs = (norm_name != stored_name)
            dob_differs = (norm_dob != stored_dob)

            if name_differs or dob_differs:
                # T1 Contradiction: Demographic Identity Swap
                reason_parts = []
                if name_differs:
                    reason_parts.append(f"Name differs ('{norm_name}' vs prior '{stored_name}')")
                if dob_differs:
                    reason_parts.append(f"DOB differs ('{norm_dob}' vs prior '{stored_dob}')")

                findings.append(
                    Finding(
                        code="PP-HIST-006",
                        check_id="I-6",
                        status=CheckStatus.FAIL,
                        check_class=CheckClass.T1,
                        field="passport_no",
                        message="Identity Clash: Passport number was previously submitted with different demographics: " + "; ".join(reason_parts),
                        evidence={
                            "passport_hmac": num_hmac[:12] + "...",
                            "prior_submission_id": existing.get("submission_id"),
                            "prior_timestamp": existing.get("timestamp"),
                            "demographic_clash": reason_parts,
                        },
                    )
                )
                result.status = CheckStatus.FAIL
            else:
                # Legitimate repeat submission
                findings.append(
                    Finding(
                        code="PP-HIST-006",
                        check_id="I-6",
                        status=CheckStatus.PASS,
                        check_class=CheckClass.INFO,
                        field="passport_no",
                        message="Known identity record re-submitted (demographics match prior record).",
                        evidence={
                            "passport_hmac": num_hmac[:12] + "...",
                            "prior_submission_id": existing.get("submission_id"),
                        },
                    )
                )
        else:
            # First time seeing this passport number
            self._number_index[num_hmac] = {
                "name": norm_name,
                "dob": norm_dob,
                "submission_id": submission_id or "sub_0",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

        # 2. Check Photo Reuse Clash (T2 Signal)
        if photo_hash:
            if photo_hash in self._photo_index:
                prior_num_hmac = self._photo_index[photo_hash]
                if prior_num_hmac != num_hmac:
                    findings.append(
                        Finding(
                            code="PP-HIST-007",
                            check_id="I-6",
                            status=CheckStatus.FAIL,
                            check_class=CheckClass.T2,
                            field="photo",
                            message="Photo Reuse Alert: Face portrait matches a previously seen passport with a different passport number.",
                            evidence={"photo_hash": photo_hash, "prior_passport_hmac": prior_num_hmac[:12] + "..."},
                        )
                    )
                    if result.status != CheckStatus.FAIL:
                        result.status = CheckStatus.FAIL
            else:
                self._photo_index[photo_hash] = num_hmac

        result.findings = findings
        return result

    def clear(self) -> None:
        """Clears in-memory records (useful for test isolation)."""
        self._number_index.clear()
        self._photo_index.clear()


# Default singleton instance
default_reuse_index = PassportReuseIndex()
