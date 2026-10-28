"""
tests/test_api_passport.py - Integration tests for Passport API endpoint (/api/screen/passport).
"""

import sys
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from api.main import app

client = TestClient(app)


def test_api_samples_includes_passport():
    resp = client.get("/api/samples")
    assert resp.status_code == 200
    samples = resp.json().get("samples", [])
    
    passport_samples = [s for s in samples if s.get("doc_type") == "passport"]
    assert len(passport_samples) >= 4
    
    sample_ids = [s["id"] for s in passport_samples]
    assert "data/samples/sample_passport_authentic.jpg" in sample_ids
    assert "data/samples/sample_passport_tampered.jpg" in sample_ids


def test_api_sample_file_download():
    resp = client.get("/api/sample/data/samples/sample_passport_authentic.jpg")
    assert resp.status_code == 200
    assert len(resp.content) > 1000


def test_screen_passport_missing_payload():
    resp = client.post("/api/screen/passport")
    assert resp.status_code == 400
    assert "No passport image provided" in resp.json().get("detail", "")


def test_screen_passport_authentic_sample():
    resp = client.post(
        "/api/screen/passport",
        data={"passport_sample": "data/samples/sample_passport_authentic.jpg"},
    )
    assert resp.status_code == 200
    data = resp.json()

    assert data["success"] is True
    assert data["document"] == "indian_passport"
    assert "verdict" in data
    assert "risk_index" in data
    assert "mrz" in data
    assert "cross_checks" in data
    assert "crops" in data
    assert "findings" in data
