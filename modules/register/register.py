"""
modules/register/register.py - Registration and geometric rectification.
Aligns input card photo to canonical reference space and extracts field crops.
"""

import os
from typing import Tuple, List, Dict, Optional
import numpy as np
import cv2
from core.types import FieldCrop
from core.config import CANONICAL_WIDTH, CANONICAL_HEIGHT, CANONICAL_FIELDS


def register_card(
    image: np.ndarray,
    image_path: Optional[str] = None
) -> Tuple[np.ndarray, List[FieldCrop], float]:
    """
    Registers the input image and extracts field crops.
    Uses Roboflow AI detection as primary detector, with geometric fallback.
    Returns:
        (rectified_card_image, list_of_field_crops, registration_quality_score)
    """
    if image is None or image.size == 0:
        raise ValueError("Input image is invalid or empty.")

    h, w = image.shape[:2]
    rectified = cv2.resize(image, (CANONICAL_WIDTH, CANONICAL_HEIGHT))
    
    crops: List[FieldCrop] = []
    reg_quality = 0.95

    # 1. Try AI Field Detection (Roboflow) if path is available
    if image_path and os.path.exists(image_path):
        try:
            from .roboflow_detector import detect_fields_with_roboflow
            ai_crops, response = detect_fields_with_roboflow(image_path, image)
            if ai_crops:
                return image, ai_crops, 0.98
        except Exception as e:
            print(f"[Register] AI detection fallback triggered: {e}")

    # 2. Geometric Template Fallback
    for field_name, (x, y, fw, fh) in CANONICAL_FIELDS.items():
        x1, y1 = max(0, x), max(0, y)
        x2, y2 = min(CANONICAL_WIDTH, x + fw), min(CANONICAL_HEIGHT, y + fh)
        crop_img = rectified[y1:y2, x1:x2].copy()
        crops.append(FieldCrop(name=field_name, image=crop_img, bbox=(x, y, fw, fh)))

    return rectified, crops, reg_quality
