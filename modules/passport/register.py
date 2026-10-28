"""
modules/passport/register.py - Passport Registration, Perspective Rectification & Field Cropping.
Conforms to ICAO Doc 9303 Part 4 TD3 standard (aspect ratio ~1.42).
"""

from typing import Tuple, Dict, List, Optional
import numpy as np
import cv2
from core.types import FieldCrop

# Canonical Dimensions for Indian Passport Data Page (1000 x 700, aspect ratio 1.428)
PASSPORT_CANONICAL_WIDTH = 1000
PASSPORT_CANONICAL_HEIGHT = 700

# Canonical Field Bounding Boxes (x, y, w, h) in canonical space
CANONICAL_PASSPORT_FIELDS = {
    "passport_no": (730, 45, 240, 55),
    "photo": (40, 140, 240, 320),
    "surname": (290, 105, 680, 50),
    "given_names": (290, 170, 680, 50),
    "nationality": (290, 235, 200, 45),
    "sex": (520, 235, 80, 45),
    "dob": (640, 235, 200, 45),
    "pob": (290, 295, 680, 45),
    "poi": (290, 355, 680, 45),
    "doi": (290, 415, 300, 45),
    "doe": (640, 415, 300, 45),
    "mrz": (25, 520, 950, 165),
}


def order_quad_points(pts: np.ndarray) -> np.ndarray:
    """
    Orders 4 points in [top-left, top-right, bottom-right, bottom-left] sequence.
    """
    rect = np.zeros((4, 2), dtype="float32")
    s = pts.sum(axis=1)
    rect[0] = pts[np.argmin(s)]      # Top-left (smallest sum)
    rect[2] = pts[np.argmax(s)]      # Bottom-right (largest sum)

    diff = np.diff(pts, axis=1)
    rect[1] = pts[np.argmin(diff)]   # Top-right (smallest difference)
    rect[3] = pts[np.argmax(diff)]   # Bottom-left (largest difference)
    return rect


def rectify_passport_perspective(
    image: np.ndarray,
    target_width: int = PASSPORT_CANONICAL_WIDTH,
    target_height: int = PASSPORT_CANONICAL_HEIGHT,
) -> Tuple[np.ndarray, float]:
    """
    Detects the 4 outer corners of the passport booklet/data page and applies
    homography perspective warping to transform into the canonical target dimensions.
    Returns: (rectified_image, quality_score)
    """
    if image is None or image.size == 0:
        raise ValueError("Image is empty or invalid.")

    orig_h, orig_w = image.shape[:2]
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image

    # Blur & Canny edge detection
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blurred, 50, 150)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    dilated = cv2.dilate(edges, kernel, iterations=2)

    contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    quad_contour = None
    max_area = 0.0
    min_area = (orig_w * orig_h) * 0.25  # Passport must cover at least 25% of image area

    # Sort contours by area descending
    for cnt in sorted(contours, key=cv2.contourArea, reverse=True)[:5]:
        area = cv2.contourArea(cnt)
        if area > min_area:
            peri = cv2.arcLength(cnt, True)
            approx = cv2.approxPolyDP(cnt, 0.02 * peri, True)
            if len(approx) == 4 and area > max_area:
                quad_contour = approx
                max_area = area
                break

    if quad_contour is not None:
        pts = quad_contour.reshape(4, 2)
        ordered_pts = order_quad_points(pts)

        dst_pts = np.array([
            [0, 0],
            [target_width - 1, 0],
            [target_width - 1, target_height - 1],
            [0, target_height - 1]
        ], dtype="float32")

        M = cv2.getPerspectiveTransform(ordered_pts, dst_pts)
        rectified = cv2.warpPerspective(image, M, (target_width, target_height))
        quality = 0.95
        return rectified, quality

    # Fallback: direct resize if pre-cropped or edges ambiguous
    rectified = cv2.resize(image, (target_width, target_height), interpolation=cv2.INTER_LINEAR)
    quality = 0.80
    return rectified, quality


def locate_mrz_strip_morphological(rectified_gray: np.ndarray) -> Tuple[int, int, int, int]:
    """
    Uses Blackhat morphology with a horizontal structuring element to isolate
    the dense, high-frequency monospace text of the 2-line MRZ band.
    Returns: (x, y, w, h) bounding box.
    """
    h, w = rectified_gray.shape[:2]
    # Restrict search to bottom 35% of page
    y_start = int(h * 0.65)
    bottom_crop = rectified_gray[y_start:, :]

    # Horizontal Blackhat kernel highlights dark horizontal characters on light background
    rect_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (17, 3))
    blackhat = cv2.morphologyEx(bottom_crop, cv2.MORPH_BLACKHAT, rect_kernel)

    # Compute horizontal gradients
    grad_x = cv2.Sobel(blackhat, ddepth=cv2.CV_32F, dx=1, dy=0, ksize=-1)
    grad_x = np.absolute(grad_x)
    min_v, max_v = np.min(grad_x), np.max(grad_x)
    grad_x = (255 * ((grad_x - min_v) / (max_v - min_v + 1e-6))).astype("uint8")

    # Blur, threshold & close
    grad_x = cv2.GaussianBlur(grad_x, (5, 5), 0)
    _, thresh = cv2.threshold(grad_x, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
    close_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (21, 5))
    closed = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, close_kernel)

    # Find contours in bottom region
    contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    mrz_boxes = []

    for cnt in contours:
        bx, by, bw, bh = cv2.boundingRect(cnt)
        aspect = bw / float(bh) if bh > 0 else 0
        # MRZ line or band has wide aspect ratio and spans significant width
        if aspect > 3.0 and bw > (w * 0.40):
            mrz_boxes.append((bx, y_start + by, bw, bh))

    if mrz_boxes:
        min_x = min(b[0] for b in mrz_boxes)
        min_y = min(b[1] for b in mrz_boxes)
        max_x = max(b[0] + b[2] for b in mrz_boxes)
        max_y = max(b[1] + b[3] for b in mrz_boxes)
        pad_y = 10
        min_y = max(0, min_y - pad_y)
        h_box = min(h - min_y, (max_y - min_y) + 2 * pad_y)
        w_box = max_x - min_x
        return (min_x, min_y, w_box, h_box)

    # Fallback to canonical box
    return CANONICAL_PASSPORT_FIELDS["mrz"]


def register_passport_page(
    image: np.ndarray,
) -> Tuple[np.ndarray, Dict[str, FieldCrop], float]:
    """
    Registers the input passport scan:
    1. Homography perspective unwarping to 1000x700 canonical space.
    2. Morphological refinement of the MRZ band.
    3. Extraction of canonical field crops.
    Returns: (rectified_image, crops_dict, registration_quality_score)
    """
    rectified, reg_quality = rectify_passport_perspective(image)
    gray = cv2.cvtColor(rectified, cv2.COLOR_BGR2GRAY) if len(rectified.shape) == 3 else rectified

    # Refine MRZ box dynamically
    mrz_box = locate_mrz_strip_morphological(gray)

    crops: Dict[str, FieldCrop] = {}

    for field_name, (x, y, fw, fh) in CANONICAL_PASSPORT_FIELDS.items():
        if field_name == "mrz":
            bx, by, bw, bh = mrz_box
        else:
            bx, by, bw, bh = x, y, fw, fh

        x1 = max(0, bx)
        y1 = max(0, by)
        x2 = min(PASSPORT_CANONICAL_WIDTH, bx + bw)
        y2 = min(PASSPORT_CANONICAL_HEIGHT, by + bh)

        crop_img = rectified[y1:y2, x1:x2].copy()
        crops[field_name] = FieldCrop(
            name=field_name,
            image=crop_img,
            bbox=(bx, by, bw, bh),
        )

    return rectified, crops, reg_quality
