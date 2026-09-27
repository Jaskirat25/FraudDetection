"""
test_qr.py - Test Runner for Secure QR Decoding & Cryptographic Cross-Checking (M3).
Usage:
    python test_qr.py [path_to_image.jpg]
"""

import sys
import os
import time
from pathlib import Path
import cv2

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from modules.register.roboflow_detector import detect_fields_with_roboflow
from modules.ocr.ocr_extractor import extract_fields
from modules.qr.qr_verifier import decode_and_verify_qr, cross_check_qr_with_ocr


def main():
    if len(sys.argv) > 1:
        image_path = sys.argv[1]
    else:
        image_path = "WhatsApp Image 2026-09-27 at 5.05.50 PM.jpeg"
        if not os.path.exists(image_path):
            image_path = "sample.jpg"

    if not os.path.exists(image_path):
        print(f"[-] Image not found: {image_path}")
        return

    print("\n=======================================================")
    print("  Testing Secure QR Decode & Cryptographic Cross-Check (L1)")
    print("=======================================================")
    print(f"Card Image: {image_path}")

    # 1. Detect Fields
    image = cv2.imread(image_path)
    print("\n1. Extracting card crops...")
    crops, _ = detect_fields_with_roboflow(image_path, image)
    
    qr_crop = next((c.image for c in crops if c.name == "qr_code"), None)
    if qr_crop is not None:
        print(f"   [+] Located QR code crop: shape={qr_crop.shape}")
    else:
        print("   [-] Dedicated QR crop not found; will scan entire card.")

    # 2. Run OCR for comparison
    print("\n2. Extracting printed text via OCR...")
    ocr_fields = extract_fields(crops)
    for f, (val, conf) in ocr_fields.items():
        print(f"   * Printed {f:12s}: '{val}' ({conf*100:.1f}%)")

    # 3. Decode QR Code (L1)
    print("\n3. Decoding & Verifying QR Code (L1)...")
    t0 = time.time()
    qr_result = decode_and_verify_qr(image, qr_crop=qr_crop)
    print(f"   [+] QR Decode executed in {time.time() - t0:.3f}s")

    print(f"   * QR Present:         {qr_result.present}")
    print(f"   * Is Secure QR (2019+): {qr_result.is_secure_qr}")
    print(f"   * Signature Valid:    {qr_result.signature_valid}")
    
    if qr_result.payload:
        print("\n--- Decompressed QR Demographics (Digital Source of Truth) ---")
        for k, v in qr_result.payload.items():
            if k != "raw":
                print(f"   * QR {k:15s}: '{v}'")

    if qr_result.photo is not None:
        photo_save_path = Path("data/test_crops/qr_embedded_photo.jpg")
        photo_save_path.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(photo_save_path), qr_result.photo)
        print(f"   [+] Extracted embedded QR face photo to: {photo_save_path}")

    # 4. Cryptographic Cross-Check (QR vs Print)
    print("\n4. Running Cryptographic Cross-Check (QR vs Printed Card)...")
    if qr_result.present and qr_result.payload:
        is_fraud, violations, scores = cross_check_qr_with_ocr(qr_result.payload, ocr_fields)
        if is_fraud:
            print("\n  🚨 [VERDICT: FRAUD DETECTED]")
            for v in violations:
                print(f"     ❌ {v}")
        else:
            print("\n  ✅ [VERDICT: GENUINE / AUTHENTIC CARD]")
            print("     All printed fields align with the cryptographically signed QR code payload!")
    else:
        print("  ⚠️ QR code was not readable on this scan; defaulting to ML and heuristic layers.")

    print("\n=======================================================\n")


if __name__ == "__main__":
    main()
