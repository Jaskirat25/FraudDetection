import os
import sys
from pathlib import Path
from starlette.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from api.main import app

client = TestClient(app)

def test_dashboard_html():
    response = client.get("/")
    assert response.status_code == 200
    assert "Dual-Sided (Front &amp; Back)" in response.text or "Dual-Sided (Front & Back)" in response.text
    assert "front-drop-zone" in response.text
    assert "back-drop-zone" in response.text
    print(" PASS: Dashboard HTML contains Dual-Sided UI elements.")

def test_samples_endpoint():
    response = client.get("/api/samples")
    assert response.status_code == 200
    data = response.json()
    assert "samples" in data
    ids = [s["id"] for s in data["samples"]]
    assert "sample_pair_jaskirat" in ids
    print(f" PASS: /api/samples returns sample_pair_jaskirat among {len(ids)} samples.")

def test_screen_dual_sample():
    response = client.post("/api/screen", data={"card_sample": "sample_pair_jaskirat"})
    assert response.status_code == 200, response.text
    r = response.json()
    assert r["verdict"] == "VERIFIED", f"Expected VERIFIED, got {r['verdict']}"
    assert r["risk_score"] == 0.0
    assert r["qr"]["signature_valid"] is True
    assert r["biometrics"]["card_qr_match"] is True
    print(f" PASS: /api/screen with dual sample verified. Verdict: {r['verdict']}, Risk: {r['risk_score']}")

def test_screen_dual_files():
    front_path = PROJECT_ROOT / "aadhar_front.jpeg"
    back_path = PROJECT_ROOT / "WhatsApp Image 2026-09-27 at 5.05.50 PM.jpeg"
    assert front_path.exists() and back_path.exists()

    with open(front_path, "rb") as f_front, open(back_path, "rb") as f_back:
        files = {
            "front_file": ("aadhar_front.jpeg", f_front, "image/jpeg"),
            "back_file": ("back_qr.jpeg", f_back, "image/jpeg"),
        }
        response = client.post("/api/screen", files=files)
    
    assert response.status_code == 200, response.text
    r = response.json()
    assert r["verdict"] == "VERIFIED", f"Expected VERIFIED, got {r['verdict']}"
    assert r["risk_score"] == 0.0
    assert r["qr"]["signature_valid"] is True
    print(f" PASS: /api/screen with dual uploaded files verified. Verdict: {r['verdict']}, Risk: {r['risk_score']}")

def test_screen_single_combined_backward_compat():
    combined_path = PROJECT_ROOT / "combined-image.jpg"
    assert combined_path.exists()

    with open(combined_path, "rb") as f:
        files = {
            "card_file": ("combined-image.jpg", f, "image/jpeg"),
        }
        response = client.post("/api/screen", files=files)
    
    assert response.status_code == 200, response.text
    r = response.json()
    assert r["verdict"] == "VERIFIED", f"Expected VERIFIED, got {r['verdict']}"
    assert r["risk_score"] <= 20.0, f"Expected risk_score <= 20.0, got {r['risk_score']}"
    print(f" PASS: Backward compatibility with single combined card verified. Verdict: {r['verdict']}, Risk: {r['risk_score']}")

if __name__ == "__main__":
    test_dashboard_html()
    test_samples_endpoint()
    test_samples_endpoint()
    test_screen_dual_sample()
    test_screen_dual_files()
    test_screen_single_combined_backward_compat()
    print("\nALL DUAL-INTAKE REST API TESTS PASSED SUCCESSFULLY!")
