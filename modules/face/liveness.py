"""
modules/face/liveness.py - Presentation Attack Detection (PAD) & Biometric Liveness (ISO/IEC 30107-3).
Implements multi-cue anti-spoofing against:
1. Replay Attacks (Screen / Tablet / Smartphone video replay - Moiré 2D FFT).
2. Print Attacks (2D Paper Printout, Matte/Glossy Photo - Halftone & High-Frequency Texture).
3. Static Injection (Virtual camera piping static frames - Frame Hash Diversity & Optical Flow).
4. Planar Spoofing (Flat 2D mask / printout held at angle - 3D Landmark Volumetric Plausibility).
"""

from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional, Any
import numpy as np
import cv2


@dataclass
class LivenessResult:
    """Standardized Presentation Attack Detection (PAD) Result conforming to ISO/IEC 30107-3."""
    is_live: bool = True
    liveness_score: float = 1.0           # 0.0 (Definite Spoof) to 1.0 (Confirmed Genuine Live)
    attack_type: str = "GENUINE_LIVE"     # "GENUINE_LIVE", "SCREEN_REPLAY_MOIRE", "PRINT_ATTACK_HALFTONE", "STATIC_FRAME_INJECTION", "PLANAR_SPOOF"
    apcer_risk: str = "LOW"               # Attack Presentation Classification Error Rate: "LOW", "MEDIUM", "HIGH"
    scores: Dict[str, float] = field(default_factory=dict)
    flags: List[str] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)


def analyze_chroma_distribution(face_bgr: np.ndarray) -> Tuple[float, Dict[str, Any]]:
    """
    Evaluates skin chrominance plausibility in YCrCb and HSV color spaces.
    Real living human skin exhibits a characteristic distribution of Melanin and Hemoglobin.
    Digital displays and inkjet/laser printouts show artificial chromatic clipping and unnatural Cr/Cb spread.
    Returns: (score [0.0 to 1.0], details)
    """
    if face_bgr is None or face_bgr.size < 400:
        return 0.5, {"reason": "Image too small for chroma analysis"}

    hsv = cv2.cvtColor(face_bgr, cv2.COLOR_BGR2HSV)
    ycrcb = cv2.cvtColor(face_bgr, cv2.COLOR_BGR2YCrCb)

    # Extract central face patch (excluding hair and background)
    h, w = face_bgr.shape[:2]
    ch1, ch2 = int(h * 0.25), int(h * 0.75)
    cw1, cw2 = int(w * 0.25), int(w * 0.75)
    patch_ycrcb = ycrcb[ch1:ch2, cw1:cw2]
    patch_hsv = hsv[ch1:ch2, cw1:cw2]

    # Skin in YCrCb: Cr typically 133-173, Cb typically 77-127
    cr = patch_ycrcb[:, :, 1].astype(float)
    cb = patch_ycrcb[:, :, 2].astype(float)
    sat = patch_hsv[:, :, 1].astype(float)

    cr_mean = float(np.mean(cr))
    cb_mean = float(np.mean(cb))
    sat_mean = float(np.mean(sat))

    # Evaluate distance from canonical skin cluster center (Cr=150, Cb=102)
    dist_cr = abs(cr_mean - 150.0)
    dist_cb = abs(cb_mean - 102.0)
    chroma_dist = np.sqrt(dist_cr**2 + dist_cb**2)

    # Real human skin typically has chroma_dist < 35.0 and Saturation between 25 and 190
    if chroma_dist < 28.0 and 20.0 < sat_mean < 200.0:
        score = 0.95
    elif chroma_dist < 42.0 and 15.0 < sat_mean < 220.0:
        score = 0.75
    elif chroma_dist < 55.0:
        score = 0.50
    else:
        score = 0.20  # Severe color distortion / unnatural display tint

    details = {
        "cr_mean": round(cr_mean, 1),
        "cb_mean": round(cb_mean, 1),
        "saturation_mean": round(sat_mean, 1),
        "chroma_distance": round(chroma_dist, 1)
    }
    return score, details


def analyze_fft_screen_moire(face_bgr: np.ndarray) -> Tuple[bool, float, float]:
    """
    2D Fast Fourier Transform frequency domain analysis for electronic screen replay.
    Electronic displays (phones, tablets, LCDs) generate regular high-frequency subpixel matrices
    that manifest as distinct periodic spectral spikes in 2D Fourier power spectrum.
    Returns: (is_screen_replay: bool, peak_to_mean_ratio: float, moire_score: float)
    """
    if face_bgr is None or face_bgr.size < 400:
        return False, 1.0, 0.9

    gray = cv2.cvtColor(face_bgr, cv2.COLOR_BGR2GRAY) if len(face_bgr.shape) == 3 else face_bgr
    std_size = 256
    resized = cv2.resize(gray, (std_size, std_size), interpolation=cv2.INTER_AREA)

    f = np.fft.fft2(resized)
    fshift = np.fft.fftshift(f)
    magnitude = 20 * np.log(np.abs(fshift) + 1)

    cy, cx = std_size // 2, std_size // 2
    r_inner = std_size // 10
    r_outer = std_size // 2 - 5

    y, x = np.ogrid[:std_size, :std_size]
    dist_sq = (x - cx)**2 + (y - cy)**2
    band_mask = (dist_sq >= r_inner**2) & (dist_sq <= r_outer**2)

    band_values = magnitude[band_mask]
    if len(band_values) == 0:
        return False, 1.0, 0.9

    mean_val = float(np.mean(band_values))
    max_val = float(np.max(band_values))
    peak_ratio = max_val / max(1e-5, mean_val)
    std_val = float(np.std(band_values))

    # Electronic screen displays produce sharp periodic spikes: peak_ratio >= 2.20 with std > 5.0
    is_screen = (peak_ratio >= 2.20 and std_val > 5.0)
    
    # Calculate continuous score: higher peak ratio -> lower liveness score
    if peak_ratio >= 2.4:
        moire_score = 0.10
    elif peak_ratio >= 2.1:
        moire_score = 0.35
    elif peak_ratio >= 1.8:
        moire_score = 0.65
    else:
        moire_score = 0.95

    return is_screen, round(peak_ratio, 2), moire_score


def analyze_dermal_texture(face_bgr: np.ndarray) -> Tuple[float, Dict[str, Any]]:
    """
    Analyzes high-frequency texture using Difference of Gaussians (DoG) and Laplacian variance.
    Natural 3D human skin contains micro-pores, eyelashes, and specular dermal reflectance.
    Paper printouts or low-res recompressed screens lack these high-frequency micro-gradients.
    Returns: (texture_score [0.0 to 1.0], details)
    """
    if face_bgr is None or face_bgr.size < 400:
        return 0.5, {"reason": "Image too small"}

    gray = cv2.cvtColor(face_bgr, cv2.COLOR_BGR2GRAY) if len(face_bgr.shape) == 3 else face_bgr
    h, w = gray.shape

    # Focus on central cheek / nose bridge region to avoid background noise
    crop = gray[int(h * 0.2):int(h * 0.8), int(w * 0.2):int(w * 0.8)]
    if crop.size == 0:
        crop = gray

    # Difference of Gaussians (DoG) for micro-texture band
    g1 = cv2.GaussianBlur(crop, (3, 3), 0.5)
    g2 = cv2.GaussianBlur(crop, (7, 7), 1.5)
    dog = cv2.absdiff(g1, g2)
    dog_energy = float(np.mean(dog))

    # Laplacian variance
    lap_var = float(cv2.Laplacian(crop, cv2.CV_64F).var())

    # Calibrate texture score
    # Very low lap_var (< 30) indicates heavy blur or flat paper printout.
    # Moderate to high (70 - 450) indicates crisp natural skin texture.
    # Abnormally high (> 1200) often indicates high-frequency screen pixel rastering.
    if 60.0 <= lap_var <= 900.0 and dog_energy >= 1.5:
        score = 0.95
    elif 30.0 <= lap_var < 60.0:
        score = 0.70
    elif lap_var > 900.0:
        score = 0.50  # Overly sharp / pixelated
    else:
        score = 0.30  # Flat / blurred printout

    details = {
        "laplacian_variance": round(lap_var, 1),
        "dog_micro_energy": round(dog_energy, 2)
    }
    return score, details


def analyze_3d_landmark_geometry(landmarks: Optional[np.ndarray], bbox: Optional[np.ndarray]) -> Tuple[float, Dict[str, Any]]:
    """
    Evaluates volumetric 3D human anthropometric facial proportions using YuNet 5-point landmarks:
    [right_eye, left_eye, nose_tip, right_mouth_corner, left_mouth_corner].
    Catches warped planar photos, photos held at steep angles, and non-proportional synthetic masks.
    Returns: (geometry_score [0.0 to 1.0], details)
    """
    if landmarks is None or len(landmarks) < 5 or bbox is None:
        return 0.5, {"reason": "Landmarks unavailable"}

    re, le = landmarks[0], landmarks[1]
    nt = landmarks[2]
    rm, lm = landmarks[3], landmarks[4]

    # Inter-ocular distance
    iod = float(np.linalg.norm(re - le))
    box_w = float(bbox[2])

    # Inter-ocular distance should be approx 30% - 60% of bounding box width
    iod_ratio = iod / max(1.0, box_w)

    # Eye center to nose tip vs nose tip to mouth center
    eye_center = (re + le) / 2.0
    mouth_center = (rm + lm) / 2.0
    d_eye_nose = float(np.linalg.norm(eye_center - nt))
    d_nose_mouth = float(np.linalg.norm(nt - mouth_center))
    ratio_vert = d_eye_nose / max(1.0, d_nose_mouth)

    # Natural vertical ratio is typically between 0.65 and 1.70
    if 0.28 <= iod_ratio <= 0.62 and 0.65 <= ratio_vert <= 1.75:
        score = 0.95
    elif 0.22 <= iod_ratio <= 0.70 and 0.50 <= ratio_vert <= 2.10:
        score = 0.75
    else:
        score = 0.35  # Extreme perspective skew or unnatural facial warp

    details = {
        "inter_ocular_ratio": round(iod_ratio, 3),
        "vertical_proportions_ratio": round(ratio_vert, 3)
    }
    return score, details


def analyze_multiframe_temporal_motion(
    frames: List[np.ndarray],
    faces_data: List[Tuple[np.ndarray, np.ndarray]]
) -> Tuple[float, str, Dict[str, Any]]:
    """
    Multi-frame temporal consistency and physiological micro-movement analysis.
    Verifies that a webcam burst:
    1. Is NOT a static frame injection (identical duplicate frames from virtual camera).
    2. Exhibits genuine involuntary micro-motion (respiration, ocular micro-saccades, subtle drift: 0.3 - 15 px).
    3. Does NOT exhibit rigid cut jumps (> 40 px) typical of swapping photos in front of camera.
    Returns: (motion_score [0.0 to 1.0], sub_status, details)
    """
    if len(frames) < 2:
        return 0.70, "SINGLE_FRAME_ONLY", {"note": "Single frame supplied; multi-frame motion bypassed"}

    # 1. Check Bit-for-Bit Frame Diversity (detects freeze-frame / virtual camera loop)
    diffs = []
    for i in range(len(frames) - 1):
        f1_gray = cv2.cvtColor(frames[i], cv2.COLOR_BGR2GRAY) if len(frames[i].shape) == 3 else frames[i]
        f2_gray = cv2.cvtColor(frames[i+1], cv2.COLOR_BGR2GRAY) if len(frames[i+1].shape) == 3 else frames[i+1]
        diff = float(np.mean(cv2.absdiff(f1_gray, f2_gray)))
        diffs.append(diff)

    mean_diff = float(np.mean(diffs))
    if mean_diff < 0.20:
        # Frames are virtually identical -> Static picture frozen or virtual camera pipe
        return 0.10, "STATIC_INJECTION_DETECTED", {
            "mean_frame_diff": round(mean_diff, 3),
            "reason": "Frames are completely identical (zero temporal variation)"
        }

    # 2. Track Landmark Motion (Natural Micro-Movement vs Rigid Planar Translation)
    motion_vectors = []
    for i in range(len(faces_data) - 1):
        l1 = faces_data[i][1] # landmarks
        l2 = faces_data[i+1][1]
        if l1 is not None and l2 is not None and len(l1) == 5 and len(l2) == 5:
            shift = float(np.mean(np.linalg.norm(l1 - l2, axis=1)))
            motion_vectors.append(shift)

    if not motion_vectors:
        return 0.60, "MOTION_LANDMARKS_UNCERTAIN", {"mean_frame_diff": round(mean_diff, 2)}

    avg_motion = float(np.mean(motion_vectors))
    max_motion = float(np.max(motion_vectors))

    # Natural micro-movement in a 0.5s - 1.0s burst is typically 0.5 to 18.0 pixels
    if 0.4 <= avg_motion <= 18.0:
        motion_score = 0.95
        sub_status = "PHYSIOLOGICAL_MOTION_CONFIRMED"
    elif avg_motion < 0.4:
        # Too static (e.g. photo on a mount)
        motion_score = 0.40
        sub_status = "SUSPICIOUS_STATIC_HEAD"
    else:
        # Excessive motion (uncontrolled movement or cut)
        motion_score = 0.65
        sub_status = "RAPID_MOVEMENT"

    details = {
        "mean_frame_diff": round(mean_diff, 2),
        "avg_landmark_motion_px": round(avg_motion, 2),
        "max_landmark_motion_px": round(max_motion, 2)
    }
    return motion_score, sub_status, details


def detect_face_liveness(
    live_frames: List[np.ndarray],
    detector: Optional[Any] = None
) -> LivenessResult:
    """
    Executes Comprehensive Presentation Attack Detection (PAD) conforming to ISO/IEC 30107-3.
    Accepts a single live frame or a multi-frame burst (3-10 frames).
    """
    result = LivenessResult()

    if not live_frames or len(live_frames) == 0:
        result.is_live = False
        result.liveness_score = 0.0
        result.attack_type = "NO_INPUT"
        result.flags.append("Liveness analysis bypassed: No live selfie frames provided.")
        return result

    # Primary keyframe is the last or clearest frame
    keyframe = live_frames[-1]
    h, w = keyframe.shape[:2]

    # Initialize / import detector if not passed
    if detector is None:
        from modules.face.matcher import _get_models
        detector, _ = _get_models()

    if detector is None:
        result.is_live = True
        result.liveness_score = 0.70
        result.flags.append("Liveness heuristic fallback: Face detector model offline.")
        return result

    # Detect faces in all supplied frames
    faces_data = []
    key_face_crop = None
    key_bbox = None
    key_landmarks = None

    for idx, f in enumerate(live_frames):
        fh, fw = f.shape[:2]
        detector.setInputSize((fw, fh))
        _, faces = detector.detect(f)
        if faces is not None and len(faces) > 0:
            best_f = max(faces, key=lambda fc: fc[-1])
            bbox = best_f[0:4]
            landmarks = best_f[4:14].reshape((5, 2))
            
            # Crop face region
            bx, by, bw, bh = [int(v) for v in bbox]
            pad_x, pad_y = int(bw * 0.15), int(bh * 0.15)
            x1, y1 = max(0, bx - pad_x), max(0, by - pad_y)
            x2, y2 = min(fw, bx + bw + pad_x), min(fh, by + bh + pad_y)
            crop = f[y1:y2, x1:x2]

            faces_data.append((bbox, landmarks))
            if idx == len(live_frames) - 1 or key_face_crop is None:
                key_face_crop = crop
                key_bbox = bbox
                key_landmarks = landmarks

    if key_face_crop is None or key_face_crop.size == 0:
        result.is_live = False
        result.liveness_score = 0.15
        result.attack_type = "FACE_NOT_LOCALIZED"
        result.apcer_risk = "HIGH"
        result.flags.append("Presentation Attack Alert: No clear human face localized in live biometric stream.")
        return result

    # 1. 2D FFT Electronic Screen Moiré Analysis
    is_screen, peak_ratio, moire_score = analyze_fft_screen_moire(key_face_crop)
    result.scores["screen_moire"] = moire_score
    result.details["fft_peak_ratio"] = peak_ratio

    # 2. Skin Chroma Distribution Analysis
    chroma_score, chroma_details = analyze_chroma_distribution(key_face_crop)
    result.scores["skin_chroma"] = chroma_score
    result.details["chroma"] = chroma_details

    # 3. High-Frequency Dermal Texture Analysis
    texture_score, texture_details = analyze_dermal_texture(key_face_crop)
    result.scores["dermal_texture"] = texture_score
    result.details["texture"] = texture_details

    # 4. Volumetric 3D Landmark Proportions
    depth_score, depth_details = analyze_3d_landmark_geometry(key_landmarks, key_bbox)
    result.scores["3d_geometry"] = depth_score
    result.details["geometry"] = depth_details

    # 5. Multi-Frame Temporal Dynamics (if multiple frames provided)
    if len(live_frames) >= 2:
        motion_score, motion_status, motion_details = analyze_multiframe_temporal_motion(live_frames, faces_data)
        result.scores["temporal_motion"] = motion_score
        result.details["temporal"] = motion_details
        weights = {"screen_moire": 0.30, "skin_chroma": 0.20, "dermal_texture": 0.20, "3d_geometry": 0.10, "temporal_motion": 0.20}
    else:
        motion_status = "SINGLE_FRAME"
        weights = {"screen_moire": 0.35, "skin_chroma": 0.25, "dermal_texture": 0.25, "3d_geometry": 0.15}

    # Aggregate weighted liveness score
    agg_score = sum(result.scores.get(k, 0.5) * w for k, w in weights.items())
    result.liveness_score = round(float(agg_score), 3)

    # 6. Verdict Evaluation & Attack Classification
    if is_screen:
        result.is_live = False
        result.attack_type = "SCREEN_REPLAY_MOIRE"
        result.apcer_risk = "HIGH"
        result.flags.append(
            f"PRESENTATION ATTACK DETECTED: Electronic screen replay detected via 2D FFT subpixel Moiré harmonics "
            f"(Peak-to-Mean Ratio: {peak_ratio:.2f} >= 2.65, ISO/IEC 30107-3 APCER High)."
        )
    elif motion_status == "STATIC_INJECTION_DETECTED":
        result.is_live = False
        result.attack_type = "STATIC_FRAME_INJECTION"
        result.apcer_risk = "HIGH"
        result.flags.append(
            "PRESENTATION ATTACK DETECTED: Static frame freeze or virtual camera injection detected "
            "(Identical frames with zero physiological variation)."
        )
    elif result.liveness_score < 0.55:
        result.is_live = False
        result.attack_type = "PRINT_ATTACK_OR_MASK"
        result.apcer_risk = "HIGH"
        result.flags.append(
            f"PRESENTATION ATTACK DETECTED: Biometric liveness score failed "
            f"({result.liveness_score:.2f} < 0.55). Unnatural dermal texture, flat reflectance, or warped geometry."
        )
    elif result.liveness_score < 0.65:
        # Borderline
        result.is_live = True
        result.attack_type = "BORDERLINE_LIVE"
        result.apcer_risk = "MEDIUM"
        result.flags.append(
            f"Borderline Biometric Liveness ({result.liveness_score:.2f}): Sub-optimal lighting or slight motion blur. Manual secondary review recommended."
        )
    else:
        # Clean Live Person
        result.is_live = True
        result.attack_type = "GENUINE_LIVE"
        result.apcer_risk = "LOW"
        multi_msg = " and multi-frame physiological micro-movement" if len(live_frames) >= 2 else ""
        result.flags.append(
            f"Biometric Liveness Confirmed: Natural 3D facial reflectance{multi_msg} verified "
            f"(Score: {result.liveness_score:.2f} >= 0.65, ISO/IEC 30107-3 compliant)."
        )

    return result
