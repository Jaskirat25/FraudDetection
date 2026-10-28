import os
import sys
import json
import base64
from pathlib import Path
import numpy as np
import cv2

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from modules.face.liveness import (
    detect_face_liveness,
    analyze_chroma_distribution,
    analyze_fft_screen_moire,
    analyze_dermal_texture,
    analyze_3d_landmark_geometry,
    analyze_multiframe_temporal_motion
)
from modules.face.matcher import verify_face, _get_models
from starlette.testclient import TestClient
from api.main import app

def test_real_photo_liveness():
    real_img_path = PROJECT_ROOT / "WhatsApp Image 2026-09-25 at 10.32.28 AM.jpeg"
    assert real_img_path.exists(), "Test image WhatsApp Image 2026-09-25 at 10.32.28 AM.jpeg missing"
    
    img = cv2.imread(str(real_img_path))
    res = detect_face_liveness([img])
    
    assert res.is_live is True, f"Expected real photo to pass liveness, got {res.attack_type}"
    assert res.liveness_score >= 0.65, f"Expected score >= 0.65, got {res.liveness_score}"
    assert res.attack_type == "GENUINE_LIVE"
    assert res.apcer_risk == "LOW"
    print(f" PASS: Genuine photo liveness verified. Score: {res.liveness_score}, Attack: {res.attack_type}")

def test_static_frame_injection_spoof():
    real_img_path = PROJECT_ROOT / "WhatsApp Image 2026-09-25 at 10.32.28 AM.jpeg"
    img = cv2.imread(str(real_img_path))
    
    # Simulate a virtual camera injecting identical freeze-frames
    frozen_burst = [img.copy() for _ in range(5)]
    res = detect_face_liveness(frozen_burst)
    
    assert res.is_live is False, "Expected identical frames to fail liveness"
    assert res.attack_type == "STATIC_FRAME_INJECTION", f"Expected STATIC_FRAME_INJECTION, got {res.attack_type}"
    assert res.apcer_risk == "HIGH"
    print(f" PASS: Virtual camera static frame injection spoof caught. Attack: {res.attack_type}")

def test_screen_replay_moire_detection():
    real_img_path = PROJECT_ROOT / "WhatsApp Image 2026-09-25 at 10.32.28 AM.jpeg"
    img = cv2.imread(str(real_img_path))
    
    # Extract real face crop
    detector, _ = _get_models()
    detector.setInputSize((img.shape[1], img.shape[0]))
    _, faces = detector.detect(img)
    assert faces is not None and len(faces) > 0
    bx, by, bw, bh = [int(v) for v in faces[0][0:4]]
    face_crop = img[max(0, by):min(img.shape[0], by+bh), max(0, bx):min(img.shape[1], bx+bw)]

    # Add realistic screen subpixel periodic modulation (Moiré interference)
    moire_crop = face_crop.copy()
    y_coords, x_coords = np.mgrid[:moire_crop.shape[0], :moire_crop.shape[1]]
    moire_pattern = (18 * np.sin(2 * np.pi * x_coords / 4.0) + 18 * np.sin(2 * np.pi * y_coords / 4.0)).astype(np.int16)
    moire_crop = np.clip(moire_crop.astype(np.int16) + moire_pattern[:, :, None], 0, 255).astype(np.uint8)

    is_screen, peak_ratio, score = analyze_fft_screen_moire(moire_crop)
    assert is_screen is True, f"Expected Moiré screen detection, got peak_ratio={peak_ratio}"
    assert peak_ratio >= 2.20, f"Expected peak_ratio >= 2.20, got {peak_ratio}"
    assert score <= 0.40, f"Expected low liveness score for moiré screen, got {score}"
    print(f" PASS: Electronic screen replay Moiré spoof detected. Peak Ratio: {peak_ratio}, Score: {score}")

def test_multi_frame_micro_movement():
    real_img_path = PROJECT_ROOT / "WhatsApp Image 2026-09-25 at 10.32.28 AM.jpeg"
    img = cv2.imread(str(real_img_path))
    h, w = img.shape[:2]

    # Synthesize natural physiological micro-drift (0.5 to 2.0 pixel subtle shift and lighting variance)
    burst = []
    for i in range(5):
        # Subtle sub-pixel affine translation simulating human micro-movement
        M = np.float32([[1, 0, 0.4 * i], [0, 1, 0.3 * (i % 2)]])
        shifted = cv2.warpAffine(img, M, (w, h), borderMode=cv2.BORDER_REFLECT)
        # Subtle micro-luminance fluctuation
        shifted = np.clip(shifted.astype(int) + (i % 3 - 1), 0, 255).astype(np.uint8)
        burst.append(shifted)

    res = detect_face_liveness(burst)
    assert res.is_live is True, f"Expected micro-movement burst to be live, got {res.attack_type}"
    assert res.liveness_score >= 0.70
    assert "temporal_motion" in res.scores
    print(f" PASS: Physiological multi-frame micro-drift verified. Score: {res.liveness_score}")

def test_api_liveness_integration():
    client = TestClient(app)
    real_img_path = PROJECT_ROOT / "WhatsApp Image 2026-09-25 at 10.32.28 AM.jpeg"
    img = cv2.imread(str(real_img_path))
    _, buffer = cv2.imencode(".jpg", img)
    b64_str = f"data:image/jpeg;base64,{base64.b64encode(buffer).decode('utf-8')}"
    
    # 3-frame burst payload
    burst_json = json.dumps([b64_str, b64_str, b64_str])

    response = client.post(
        "/api/screen",
        data={
            "card_sample": "sample_pair_jaskirat",
            "live_data": b64_str,
            "live_frames_data": burst_json
        }
    )
    assert response.status_code == 200, response.text
    r = response.json()
    assert "liveness" in r, "Expected liveness field in response"
    assert "liveness_score" in r["liveness"]
    assert "attack_type" in r["liveness"]
    print(f" PASS: REST API /api/screen returns ISO/IEC 30107-3 Liveness payload: {r['liveness']['attack_type']}, Score: {r['liveness']['liveness_score']}")

if __name__ == "__main__":
    test_real_photo_liveness()
    test_static_frame_injection_spoof()
    test_screen_replay_moire_detection()
    test_multi_frame_micro_movement()
    test_api_liveness_integration()
    print("\nALL PRESENTATION ATTACK DETECTION (PAD) & LIVENESS TESTS PASSED SUCCESSFULLY!")
