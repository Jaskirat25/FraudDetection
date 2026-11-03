"""
modules/passport/ocr.py - Robust Passport MRZ & VIZ OCR Extraction Engine.
Includes:
- Monospace gap chevron reconstruction (eliminating EasyOCR space-drop column shifts).
- Datatype column coercion for ICAO Doc 9303 TD3 check digits and dates.
- Full-page MRZ regex fallback scanner.
- Bilingual (English / Hindi) prompt label stripping and semantic anchor extraction for VIZ.
"""

import re
from typing import Dict, Tuple, List, Optional
import numpy as np
import cv2
from core.types import FieldCrop

_READER_EN = None

# OCR character glyphs frequently confused with '<' (filler chevron)
CHEVRON_ALIASES = r"[()\[\]{}\-–—«»/\\|_]"

# ICAO TD3 Character-to-Digit mapping for mandatory numeric columns
CHAR_TO_DIGIT = {
    "O": "0", "D": "0", "Q": "0",
    "I": "1", "L": "1", "T": "1", "|": "1",
    "Z": "2",
    "S": "5",
    "B": "8",
    "G": "6",
}

# ICAO TD3 Digit-to-Char mapping for mandatory alphabetic columns
DIGIT_TO_CHAR = {
    "0": "O",
    "1": "I",
    "2": "Z",
    "5": "S",
    "8": "B",
}

# Common bilingual (English/Hindi) prompt labels to strip from VIZ fields
PROMPT_LABELS = [
    r"(?i)\b(SURNAME|उपनाम)\b",
    r"(?i)\b(GIVEN\s*NAMES?|दिया\s*गया\s*नाम|NAME)\b",
    r"(?i)\b(NATIONALITY|राष्ट्रीयता)\b",
    r"(?i)\b(SEX|लिंग)\b",
    r"(?i)\b(DATE\s*OF\s*BIRTH|जन्म\s*तिथि|D\.?O\.?B\.?|BIRTH)\b",
    r"(?i)\b(PLACE\s*OF\s*BIRTH|जन्म\s*स्थान|P\.?O\.?B\.?)\b",
    r"(?i)\b(PLACE\s*OF\s*ISSUE|जारी\s*करने\s*का\s*स्थान|P\.?O\.?I\.?)\b",
    r"(?i)\b(DATE\s*OF\s*ISSUE|जारी\s*करने\s*की\s*तिथि|D\.?O\.?I\.?|ISSUE)\b",
    r"(?i)\b(DATE\s*OF\s*EXPIRY|समाप्ति\s*की\s*तिथि|D\.?O\.?E\.?|EXPIRY)\b",
    r"(?i)\b(PASSPORT\s*NO\.?|पासपोर्ट\s*संख्या|PASSPORT)\b",
    r"(?i)\b(TYPE|टाइप)\b",
    r"(?i)\b(COUNTRY\s*CODE|देश\s*कोड)\b",
    r"(?i)\b(REPUBLIC\s*OF\s*INDIA|GOVERNMENT\s*OF\s*INDIA|भारत\s*सरकार)\b",
]


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

    # Add 20px border padding
    padded = cv2.copyMakeBorder(gray, 20, 20, 20, 20, cv2.BORDER_CONSTANT, value=255)

    if is_mrz:
        clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
        enhanced = clahe.apply(padded)
        return enhanced

    # Unsharp mask for crisp numeric / alphanumeric text
    gaussian = cv2.GaussianBlur(padded, (0, 0), 1.5)
    sharpened = cv2.addWeighted(padded, 1.8, gaussian, -0.8, 0)
    return sharpened


def reconstruct_line_from_blocks(blocks: List[Tuple[float, float, str]], target_len: int = 44) -> str:
    """
    Reconstructs an MRZ line from bounding-box words, inserting '<' chevrons in whitespace
    gaps based on estimated monospace character width to prevent column shifts.
    blocks: list of (x_min, x_max, text) sorted by x_min.
    """
    if not blocks:
        return "<" * target_len

    cleaned_blocks = []
    for x1, x2, txt in blocks:
        t = txt.strip().upper()
        # Map bracket/punctuation aliases directly to '<'
        t = re.sub(CHEVRON_ALIASES, "<", t)
        # Keep valid ICAO characters
        t = re.sub(r"[^A-Z0-9<]", "", t)
        if t:
            cleaned_blocks.append((x1, x2, t))

    if not cleaned_blocks:
        return "<" * target_len

    # Calculate average character width
    total_chars = sum(len(b[2]) for b in cleaned_blocks)
    total_w = sum((b[1] - b[0]) for b in cleaned_blocks)
    char_w = total_w / max(1, total_chars)

    reconstructed = ""
    last_x2 = None

    for x1, x2, text in cleaned_blocks:
        if last_x2 is not None:
            gap = x1 - last_x2
            # If gap between words exceeds character spacing, reconstruct missing '<' chevrons
            if gap > 0.65 * char_w:
                gap_chars = max(1, round(gap / char_w))
                reconstructed += "<" * gap_chars
        reconstructed += text
        last_x2 = x2

    # Pad or trim to exactly target_len
    if len(reconstructed) < target_len:
        reconstructed = reconstructed.ljust(target_len, "<")
    elif len(reconstructed) > target_len:
        reconstructed = reconstructed[:target_len]

    return reconstructed


def clean_td3_line2_columns(line2: str, expected_country: str = "IND") -> str:
    """
    Applies ICAO Doc 9303 TD3 datatype constraints and column alignment to Line 2:
    - Anchors country code (IND) to pos 10-12 if slightly shifted.
    - Coerces mandatory numeric columns (Check digits, DOB, Expiry).
    - Coerces mandatory alphabetic columns (Nationality, Sex).
    """
    chars = list(line2.ljust(44, "<")[:44])

    # 1. Alignment check: Country Code (IND) is at pos 10..12 in TD3 Line 2
    raw_str = "".join(chars)
    idx = raw_str.find(expected_country)
    if idx != -1 and idx != 10:
        shift = idx - 10
        if abs(shift) <= 2:
            if shift > 0:
                # Line shifted right: trim extra leading characters
                adjusted = raw_str[:10] + raw_str[idx:]
                chars = list(adjusted.ljust(44, "<")[:44])
            elif shift < 0:
                # Line shifted left: insert filler chevrons before country code
                adjusted = raw_str[:9] + ("<" * abs(shift)) + raw_str[9:]
                chars = list(adjusted.ljust(44, "<")[:44])

    # 2. Mandatory numeric positions in TD3 Line 2:
    # Pos 9: Passport No Check Digit
    # Pos 13..18: DOB (YYMMDD)
    # Pos 19: DOB Check Digit
    # Pos 21..26: Expiry Date (YYMMDD)
    # Pos 27: Expiry Check Digit
    # Pos 43: Master Composite Check Digit
    numeric_indices = [9, 13, 14, 15, 16, 17, 18, 19, 21, 22, 23, 24, 25, 26, 27, 43]
    for i in numeric_indices:
        if i < len(chars):
            ch = chars[i]
            if ch in CHAR_TO_DIGIT:
                chars[i] = CHAR_TO_DIGIT[ch]

    # 3. Mandatory alphabetic positions:
    # Pos 10..12: Nationality (IND)
    for i in [10, 11, 12]:
        if i < len(chars):
            ch = chars[i]
            if ch in DIGIT_TO_CHAR:
                chars[i] = DIGIT_TO_CHAR[ch]

    # Pos 20: Sex (M, F, X, <)
    if len(chars) > 20:
        if chars[20] in ("0", "O"):
            chars[20] = "<"
        elif chars[20] not in ("M", "F", "X", "<"):
            if "M" in chars[20]:
                chars[20] = "M"
            elif "F" in chars[20]:
                chars[20] = "F"

    return "".join(chars)


def scan_mrz_from_full_page(image: np.ndarray) -> Tuple[str, str, float]:
    """
    Fallback scanner: searches the full page or bottom 50% for lines matching TD3 MRZ syntax.
    """
    reader = _get_reader()
    if reader is None or image is None or image.size == 0:
        return "", "", 0.0

    h = image.shape[0]
    bottom_crop = image[int(h * 0.40):, :]  # search bottom 60%
    enhanced = preprocess_for_ocr(bottom_crop, is_mrz=True)

    allowlist = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ<()[]{}/\\-_|«»"
    results = reader.readtext(enhanced, allowlist=allowlist, paragraph=False)
    if not results:
        return "", "", 0.0

    # Sort blocks top-to-bottom
    def get_y_center(bbox):
        return sum(pt[1] for pt in bbox) / 4.0

    sorted_res = sorted(results, key=lambda b: get_y_center(b[0]))

    # Find line starting with 'P<' or 'P<IND'
    line1_idx = None
    for idx, b in enumerate(sorted_res):
        txt = b[1].strip().upper().replace(" ", "")
        txt = re.sub(CHEVRON_ALIASES, "<", txt)
        if txt.startswith("P<") or (txt.startswith("P") and "IND" in txt):
            line1_idx = idx
            break

    if line1_idx is not None and line1_idx + 1 < len(sorted_res):
        l1_raw = sorted_res[line1_idx][1]
        l2_raw = sorted_res[line1_idx + 1][1]
        conf = (sorted_res[line1_idx][2] + sorted_res[line1_idx + 1][2]) / 2.0
        
        l1 = re.sub(CHEVRON_ALIASES, "<", l1_raw.strip().upper().replace(" ", ""))
        l1 = re.sub(r"[^A-Z0-9<]", "", l1).ljust(44, "<")[:44]
        
        l2 = re.sub(CHEVRON_ALIASES, "<", l2_raw.strip().upper().replace(" ", ""))
        l2 = re.sub(r"[^A-Z0-9<]", "", l2).ljust(44, "<")[:44]
        l2 = clean_td3_line2_columns(l2)
        return l1, l2, conf

    return "", "", 0.0


def count_valid_check_digits(line2: str) -> int:
    """
    Validates ICAO Doc 9303 TD3 Line 2 check digits (passport no, dob, expiry, composite).
    Returns count of passing check digits (0..4), or -1 if line length is invalid.
    """
    if len(line2) != 44:
        return -1
    valid_count = 0
    from modules.passport.mrz import calculate_icao_check_digit
    try:
        if calculate_icao_check_digit(line2[0:9]) == int(line2[9]):
            valid_count += 1
    except Exception:
        pass
    try:
        if calculate_icao_check_digit(line2[13:19]) == int(line2[19]):
            valid_count += 1
    except Exception:
        pass
    try:
        if calculate_icao_check_digit(line2[21:27]) == int(line2[27]):
            valid_count += 1
    except Exception:
        pass
    try:
        comp_data = line2[0:10] + line2[13:20] + line2[21:43]
        if calculate_icao_check_digit(comp_data) == int(line2[43]):
            valid_count += 1
    except Exception:
        pass
    return valid_count


def extract_mrz_text(
    mrz_crop: np.ndarray,
    full_image: Optional[np.ndarray] = None,
) -> Tuple[str, str, float]:
    """
    Extracts 2-line ICAO TD3 MRZ text using EasyOCR with gap chevron reconstruction,
    datatype coercion, and fallback full-image regex search.
    Returns: (line1, line2, confidence)
    """
    reader = _get_reader()
    if reader is None or mrz_crop is None or mrz_crop.size == 0:
        if full_image is not None:
            return scan_mrz_from_full_page(full_image)
        return "", "", 0.0

    enhanced = preprocess_for_ocr(mrz_crop, is_mrz=True)
    mrz_allowlist = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ<()[]{}/\\-_|«»"
    results = reader.readtext(enhanced, allowlist=mrz_allowlist, paragraph=False)

    if not results and full_image is not None:
        return scan_mrz_from_full_page(full_image)
    if not results:
        return "", "", 0.0

    def get_y_center(bbox):
        return sum(pt[1] for pt in bbox) / 4.0

    sorted_blocks = sorted(results, key=lambda res: get_y_center(res[0]))

    # Split into 2 distinct lines by vertical center
    h = enhanced.shape[0]
    mid_y = h / 2.0
    
    top_items = []
    bot_items = []
    for b in sorted_blocks:
        bbox, text, conf_val = b
        x1 = min(pt[0] for pt in bbox)
        x2 = max(pt[0] for pt in bbox)
        y_c = get_y_center(bbox)
        if y_c < mid_y:
            top_items.append((x1, x2, text))
        else:
            bot_items.append((x1, x2, text))

    # Sort each line horizontally
    top_items.sort(key=lambda item: item[0])
    bot_items.sort(key=lambda item: item[0])

    line1 = reconstruct_line_from_blocks(top_items, 44)
    line2 = reconstruct_line_from_blocks(bot_items, 44)

    # Sanitize prefix
    if not line1.startswith("P"):
        if line1.startswith("<"):
            line1 = "P" + line1[1:]
        elif "IND" in line1:
            line1 = "P<" + line1[line1.find("IND"):]
    line1 = line1.ljust(44, "<")[:44]

    # Clean Line 2 columns & alignment
    line2 = clean_td3_line2_columns(line2)

    avg_conf = float(np.mean([b[2] for b in results])) if results else 0.5

    # Check if crop extraction has any failing check digits
    crop_valid_cds = count_valid_check_digits(line2)
    if (not line1.startswith("P<") or len(line2.strip("<")) < 15 or crop_valid_cds < 4) and full_image is not None:
        l1_alt, l2_alt, conf_alt = scan_mrz_from_full_page(full_image)
        if l1_alt.startswith("P<") and len(l2_alt.strip("<")) >= 20:
            alt_valid_cds = count_valid_check_digits(l2_alt)
            if alt_valid_cds > crop_valid_cds or (crop_valid_cds < 4 and alt_valid_cds >= 3):
                return l1_alt, l2_alt, conf_alt

    return line1, line2, avg_conf


# =============================================================================
# Visual Inspection Zone (VIZ) Extraction & Semantic Anchor Parsing
# =============================================================================

def clean_viz_field_text(field_name: str, raw_text: str) -> str:
    """
    Strips bilingual prompt labels (English & Devanagari) and normalizes field value.
    """
    clean_text = raw_text.strip().upper()

    # 1. Strip known prompt labels
    for pattern in PROMPT_LABELS:
        clean_text = re.sub(pattern, " ", clean_text)

    # 2. Field-specific semantic extraction
    if field_name in ("dob", "doi", "doe"):
        # Match standard DD/MM/YYYY date
        date_match = re.search(r"(\d{2})[/\-.](\d{2})[/\-.](\d{4})", clean_text)
        if date_match:
            return f"{date_match.group(1)}/{date_match.group(2)}/{date_match.group(3)}"
        digits = re.sub(r"\D", "", clean_text)
        if len(digits) == 8:
            return f"{digits[0:2]}/{digits[2:4]}/{digits[4:8]}"
        return ""

    if field_name == "passport_no":
        # Indian passport regex: 1 letter followed by 7 digits
        num_match = re.search(r"([A-PR-WY]\d{7})", clean_text.replace(" ", ""))
        if num_match:
            return num_match.group(1)
        # Fallback: strip all non-alphanumeric
        cleaned = re.sub(r"[^A-Z0-9]", "", clean_text)
        return cleaned[:8] if len(cleaned) >= 8 else cleaned

    if field_name == "nationality":
        if "IND" in clean_text or "भारतीय" in clean_text:
            return "INDIAN"
        return "INDIAN" if "INDIAN" in clean_text else clean_text.strip()

    if field_name == "sex":
        clean_no_space = clean_text.replace(" ", "")
        if "M" in clean_no_space:
            return "M"
        if "F" in clean_no_space:
            return "F"
        if "X" in clean_no_space:
            return "X"
        return ""

    if field_name in ("surname", "given_names"):
        # Remove Devanagari script, punctuation and digits
        clean_text = re.sub(r"[\u0900-\u097F0-9/\\:.\-_()«»]", " ", clean_text)
        # Remove common title abbreviations
        clean_text = re.sub(r"(?i)\b(MR|MS|MRS|SHRI|SMT|LATE|DR)\b", " ", clean_text)
        # Collapse whitespace
        words = [w.strip() for w in clean_text.split() if len(w.strip()) > 1]
        return " ".join(words)

    return clean_text.strip()


def extract_viz_by_semantic_anchors(
    image: np.ndarray,
) -> Dict[str, Tuple[str, float]]:
    """
    Extracts Visual Inspection Zone (VIZ) demographic fields dynamically using
    bilingual semantic anchor recognition, completely independent of fixed pixel bounding boxes.
    """
    reader = _get_reader()
    extracted: Dict[str, Tuple[str, float]] = {}
    if reader is None or image is None or image.size == 0:
        return extracted

    h, w = image.shape[:2]
    # Run EasyOCR on top 75% of the page to avoid bottom MRZ monospace text
    bio_crop = image[:int(h * 0.75), :]
    results = reader.readtext(bio_crop, paragraph=False)
    if not results:
        return extracted

    blocks = []
    for bbox, text, conf in results:
        t_clean = text.strip()
        if not t_clean:
            continue
        x_min = float(min(pt[0] for pt in bbox))
        x_max = float(max(pt[0] for pt in bbox))
        y_min = float(min(pt[1] for pt in bbox))
        y_max = float(max(pt[1] for pt in bbox))
        blocks.append({
            "bbox": bbox,
            "text": t_clean,
            "conf": float(conf),
            "x_min": x_min,
            "x_max": x_max,
            "y_min": y_min,
            "y_max": y_max,
            "y_c": (y_min + y_max) / 2.0,
            "x_c": (x_min + x_max) / 2.0,
            "h": max(1.0, y_max - y_min),
        })

    # Sort blocks top-to-bottom
    blocks.sort(key=lambda b: b["y_c"])

    # 1. Direct Regex Searches
    # Passport Number: Letter (excluding Q/X/Z) + 7 digits
    for b in blocks:
        m = re.search(r"\b([A-PR-WY]\s*[0-9]{7})\b", b["text"].upper())
        if m:
            clean_num = m.group(1).replace(" ", "")
            extracted["passport_no"] = (clean_num, b["conf"])
            break

    # Nationality
    for b in blocks:
        t_up = b["text"].upper()
        if "INDIAN" in t_up or "भारतीय" in t_up or re.search(r"\bIND\b", t_up):
            extracted["nationality"] = ("INDIAN", b["conf"])
            break

    # Dates (DD/MM/YYYY)
    dates_found = []
    for b in blocks:
        dm = re.findall(r"\b(\d{2}[/\-.]\d{2}[/\-.]\d{4})\b", b["text"])
        for d in dm:
            std_d = d.replace("-", "/").replace(".", "/")
            dates_found.append((std_d, b["y_c"], b["conf"]))

    if len(dates_found) >= 3:
        # Sort chronologically by converting DD/MM/YYYY to (YYYY, MM, DD)
        def _date_key(item):
            parts = item[0].split("/")
            return (int(parts[2]), int(parts[1]), int(parts[0]))
        dates_sorted = sorted(dates_found, key=_date_key)
        extracted["dob"] = (dates_sorted[0][0], dates_sorted[0][2])
        extracted["doi"] = (dates_sorted[1][0], dates_sorted[1][2])
        extracted["doe"] = (dates_sorted[2][0], dates_sorted[2][2])
    elif len(dates_found) == 2:
        dates_sorted = sorted(dates_found, key=lambda x: x[0].split("/")[2])
        extracted["dob"] = (dates_sorted[0][0], dates_sorted[0][2])
        extracted["doe"] = (dates_sorted[1][0], dates_sorted[1][2])
    elif len(dates_found) == 1:
        extracted["dob"] = (dates_found[0][0], dates_found[0][2])

    # 2. Semantic Anchors for Names & Locations
    # Locate anchor blocks
    surname_anchor = next((b for b in blocks if re.search(r"(?i)(SURNAME|उपनाम|SUTO)", b["text"])), None)
    given_anchor = next((b for b in blocks if re.search(r"(?i)(GIVEN|NAMETS?|दिया)", b["text"])), None)
    dob_anchor = next((b for b in blocks if re.search(r"(?i)(BIRTH|DOB|जन्म)", b["text"])), None)
    pob_anchor = next((b for b in blocks if re.search(r"(?i)(PLACE\s*OF\s*BIRTH|स्थान)", b["text"])), None)
    poi_anchor = next((b for b in blocks if re.search(r"(?i)(PLACE\s*OF\s*ISSUE|जारी)", b["text"])), None)
    sex_anchor = next((b for b in blocks if re.search(r"(?i)\b(SEX|GENDER|लिंग)\b", b["text"])), None)

    # Surname: candidate blocks between surname_anchor and given_anchor
    if surname_anchor:
        y_top = surname_anchor["y_max"]
        y_bot = given_anchor["y_min"] if given_anchor else (y_top + 3.0 * surname_anchor["h"])
        s_cands = [b for b in blocks if y_top <= b["y_c"] <= y_bot and b != surname_anchor]
        if s_cands:
            s_text = " ".join(b["text"] for b in sorted(s_cands, key=lambda x: x["x_min"]))
            clean_s = clean_viz_field_text("surname", s_text)
            if clean_s:
                avg_c = float(np.mean([b["conf"] for b in s_cands]))
                extracted["surname"] = (clean_s, avg_c)

    # Given Names: candidate blocks between given_anchor and dob_anchor
    if given_anchor:
        y_top = given_anchor["y_max"]
        y_bot = dob_anchor["y_min"] if dob_anchor else (y_top + 3.0 * given_anchor["h"])
        g_cands = [b for b in blocks if y_top <= b["y_c"] <= y_bot and b != given_anchor]
        if g_cands:
            g_text = " ".join(b["text"] for b in sorted(g_cands, key=lambda x: x["x_min"]))
            clean_g = clean_viz_field_text("given_names", g_text)
            if clean_g:
                avg_c = float(np.mean([b["conf"] for b in g_cands]))
                extracted["given_names"] = (clean_g, avg_c)

    # Sex: check near sex_anchor or in bio blocks
    if sex_anchor:
        s_val = next((b for b in blocks if abs(b["y_c"] - sex_anchor["y_c"]) < 1.5 * sex_anchor["h"]
                      and b["x_min"] >= sex_anchor["x_min"] and b["text"].upper() in ("M", "F", "X")), None)
        if s_val:
            extracted["sex"] = (s_val["text"].upper(), s_val["conf"])
        else:
            for b in blocks:
                if b["text"].upper() in ("M", "F") and abs(b["y_c"] - sex_anchor["y_c"]) < 2.5 * sex_anchor["h"]:
                    extracted["sex"] = (b["text"].upper(), b["conf"])
                    break

    # Place of Birth (pob)
    if pob_anchor:
        y_top = pob_anchor["y_max"]
        y_bot = poi_anchor["y_min"] if poi_anchor else (y_top + 3.0 * pob_anchor["h"])
        p_cands = [b for b in blocks if y_top <= b["y_c"] <= y_bot and b != pob_anchor]
        if p_cands:
            p_text = " ".join(b["text"] for b in sorted(p_cands, key=lambda x: x["x_min"]))
            clean_p = clean_viz_field_text("pob", p_text)
            if clean_p:
                extracted["pob"] = (clean_p, float(np.mean([b["conf"] for b in p_cands])))

    # Place of Issue (poi)
    if poi_anchor:
        y_top = poi_anchor["y_max"]
        y_bot = y_top + 3.0 * poi_anchor["h"]
        p_cands = [b for b in blocks if y_top <= b["y_c"] <= y_bot and b != poi_anchor]
        if p_cands:
            p_text = " ".join(b["text"] for b in sorted(p_cands, key=lambda x: x["x_min"]))
            clean_p = clean_viz_field_text("poi", p_text)
            if clean_p:
                extracted["poi"] = (clean_p, float(np.mean([b["conf"] for b in p_cands])))

    return extracted


def is_contaminated_or_noisy(field_name: str, val: str) -> bool:
    """Detects if an extracted VIZ value contains prompt labels, header clutter, or wrong format."""
    if not val or len(val.strip()) < 2:
        return True
    val_upper = val.upper()
    noisy_tokens = [
        "REPUBLIC", "INDIA", "TYPE", "COUNTRY", "CODE", "PASSPORT", "NATIONALITY",
        "SURNAME", "GIVEN", "BIRTH", "ISSUE", "EXPIRY", "PLACE", "DATE", "POGOPORT",
        "MULLONALITY", "VRERKLL", "CHLE", "TYNO",
        "उपनाम", "नाम", "राष्ट्रीयता", "लिंग", "जन्म", "स्थान", "जारी"
    ]
    if any(tok in val_upper for tok in noisy_tokens):
        return True
    if field_name == "nationality" and val_upper != "INDIAN":
        return True
    if field_name in ("surname", "given_names") and len(val.split()) > 4:
        return True
    if field_name == "passport_no" and not re.match(r"^[A-PR-WY]\d{7}$", val_upper):
        return True
    if field_name in ("dob", "doi", "doe") and not re.match(r"^\d{2}/\d{2}/\d{4}$", val):
        return True
    return False


def extract_viz_fields(
    crops: Dict[str, FieldCrop],
    full_image: Optional[np.ndarray] = None,
) -> Dict[str, Tuple[str, float]]:
    """
    Extracts text from VIZ field crops with bilingual prompt label stripping,
    fused with dynamic semantic anchor parsing from full_image when available.
    Returns: mapping of field_name -> (extracted_clean_text, confidence)
    """
    reader = _get_reader()
    extracted: Dict[str, Tuple[str, float]] = {}

    if reader is None:
        return extracted

    # 1. Static crop extraction
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

        full_text = " ".join([b[1] for b in res]).strip()
        avg_conf = float(np.mean([b[2] for b in res]))
        cleaned = clean_viz_field_text(field_name, full_text)

        extracted[field_name] = (cleaned, avg_conf)

    # 2. Semantic Anchor Fallback and Fusion
    if full_image is not None and full_image.size > 0:
        anchor_fields = extract_viz_by_semantic_anchors(full_image)
        for f_name, (val, conf) in anchor_fields.items():
            if not val:
                continue
            curr_val, curr_conf = extracted.get(f_name, ("", 0.0))
            # Always prefer anchor if crop is noisy, contaminated, or missing
            if is_contaminated_or_noisy(f_name, curr_val) or not curr_val:
                extracted[f_name] = (val, conf)
            elif f_name in ("surname", "given_names") and ("surname" in anchor_fields and "given_names" in anchor_fields):
                # When both names are structurally resolved via anchors, prefer them over static boxes
                extracted[f_name] = (val, conf)
            elif conf > curr_conf + 0.10:
                extracted[f_name] = (val, conf)

    return extracted
