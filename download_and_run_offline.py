"""
download_and_run_offline.py - Local Model Cacher and Offline Detector.
Downloads 'card_detection_better/9' weights to your local machine on the first run.
After the first run, it executes 100% offline without needing internet.
"""

import os
import sys
import time
from pathlib import Path
import cv2

try:
    from inference import get_model
except ImportError:
    print("[-] 'inference' package is not installed.")
    print("[!] Please run: pip install inference")
    sys.exit(1)

# Configuration
MODEL_ID = "card_detection_better/9"
API_KEY = "kSVtqUq5B0X9afwZyNag"

# Sample image
IMAGE_PATH = sys.argv[1] if len(sys.argv) > 1 else "WhatsApp Image 2026-09-24 at 12.09.37 AM.jpeg"


def main():
    if not os.path.exists(IMAGE_PATH):
        print(f"[-] Target image '{IMAGE_PATH}' not found.")
        print("    Usage: python download_and_run_offline.py path_to_image.jpg")
        return

    print("=======================================================")
    print("  Loading Local Model: card_detection_better/9")
    print("  (Downloads to local disk cache on 1st run; offline afterwards)")
    print("=======================================================")
    
    t0 = time.time()
    # Loads or downloads model to local cache
    model = get_model(model_id=MODEL_ID, api_key=API_KEY)
    print(f"[+] Model loaded into memory in {time.time() - t0:.2f}s")

    print(f"\nRunning local inference on: {IMAGE_PATH}")
    t1 = time.time()
    results = model.infer(IMAGE_PATH)
    inference_time = time.time() - t1
    print(f"[+] Local inference finished in {inference_time:.2f}s!")

    print("\n--- Detections ---")
    predictions = results[0].predictions if hasattr(results[0], 'predictions') else getattr(results, 'predictions', results)
    
    # Print predictions cleanly
    if isinstance(predictions, list):
        for idx, pred in enumerate(predictions, 1):
            cls_name = getattr(pred, 'class_name', getattr(pred, 'class', 'unknown'))
            conf = getattr(pred, 'confidence', 0.0)
            x = getattr(pred, 'x', 0)
            y = getattr(pred, 'y', 0)
            w = getattr(pred, 'width', 0)
            h = getattr(pred, 'height', 0)
            print(f"  {idx}. Class: '{cls_name:15s}' | Conf: {conf*100:5.1f}% | Box: (x={x:.1f}, y={y:.1f}, w={w:.1f}, h={h:.1f})")
    else:
        print(results)

    print("=======================================================\n")


if __name__ == "__main__":
    main()
