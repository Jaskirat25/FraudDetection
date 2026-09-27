"""
test_ocr.py - Test Script for Fast OCR (M4) + Verhoeff Checksum Validation (M5).
Usage:
    python test_ocr.py [path_to_image.jpg]
"""

import sys
import os
import time
from pathlib import Path
import cv2

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from core.types import FieldCrop
from modules.register.roboflow_detector import detect_fields_with_roboflow
from modules.ocr.ocr_extractor import extract_fields
from modules.validate.verhoeff import validate_verhoeff


def main():
    if len(sys.argv) > 1:
        image_path = sys.argv[1]
    else:
        image_path = "WhatsApp Image 2026-09-27 at 5.05.50 PM.jpeg"
        if not os.path.exists(image_path):
            image_path = "sample.jpg"

    print(f"\n=======================================================")
    print(f"  Testing Fast OCR (M4) & Verhoeff Checksum (M5)")
    print(f"=======================================================")
    print(f"Target Image: {image_path}")

    # Step 1: Detect Crops using Roboflow
    start_total = time.time()
    t0 = time.time()
    image = cv2.imread(image_path)
    if image is None:
        print(f"[-] Could not load image: {image_path}")
        return

    print("\n1. Running Roboflow Field Detection...")
    crops, _ = detect_fields_with_roboflow(image_path, image)
    print(f"   [+] Detected {len(crops)} fields in {time.time() - t0:.2f}s")

    if not crops:
        print("[-] No crops found.")
        return

    # Step 2: Run Optimized OCR
    t1 = time.time()
    print("\n2. Running Optimized OCR Extraction...")
    ocr_results = extract_fields(crops)
    print(f"   [+] OCR extracted in {time.time() - t1:.2f}s")

    print("\n--- Extracted Fields ---")
    for f_name, (text, conf) in ocr_results.items():
        print(f"  * {f_name:15s} : '{text}' (Confidence: {conf * 100:.1f}%)")

    # Step 3: Verhoeff Checksum
    print("\n3. Testing Verhoeff Checksum (L2)...")
    aadhaar_val = ocr_results.get("aadhaar_no", ("", 0.0))[0]
    raw_digits = "".join(filter(str.isdigit, aadhaar_val))

    if len(raw_digits) == 12:
        is_valid = validate_verhoeff(raw_digits)
        status_str = "[PASS] VALID (Real Aadhaar Number structure)" if is_valid else "[FAIL] INVALID / CORRUPTED (Checksum Failed)"
        print(f"  * Aadhaar Number: {aadhaar_val}")
        print(f"  * Checksum Status: {status_str}")
    elif len(raw_digits) >= 4:
        print(f"  * Masked Aadhaar: {aadhaar_val} (Last 4: {raw_digits[-4:]})")
    else:
        print(f"  * Aadhaar number could not be parsed: '{aadhaar_val}'")

    print(f"\nTotal Pipeline Time: {time.time() - start_total:.2f}s")
    print(f"=======================================================\n")


if __name__ == "__main__":
    main()
