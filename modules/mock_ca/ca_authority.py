"""
modules/mock_ca/ca_authority.py - Mock-UIDAI Certificate Authority (CA) & RSA-2048 Signer.
Generates an internal test Root CA, X.509 Certificate, and RSA-2048 keypair to cryptographically
sign synthetic V5 Secure QR payloads conforming to official UIDAI specifications.
"""

import hashlib
import datetime
from pathlib import Path
from typing import Tuple, Optional
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives import serialization, hashes
from cryptography import x509
from cryptography.x509.oid import NameOID

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
MOCK_CERTS_DIR = PROJECT_ROOT / "data" / "certs" / "mock"
PRIVATE_KEY_PATH = MOCK_CERTS_DIR / "mock_uidai_ca_private.pem"
CERT_DER_PATH = MOCK_CERTS_DIR / "mock_uidai_ca.cer"
CERT_PEM_PATH = MOCK_CERTS_DIR / "mock_uidai_ca.pem"

_CA_CACHE: Optional[Tuple[rsa.RSAPrivateKey, x509.Certificate, str]] = None


def get_or_create_mock_ca(force_regenerate: bool = False) -> Tuple[rsa.RSAPrivateKey, x509.Certificate, str]:
    """
    Retrieves or generates the Mock-UIDAI CA keypair and X.509 certificate.
    Returns:
        (private_key, certificate, sha256_fingerprint)
    """
    global _CA_CACHE
    if _CA_CACHE is not None and not force_regenerate:
        return _CA_CACHE

    MOCK_CERTS_DIR.mkdir(parents=True, exist_ok=True)

    if not force_regenerate and PRIVATE_KEY_PATH.exists() and CERT_DER_PATH.exists():
        try:
            priv_pem = PRIVATE_KEY_PATH.read_bytes()
            private_key = serialization.load_pem_private_key(priv_pem, password=None)
            cert_der = CERT_DER_PATH.read_bytes()
            cert = x509.load_der_x509_certificate(cert_der)
            fingerprint = hashlib.sha256(cert_der).hexdigest().upper()
            _CA_CACHE = (private_key, cert, fingerprint)
            return _CA_CACHE
        except Exception:
            pass

    # 1. Generate RSA-2048 Private Key
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048
    )

    # 2. Build Self-Signed X.509 Certificate
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, "IN"),
        x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "New Delhi"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Unique Identification Authority of India (Test CA)"),
        x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, "Mock Offline Verification Test Authority"),
        x509.NameAttribute(NameOID.COMMON_NAME, "Mock UIDAI Offline Key 2026"),
    ])

    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=365))
        .not_valid_after(now + datetime.timedelta(days=365 * 10))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(private_key, hashes.SHA256())
    )

    # 3. Serialize and save key and certificates
    priv_bytes = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    )
    cert_der = cert.public_bytes(serialization.Encoding.DER)
    cert_pem = cert.public_bytes(serialization.Encoding.PEM)

    PRIVATE_KEY_PATH.write_bytes(priv_bytes)
    CERT_DER_PATH.write_bytes(cert_der)
    CERT_PEM_PATH.write_bytes(cert_pem)

    fingerprint = hashlib.sha256(cert_der).hexdigest().upper()
    _CA_CACHE = (private_key, cert, fingerprint)
    return _CA_CACHE


def sign_qr_payload(data_bytes: bytes, private_key: Optional[rsa.RSAPrivateKey] = None) -> bytes:
    """
    Signs uncompressed payload bytes using RSA PKCS#1 v1.5 with SHA-256.
    Returns exactly 256 signature bytes.
    """
    if private_key is None:
        private_key, _, _ = get_or_create_mock_ca()

    signature = private_key.sign(
        data_bytes,
        padding.PKCS1v15(),
        hashes.SHA256()
    )
    assert len(signature) == 256, f"Expected 256 signature bytes, got {len(signature)}"
    return signature


def get_mock_cert_info() -> dict:
    """Returns Mock CA metadata for trust-store integration."""
    _, cert, fp = get_or_create_mock_ca()
    return {
        "name": CERT_DER_PATH.name,
        "path": CERT_DER_PATH,
        "fingerprint": fp,
        "subject_cn": "UIDAI Test Mock CA Root",
        "valid_from": cert.not_valid_before_utc.strftime("%Y-%m-%d"),
        "valid_to": cert.not_valid_after_utc.strftime("%Y-%m-%d"),
        "description": "Mock UIDAI Offline Test Key (Synthetic Benchmark)"
    }
