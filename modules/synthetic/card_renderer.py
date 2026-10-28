"""
modules/synthetic/card_renderer.py - High-Fidelity Synthetic Aadhaar Card Generator.
Renders photorealistic Front & Back cards adhering to UIDAI physical specifications:
- 1000x630 canonical coordinate system
- Exact CANONICAL_FIELDS spatial alignment for flawless automated localization
- Microprint / Guilloche security wave pattern rendering
- Ashoka Emblem & Government of India bilingual headers
- Embedded V5 Secure QR with real RSA-2048 Mock CA signature
- Verhoeff-compliant 12-digit Aadhaar numbers
"""

import math
import random
from pathlib import Path
from typing import Dict, Tuple, Optional, Any, List
import numpy as np
import cv2
from PIL import Image, ImageDraw, ImageFont

from core.config import CANONICAL_WIDTH, CANONICAL_HEIGHT, CANONICAL_FIELDS
from modules.validate.verhoeff import generate_verhoeff
from modules.mock_ca.qr_encoder import create_synthetic_qr_payload


# Pre-defined realistic demographic pool
SYNTHETIC_IDENTITIES = [
    {
        "name_en": "Aarav Sharma",
        "name_hi": "आरव शर्मा",
        "gender": "MALE",
        "gender_hi": "पुरुष",
        "address_en": "42 Connaught Place, Central Delhi, New Delhi",
        "address_hi": "४२ कनॉट प्लेस, मध्य दिल्ली, नई दिल्ली",
        "pincode": "110001",
        "state": "DELHI",
        "dob": "15/08/1992"
    },
    {
        "name_en": "Priya Patel",
        "name_hi": "प्रिया पटेल",
        "gender": "FEMALE",
        "gender_hi": "महिला",
        "address_en": "108 Ellis Bridge, Ashram Road, Ahmedabad, Gujarat",
        "address_hi": "१०८ एलिस ब्रिज, आश्रम रोड, अहमदाबाद, गुजरात",
        "pincode": "380006",
        "state": "GUJARAT",
        "dob": "22/04/1996"
    },
    {
        "name_en": "Rajesh Kumar",
        "name_hi": "राजेश कुमार",
        "gender": "MALE",
        "gender_hi": "पुरुष",
        "address_en": "15 Fraser Road, Gandhi Maidan, Patna, Bihar",
        "address_hi": "१५ फ्रेजर रोड, गांधी मैदान, पटना, बिहार",
        "pincode": "800001",
        "state": "BIHAR",
        "dob": "10/11/1988"
    },
    {
        "name_en": "Ananya Iyer",
        "name_hi": "अनन्या अय्यर",
        "gender": "FEMALE",
        "gender_hi": "महिला",
        "address_en": "24 Mylapore High Road, Chennai, Tamil Nadu",
        "address_hi": "२४ मायलापुर हाई रोड, चेन्नई, तमिलनाडु",
        "pincode": "600004",
        "state": "TAMIL NADU",
        "dob": "05/01/1999"
    },
    {
        "name_en": "Vikram Singh",
        "name_hi": "विक्रम सिंह",
        "gender": "MALE",
        "gender_hi": "पुरुष",
        "address_en": "77 Mall Road, Civil Lines, Jaipur, Rajasthan",
        "address_hi": "७७ मॉल रोड, सिविल लाइंस, जयपुर, राजस्थान",
        "pincode": "302006",
        "state": "RAJASTHAN",
        "dob": "18/07/1985"
    },
    {
        "name_en": "Pooja Verma",
        "name_hi": "पूजा वर्मा",
        "gender": "FEMALE",
        "gender_hi": "महिला",
        "address_en": "12 Hazratganj, Lucknow, Uttar Pradesh",
        "address_hi": "१२ हजरतगंज, लखनऊ, उत्तर प्रदेश",
        "pincode": "226001",
        "state": "UTTAR PRADESH",
        "dob": "30/09/1994"
    },
    {
        "name_en": "Rohan Gupta",
        "name_hi": "रोहन गुप्ता",
        "gender": "MALE",
        "gender_hi": "पुरुष",
        "address_en": "54 Park Street, Kolkata, West Bengal",
        "address_hi": "५४ पार्क स्ट्रीट, कोलकाता, पश्चिम बंगाल",
        "pincode": "700016",
        "state": "WEST BENGAL",
        "dob": "12/03/1991"
    },
    {
        "name_en": "Sneha Reddy",
        "name_hi": "स्नेहा रेड्डी",
        "gender": "FEMALE",
        "gender_hi": "महिला",
        "address_en": "88 Banjara Hills Road No 3, Hyderabad, Telangana",
        "address_hi": "८८ बंजारा हिल्स रोड नंबर ३, हैदराबाद, तेलंगाना",
        "pincode": "500034",
        "state": "TELANGANA",
        "dob": "19/12/1997"
    }
]

# Font cache
_FONT_CACHE: Dict[str, ImageFont.FreeTypeFont] = {}


def _get_font(name: str, size: int) -> ImageFont.FreeTypeFont:
    key = f"{name}_{size}"
    if key in _FONT_CACHE:
        return _FONT_CACHE[key]

    font_paths = {
        "hindi": ["C:\\Windows\\Fonts\\Nirmala.ttc", "C:\\Windows\\Fonts\\mangal.ttf", "arial.ttf"],
        "bold": ["C:\\Windows\\Fonts\\arialbd.ttf", "C:\\Windows\\Fonts\\segoeuib.ttf", "arial.ttf"],
        "regular": ["C:\\Windows\\Fonts\\arial.ttf", "C:\\Windows\\Fonts\\segoeui.ttf", "arial.ttf"],
        "mono": ["C:\\Windows\\Fonts\\courbd.ttf", "C:\\Windows\\Fonts\\arialbd.ttf", "arial.ttf"],
    }

    candidates = font_paths.get(name, font_paths["regular"])
    for p in candidates:
        if Path(p).exists():
            try:
                font = ImageFont.truetype(p, size)
                _FONT_CACHE[key] = font
                return font
            except Exception:
                continue

    fallback = ImageFont.load_default()
    _FONT_CACHE[key] = fallback
    return fallback


def generate_demographic_identity(seed: Optional[int] = None) -> Dict[str, Any]:
    """Generates a complete, mathematically valid Aadhaar identity."""
    rng = random.Random(seed)
    base = rng.choice(SYNTHETIC_IDENTITIES).copy()

    # Generate 11 random digits starting with 2-9
    first_digit = rng.randint(2, 9)
    remaining_10 = "".join(str(rng.randint(0, 9)) for _ in range(10))
    eleven_digits = f"{first_digit}{remaining_10}"
    check_digit = generate_verhoeff(eleven_digits)
    aadhaar_num = f"{eleven_digits}{check_digit}"

    base["aadhaar_no"] = aadhaar_num
    base["aadhaar_last4"] = aadhaar_num[-4:]
    base["aadhaar_formatted"] = f"{aadhaar_num[:4]} {aadhaar_num[4:8]} {aadhaar_num[8:]}"
    return base


def _draw_guilloche_background(draw: ImageDraw.ImageDraw, width: int, height: int):
    """Draws fine security guilloche sine-wave curves to mimic official security background."""
    for i in range(0, height, 18):
        pts = []
        phase = i * 0.1
        amp = 6.0
        for x in range(0, width, 10):
            y = i + amp * math.sin(x * 0.03 + phase)
            pts.append((x, y))
        draw.line(pts, fill=(236, 230, 218), width=1)

    for i in range(0, width, 35):
        pts = []
        phase = i * 0.08
        amp = 4.0
        for y in range(0, height, 8):
            x = i + amp * math.cos(y * 0.04 + phase)
            pts.append((x, y))
        draw.line(pts, fill=(240, 235, 225), width=1)


def _draw_ashoka_emblem(draw: ImageDraw.ImageDraw, x: int, y: int, w: int, h: int):
    """Draws a stylized Ashoka Lion Capital emblem icon."""
    cx = x + w // 2
    # Base pedestal
    draw.rectangle([cx - 24, y + h - 14, cx + 24, y + h - 4], fill=(130, 105, 50))
    # Ashoka Chakra wheel in base
    draw.ellipse([cx - 7, y + h - 13, cx + 7, y + h - 5], outline=(255, 255, 255), width=1)
    # Pillars
    draw.rectangle([cx - 18, y + 16, cx - 6, y + h - 14], fill=(160, 130, 60))
    draw.rectangle([cx - 6, y + 10, cx + 6, y + h - 14], fill=(175, 140, 65))
    draw.rectangle([cx + 6, y + 16, cx + 18, y + h - 14], fill=(160, 130, 60))
    # Lion heads / top crown
    draw.ellipse([cx - 20, y + 6, cx + 20, y + 26], fill=(150, 120, 55))
    draw.polygon([(cx - 16, y + 8), (cx, y), (cx + 16, y + 8)], fill=(140, 110, 50))


def _draw_aadhaar_logo(draw: ImageDraw.ImageDraw, x: int, y: int, w: int, h: int):
    """Draws the iconic stylized yellow-red Aadhaar sunburst symbol."""
    cx = x + w // 2
    cy = y + h // 2
    radius = min(w, h) // 2 - 4

    # Sunburst rays
    for deg in range(0, 360, 30):
        rad = math.radians(deg)
        x1 = cx + (radius * 0.45) * math.cos(rad)
        y1 = cy + (radius * 0.45) * math.sin(rad)
        x2 = cx + radius * math.cos(rad)
        y2 = cy + radius * math.sin(rad)
        draw.line([(x1, y1), (x2, y2)], fill=(220, 40, 30), width=3)

    # Inner core
    draw.ellipse([cx - radius * 0.4, cy - radius * 0.4, cx + radius * 0.4, cy + radius * 0.4], fill=(235, 150, 20))
    draw.ellipse([cx - radius * 0.22, cy - radius * 0.22, cx + radius * 0.22, cy + radius * 0.22], fill=(245, 210, 40))


def _generate_synthetic_face_portrait(w: int = 200, h: int = 250) -> np.ndarray:
    """Generates a neutral photorealistic face portrait with facial landmarks for SFace/YuNet."""
    # Look for cached test faces first
    sample_faces = [
        "WhatsApp Image 2026-09-25 at 10.32.28 AM.jpeg",
        "aadhar_front.jpeg",
        "sample_addhar.jpeg"
    ]
    for sf in sample_faces:
        if Path(sf).exists():
            img = cv2.imread(sf)
            if img is not None and img.size > 0:
                # Resize directly to requested portrait bbox
                return cv2.resize(img, (w, h))

    # Synthetic portrait fallback (soft skin tones, hair, eyes, lips)
    face_img = np.full((h, w, 3), (210, 220, 230), dtype=np.uint8)
    # Head contour
    cv2.ellipse(face_img, (w // 2, h // 2), (w // 3, int(h * 0.42)), 0, 0, 360, (160, 180, 210), -1)
    # Hair
    cv2.ellipse(face_img, (w // 2, int(h * 0.25)), (int(w * 0.35), int(h * 0.2)), 0, 180, 360, (30, 25, 20), -1)
    # Eyes
    cv2.circle(face_img, (int(w * 0.38), int(h * 0.45)), 8, (255, 255, 255), -1)
    cv2.circle(face_img, (int(w * 0.38), int(h * 0.45)), 4, (40, 30, 20), -1)
    cv2.circle(face_img, (int(w * 0.62), int(h * 0.45)), 8, (255, 255, 255), -1)
    cv2.circle(face_img, (int(w * 0.62), int(h * 0.45)), 4, (40, 30, 20), -1)
    # Nose
    cv2.line(face_img, (w // 2, int(h * 0.48)), (w // 2, int(h * 0.58)), (140, 160, 190), 2)
    # Mouth
    cv2.ellipse(face_img, (w // 2, int(h * 0.68)), (18, 6), 0, 0, 180, (90, 100, 180), -1)
    return face_img


def render_synthetic_aadhaar_card(
    demographics: Optional[Dict[str, Any]] = None,
    face_photo: Optional[np.ndarray] = None,
    qr_image: Optional[np.ndarray] = None,
    tamper_recipe: Optional[Dict[str, Any]] = None
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, Dict[str, Any]]:
    """
    Renders high-resolution Front & Back Aadhaar cards.
    
    Returns:
        (front_bgr, back_bgr, combined_bgr, final_metadata)
    """
    if demographics is None:
        demographics = generate_demographic_identity()
    else:
        demographics = demographics.copy()

    # Apply any pre-render tamper recipes to demographics
    tamper_recipe = tamper_recipe or {}
    if "override_printed_dob" in tamper_recipe:
        demographics["dob"] = tamper_recipe["override_printed_dob"]
    if "override_printed_name_en" in tamper_recipe:
        demographics["name_en"] = tamper_recipe["override_printed_name_en"]
    if "override_printed_aadhaar_no" in tamper_recipe:
        demographics["aadhaar_no"] = tamper_recipe["override_printed_aadhaar_no"]
        demographics["aadhaar_formatted"] = " ".join([demographics["aadhaar_no"][i:i+4] for i in range(0, 12, 4)])

    # Setup Face Photo
    if face_photo is None:
        face_photo = _generate_synthetic_face_portrait(200, 250)
    else:
        face_photo = cv2.resize(face_photo, (200, 250))

    # Setup QR Code
    if qr_image is None:
        qr_payload_input = {
            "name": tamper_recipe.get("qr_name", demographics["name_en"]),
            "dob": tamper_recipe.get("qr_dob", demographics["dob"]),
            "gender": "M" if "MALE" in demographics["gender"].upper() else "F",
            "last4": tamper_recipe.get("qr_last4", demographics.get("aadhaar_last4", demographics["aadhaar_no"][-4:])),
            "address": tamper_recipe.get("qr_address", demographics["address_en"]),
            "pincode": tamper_recipe.get("qr_pincode", demographics["pincode"]),
            "state": demographics.get("state", "DELHI"),
            "issue_date": tamper_recipe.get("qr_issue_date", "2023-05-10 14:22:10")
        }
        tamper_sig = tamper_recipe.get("corrupt_qr_signature", False)
        _, _, qr_image = create_synthetic_qr_payload(
            qr_payload_input,
            photo_bgr=face_photo,
            corrupt_signature=tamper_sig
        )

    # -------------------------------------------------------------
    # 1. RENDER FRONT CARD (CANONICAL_WIDTH x CANONICAL_HEIGHT = 1000 x 630)
    # -------------------------------------------------------------
    front_pil = Image.new("RGB", (CANONICAL_WIDTH, CANONICAL_HEIGHT), color=(242, 241, 238))
    draw_front = ImageDraw.Draw(front_pil)

    # Security guilloche pattern
    _draw_guilloche_background(draw_front, CANONICAL_WIDTH, CANONICAL_HEIGHT)

    # Top Header Tricolor bar
    draw_front.rectangle([30, 15, CANONICAL_WIDTH - 30, 20], fill=(245, 130, 32))  # Saffron
    draw_front.rectangle([30, 20, CANONICAL_WIDTH - 30, 23], fill=(255, 255, 255)) # White
    draw_front.rectangle([30, 23, CANONICAL_WIDTH - 30, 28], fill=(19, 136, 8))   # Green

    # Ashoka Emblem (Left / Header)
    _draw_ashoka_emblem(draw_front, 45, 30, 75, 65)

    # Header Text
    font_header_hi = _get_font("hindi", 22)
    font_header_en = _get_font("bold", 20)
    draw_front.text((150, 34), "भारत सरकार", fill=(20, 20, 20), font=font_header_hi)
    draw_front.text((150, 64), "Government of India", fill=(40, 40, 40), font=font_header_en)

    # Top Right Aadhaar Emblem
    _draw_aadhaar_logo(draw_front, 860, 32, 80, 65)

    # Card Photo (Matches CANONICAL_FIELDS["photo"]: (50, 120, 200, 250))
    face_pil = Image.fromarray(cv2.cvtColor(face_photo, cv2.COLOR_BGR2RGB))
    front_pil.paste(face_pil, (50, 120))
    draw_front.rectangle([49, 119, 251, 371], outline=(170, 170, 170), width=1)

    # Demographic Fields (Matches CANONICAL_FIELDS positions)
    font_name_hi = _get_font("hindi", 24)
    font_name_en = _get_font("bold", 22)
    font_details = _get_font("bold", 19)

    # Name Hindi (280, 120)
    draw_front.text((280, 120), demographics["name_hi"], fill=(15, 15, 15), font=font_name_hi)
    # Name English (280, 168)
    draw_front.text((280, 168), demographics["name_en"], fill=(15, 15, 15), font=font_name_en)
    # DOB (280, 222)
    draw_front.text((280, 222), f"जन्म तिथि / DOB: {demographics['dob']}", fill=(30, 30, 30), font=font_details)
    # Gender (280, 272)
    draw_front.text((280, 272), f"{demographics.get('gender_hi', 'पुरुष')} / {demographics['gender']}", fill=(30, 30, 30), font=font_details)

    # Aadhaar Number Block (CANONICAL_FIELDS["aadhaar_no"]: (280, 430, 440, 60))
    font_aadhaar = _get_font("bold", 36)
    draw_front.text((290, 435), demographics["aadhaar_formatted"], fill=(10, 10, 10), font=font_aadhaar)

    # Red divider line above Aadhaar number
    draw_front.line([(280, 420), (740, 420)], fill=(210, 40, 30), width=2)

    # Bottom identity ribbon
    font_footer_hi = _get_font("hindi", 18)
    draw_front.rectangle([30, 570, CANONICAL_WIDTH - 30, 605], fill=(240, 45, 35))
    draw_front.text((360, 575), "मेरा आधार, मेरी पहचान", fill=(255, 255, 255), font=font_footer_hi)

    front_bgr = cv2.cvtColor(np.array(front_pil), cv2.COLOR_RGB2BGR)

    # -------------------------------------------------------------
    # 2. RENDER BACK CARD (CANONICAL_WIDTH x CANONICAL_HEIGHT = 1000 x 630)
    # -------------------------------------------------------------
    back_pil = Image.new("RGB", (CANONICAL_WIDTH, CANONICAL_HEIGHT), color=(242, 241, 238))
    draw_back = ImageDraw.Draw(back_pil)

    # Security guilloche pattern
    _draw_guilloche_background(draw_back, CANONICAL_WIDTH, CANONICAL_HEIGHT)

    # Header
    draw_back.rectangle([30, 15, CANONICAL_WIDTH - 30, 20], fill=(245, 130, 32))
    draw_back.rectangle([30, 20, CANONICAL_WIDTH - 30, 23], fill=(255, 255, 255))
    draw_back.rectangle([30, 23, CANONICAL_WIDTH - 30, 28], fill=(19, 136, 8))

    font_back_hi = _get_font("hindi", 20)
    font_back_en = _get_font("bold", 18)
    draw_back.text((50, 35), "भारतीय विशिष्ट पहचान प्राधिकरण", fill=(20, 20, 20), font=font_back_hi)
    draw_back.text((50, 62), "Unique Identification Authority of India", fill=(40, 40, 40), font=font_back_en)
    _draw_aadhaar_logo(draw_back, 860, 32, 80, 65)

    # Address block (Left side, x: 50 to 650)
    font_addr_title = _get_font("bold", 17)
    font_addr_hi = _get_font("hindi", 17)
    font_addr_en = _get_font("regular", 16)

    draw_back.text((50, 125), "पता:", fill=(20, 20, 20), font=font_addr_title)
    draw_back.text((50, 150), demographics["address_hi"], fill=(30, 30, 30), font=font_addr_hi)
    draw_back.text((50, 180), f"पिन कोड: {demographics['pincode']}", fill=(20, 20, 20), font=font_addr_hi)

    draw_back.text((50, 235), "Address:", fill=(20, 20, 20), font=font_addr_title)
    draw_back.text((50, 260), demographics["address_en"], fill=(30, 30, 30), font=font_addr_en)
    draw_back.text((50, 290), f"PIN: {demographics['pincode']}", fill=(20, 20, 20), font=font_addr_title)

    # Embedded Secure QR Code (Matches CANONICAL_FIELDS["qr_code"]: (730, 120, 230, 230))
    qr_resized = cv2.resize(qr_image, (230, 230))
    qr_pil = Image.fromarray(cv2.cvtColor(qr_resized, cv2.COLOR_BGR2RGB))
    back_pil.paste(qr_pil, (730, 120))
    draw_back.rectangle([729, 119, 961, 351], outline=(180, 180, 180), width=1)

    # Aadhaar Number on back as well (bottom center)
    draw_back.line([(50, 420), (950, 420)], fill=(210, 40, 30), width=2)
    draw_back.text((290, 435), demographics["aadhaar_formatted"], fill=(10, 10, 10), font=font_aadhaar)

    # Footer helpline banner
    font_help = _get_font("bold", 15)
    draw_back.rectangle([30, 570, CANONICAL_WIDTH - 30, 605], fill=(235, 235, 238))
    draw_back.text((220, 578), "1947 | help@uidai.gov.in | www.uidai.gov.in", fill=(50, 50, 50), font=font_help)

    back_bgr = cv2.cvtColor(np.array(back_pil), cv2.COLOR_RGB2BGR)

    # -------------------------------------------------------------
    # 3. COMBINED IMAGE CANVAS (Side-by-side: 2040 x 670)
    # -------------------------------------------------------------
    combined_h = CANONICAL_HEIGHT + 40
    combined_w = CANONICAL_WIDTH * 2 + 60
    combined_bgr = np.full((combined_h, combined_w, 3), 242, dtype=np.uint8)

    # Place front card on left, back card on right
    combined_bgr[20:20 + CANONICAL_HEIGHT, 20:20 + CANONICAL_WIDTH] = front_bgr
    combined_bgr[20:20 + CANONICAL_HEIGHT, 40 + CANONICAL_WIDTH:40 + CANONICAL_WIDTH * 2] = back_bgr

    return front_bgr, back_bgr, combined_bgr, demographics
