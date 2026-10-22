"""
modules/face/matcher.py - 3-Way Biometric Face Verification (Layer 5).
Compares:
1. Card Crop Photo <-> QR-Embedded Photo (Instant Photo-Swap Forgery Detection - Tier 1)
2. Card Crop Photo <-> Live Selfie Photo (Impostor Detection - Tier 2)
3. QR-Embedded Photo <-> Live Selfie Photo (Cryptographic Identity Anchor - Tier 1)
"""

import os
import urllib.request
from pathlib import Path
from typing import Optional, Tuple, Dict, Any
import numpy as np
import cv2

from core.types import ModuleResult

# Default SFace Cosine Similarity Threshold (standard recommended by OpenCV Zoo is 0.363)
# Cosine similarity > 0.363 means same person.
SFACE_COSINE_THRESHOLD = 0.363

# Paths to models
MODELS_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "models"
YUNET_PATH = MODELS_DIR / "face_detection_yunet_2023mar.onnx"
SFACE_PATH = MODELS_DIR / "face_recognition_sface_2021dec.onnx"

MODEL_URLS = {
    YUNET_PATH: "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx",
    SFACE_PATH: "https://github.com/opencv/opencv_zoo/raw/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx",
}

_DETECTOR = None
_RECOGNIZER = None


def _ensure_models_exist():
    """Ensures ONNX model files are downloaded in data/models/."""
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    for model_path, url in MODEL_URLS.items():
        if not model_path.exists() or model_path.stat().st_size < 1000:
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=30) as resp, open(model_path, "wb") as out_f:
                    while True:
                        chunk = resp.read(1024 * 1024)
                        if not chunk:
                            break
                        out_f.write(chunk)
            except Exception as e:
                print(f"[Face Matcher Warning]: Failed downloading {model_path.name}: {e}")


def _get_models():
    """Initializes and returns cached instances of YuNet detector and SFace recognizer."""
    global _DETECTOR, _RECOGNIZER
    if _DETECTOR is None or _RECOGNIZER is None:
        _ensure_models_exist()
        if YUNET_PATH.exists() and SFACE_PATH.exists():
            try:
                _DETECTOR = cv2.FaceDetectorYN.create(
                    str(YUNET_PATH),
                    "",
                    (300, 300),
                    score_threshold=0.5,
                    nms_threshold=0.3,
                    top_k=5000,
                )
                _RECOGNIZER = cv2.FaceRecognizerSF.create(str(SFACE_PATH), "")
            except Exception as e:
                print(f"[Face Matcher Error]: Failed initializing models: {e}")
                _DETECTOR = None
                _RECOGNIZER = None
    return _DETECTOR, _RECOGNIZER


def extract_face_embedding(image: Optional[np.ndarray]) -> Tuple[Optional[np.ndarray], Optional[np.ndarray]]:
    """
    Detects face, performs affine landmark alignment to 112x112, and extracts 128-D L2 embedding.
    Returns:
        (embedding_128d, aligned_face_crop) or (None, None)
    """
    if image is None or image.size == 0:
        return None, None

    detector, recognizer = _get_models()
    if detector is None or recognizer is None:
        return None, None

    # Handle grayscale or RGBA
    if len(image.shape) == 2:
        img_bgr = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    elif image.shape[2] == 4:
        img_bgr = cv2.cvtColor(image, cv2.COLOR_BGRA2BGR)
    else:
        img_bgr = image.copy()

    h, w = img_bgr.shape[:2]

    # Attempt 1: Native size detection
    detector.setInputSize((w, h))
    _, faces = detector.detect(img_bgr)

    # Attempt 2: If image is very small (e.g. 60x60 QR photo), upscale 2x
    if faces is None or len(faces) == 0:
        if min(w, h) < 120:
            upscaled = cv2.resize(img_bgr, (w * 2, h * 2), interpolation=cv2.INTER_CUBIC)
            detector.setInputSize((w * 2, h * 2))
            _, faces = detector.detect(upscaled)
            if faces is not None and len(faces) > 0:
                img_bgr = upscaled

    # Attempt 3: Contrast enhancement (CLAHE) for low-contrast/dark card crops
    if faces is None or len(faces) == 0:
        lab = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        cl = clahe.apply(l)
        enhanced = cv2.cvtColor(cv2.merge((cl, a, b)), cv2.COLOR_LAB2BGR)
        detector.setInputSize((enhanced.shape[1], enhanced.shape[0]))
        _, faces = detector.detect(enhanced)
        if faces is not None and len(faces) > 0:
            img_bgr = enhanced

    if faces is None or len(faces) == 0:
        return None, None

    # Select the highest confidence face
    best_face = max(faces, key=lambda f: f[-1])
    try:
        aligned_face = recognizer.alignCrop(img_bgr, best_face)
        feat = recognizer.feature(aligned_face)
        return feat, aligned_face
    except Exception as e:
        print(f"[Face Alignment Error]: {e}")
        return None, None


def compare_embeddings(feat1: np.ndarray, feat2: np.ndarray) -> Tuple[float, float, bool]:
    """
    Computes cosine similarity and cosine distance between two face embeddings.
    Returns:
        (cosine_similarity, cosine_distance, is_match)
    """
    _, recognizer = _get_models()
    if recognizer is not None:
        cosine_sim = float(recognizer.match(feat1, feat2, cv2.FaceRecognizerSF_FR_COSINE))
    else:
        # Fallback numpy cosine similarity
        norm1 = np.linalg.norm(feat1)
        norm2 = np.linalg.norm(feat2)
        cosine_sim = float(np.dot(feat1.flatten(), feat2.flatten()) / (norm1 * norm2 + 1e-9))

    cosine_dist = max(0.0, 1.0 - cosine_sim)
    is_match = cosine_sim >= SFACE_COSINE_THRESHOLD
    return cosine_sim, cosine_dist, is_match


def verify_face(
    card_photo: Optional[np.ndarray],
    live_photo: Optional[np.ndarray] = None,
    qr_photo: Optional[np.ndarray] = None
) -> ModuleResult:
    """
    Performs 3-Way Face Verification:
    1. Card Photo <-> QR Photo (Detects Photo-Swap: Tier 1 Hard Reject)
    2. Card Photo <-> Live Selfie (Detects Impostor: Tier 2 Flag)
    3. QR Photo <-> Live Selfie (Cryptographic Anchor: Tier 1 Hard Reject)
    """
    result = ModuleResult(module_name="face_verification")
    result.evidence["threshold_cosine"] = SFACE_COSINE_THRESHOLD

    # 1. Extract Embeddings
    card_feat, card_aligned = extract_face_embedding(card_photo)
    qr_feat, qr_aligned = extract_face_embedding(qr_photo)
    live_feat, live_aligned = extract_face_embedding(live_photo)

    result.evidence["card_face_detected"] = card_feat is not None
    result.evidence["qr_face_detected"] = qr_feat is not None
    result.evidence["live_face_detected"] = live_feat is not None

    # Track evaluated face pairs
    evaluated_pairs = 0

    # -------------------------------------------------------------
    # Pair 1: Card Photo <-> QR Photo (Photo-Swap Forgery Check)
    # -------------------------------------------------------------
    if card_feat is not None and qr_feat is not None:
        evaluated_pairs += 1
        sim, dist, is_match = compare_embeddings(card_feat, qr_feat)
        result.evidence["card_qr_cosine_sim"] = round(sim, 4)
        result.evidence["card_qr_distance"] = round(dist, 4)

        if not is_match:
            # Definite Photo-Swap: Someone pasted a different face on an authentic card
            result.hard_fail = True
            result.scores["photo"] = 1.0
            result.scores["photo_swap"] = 1.0
            result.flags.append(
                f"Biometric Photo-Swap FRAUD: Physical card photo does not match cryptographically signed QR photo "
                f"(Cosine Sim: {sim:.3f} < {SFACE_COSINE_THRESHOLD})"
            )
        else:
            result.scores["photo"] = 0.0
            result.scores["photo_swap"] = 0.0
            result.flags.append(
                f"Biometric Match: Physical card photo matches cryptographically signed QR photo "
                f"(Cosine Sim: {sim:.3f} >= {SFACE_COSINE_THRESHOLD})"
            )
    elif card_photo is not None and qr_photo is not None:
        # Both photos existed but at least one face could not be detected
        missing = []
        if card_feat is None:
            missing.append("card surface photo")
        if qr_feat is None:
            missing.append("QR-embedded photo")
        result.flags.append(f"Face biometrics degraded: Unable to locate clear facial landmarks in {', '.join(missing)}.")
        result.scores["photo_consistency"] = 0.25

    # -------------------------------------------------------------
    # Pair 2: Card Photo <-> Live Selfie (Impostor Check)
    # -------------------------------------------------------------
    if card_feat is not None and live_feat is not None:
        evaluated_pairs += 1
        sim, dist, is_match = compare_embeddings(card_feat, live_feat)
        result.evidence["card_live_cosine_sim"] = round(sim, 4)
        result.evidence["card_live_distance"] = round(dist, 4)

        if not is_match:
            result.scores["face_mismatch_live"] = 1.0
            result.flags.append(
                f"Identity Mismatch: Live selfie does not match physical cardholder photo "
                f"(Cosine Sim: {sim:.3f} < {SFACE_COSINE_THRESHOLD})"
            )
        else:
            result.scores["face_mismatch_live"] = 0.0
            result.flags.append(
                f"Identity Verified: Live selfie matches physical card photo "
                f"(Cosine Sim: {sim:.3f} >= {SFACE_COSINE_THRESHOLD})"
            )

    # -------------------------------------------------------------
    # Pair 3: QR Photo <-> Live Selfie (Cryptographic Anchor Check)
    # -------------------------------------------------------------
    if qr_feat is not None and live_feat is not None:
        evaluated_pairs += 1
        sim, dist, is_match = compare_embeddings(qr_feat, live_feat)
        result.evidence["qr_live_cosine_sim"] = round(sim, 4)
        result.evidence["qr_live_distance"] = round(dist, 4)

        if not is_match:
            # Person present does not match the UIDAI digitally signed face
            result.hard_fail = True
            result.scores["qr_live_mismatch"] = 1.0
            result.flags.append(
                f"Cryptographic Identity FRAUD: Live selfie does not match UIDAI signed QR photo "
                f"(Cosine Sim: {sim:.3f} < {SFACE_COSINE_THRESHOLD})"
            )
        else:
            result.scores["qr_live_mismatch"] = 0.0
            result.flags.append(
                f"Cryptographic Identity Confirmed: Live selfie matches UIDAI signed QR photo "
                f"(Cosine Sim: {sim:.3f} >= {SFACE_COSINE_THRESHOLD})"
            )

    # If no face pairs could be evaluated
    if evaluated_pairs == 0:
        if card_photo is None and qr_photo is None and live_photo is None:
            result.flags.append("Face verification skipped: No face photos provided.")
        elif qr_photo is None and live_photo is None:
            result.flags.append("Face verification standby: Only card photo available (no QR photo or live selfie to verify against).")
            result.scores["photo"] = 0.05

    return result
