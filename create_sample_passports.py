"""
create_sample_passports.py - Generate realistic demo passport biodata images for UI testing.
"""

from pathlib import Path
import numpy as np
import cv2

from tests.test_passport_mrz import build_sample_mrz
from modules.passport.mrz import calculate_icao_check_digit
from modules.passport.register import PASSPORT_CANONICAL_WIDTH, PASSPORT_CANONICAL_HEIGHT

SAMPLES_DIR = Path("data/samples")
SAMPLES_DIR.mkdir(parents=True, exist_ok=True)

# Load a real face crop for testing biometric match
front_img = cv2.imread("aadhar_front.jpeg")
if front_img is not None:
    # Face region in aadhar_front.jpeg: approximately (y: 290..760, x: 35..320)
    h, w = front_img.shape[:2]
    face_crop = front_img[int(h * 0.28):int(h * 0.78), int(w * 0.03):int(w * 0.33)]
    face_crop = cv2.resize(face_crop, (220, 280))
else:
    face_crop = np.full((280, 220, 3), 200, dtype=np.uint8)
    cv2.putText(face_crop, "PHOTO", (50, 150), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (50, 50, 50), 2)


def make_passport_canvas(
    passport_no: str,
    surname: str,
    given_names: str,
    dob_str: str,  # "DD/MM/YYYY"
    doi_str: str,  # "DD/MM/YYYY"
    doe_str: str,  # "DD/MM/YYYY"
    sex: str,
    nationality: str,
    mrz_line1: str,
    mrz_line2: str,
) -> np.ndarray:
    # Canvas size: 1000x700 (PASSPORT_CANONICAL_WIDTH x PASSPORT_CANONICAL_HEIGHT)
    canvas = np.full((PASSPORT_CANONICAL_HEIGHT, PASSPORT_CANONICAL_WIDTH, 3), 245, dtype=np.uint8)
    
    # Subtly patterned background (watermark / guilloche tint)
    for y in range(0, PASSPORT_CANONICAL_HEIGHT, 15):
        cv2.line(canvas, (0, y), (PASSPORT_CANONICAL_WIDTH, y), (240, 240, 238), 1)

    # Header section
    cv2.rectangle(canvas, (20, 15), (980, 95), (230, 235, 240), -1)
    cv2.rectangle(canvas, (20, 15), (980, 95), (180, 190, 205), 1)
    cv2.putText(canvas, "GOVERNMENT OF INDIA / BHARAT SARKAR", (300, 42), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (70, 70, 80), 2)
    cv2.putText(canvas, "PASSPORT / PASSPORT", (380, 72), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (20, 30, 60), 2)

    # Emblem placeholder
    cv2.circle(canvas, (80, 55), 25, (160, 170, 185), -1)
    cv2.putText(canvas, "IND", (68, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)

    # Insert Portrait Photo (x: 45..265, y: 130..410)
    canvas[130:410, 45:265] = face_crop
    cv2.rectangle(canvas, (45, 130), (265, 410), (140, 150, 165), 2)

    # VIZ Header fields matching CANONICAL_PASSPORT_FIELDS exactly:
    # 1. Passport No. (x: 730, y: 45, w: 240, h: 55)
    cv2.putText(canvas, "Passport No.", (735, 62), cv2.FONT_HERSHEY_SIMPLEX, 0.40, (120, 120, 130), 1)
    cv2.putText(canvas, passport_no, (735, 92), cv2.FONT_HERSHEY_SIMPLEX, 0.80, (10, 10, 20), 2)

    # 2. Surname (x: 290, y: 105, w: 680, h: 50)
    cv2.putText(canvas, "Surname", (295, 122), cv2.FONT_HERSHEY_SIMPLEX, 0.40, (120, 120, 130), 1)
    cv2.putText(canvas, surname, (295, 148), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (10, 10, 20), 2)

    # 3. Given Names (x: 290, y: 170, w: 680, h: 50)
    cv2.putText(canvas, "Given Name(s)", (295, 187), cv2.FONT_HERSHEY_SIMPLEX, 0.40, (120, 120, 130), 1)
    cv2.putText(canvas, given_names, (295, 212), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (10, 10, 20), 2)

    # 4. Nationality (x: 290, y: 235, w: 200, h: 45)
    cv2.putText(canvas, "Nationality", (295, 252), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (120, 120, 130), 1)
    cv2.putText(canvas, nationality, (295, 274), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (10, 10, 20), 2)

    # 5. Sex (x: 520, y: 235, w: 80, h: 45)
    cv2.putText(canvas, "Sex", (525, 252), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (120, 120, 130), 1)
    cv2.putText(canvas, sex, (525, 274), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (10, 10, 20), 2)

    # 6. Date of Birth (x: 640, y: 235, w: 200, h: 45)
    cv2.putText(canvas, "Date of Birth", (645, 252), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (120, 120, 130), 1)
    cv2.putText(canvas, dob_str, (645, 274), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (10, 10, 20), 2)

    # 7. Date of Issue (x: 290, y: 415, w: 300, h: 45)
    cv2.putText(canvas, "Date of Issue", (295, 432), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (120, 120, 130), 1)
    cv2.putText(canvas, doi_str, (295, 454), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (10, 10, 20), 2)

    # 8. Date of Expiry (x: 640, y: 415, w: 300, h: 45)
    cv2.putText(canvas, "Date of Expiry", (645, 432), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (120, 120, 130), 1)
    cv2.putText(canvas, doe_str, (645, 454), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (10, 10, 20), 2)

    # MRZ Zone Background Strip (natural off-white document paper, not saturated glare)
    cv2.rectangle(canvas, (20, 520), (980, 680), (242, 244, 246), -1)
    cv2.rectangle(canvas, (20, 520), (980, 680), (200, 205, 215), 1)

    # High contrast MRZ Lines in OCR-B font style (monospace)
    cv2.putText(canvas, mrz_line1, (35, 575), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (10, 10, 15), 2)
    cv2.putText(canvas, mrz_line2, (35, 635), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (10, 10, 15), 2)

    return canvas


def main():
    # 1. Sample Authentic Passport (Jaskirat Singh)
    l1, l2 = build_sample_mrz(
        surname="SINGH",
        given_names="JASKIRAT",
        passport_no="L1234567<",
        dob="031125",
        sex="M",
        expiry="300109",
    )
    p_auth = make_passport_canvas(
        passport_no="L1234567",
        surname="SINGH",
        given_names="JASKIRAT",
        dob_str="25/11/2003",
        doi_str="10/01/2020",
        doe_str="09/01/2030",
        sex="M",
        nationality="INDIAN",
        mrz_line1=l1,
        mrz_line2=l2,
    )
    cv2.imwrite(str(SAMPLES_DIR / "sample_passport_authentic.jpg"), p_auth)
    print("Created sample_passport_authentic.jpg")

    # 2. Sample Tampered VIZ (Number altered on card text)
    p_tamper = make_passport_canvas(
        passport_no="Z9876543",  # Forged VIZ number
        surname="SINGH",
        given_names="JASKIRAT",
        dob_str="25/11/2003",
        doi_str="10/01/2020",
        doe_str="09/01/2030",
        sex="M",
        nationality="INDIAN",
        mrz_line1=l1,
        mrz_line2=l2,  # MRZ still has genuine L1234567
    )
    cv2.imwrite(str(SAMPLES_DIR / "sample_passport_tampered.jpg"), p_tamper)
    print("Created sample_passport_tampered.jpg")

    # 3. Sample Expired Passport
    l1_exp, l2_exp = build_sample_mrz(
        surname="SINGH",
        given_names="JASKIRAT",
        passport_no="L1234567<",
        dob="031125",
        sex="M",
        expiry="220109",  # Expired in 2022
    )
    p_expired = make_passport_canvas(
        passport_no="L1234567",
        surname="SINGH",
        given_names="JASKIRAT",
        dob_str="25/11/2003",
        doi_str="10/01/2012",
        doe_str="09/01/2022",
        sex="M",
        nationality="INDIAN",
        mrz_line1=l1_exp,
        mrz_line2=l2_exp,
    )
    cv2.imwrite(str(SAMPLES_DIR / "sample_passport_expired.jpg"), p_expired)
    print("Created sample_passport_expired.jpg")

    # 4. Sample OCR Confusion / C-11 Repair
    # Corrupt l2 with 'O' instead of '0' in passport number
    l1_rep, l2_clean = build_sample_mrz(
        surname="SINGH",
        given_names="JASKIRAT",
        passport_no="L1234560<",
        dob="031125",
        sex="M",
        expiry="300109",
    )
    l2_corrupt = l2_clean[:7] + "O" + l2_clean[8:]
    p_repair = make_passport_canvas(
        passport_no="L1234560",  # VIZ has clean digit 0
        surname="SINGH",
        given_names="JASKIRAT",
        dob_str="25/11/2003",
        doi_str="10/01/2020",
        doe_str="09/01/2030",
        sex="M",
        nationality="INDIAN",
        mrz_line1=l1_rep,
        mrz_line2=l2_corrupt,
    )
    cv2.imwrite(str(SAMPLES_DIR / "sample_passport_repair.jpg"), p_repair)
    print("Created sample_passport_repair.jpg")


if __name__ == "__main__":
    main()
