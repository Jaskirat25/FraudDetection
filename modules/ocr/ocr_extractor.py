"""
modules/ocr/ocr_extractor.py - High-Speed & High-Accuracy Field OCR.
Includes unsharp-mask sharpening for numbers and Indian name lexicon post-processing.
"""

import re
from typing import List, Dict, Tuple
import numpy as np
import cv2
from core.types import FieldCrop

_READER_EN = None

# Common OCR character confusion replacements for Indian IDs
SURNAME_CORRECTIONS = {
    "slngh": "Singh",
    "singh": "Singh",
    "kurnar": "Kumar",
    "kunmar": "Kumar",
    "kumar": "Kumar",
    "sharnma": "Sharma",
    "sharma": "Sharma",
    "verrna": "Verma",
    "verma": "Verma",
    "gupla": "Gupta",
    "gupta": "Gupta",
    "patol": "Patel",
    "patel": "Patel"
}


def _get_en_reader():
    global _READER_EN
    if _READER_EN is None:
        try:
            import easyocr
            _READER_EN = easyocr.Reader(['en'], gpu=False, verbose=False)
        except Exception as e:
            print(f"[Warning] EasyOCR init failed: {e}")
            _READER_EN = None
    return _READER_EN


def sharpen_image(gray_img: np.ndarray) -> np.ndarray:
    """Applies unsharp masking to separate blurred numeric curves (e.g., 5 vs 6)."""
    gaussian = cv2.GaussianBlur(gray_img, (0, 0), 2.0)
    sharpened = cv2.addWeighted(gray_img, 1.8, gaussian, -0.8, 0)
    return sharpened


def add_padding_and_enhance(crop_img: np.ndarray, is_numeric: bool = False) -> np.ndarray:
    if crop_img is None or crop_img.size == 0:
        return crop_img

    if len(crop_img.shape) == 3:
        gray = cv2.cvtColor(crop_img, cv2.COLOR_BGR2GRAY)
    else:
        gray = crop_img.copy()

    # 1. Add 20px white border padding
    pad = 20
    padded = cv2.copyMakeBorder(gray, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=255)

    # 2. Resize to optimal scale
    h, w = padded.shape[:2]
    target_h = 80 if is_numeric else 70
    scale = target_h / max(1, h)
    resized = cv2.resize(padded, (int(w * scale), target_h), interpolation=cv2.INTER_CUBIC)

    # 3. Apply sharpening for numeric crops to fix blurred loops in 5/6/8
    if is_numeric:
        enhanced = sharpen_image(resized)
    else:
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(resized)

    return enhanced


def clean_name_string(raw_text: str) -> str:
    """Cleans extracted name and corrects common OCR glyph confusions."""
    words = raw_text.split()
    corrected_words = []
    
    for word in words:
        clean_word = re.sub(r"[^a-zA-Z]", "", word)
        if not clean_word:
            continue
        
        lower_word = clean_word.lower()
        if lower_word in SURNAME_CORRECTIONS:
            corrected_words.append(SURNAME_CORRECTIONS[lower_word])
        else:
            # Fix 'Sl' pattern at the start of words (e.g., Slngh -> Singh)
            if clean_word.startswith("Sl") or clean_word.startswith("sl"):
                clean_word = "Si" + clean_word[2:]
            corrected_words.append(clean_word.capitalize())

    return " ".join(corrected_words)


def extract_fields(crops: List[FieldCrop]) -> Dict[str, Tuple[str, float]]:
    results: Dict[str, Tuple[str, float]] = {}
    reader = _get_en_reader()

    TARGET_FIELDS = {"aadhaar_no", "dob", "gender", "name_en", "aadhar-address", "address"}

    for crop in crops:
        if crop.name not in TARGET_FIELDS:
            continue

        img = crop.image
        if img is None or img.size == 0:
            continue

        extracted_text = ""
        confidence = 0.0

        if reader is not None:
            is_num = crop.name in ("aadhaar_no", "dob")
            proc_img = add_padding_and_enhance(img, is_numeric=is_num)

            ocr_res = reader.readtext(proc_img, detail=1, paragraph=False)
            if ocr_res:
                texts = [item[1] for item in ocr_res]
                confs = [item[2] for item in ocr_res]
                extracted_text = " ".join(texts).strip()
                confidence = float(np.mean(confs)) if confs else 0.0

        # Post-Processing
        if crop.name == "aadhaar_no":
            digits = re.sub(r"\D", "", extracted_text)
            if len(digits) >= 12:
                digits = digits[-12:]
                extracted_text = f"{digits[0:4]} {digits[4:8]} {digits[8:12]}"
            elif len(digits) >= 4:
                extracted_text = f"XXXX XXXX {digits[-4:]}"

        elif crop.name == "dob":
            match = re.search(r"(\d{2}/\d{2}/\d{4}|\d{2}-\d{2}-\d{4}|\d{4})", extracted_text)
            if match:
                extracted_text = match.group(1).replace("-", "/")

        elif crop.name == "gender":
            upper = extracted_text.upper()
            if "FEM" in upper:
                extracted_text = "FEMALE"
            elif "MAL" in upper:
                extracted_text = "MALE"
            elif "TRANS" in upper:
                extracted_text = "TRANSGENDER"

        elif crop.name == "name_en":
            extracted_text = clean_name_string(extracted_text)

        elif crop.name in ("aadhar-address", "address"):
            # Extract 6-digit PIN code if present in address text
            pin_match = re.search(r"\b([1-9]\d{5})\b", extracted_text)
            if pin_match:
                results["pincode"] = (pin_match.group(1), round(confidence, 3))
            results["address"] = (extracted_text, round(confidence, 3))
            continue

        results[crop.name] = (extracted_text, round(confidence, 3))

    return results
