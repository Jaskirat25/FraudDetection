"""
test_face.py - Standalone Verification Test Runner for Layer 5 Face Biometrics (M7).
Usage:
    python test_face.py [path_to_card_image] [--live path_to_live_selfie]
"""

import sys
import os
import time
import argparse
from pathlib import Path
import cv2
import numpy as np

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

from modules.register.roboflow_detector import detect_fields_with_roboflow
from modules.qr.qr_verifier import decode_and_verify_qr
from modules.face.matcher import verify_face, extract_face_embedding, compare_embeddings, SFACE_COSINE_THRESHOLD


def main():
    parser = argparse.ArgumentParser(description="Test Layer 5 Face Biometrics (3-Way Verification)")
    parser.add_argument("card_image", nargs="?", default="combined-image.jpg", help="Path to Aadhaar card image")
    parser.add_argument("--live", default=None, help="Path to optional live selfie image")
    parser.add_argument("--simulate-swap", action="store_true", help="Simulate a photo-swap forgery using an impostor face")
    args = parser.parse_args()

    print("\n=======================================================")
    print("  Testing 3-Way Biometric Face Verification (Layer 5)")
    print("=======================================================")
    print(f"Card Image: {args.card_image}")
    if args.live:
        print(f"Live Selfie: {args.live}")

    if not os.path.exists(args.card_image):
        print(f"[-] Image not found: {args.card_image}")
        return

    card_bgr = cv2.imread(args.card_image)
    live_bgr = cv2.imread(args.live) if args.live and os.path.exists(args.live) else None

    # Step 1: Detect card fields (Photo Crop & QR Crop)
    print("\n1. Detecting card fields & extracting crops...")
    crops, _ = detect_fields_with_roboflow(args.card_image, card_bgr)
    photo_crop = next((c.image for c in crops if c.name == "photo"), None)
    qr_crop = next((c.image for c in crops if c.name == "qr_code"), None)

    if photo_crop is not None:
        print(f"   [+] Located Card Photo crop: shape={photo_crop.shape}")
    else:
        print("   [-] Card Photo crop not located in this image.")

    # Step 2: Decode QR & Extract Signed Photo
    print("\n2. Decoding Secure QR & extracting signed photo...")
    t0 = time.time()
    qr_res = decode_and_verify_qr(card_bgr, qr_crop)
    t_qr = time.time() - t0
    print(f"   [+] QR decoded in {t_qr:.3f}s (Present: {qr_res.present}, Sig Valid: {qr_res.signature_valid})")

    if qr_res.photo is not None:
        print(f"   [+] Extracted embedded QR face photo: shape={qr_res.photo.shape}")
    else:
        print("   [-] No embedded face photo in QR code.")

    # Optional: Simulate Photo-Swap Forgery
    card_photo_to_test = photo_crop
    if args.simulate_swap:
        print("\n  ⚠️ [SIMULATION ACTIVE]: Inverting card photo colors and adding noise to simulate photo-swap...")
        if card_photo_to_test is not None:
            # Create a synthetic swapped face by inverting and flipping
            card_photo_to_test = cv2.bitwise_not(cv2.flip(card_photo_to_test, 1))

    # Step 3: Run 3-Way Face Verification
    print("\n3. Executing 3-Way Biometric Verification (M7)...")
    t1 = time.time()
    face_res = verify_face(card_photo=card_photo_to_test, live_photo=live_bgr, qr_photo=qr_res.photo)
    t_face = time.time() - t1
    print(f"   [+] Face matching completed in {t_face:.3f}s")

    print(f"\n--- Diagnostic Evidence ---")
    for k, v in face_res.evidence.items():
        print(f"   * {k:24s}: {v}")

    print(f"\n--- Verification Findings ---")
    for flag in face_res.flags:
        if "FRAUD" in flag or "Mismatch" in flag:
            print(f"   🚨 {flag}")
        elif "Match" in flag or "Verified" in flag or "Confirmed" in flag:
            print(f"   ✅ {flag}")
        else:
            print(f"   ℹ️ {flag}")

    print(f"\n--- Final Module Status ---")
    print(f"   * Hard Fail (Tier 1 Reject): {face_res.hard_fail}")
    print(f"   * Tamper Scores:             {face_res.scores}")

    if face_res.hard_fail:
        print("\n  🚨 [VERDICT: BIOMETRIC FRAUD DETECTED]")
        print("     The physical document has been tampered with or an impostor was detected!")
    else:
        print("\n  ✅ [VERDICT: BIOMETRICS AUTHENTIC & MATCHED]")
        print("     Face consistency verified against cryptographic anchor!")

    print("\n=======================================================\n")


if __name__ == "__main__":
    main()
