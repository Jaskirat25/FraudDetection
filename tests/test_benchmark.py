import os
import sys
from pathlib import Path
import pytest
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
if hasattr(sys, "set_int_max_str_digits"):
    sys.set_int_max_str_digits(50000)

from modules.mock_ca.ca_authority import get_or_create_mock_ca, sign_qr_payload, get_mock_cert_info
from modules.mock_ca.qr_encoder import create_synthetic_qr_payload
from modules.qr.trust_store import enable_test_mock_ca
from modules.qr.qr_verifier import decode_and_verify_qr
from modules.synthetic.card_renderer import render_synthetic_aadhaar_card, generate_demographic_identity
from modules.synthetic.attack_generators import generate_attack_sample, ATTACK_VECTORS
from modules.synthetic.benchmark_runner import BenchmarkRunner


def test_mock_ca_creation_and_signing():
    enable_test_mock_ca(True)
    priv_key, cert, fp = get_or_create_mock_ca()
    assert priv_key is not None
    assert cert is not None
    assert len(fp) == 64
    info = get_mock_cert_info()
    assert info["subject_cn"] == "UIDAI Test Mock CA Root"

    data = b"TEST_AADHAAR_PAYLOAD_BYTES"
    sig = sign_qr_payload(data, priv_key)
    assert len(sig) == 256  # RSA-2048 produces 256-byte signature


def test_synthetic_qr_generation_and_verification():
    enable_test_mock_ca(True)
    demo = {
        "name": "Aarav Sharma",
        "dob": "15-08-1992",
        "gender": "M",
        "aadhaar_last4": "9812",
        "address": "42 Connaught Place, New Delhi",
        "pincode": "110001"
    }
    raw_bytes, dec_str, qr_bgr = create_synthetic_qr_payload(demo)
    assert len(dec_str) > 0
    assert qr_bgr.shape[0] > 100

    res = decode_and_verify_qr(qr_bgr)
    assert res.present is True
    assert res.is_secure_qr is True
    assert res.signature_valid is True
    assert res.payload.get("name") == "Aarav Sharma"
    assert res.payload.get("last4") == "9812"


def test_synthetic_card_renderer():
    front, back, combined, meta = render_synthetic_aadhaar_card()
    assert front.shape == (630, 1000, 3)
    assert back.shape == (630, 1000, 3)
    assert combined.shape[0] >= 630
    assert "aadhaar_no" in meta
    assert len(meta["aadhaar_no"]) == 12


def test_attack_generators():
    sample_a1 = generate_attack_sample("A1")
    assert sample_a1.vector_id == "A1"
    assert "REJECT" in sample_a1.expected_verdicts

    sample_a14 = generate_attack_sample("A14")
    assert sample_a14.vector_id == "A14"
    assert "VERIFIED" in sample_a14.expected_verdicts


def test_ablation_study_structure():
    runner = BenchmarkRunner()
    ablation = runner.run_ablation_study(verbose=False)
    assert "Full Pipeline (L1+L2+L3+L4+L5+PAD)" in ablation
    assert "Ablation: No Cryptographic L1 (No RSA-2048 QR)" in ablation
    assert ablation["Full Pipeline (L1+L2+L3+L4+L5+PAD)"]["catch_rate"] == 100.0
