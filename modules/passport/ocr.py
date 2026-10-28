"""
modules/passport/ocr.py - Passport MRZ & VIZ OCR Extraction Engine.
Uses EasyOCR with restricted ICAO charset allowlist for MRZ and structured cleaning for VIZ.
"""

import re
from typing import Dict, Tuple, List, Optional
import numpy as np
import cv2
from core.types import FieldCrop

_READER_EN = None


def _get_reader():
    global _READER_EN
    if _READER_EN is None:
        try:
            import easyocr
            _READER_EN = easyocr.Reader(["en"], gpu=False, verbose=False)
        except Exception as e:
            print(f"[Warning] EasyOCR initialization failed: {e}")
            _READER_EN = None
    return _READER_EN


def preprocess_for_ocr(crop_img: np.ndarray, is_mrz: bool = False) -> np.ndarray:
    """Preprocesses field crop with border padding and contrast enhancement."""
    if crop_img is None or crop_img.size == 0:
        return crop_img

    gray = cv2.cvtColor(crop_img, cv2.COLOR_BGR2GRAY) if len(crop_img.shape) == 3 else crop_img.copy()

    # Add 15px border padding
    padded = cv2.copyMakeBorder(gray, 15, 15, 15, 15, cv2.BORDER_CONSTANT, value=255)

    if is_mrz:
        # Increase contrast for monospace MRZ characters
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(padded)
        return enhanced

    # Unsharp mask for crisp numeric text
    gaussian = cv2.GaussianBlur(padded, (0, 0), 1.5)
    sharpened = cv2.addWeighted(padded, 1.6, gaussian, -0.6, 0)
    return sharpened


def extract_mrz_text(
    mrz_crop: np.ndarray,
) -> Tuple[str, str, float]:
    """
    Extracts 2-line ICAO TD3 MRZ text using EasyOCR with a restricted charset allowlist.
    Returns: (line1, line2, confidence)
    """
    reader = _get_reader()
    if reader is None or mrz_crop is None or mrz_crop.size == 0:
        return "", "", 0.0

    enhanced = preprocess_for_ocr(mrz_crop, is_mrz=True)

    # Restrict characters strictly to ICAO 9303 alphabet
    mrz_allowlist = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ<"
    results = reader.readtext(enhanced, allowlist=mrz_allowlist, paragraph=False)

    if not results:
        return "", "", 0.0

    # Sort detected blocks top-to-bottom by y-center coordinate
    def get_y_center(bbox):
        return sum(pt[1] for pt in bbox) / 4.0

    sorted_blocks = sorted(results, key=lambda res: get_y_center(res[0]))

    # Group detected text segments into two distinct horizontal lines
    if len(sorted_blocks) == 2:
        line1_raw = sorted_blocks[0][1]
        line2_raw = sorted_blocks[1][1]
        conf = (sorted_blocks[0][2] + sorted_blocks[1][2]) / 2.0
    else:
        # If OCR fragmented lines into multiple words, group by vertical position
        h = enhanced.shape[0]
        mid_y = h / 2.0
        top_words = [b[1] for b in sorted_blocks if get_y_center(b[0]) < mid_y]
        bot_words = [b[1] for b in sorted_blocks if get_y_center(b[0]) >= mid_y]
        line1_raw = "".join(top_words)
        line2_raw = "".join(bot_words)
        conf = float(np.mean([b[2] for b in sorted_blocks])) if sorted_blocks else 0.5

    # Sanitize and format to 44 characters per line
    def clean_mrz_line(raw: str, prefix_char: Optional[str] = None) -> str:
        s = raw.strip().upper().replace(" ", "")
        # Remove any stray characters outside allowlist
        s = re.sub(r"[^A-Z0-9<]", "", s)
        if prefix_char and not s.startswith(prefix_char) and len(s) > 0:
            if s.startswith("<"):
                s = prefix_char + s[1:]
        # Pad or trim to exactly 44
        if len(s) < 44:
            s = s.ljust(44, "<")
        elif len(s) > 44:
            s = s[:44]
        return s

    line1 = clean_mrz_line(line1_raw, prefix_char="P")
    line2 = clean_mrz_line(line2_raw)

    return line1, line2, conf


def extract_viz_fields(
    crops: Dict[str, FieldCrop],
) -> Dict[str, Tuple[str, float]]:
    """
    Extracts text from individual VIZ field crops.
    Returns: mapping of field_name -> (extracted_text, confidence)
    """
    reader = _get_reader()
    extracted: Dict[str, Tuple[str, float]] = {}

    if reader is None:
        return extracted

    for field_name, crop_obj in crops.items():
        if field_name in ("mrz", "photo"):
            continue

        crop_img = crop_obj.image
        if crop_img is None or crop_img.size == 0:
            continue

        enhanced = preprocess_for_ocr(crop_img, is_mrz=False)
        res = reader.readtext(enhanced, paragraph=False)

        if not res:
            extracted[field_name] = ("", 0.0)
            continue

        # Combine text fragments
        full_text = " ".join([b[1] for b in res]).strip()
        avg_conf = float(np.mean([b[2] for b in res]))

        # Post-process by field semantics
        clean_text = full_text.upper()
        if field_name in ("dob", "doi", "doe"):
            # Normalize dates into DD/MM/YYYY
            date_match = re.search(r"(\d{2})[/\-.](\d{2})[/\-.](\d{4})", clean_text)
            if date_match:
                clean_text = f"{date_match.group(1)}/{date_match.group(2)}/{date_match.group(3)}"
            else:
                digits = re.sub(r"\D", "", clean_text)
                if len(digits) == 8:
                    clean_text = f"{digits[0:2]}/{digits[2:4]}/{digits[4:8]}"

        elif field_name == "passport_no":
            # Match 1 letter + 7 digits
            num_match = re.search(r"([A-Z]\d{7})", clean_text.replace(" ", ""))
            if num_match:
                clean_text = num_match.group(1)
            else:
                clean_text = re.sub(r"[^A-Z0-9]", "", clean_text)

        elif field_name == "sex":
            if "M" in clean_text:
                clean_text = "M"
            elif "F" in clean_text:
                clean_text = "F"

        elif field_name == "nationality":
            if "IND" in clean_text:
                clean_text = "INDIAN"

        extracted[field_name] = (clean_text, avg_conf)

    return extracted
