"""
modules/synthetic/degradations.py - Realistic Physical & Camera Degradation Engine.
Simulates environmental and capture noise:
1. Gaussian & Motion Blur (camera shake, out-of-focus)
2. Glare & Specular Reflection (flash reflection, ambient light spot)
3. Perspective Tilt & Skew (handheld smartphone capture)
4. Screen Moiré & Pixel Grids (digital display replay / presentation attack)
5. Heavy JPEG Compression artifacts
"""

import math
import random
from typing import Optional, Tuple
import numpy as np
import cv2


def apply_gaussian_blur(image: np.ndarray, ksize: int = 15, sigma: float = 5.0) -> np.ndarray:
    """Applies severe or mild Gaussian blur to simulate out-of-focus capture."""
    k = ksize if ksize % 2 == 1 else ksize + 1
    return cv2.GaussianBlur(image, (k, k), sigma)


def apply_motion_blur(image: np.ndarray, size: int = 15, angle: float = 45.0) -> np.ndarray:
    """Simulates camera shake or moving document during mobile scanning."""
    kernel = np.zeros((size, size))
    rad = math.radians(angle)
    dx = math.cos(rad)
    dy = math.sin(rad)
    center = size // 2

    for i in range(size):
        offset = i - center
        x = int(round(center + offset * dx))
        y = int(round(center + offset * dy))
        if 0 <= x < size and 0 <= y < size:
            kernel[y, x] = 1.0

    k_sum = kernel.sum()
    if k_sum > 0:
        kernel /= k_sum
    else:
        kernel[center, center] = 1.0

    return cv2.filter2D(image, -1, kernel)


def apply_glare(
    image: np.ndarray,
    center: Optional[Tuple[int, int]] = None,
    radius: Optional[int] = None,
    intensity: float = 0.85
) -> np.ndarray:
    """
    Simulates high-intensity specular flash or ceiling spotlight overexposure.
    Blinds OCR and QR scanning in localized region.
    """
    h, w = image.shape[:2]
    if center is None:
        cx = random.randint(int(w * 0.2), int(w * 0.8))
        cy = random.randint(int(h * 0.2), int(h * 0.8))
    else:
        cx, cy = center

    if radius is None:
        radius = random.randint(int(min(h, w) * 0.2), int(min(h, w) * 0.45))

    y, x = np.ogrid[:h, :w]
    dist_sq = (x - cx) ** 2 + (y - cy) ** 2
    r_sq = radius ** 2

    # Smooth quadratic falloff
    mask = np.clip(1.0 - (dist_sq / r_sq), 0.0, 1.0)
    mask = (mask ** 2) * intensity

    result = image.astype(np.float32)
    for c in range(3):
        result[:, :, c] = result[:, :, c] * (1.0 - mask) + 255.0 * mask

    return np.clip(result, 0, 255).astype(np.uint8)


def apply_perspective_warp(image: np.ndarray, max_distortion: float = 0.08) -> np.ndarray:
    """Simulates realistic handheld camera perspective tilt."""
    h, w = image.shape[:2]
    dx = w * max_distortion
    dy = h * max_distortion

    src_pts = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
    dst_pts = np.float32([
        [random.uniform(0, dx), random.uniform(0, dy)],
        [w - random.uniform(0, dx), random.uniform(0, dy)],
        [w - random.uniform(0, dx), h - random.uniform(0, dy)],
        [random.uniform(0, dx), h - random.uniform(0, dy)]
    ])

    M = cv2.getPerspectiveTransform(src_pts, dst_pts)
    warped = cv2.warpPerspective(image, M, (w, h), borderMode=cv2.BORDER_REPLICATE)
    return warped


def apply_jpeg_compression(image: np.ndarray, quality: int = 25) -> np.ndarray:
    """Simulates multi-generation compression artifacts (common in messaging forwards)."""
    quality = max(5, min(95, quality))
    encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), quality]
    _, enc = cv2.imencode(".jpg", image, encode_param)
    return cv2.imdecode(enc, cv2.IMREAD_COLOR)


def apply_screen_moire(
    image: np.ndarray,
    frequency: float = 0.15,
    strength: float = 0.35,
    grid_type: str = "lcd"
) -> np.ndarray:
    """
    Simulates high-frequency optical Moiré patterns and pixel subgrid pitch
    characteristic of an electronic LCD/OLED display capture (Presentation Attack / PAD).
    """
    h, w = image.shape[:2]
    y_coords, x_coords = np.ogrid[:h, :w]

    # Diagonal and cross-hatch high-frequency ripples
    wave1 = np.sin(x_coords * frequency + y_coords * frequency * 0.7)
    wave2 = np.cos(x_coords * frequency * 0.5 - y_coords * frequency * 0.9)
    moire_pattern = (wave1 + wave2) * 0.5 * strength

    # RGB subpixel stripe effect
    subpixel_mask = np.zeros((h, w, 3), dtype=np.float32)
    for c in range(3):
        # Color phase offset simulates physical RGB subpixel arrangement
        subpixel_mask[:, :, c] = np.sin((x_coords + c * 2) * (math.pi / 1.5)) * (strength * 0.5)

    img_float = image.astype(np.float32) / 255.0
    for c in range(3):
        img_float[:, :, c] += moire_pattern + subpixel_mask[:, :, c]

    result = np.clip(img_float * 255.0, 0, 255).astype(np.uint8)
    return result


def apply_random_degradation(image: np.ndarray, severity: str = "moderate") -> np.ndarray:
    """Applies a combination of realistic distortions according to chosen severity."""
    out = image.copy()
    if severity == "mild":
        out = apply_jpeg_compression(out, quality=random.randint(55, 75))
        if random.random() < 0.3:
            out = apply_gaussian_blur(out, ksize=5, sigma=1.2)
    elif severity == "moderate":
        out = apply_jpeg_compression(out, quality=random.randint(30, 50))
        if random.random() < 0.5:
            out = apply_perspective_warp(out, max_distortion=0.04)
        if random.random() < 0.4:
            out = apply_gaussian_blur(out, ksize=7, sigma=2.0)
    elif severity == "severe":
        out = apply_jpeg_compression(out, quality=random.randint(15, 25))
        out = apply_perspective_warp(out, max_distortion=0.08)
        out = apply_gaussian_blur(out, ksize=13, sigma=4.0)
        if random.random() < 0.4:
            out = apply_glare(out, intensity=0.75)
    return out
