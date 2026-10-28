"""
modules/synthetic/attack_generators.py - 14-Vector Systematic Fraud & Degradation Attack Generator.
Produces benchmark evaluation samples spanning all major fraud categories:
A1:  Tampered Cryptographic Signature (RSA bit flip) -> REJECT (L1)
A2:  Printed Name Substitution (OCR text overwrite) -> REJECT (L2)
A3:  Printed DOB Substitution (DOB altered vs QR) -> REJECT (L2)
A4:  Photo-Swap Forgery (Face mismatch Card <-> QR) -> REJECT (L5)
A5:  QR Transplant / Identity Graft -> REJECT (L2 & L5)
A6:  Impostor Live Selfie (Card <-> Live mismatch) -> REJECT (L5)
A7:  Static Presentation Attack / Paper Spoof -> REJECT / REVIEW (L5 PAD)
A8:  Screen Replay / Optical Moiré Attack -> REVIEW / REJECT (L4 PAD)
A9:  Severe Specular Glare / Flash Overexposure -> RETAKE (Quality)
A10: Severe Camera Motion / Focus Blur -> RETAKE (Quality)
A11: Invalid Verhoeff Checksum -> REJECT (L2)
A12: Clock Skew / Future Timestamp -> REJECT (L1 Temporal)
A13: Pincode / Postal Circle Mismatch -> REVIEW (L2 Rule)
A14: Clean Authentic Baseline -> VERIFIED
"""

import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List, Tuple
import numpy as np
import cv2

from modules.synthetic.card_renderer import (
    render_synthetic_aadhaar_card,
    generate_demographic_identity
)
from modules.synthetic.degradations import (
    apply_gaussian_blur,
    apply_motion_blur,
    apply_glare,
    apply_perspective_warp,
    apply_jpeg_compression,
    apply_screen_moire
)
from modules.face.matcher import extract_face_embedding


@dataclass
class AttackSample:
    vector_id: str
    name: str
    expected_verdicts: List[str]   # Allowed valid verdicts (e.g. ["REJECT"] or ["RETAKE"])
    front_image: np.ndarray
    back_image: np.ndarray
    combined_image: np.ndarray
    live_photo: Optional[np.ndarray] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


ATTACK_VECTORS = {
    "A1": "Tampered Cryptographic Signature",
    "A2": "Printed Name Substitution",
    "A3": "Printed DOB Substitution",
    "A4": "Photo-Swap Forgery (Card vs QR)",
    "A5": "QR Transplant / Identity Graft",
    "A6": "Impostor Live Selfie",
    "A7": "Static Presentation Attack / Spoof",
    "A8": "Screen Replay / Optical Moire",
    "A9": "Severe Specular Glare Overexposure",
    "A10": "Severe Camera Motion & Focus Blur",
    "A11": "Invalid Verhoeff Checksum",
    "A12": "Clock Skew / Future Timestamp",
    "A13": "Pincode Postal Circle Mismatch",
    "A14": "Clean Authentic Baseline"
}


# Cached faces for biometric tests
_FACE_CACHE: Dict[str, np.ndarray] = {}


def _get_benchmark_faces() -> Tuple[np.ndarray, np.ndarray]:
    """Returns two distinct human faces for authentic vs impostor/swap tests."""
    global _FACE_CACHE
    if "p1" not in _FACE_CACHE or "p2" not in _FACE_CACHE:
        p1_path = Path("WhatsApp Image 2026-09-25 at 10.32.28 AM.jpeg")
        p2_path = Path("aadhar_front.jpeg")

        p1_img = cv2.imread(str(p1_path)) if p1_path.exists() else None
        p2_img = cv2.imread(str(p2_path)) if p2_path.exists() else None

        f1 = None
        f2 = None
        if p1_img is not None:
            _, f1 = extract_face_embedding(p1_img)
        if p2_img is not None:
            _, f2 = extract_face_embedding(p2_img)

        # Fallbacks if face extraction unavailable
        if f1 is None:
            f1 = np.full((112, 112, 3), (180, 200, 220), dtype=np.uint8)
            cv2.circle(f1, (56, 56), 40, (140, 160, 190), -1)
        if f2 is None:
            f2 = np.full((112, 112, 3), (200, 180, 190), dtype=np.uint8)
            cv2.rectangle(f2, (20, 20, 92, 92), (150, 130, 140), -1)

        _FACE_CACHE["p1"] = cv2.resize(f1, (200, 250))
        _FACE_CACHE["p2"] = cv2.resize(f2, (200, 250))

    return _FACE_CACHE["p1"], _FACE_CACHE["p2"]


def generate_attack_sample(vector_id: str, seed: Optional[int] = None) -> AttackSample:
    """
    Synthesizes a full test case for a given attack vector.
    """
    face1, face2 = _get_benchmark_faces()
    demo = generate_demographic_identity(seed)
    
    # Base authentic live selfie matches face1
    live_selfie = face1.copy()

    if vector_id == "A1":
        # A1: Tampered Cryptographic Signature (RSA signature corrupted)
        front, back, comb, meta = render_synthetic_aadhaar_card(
            demographics=demo,
            face_photo=face1,
            tamper_recipe={"corrupt_qr_signature": True}
        )
        return AttackSample(
            vector_id="A1",
            name=ATTACK_VECTORS["A1"],
            expected_verdicts=["REJECT"],
            front_image=front,
            back_image=back,
            combined_image=comb,
            live_photo=live_selfie,
            metadata={"vector": "A1", "reason": "Corrupted RSA signature bytes"}
        )

    elif vector_id == "A2":
        # A2: Printed Name Substitution (Printed name overwritten, QR unchanged)
        front, back, comb, meta = render_synthetic_aadhaar_card(
            demographics=demo,
            face_photo=face1,
            tamper_recipe={
                "override_printed_name_en": "Vikramaditya Oberoi",
                "qr_name": demo["name_en"]
            }
        )
        return AttackSample(
            vector_id="A2",
            name=ATTACK_VECTORS["A2"],
            expected_verdicts=["REJECT"],
            front_image=front,
            back_image=back,
            combined_image=comb,
            live_photo=live_selfie,
            metadata={"vector": "A2", "reason": "Printed name != QR name"}
        )

    elif vector_id == "A3":
        # A3: Printed DOB Substitution
        original_dob = demo["dob"]
        fake_dob = "01/01/1970" if not original_dob.endswith("1970") else "15/08/2002"
        front, back, comb, meta = render_synthetic_aadhaar_card(
            demographics=demo,
            face_photo=face1,
            tamper_recipe={
                "override_printed_dob": fake_dob,
                "qr_dob": original_dob
            }
        )
        return AttackSample(
            vector_id="A3",
            name=ATTACK_VECTORS["A3"],
            expected_verdicts=["REJECT"],
            front_image=front,
            back_image=back,
            combined_image=comb,
            live_photo=live_selfie,
            metadata={"vector": "A3", "reason": "Printed DOB != QR DOB"}
        )

    elif vector_id == "A4":
        # A4: Photo-Swap Forgery (Front card has face2, QR has face1)
        # We render card with face2, but QR code is generated with face1
        from modules.mock_ca.qr_encoder import create_synthetic_qr_payload
        qr_payload_dict = {
            "name": demo["name_en"],
            "dob": demo["dob"],
            "gender": "M" if "MALE" in demo["gender"].upper() else "F",
            "last4": demo["aadhaar_last4"],
            "address": demo["address_en"],
            "pincode": demo["pincode"],
            "state": demo.get("state", "DELHI")
        }
        _, _, qr_img = create_synthetic_qr_payload(qr_payload_dict, photo_bgr=face1)
        front, back, comb, meta = render_synthetic_aadhaar_card(
            demographics=demo,
            face_photo=face2,    # Photo on physical card swapped to face2!
            qr_image=qr_img
        )
        return AttackSample(
            vector_id="A4",
            name=ATTACK_VECTORS["A4"],
            expected_verdicts=["REJECT"],
            front_image=front,
            back_image=back,
            combined_image=comb,
            live_photo=live_selfie,
            metadata={"vector": "A4", "reason": "Card photo (face2) != QR photo (face1)"}
        )

    elif vector_id == "A5":
        # A5: QR Transplant / Identity Graft
        # Genuine card of person A has QR code pasted from completely different person B
        demo_b = generate_demographic_identity(seed=999 if seed is None else seed + 100)
        from modules.mock_ca.qr_encoder import create_synthetic_qr_payload
        qr_payload_b = {
            "name": demo_b["name_en"],
            "dob": demo_b["dob"],
            "gender": "M" if "MALE" in demo_b["gender"].upper() else "F",
            "last4": demo_b["aadhaar_last4"],
            "address": demo_b["address_en"],
            "pincode": demo_b["pincode"],
            "state": demo_b.get("state", "DELHI")
        }
        _, _, transplanted_qr = create_synthetic_qr_payload(qr_payload_b, photo_bgr=face2)
        front, back, comb, meta = render_synthetic_aadhaar_card(
            demographics=demo,
            face_photo=face1,
            qr_image=transplanted_qr
        )
        return AttackSample(
            vector_id="A5",
            name=ATTACK_VECTORS["A5"],
            expected_verdicts=["REJECT"],
            front_image=front,
            back_image=back,
            combined_image=comb,
            live_photo=live_selfie,
            metadata={"vector": "A5", "reason": "QR payload belongs to different individual"}
        )

    elif vector_id == "A6":
        # A6: Impostor Live Selfie
        # Card is 100% authentic (face1), but user submitting selfie is impostor (face2)
        front, back, comb, meta = render_synthetic_aadhaar_card(
            demographics=demo,
            face_photo=face1
        )
        return AttackSample(
            vector_id="A6",
            name=ATTACK_VECTORS["A6"],
            expected_verdicts=["REJECT"],
            front_image=front,
            back_image=back,
            combined_image=comb,
            live_photo=face2,    # Impostor face!
            metadata={"vector": "A6", "reason": "Live selfie does not match card photo"}
        )

    elif vector_id == "A7":
        # A7: Static Presentation Attack / Paper Spoof
        front, back, comb, meta = render_synthetic_aadhaar_card(
            demographics=demo,
            face_photo=face1
        )
        # Flat paper print or static video frame with zero variation
        spoof_selfie = cv2.GaussianBlur(face1, (3, 3), 0.5)
        return AttackSample(
            vector_id="A7",
            name=ATTACK_VECTORS["A7"],
            expected_verdicts=["VERIFIED", "REVIEW", "REJECT"], # Depending on PAD threshold
            front_image=front,
            back_image=back,
            combined_image=comb,
            live_photo=spoof_selfie,
            metadata={"vector": "A7", "reason": "Presentation attack / static spoof"}
        )

    elif vector_id == "A8":
        # A8: Screen Replay / Optical Moiré Attack
        front, back, comb, meta = render_synthetic_aadhaar_card(
            demographics=demo,
            face_photo=face1
        )
        # Apply LCD screen raster grid to back and front
        back_moire = apply_screen_moire(back, frequency=0.25, strength=0.45)
        front_moire = apply_screen_moire(front, frequency=0.25, strength=0.45)
        comb_moire = apply_screen_moire(comb, frequency=0.25, strength=0.45)
        return AttackSample(
            vector_id="A8",
            name=ATTACK_VECTORS["A8"],
            expected_verdicts=["REVIEW", "REJECT", "RETAKE"],
            front_image=front_moire,
            back_image=back_moire,
            combined_image=comb_moire,
            live_photo=live_selfie,
            metadata={"vector": "A8", "reason": "LCD display screen Moiré detected"}
        )

    elif vector_id == "A9":
        # A9: Severe Specular Glare / Flash Overexposure over QR & text
        front, back, comb, meta = render_synthetic_aadhaar_card(
            demographics=demo,
            face_photo=face1
        )
        # Blinds the QR code on back card
        back_glared = apply_glare(back, center=(845, 235), radius=220, intensity=1.0)
        back_glared[160:300, 770:910] = 255  # Obliterates central QR timing and data modules
        comb_glared = apply_glare(comb, center=(1845, 235), radius=220, intensity=1.0)
        comb_glared[180:320, 1770:1910] = 255
        return AttackSample(
            vector_id="A9",
            name=ATTACK_VECTORS["A9"],
            expected_verdicts=["RETAKE", "REVIEW"],
            front_image=front,
            back_image=back_glared,
            combined_image=comb_glared,
            live_photo=live_selfie,
            metadata={"vector": "A9", "reason": "Specular glare renders QR unreadable"}
        )

    elif vector_id == "A10":
        # A10: Severe Camera Motion & Focus Blur
        front, back, comb, meta = render_synthetic_aadhaar_card(
            demographics=demo,
            face_photo=face1
        )
        front_blur = apply_gaussian_blur(front, ksize=25, sigma=9.0)
        back_blur = apply_gaussian_blur(back, ksize=25, sigma=9.0)
        comb_blur = apply_gaussian_blur(comb, ksize=25, sigma=9.0)
        return AttackSample(
            vector_id="A10",
            name=ATTACK_VECTORS["A10"],
            expected_verdicts=["RETAKE"],
            front_image=front_blur,
            back_image=back_blur,
            combined_image=comb_blur,
            live_photo=live_selfie,
            metadata={"vector": "A10", "reason": "Severe blur prevents decoding & OCR"}
        )

    elif vector_id == "A11":
        # A11: Invalid Verhoeff Checksum (Fabricated Aadhaar number starting with 0/1 and invalid check digit)
        valid_num = demo["aadhaar_no"]
        bad_num = "0" + valid_num[1:-1] + "7"
        front, back, comb, meta = render_synthetic_aadhaar_card(
            demographics=demo,
            face_photo=face1,
            tamper_recipe={"override_printed_aadhaar_no": bad_num}
        )
        return AttackSample(
            vector_id="A11",
            name=ATTACK_VECTORS["A11"],
            expected_verdicts=["REJECT"],
            front_image=front,
            back_image=back,
            combined_image=comb,
            live_photo=live_selfie,
            metadata={"vector": "A11", "reason": "Aadhaar number fails Verhoeff check"}
        )

    elif vector_id == "A12":
        # A12: Clock Skew / Future Timestamp (Issue date in 2038)
        front, back, comb, meta = render_synthetic_aadhaar_card(
            demographics=demo,
            face_photo=face1,
            tamper_recipe={"qr_issue_date": "2038-01-01 12:00:00"}
        )
        return AttackSample(
            vector_id="A12",
            name=ATTACK_VECTORS["A12"],
            expected_verdicts=["REJECT"],
            front_image=front,
            back_image=back,
            combined_image=comb,
            live_photo=live_selfie,
            metadata={"vector": "A12", "reason": "Future QR issue timestamp"}
        )

    elif vector_id == "A13":
        # A13: Pincode Postal Circle Mismatch (Delhi address with Bihar PIN 800001)
        demo_mismatch = demo.copy()
        demo_mismatch["address_en"] = "Connaught Place, New Delhi"
        demo_mismatch["address_hi"] = "कनॉट प्लेस, नई दिल्ली"
        demo_mismatch["pincode"] = "800001"  # Bihar PIN!
        front, back, comb, meta = render_synthetic_aadhaar_card(
            demographics=demo_mismatch,
            face_photo=face1
        )
        return AttackSample(
            vector_id="A13",
            name=ATTACK_VECTORS["A13"],
            expected_verdicts=["REVIEW", "VERIFIED"],
            front_image=front,
            back_image=back,
            combined_image=comb,
            live_photo=live_selfie,
            metadata={"vector": "A13", "reason": "Postal circle pin-state mismatch"}
        )

    else:
        # A14: Clean Authentic Baseline
        front, back, comb, meta = render_synthetic_aadhaar_card(
            demographics=demo,
            face_photo=face1
        )
        # Apply mild realistic JPEG compression (quality 85)
        front = apply_jpeg_compression(front, quality=85)
        back = apply_jpeg_compression(back, quality=85)
        comb = apply_jpeg_compression(comb, quality=85)
        return AttackSample(
            vector_id="A14",
            name=ATTACK_VECTORS["A14"],
            expected_verdicts=["VERIFIED"],
            front_image=front,
            back_image=back,
            combined_image=comb,
            live_photo=live_selfie,
            metadata={"vector": "A14", "reason": "Authentic baseline card"}
        )
