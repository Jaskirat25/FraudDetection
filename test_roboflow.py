"""
test_roboflow.py - Standalone test script for Roboflow 'card_detection_better/9' Model.
Usage:
    python test_roboflow.py [path_to_image.jpg]
"""

import sys
import os
from pathlib import Path
import cv2
import json

# Ensure project root is in path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from modules.register.roboflow_detector import detect_fields_with_roboflow


def main():
    if len(sys.argv) > 1:
        image_path = sys.argv[1]
    else:
        # Default sample image name
        image_path = "sample.jpg"

    if not os.path.exists(image_path):
        print(f"[-] Image not found at '{image_path}'.")
        print(f"[!] Please place a card image at '{image_path}' or pass the path as an argument:")
        print(f"    python test_roboflow.py path/to/your/card.jpg")
        return

    print(f"\n=======================================================")
    print(f"  Testing Roboflow Model: card_detection_better/9")
    print(f"=======================================================")
    print(f"Target Image: {image_path}")
    print("Calling Roboflow Serverless Inference API...")

    image = cv2.imread(image_path)
    crops, raw_response = detect_fields_with_roboflow(image_path, image)

    if "error" in raw_response:
        print(f"\n[!] Inference Error: {raw_response['error']}")
        return

    predictions = raw_response.get("predictions", [])
    print(f"\n[+] Success! Received {len(predictions)} detections from model:")

    for idx, pred in enumerate(predictions, 1):
        cls_name = pred.get("class", "unknown")
        conf = pred.get("confidence", 0.0)
        x, y, w, h = pred.get("x"), pred.get("y"), pred.get("width"), pred.get("height")
        print(f"  {idx}. Class: '{cls_name:15s}' | Confidence: {conf*100:5.1f}% | Box: (x={x}, y={y}, w={w}, h={h})")

    print(f"\n[+] Standardized {len(crops)} FieldCrop objects for screening pipeline:")
    for crop in crops:
        print(f"  - Pipeline Crop Key: '{crop.name:15s}' | Crop Dimensions: {crop.image.shape}")

    # Optionally save visual crops to data/test_crops/
    output_dir = Path("data/test_crops")
    output_dir.mkdir(parents=True, exist_ok=True)
    for crop in crops:
        crop_save_path = output_dir / f"{crop.name}.jpg"
        cv2.imwrite(str(crop_save_path), crop.image)
    print(f"\n[+] Saved cropped images to: {output_dir.resolve()}")
    print(f"=======================================================\n")


if __name__ == "__main__":
    main()
