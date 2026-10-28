"""
modules/qr/trust_store.py - Cryptographic Trust Store with SHA-256 Certificate Pinning (L7)
and Temporal Plausibility & Freshness Verification (L8).
"""

import hashlib
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, Dict, List, Tuple, Any
from cryptography.x509 import load_der_x509_certificate, load_pem_x509_certificate
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives import hashes


# Hard-pinned SHA-256 fingerprints for official UIDAI Root & Sub-CA Certificates (2017 - 2029)
PINNED_UIDAI_CERTIFICATES = {
    "uidai_12_06_18_cer.cer": {
        "fingerprint": "3E6A1503F302A7C33B182DD20E0A6853EEF77BBB24ACC98C91CF16F678D8A977",
        "valid_from": "2018-06-08",
        "valid_to": "2021-06-07",
        "description": "UIDAI Sub-CA 2018-2021"
    },
    "uidai_offline_publickey_17022026.cer": {
        "fingerprint": "68607E079D81ECBF7368B07B1AB5317F1F006934016FEEF9393CBBB7B9DD49F7",
        "valid_from": "2024-02-21",
        "valid_to": "2026-02-16",
        "description": "UIDAI Offline Key 2024-2026"
    },
    "uidai_offline_publickey_2026.cer": {
        "fingerprint": "1EA1C3468AF581964056203264D470C14B890F928AEA72EFF611637D88F36A26",
        "valid_from": "2026-02-03",
        "valid_to": "2029-02-03",
        "description": "UIDAI Offline Key 2026-2029"
    },
    "uidai_offline_publickey_26022019.cer": {
        "fingerprint": "B6696EFB937378DB01A1F3306CC9AA6E309D6E9337921D5BA207274F798BB857",
        "valid_from": "2017-04-27",
        "valid_to": "2019-04-09",
        "description": "UIDAI Sub-CA 2017-2019"
    },
    "uidai_offline_publickey_26022021.cer": {
        "fingerprint": "288475EF50AC1E73550F487062EF6A8A9580310DD1E312D069FAAA1331E4847F",
        "valid_from": "2021-02-26",
        "valid_to": "2024-02-27",
        "description": "UIDAI Offline Key 2021-2024"
    },
    "uidai_offline_publickey_29032019.cer": {
        "fingerprint": "89208E69E3DA86679E0D7E0CC6E31CFC2F0D6B6D6AC996694EF631044BCD180D",
        "valid_from": "2019-03-15",
        "valid_to": "2021-02-28",
        "description": "UIDAI Offline Key 2019-2021"
    },
    "uidai_prod_cdup.cer": {
        "fingerprint": "D69BC1630B3DD70C262AD293EEA5ECFBFF99F3D757C98DAA2A53B81925A695FE",
        "valid_from": "2017-06-08",
        "valid_to": "2020-06-07",
        "description": "UIDAI CDUP Production Cert"
    },
    "uidai_public_cert.cer": {
        "fingerprint": "362FF11C4A9D420657745A8CBBFC0C588C22F6FA1C54688A9CBBF4F654039316",
        "valid_from": "2025-08-14",
        "valid_to": "2028-08-13",
        "description": "UIDAI Public Cert 2025-2028"
    },
}

_LOADED_TRUST_STORE = None
_MOCK_CA_ENABLED = False


def enable_test_mock_ca(enabled: bool = True):
    """Dynamically enables or disables the Mock-UIDAI test Root CA in the active trust store."""
    global _LOADED_TRUST_STORE, _MOCK_CA_ENABLED
    _MOCK_CA_ENABLED = enabled
    _LOADED_TRUST_STORE = None  # Invalidate cache to reload keys


def load_pinned_trust_store(cert_dir: Optional[Path] = None) -> List[Dict[str, Any]]:
    """
    Loads UIDAI public certificates from data/certs/, verifies each against the pinned
    SHA-256 fingerprint database, and caches valid certificates in memory.
    Rejects any unpinned or tampered certificate files.
    """
    global _LOADED_TRUST_STORE
    if _LOADED_TRUST_STORE is not None:
        return _LOADED_TRUST_STORE

    if cert_dir is None:
        cert_dir = Path(__file__).resolve().parent.parent.parent / "data" / "certs"

    loaded_keys = []
    if not cert_dir.exists():
        print(f"[TrustStore] Warning: Cert directory not found at {cert_dir}")
        _LOADED_TRUST_STORE = []
        return _LOADED_TRUST_STORE

    candidate_files = list(cert_dir.glob("*.cer")) + list(cert_dir.glob("*.pem")) + list(cert_dir.glob("*.crt"))

    for cert_path in candidate_files:
        try:
            raw_bytes = cert_path.read_bytes()
            computed_fp = hashlib.sha256(raw_bytes).hexdigest().upper()

            # Cryptographic Pinning Check
            pinned_info = PINNED_UIDAI_CERTIFICATES.get(cert_path.name)
            if pinned_info is None or pinned_info["fingerprint"] != computed_fp:
                print(f"[TrustStore] REJECTED unpinned/untrusted certificate: {cert_path.name} (SHA256: {computed_fp})")
                continue

            try:
                cert = load_der_x509_certificate(raw_bytes)
            except Exception:
                cert = load_pem_x509_certificate(raw_bytes)

            valid_from = cert.not_valid_before_utc if hasattr(cert, 'not_valid_before_utc') else cert.not_valid_before.replace(tzinfo=timezone.utc)
            valid_to = cert.not_valid_after_utc if hasattr(cert, 'not_valid_after_utc') else cert.not_valid_after.replace(tzinfo=timezone.utc)

            loaded_keys.append({
                "name": cert_path.name,
                "fingerprint": computed_fp,
                "pub_key": cert.public_key(),
                "valid_from": valid_from,
                "valid_to": valid_to,
                "description": pinned_info.get("description", "")
            })
        except Exception as e:
            print(f"[TrustStore] Error loading {cert_path.name}: {e}")

    # Load Mock CA if enabled for synthetic benchmark evaluation
    if _MOCK_CA_ENABLED:
        mock_cert_path = cert_dir / "mock" / "mock_uidai_ca.cer"
        if mock_cert_path.exists():
            try:
                raw_bytes = mock_cert_path.read_bytes()
                computed_fp = hashlib.sha256(raw_bytes).hexdigest().upper()
                cert = load_der_x509_certificate(raw_bytes)
                valid_from = cert.not_valid_before_utc if hasattr(cert, 'not_valid_before_utc') else cert.not_valid_before.replace(tzinfo=timezone.utc)
                valid_to = cert.not_valid_after_utc if hasattr(cert, 'not_valid_after_utc') else cert.not_valid_after.replace(tzinfo=timezone.utc)
                loaded_keys.append({
                    "name": "mock_uidai_ca.cer",
                    "fingerprint": computed_fp,
                    "pub_key": cert.public_key(),
                    "valid_from": valid_from,
                    "valid_to": valid_to,
                    "description": "Mock UIDAI Offline Test Key (Synthetic Benchmark)"
                })
            except Exception as e:
                print(f"[TrustStore] Error loading mock CA: {e}")

    _LOADED_TRUST_STORE = loaded_keys
    return _LOADED_TRUST_STORE


def verify_uidai_signature_pinned(
    payload_bytes: bytes,
    signature_bytes: bytes,
    issue_dt: Optional[datetime] = None
) -> Tuple[str, Optional[str], Optional[str], str]:
    """
    Deterministic Signature Verification with Cryptographic Trust Store Pinning (L7).

    Returns:
        (status, matching_cert_name, cert_fingerprint, diagnostic_message)
        status values:
          - "VALID": Verified by a pinned UIDAI active certificate.
          - "INVALID_SIGNATURE": Epoch matched an active pinned certificate, but cryptographic RSA verification failed (Tampered/Fake).
          - "UNKNOWN_KEY": Issue timestamp claims an epoch with no matching certificate in the pinned trust store.
          - "NO_KEYS_LOADED": Trust store was empty or unavailable.
    """
    keys = load_pinned_trust_store()
    if not keys:
        return "NO_KEYS_LOADED", None, None, "No verified pinned certificates found in UIDAI trust store."

    # Step 1: Temporal Key Filtering
    epoch_matched_keys = []
    if issue_dt is not None:
        for k in keys:
            if k["valid_from"] <= issue_dt <= k["valid_to"]:
                epoch_matched_keys.append(k)

    # Step 2: Verification against Epoch-Matched Keys
    if epoch_matched_keys:
        for k in epoch_matched_keys:
            try:
                k["pub_key"].verify(
                    signature_bytes,
                    payload_bytes,
                    padding.PKCS1v15(),
                    hashes.SHA256()
                )
                return "VALID", k["name"], k["fingerprint"], f"Verified against pinned UIDAI certificate: {k['name']} ({k['description']})"
            except Exception:
                continue

        # If it failed for all candidate active keys for that epoch:
        # Check all other pinned keys to test for clock drift
        for k in keys:
            if k not in epoch_matched_keys:
                try:
                    k["pub_key"].verify(
                        signature_bytes,
                        payload_bytes,
                        padding.PKCS1v15(),
                        hashes.SHA256()
                    )
                    return "VALID", k["name"], k["fingerprint"], f"Verified by pinned cert {k['name']} (Inter-epoch drift: Issued {issue_dt.strftime('%Y-%m-%d')})"
                except Exception:
                    continue

        return "INVALID_SIGNATURE", None, None, f"UIDAI RSA-2048 verification FAILED against active certificate for epoch ({issue_dt.strftime('%Y-%m-%d')}). Payload or signature has been tampered!"

    # Step 3: Issue date provided, but no certificate covered that epoch
    if issue_dt is not None:
        # Test all keys just in case
        for k in keys:
            try:
                k["pub_key"].verify(
                    signature_bytes,
                    payload_bytes,
                    padding.PKCS1v15(),
                    hashes.SHA256()
                )
                return "VALID", k["name"], k["fingerprint"], f"Verified by pinned cert {k['name']} outside standard epoch window."
            except Exception:
                continue

        return "UNKNOWN_KEY", None, None, f"UNKNOWN SIGNING KEY: Card issue date ({issue_dt.strftime('%Y-%m-%d')}) does not correspond to any known active UIDAI certificate in pinned trust store."

    # Step 4: No issue date available (e.g. older format or unparsed RefID)
    for k in keys:
        try:
            k["pub_key"].verify(
                signature_bytes,
                payload_bytes,
                padding.PKCS1v15(),
                hashes.SHA256()
            )
            return "VALID", k["name"], k["fingerprint"], f"Verified against pinned UIDAI certificate: {k['name']}"
        except Exception:
            continue

    return "INVALID_SIGNATURE", None, None, "Digital signature verification failed across all pinned UIDAI public keys."


def validate_temporal_plausibility(
    issue_dt: Optional[datetime],
    dob_str: Optional[str] = None,
    is_v5_qr: bool = True
) -> Tuple[bool, List[str]]:
    """
    Temporal Plausibility & Freshness Engine (L8).
    Evaluates:
      1. Future issue timestamps (exceeding current time + 5m clock skew).
      2. UIDAI V5 epoch bounds (V5 Secure QR was launched in 2018).
      3. Chronological consistency (Issue date cannot precede Date of Birth).
      4. Age at issuance bounds (0 <= Age <= 120).

    Returns:
        (is_plausible: bool, issues: List[str])
    """
    issues = []
    if issue_dt is None:
        return True, issues

    now_utc = datetime.now(timezone.utc)

    # 1. Future Date Check (with 300s clock skew margin)
    if issue_dt > now_utc + timedelta(seconds=300):
        skew_hours = (issue_dt - now_utc).total_seconds() / 3600.0
        issues.append(f"FUTURE TIMESTAMP: Card claims issuance in the future ({issue_dt.strftime('%Y-%m-%d %H:%M:%S')} UTC, +{skew_hours:.1f}h ahead of current time).")

    # 2. V5 QR Epoch Boundary (UIDAI V5 Secure QR did not exist prior to 2018)
    if is_v5_qr and issue_dt.year < 2018:
        issues.append(f"PRE-EPOCH QR: Document contains a V5 Secure QR code claiming issue date in {issue_dt.year}, but V5 Secure QR was only introduced in 2018.")

    # 3. DOB vs Issue Date Consistency
    if dob_str:
        dob_dt = None
        cleaned_dob = dob_str.strip()
        for fmt in ("%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d", "%Y/%m/%d"):
            try:
                dob_dt = datetime.strptime(cleaned_dob, fmt).replace(tzinfo=timezone.utc)
                break
            except Exception:
                continue

        # If only year was provided (e.g. "1995")
        if dob_dt is None and len(cleaned_dob) == 4 and cleaned_dob.isdigit():
            try:
                dob_dt = datetime(int(cleaned_dob), 1, 1, tzinfo=timezone.utc)
            except Exception:
                pass

        if dob_dt is not None:
            if dob_dt > issue_dt:
                issues.append(f"CHRONOLOGICAL INVERSION: Card issue date ({issue_dt.strftime('%Y-%m-%d')}) precedes holder's date of birth ({dob_str}).")
            else:
                age_at_issue = (issue_dt - dob_dt).days / 365.25
                if age_at_issue > 120:
                    issues.append(f"IMPLAUSIBLE AGE AT ISSUE: Calculated age at issuance is {age_at_issue:.1f} years (DOB: {dob_str}, Issued: {issue_dt.strftime('%Y-%m-%d')}).")

    is_valid = len(issues) == 0
    return is_valid, issues
