import os
import warnings
import sys

# Silence noisy optional plugin warnings from Roboflow and ONNX
os.environ["CORE_MODEL_GAZE_ENABLED"] = "False"
os.environ["CORE_MODEL_SAM_ENABLED"] = "False"
os.environ["CORE_MODEL_SAM3_ENABLED"] = "False"
os.environ["CORE_MODEL_YOLO_WORLD_ENABLED"] = "False"
os.environ["ONNXRUNTIME_LOG_LEVEL"] = "3"
warnings.filterwarnings("ignore")

from typing import List, Tuple, Dict, Any, Optional
import numpy as np
import cv2
from core.types import FieldCrop

ROBOFLOW_API_KEY = "kSVtqUq5B0X9afwZyNag"
MODEL_ID = "card_detection_better/9"

# Cache local model instance
_LOCAL_MODEL = None


def _get_local_model():
    """Loads local cached model if 'inference' package is installed."""
    global _LOCAL_MODEL
    if _LOCAL_MODEL is None:
        try:
            from inference import get_model
            _LOCAL_MODEL = get_model(model_id=MODEL_ID, api_key=ROBOFLOW_API_KEY)
        except Exception as e:
            _LOCAL_MODEL = None
    return _LOCAL_MODEL


def detect_fields_with_roboflow(
    image_path: str,
    image_np: Optional[np.ndarray] = None
) -> Tuple[List[FieldCrop], Dict[str, Any]]:
    """
    Detects card fields using local cached model first, falling back to serverless API.
    Returns:
        (crops_list, raw_predictions_dict)
    """
    if image_np is None:
        image_np = cv2.imread(image_path)
        if image_np is None:
            raise ValueError(f"Unable to read image at: {image_path}")

    img_h, img_w = image_np.shape[:2]
    predictions = []
    raw_response = {}

    # 1. Try Local Offline Engine First
    local_model = _get_local_model()
    if local_model is not None:
        try:
            res = local_model.infer(image_path)
            raw_response = {"source": "local_offline", "result": res}
            preds_obj = res[0].predictions if (isinstance(res, list) and hasattr(res[0], 'predictions')) else getattr(res, 'predictions', [])
            
            for p in preds_obj:
                predictions.append({
                    "class": getattr(p, 'class_name', getattr(p, 'class', 'unknown')),
                    "confidence": getattr(p, 'confidence', 0.0),
                    "x": getattr(p, 'x', 0),
                    "y": getattr(p, 'y', 0),
                    "width": getattr(p, 'width', 0),
                    "height": getattr(p, 'height', 0)
                })
        except Exception as e:
            print(f"[Roboflow Local Notice]: {e}. Trying HTTP client...")

    # 2. Fallback to HTTP Serverless Client if local was unavailable
    if not predictions:
        try:
            from inference_sdk import InferenceHTTPClient, InferenceConfiguration
            client = InferenceHTTPClient(
                api_url="https://serverless.roboflow.com",
                api_key=ROBOFLOW_API_KEY
            ).configure(InferenceConfiguration(api_key_transport="header"))
            
            res = client.infer(image_path, model_id=MODEL_ID)
            raw_response = res
            predictions = res.get("predictions", [])
        except Exception as e:
            print(f"[Roboflow Error]: {e}")
            return [], {"error": str(e)}

    # 3. Standardize Predictions into FieldCrops
    label_map = {
        "picture": "photo",
        "face": "photo",
        "photo": "photo",
        "aadhar-qr": "qr_code",
        "aadhar_qr": "qr_code",
        "qr": "qr_code",
        "qr_code": "qr_code",
        "aadhar-number": "aadhaar_no",
        "aadhar_number": "aadhaar_no",
        "aadhaar_number": "aadhaar_no",
        "aadhaar_no": "aadhaar_no",
        "aadhar-dob": "dob",
        "aadhar_dob": "dob",
        "dob": "dob",
        "aadhar-name": "name_en",
        "aadhar_name": "name_en",
        "name": "name_en",
        "aadhar-gender": "gender",
        "aadhar_gender": "gender",
        "gender": "gender",
        "aadhar-front": "card_front",
        "aadhar-emblem": "emblem",
        "aadhar-goi": "header_goi",
        "aadhar-claim": "claim_tagline"
    }

    crops: List[FieldCrop] = []
    for pred in predictions:
        raw_label = str(pred.get("class", "unknown")).lower().strip()
        normalized_name = label_map.get(raw_label, raw_label)

        cx, cy = pred["x"], pred["y"]
        w, h = pred["width"], pred["height"]

        x1 = max(0, int(cx - w / 2))
        y1 = max(0, int(cy - h / 2))
        x2 = min(img_w, int(cx + w / 2))
        y2 = min(img_h, int(cy + h / 2))

        crop_img = image_np[y1:y2, x1:x2].copy()
        crops.append(FieldCrop(
            name=normalized_name,
            image=crop_img,
            bbox=(x1, y1, max(1, x2 - x1), max(1, y2 - y1))
        ))

    return crops, raw_response
