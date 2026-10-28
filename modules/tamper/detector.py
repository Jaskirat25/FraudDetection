"""
modules/tamper/detector.py - Presentation Attack Detection (PAD) & Forensic Tamper Analysis (L4).
Implements:
1. Screen-Replay / Moiré Detection (2D FFT frequency periodic peak-to-mean analysis).
2. Specular Glare / Flash Overexposure Detection.
3. Defocus Blur / Edge Variance Analysis.
4. Noise Residual Splicing Detection.
"""

from typing import List, Optional
import numpy as np
import cv2
from core.types import FieldCrop, ModuleResult


def analyze_fft_moire(gray_img: np.ndarray) -> tuple:
    """
    Analyzes 2D Fourier transform power spectrum for periodic spikes indicative
    of an electronic screen subpixel display matrix (Moiré interference).
    Returns: (is_screen_replay: bool, peak_ratio: float, details: str)
    """
    if gray_img is None or gray_img.size < 400:
        return False, 1.0, "Crop too small for frequency analysis"

    # Resize to standard power-of-2 dimensions for uniform FFT
    h, w = gray_img.shape
    std_size = 256
    resized = cv2.resize(gray_img, (std_size, std_size), interpolation=cv2.INTER_AREA)

    # 2D FFT
    f = np.fft.fft2(resized)
    fshift = np.fft.fftshift(f)
    magnitude = 20 * np.log(np.abs(fshift) + 1)

    cy, cx = std_size // 2, std_size // 2
    r_inner = std_size // 10   # Exclude DC baseline
    r_outer = std_size // 2 - 5

    y, x = np.ogrid[:std_size, :std_size]
    dist_sq = (x - cx)**2 + (y - cy)**2
    band_mask = (dist_sq >= r_inner**2) & (dist_sq <= r_outer**2)

    band_values = magnitude[band_mask]
    if len(band_values) == 0:
        return False, 1.0, "Empty frequency band"

    mean_val = float(np.mean(band_values))
    max_val = float(np.max(band_values))
    peak_ratio = max_val / max(1e-5, mean_val)

    # Threshold: Screens produce pronounced periodic spikes (peak_ratio >= 2.8 with high variance)
    # Printed cards have diffuse continuous spectrum (peak_ratio typically < 2.0)
    std_val = float(np.std(band_values))
    is_screen = (peak_ratio >= 2.8 and std_val > 8.0)

    return is_screen, round(peak_ratio, 2), f"FFT Peak-to-Mean Ratio: {peak_ratio:.2f}"


def analyze_glare(gray_img: np.ndarray) -> tuple:
    """
    Measures percentage of overexposed/saturated pixels (glare from flash or harsh lighting).
    """
    if gray_img is None or gray_img.size == 0:
        return False, 0.0
    glare_ratio = float(np.mean(gray_img >= 253))
    # If > 10% of pixels in crop are clipped white, critical field content is obliterated
    return (glare_ratio >= 0.10), round(glare_ratio, 3)


def analyze_blur(gray_img: np.ndarray) -> tuple:
    """
    Measures image sharpness using Laplacian variance.
    """
    if gray_img is None or gray_img.size == 0:
        return True, 0.0
    var = float(cv2.Laplacian(gray_img, cv2.CV_64F).var())
    # Critical blur threshold: < 25.0 (severe defocus where text/features cannot be resolved)
    return (var < 25.0), round(var, 1)


def detect_tamper(
    crops: List[FieldCrop],
    full_image: Optional[np.ndarray] = None
) -> ModuleResult:
    """
    Computes per-field and full-card forensic anomaly scores.
    """
    result = ModuleResult(module_name="tamper_detection")
    
    # 1. Full-Document Screen Replay Analysis (if provided)
    if full_image is not None and full_image.size > 0:
        gray_full = cv2.cvtColor(full_image, cv2.COLOR_BGR2GRAY) if len(full_image.shape) == 3 else full_image
        is_screen, peak_ratio, details = analyze_fft_moire(gray_full)
        result.evidence["full_card_fft_peak_ratio"] = peak_ratio

        if is_screen:
            result.flags.append(f"PRESENTATION ATTACK ALERT: Digital screen replay detected via 2D FFT Moiré subpixel harmonics ({details}).")
            result.scores["screen_replay"] = 1.0
            result.hard_fail = True

    # 2. Per-Crop Forensic Inspection
    photo_noise_var = None
    background_noise_var = None

    for crop in crops:
        img = crop.image
        if img is None or img.size == 0:
            result.scores[crop.name] = 0.05
            continue

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if len(img.shape) == 3 else img
        crop_score = 0.05

        # Check Glare (exclude binary 2D QR matrix where pure white modules are naturally 255)
        if crop.name != "qr_code":
            has_glare, glare_val = analyze_glare(gray)
            if has_glare:
                result.flags.append(f"RETAKE ADVICE: Severe specular glare in '{crop.name}' ({glare_val*100:.1f}% pixels overexposed).")
                crop_score = max(crop_score, 0.35)

        # Check Blur on critical crops
        if crop.name in ("photo", "dob", "aadhaar_no", "qr_code"):
            is_blurry, blur_val = analyze_blur(gray)
            if is_blurry:
                result.flags.append(f"RETAKE ADVICE: Crop '{crop.name}' is out-of-focus or blurred (sharpness {blur_val:.1f} < 25.0).")
                crop_score = max(crop_score, 0.30)

        # High-pass noise residual variance (for splicing detection)
        median = cv2.medianBlur(gray, 3)
        residual = cv2.subtract(gray, median)
        noise_var = float(np.var(residual))

        if crop.name == "photo":
            photo_noise_var = noise_var
            # Also check photo crop for digital screen capture
            is_screen_photo, p_ratio, _ = analyze_fft_moire(gray)
            if is_screen_photo:
                result.flags.append("PRESENTATION ATTACK: Photo region displays electronic display Moiré patterns.")
                crop_score = 1.0
                result.hard_fail = True
        elif crop.name in ("card_front", "aadhar-back"):
            background_noise_var = noise_var

        result.scores[crop.name] = round(crop_score, 2)

    # 3. Splicing / Photo-Paste Anomaly (Noise Discrepancy)
    if photo_noise_var is not None and background_noise_var is not None and background_noise_var > 0:
        ratio = photo_noise_var / max(1e-5, background_noise_var)
        result.evidence["noise_residual_ratio"] = round(ratio, 2)
        if ratio > 5.0 or ratio < 0.2:
            result.flags.append(f"Forensic Anomaly: Photo noise signature diverges significantly from card substrate (Ratio: {ratio:.2f}). Possible digital paste.")
            result.scores["photo_splicing"] = 0.40

    return result
