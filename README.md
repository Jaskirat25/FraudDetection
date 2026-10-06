# Aadhaar Authenticity Screening System (v1)

> **A deterministic, layered document authenticity screening pipeline for Indian Aadhaar cards.**  
> Prioritizes cryptographic proofs and mathematical validation over opaque deep learning classifiers to detect document tampering with 100% certainty.

---

## 🚀 Key Features & Current Progress

- **⚡ Cryptographic Core (Layer 1 — RSA-2048 & Secure QR):**
  - Decodes high-density **UIDAI V5 Secure QR Codes** (2,894-digit Big-Integer decimal streams) in **< 0.1 seconds** using native `zxing-cpp`.
  - Unpacks signed demographics (`Name`, `DOB`, `Gender`, `Address`, `Care-Of`, `PIN`) and embedded JPEG2000 face photos.
  - **Certificate Authority Trust Store:** Includes UIDAI signing certificates spanning **2017 to 2029**.
  - **Deterministic Temporal Key Binding:** Automatically parses microsecond issue timestamps (`YYYYMMDDHHMMSS`) from Reference IDs and binds them to the active certificate validity window.
  - **QR $\leftrightarrow$ Print Cross-Check:** Instantly catches digital text edits (e.g., Photoshop DOB changes) by comparing print text against the signed digital payload.

- **🔢 Mathematical Rule Engine (Layer 2 — Verhoeff Checksum):**
  - Full implementation of the **Verhoeff Checksum Algorithm** ($D_5$ dihedral group).
  - Validates the 12th check digit of Aadhaar numbers in $O(1)$ time to catch fabricated numbers.
  - Validates PIN-to-State geographic consistency.

- **👁️ AI Field Localization (Layer 3 — Localized YOLO):**
  - Runs **100% offline** on local CPU/GPU using fine-tuned weights (`card_detection_better/9`).
  - Automatically isolates bounding crops: `photo`, `qr_code`, `aadhaar_no`, `dob`, `gender`, `name_en`.

- **📝 High-Speed Targeted OCR (Layer 4):**
  - Tailored crop pre-processing with 20px padding and unsharp masking to resolve ambiguous digits (e.g. `5` vs `6`).
  - Built-in Indian surname lexicon autocorrect (`Slngh` $\rightarrow$ `Singh`).
  - Average execution time: **~2.5 seconds**.

- **⚖️ Calibrated Two-Tier Risk Fusion (Layer 1–5 Fusion):**
  - **Tier 1 (Hard Fail):** Conclusive instant rejections on cryptographic mismatches or Verhoeff failures.
  - **Tier 2 (Weighted Points):** Accumulates soft diagnostic flags without generating false-positive rejections.
  - Generates plain-language, explainable diagnostic findings.

---

## 📊 System Architecture

```
                  Input Image (Physical Card Photo)
                                │
                                ▼
               [M2] AI Field Localization (YOLO)
              Isolates Photo, QR, Number, DOB, Name
                                │
        ┌───────────────────────┴───────────────────────┐
        ▼                                               ▼
[M3] Secure QR Engine (L1)                    [M4] Targeted OCR (L4)
- Decodes V5 BigInt Stream                    - Unsharp masking on numbers
- Binds Temporal Cert (2017-2029)             - Surname lexicon correction
- Validates RSA-2048 Signature                          │
        │                                               ▼
        │                                 [M5] Deterministic Rules (L2)
        │                                 - Verhoeff Checksum (D5 Group)
        │                                 - PIN ↔ State Consistency
        │                                               │
        └───────────────────────┬───────────────────────┘
                                ▼
               [M8] Two-Tier Risk Fusion Engine
             - Tier 1: Hard Reject (Tamper Detected)
             - Tier 2: Weighted Point Accumulator
                                │
                                ▼
              Final Verdict: LOW / MEDIUM / HIGH
                   + Explainable Audit Log
```

---

## 📁 Repository Structure

```text
FraudDetection/
├── core/
│   ├── types.py            # Standard dataclasses (FieldCrop, QRResult, RiskReport)
│   └── config.py           # Canonical dimensions, bounding boxes, risk weights
├── modules/
│   ├── register/           # M2 (L3): Offline YOLO field detector
│   ├── qr/                 # M3 (L1): V5 Secure QR decoder, Trust Store, RSA verifier
│   ├── ocr/                # M4 (L4): Field-specific OCR with unsharp masking
│   ├── validate/           # M5 (L2): Verhoeff checksum & deterministic rules
│   ├── tamper/             # M6 (L4): Spatial forensic anomaly checks
│   ├── face/               # M7 (L5): 3-Way biometric face matcher (Upcoming)
│   └── scoring/            # M8: Two-tier risk fusion & explainability engine
├── data/
│   ├── certs/              # UIDAI Root Certificate Trust Store (2017–2029)
│   ├── templates/          # Canonical layout templates & bbox specifications
│   └── test_crops/         # Extracted visual crops and debug outputs
├── test_qr.py              # Dedicated Secure QR & Cryptographic test runner
├── test_ocr.py             # Dedicated OCR & Verhoeff validation test runner
├── run_pipeline.py         # End-to-end screening CLI
└── requirements.txt        # Python dependencies
```

---

## ⚡ Quick Start

### 1. Prerequisites & Virtual Environment
```bash
# Clone the repository
git clone https://github.com/your-username/FraudDetection.git
cd FraudDetection

# Create and activate virtual environment
python -m venv venv
.\venv\Scripts\activate   # On Windows

# Install dependencies
pip install -r requirements.txt
```

### 2. Run Verification Modules

#### Test Secure QR Decoding & RSA Signature Verification:
```bash
python test_qr.py "path/to/card_image.jpg"
```

#### Test Text Extraction & Verhoeff Checksum:
```bash
python test_ocr.py "path/to/card_image.jpg"
```

#### Run Complete End-to-End Screening Pipeline:
```bash
python run_pipeline.py "path/to/card_image.jpg"
```

---

## 📈 Current Milestone Status

- [x] **M0: Foundation & Contracts** — Standard types, configuration, CLI runner.
- [x] **M2: Field Localization** — Localized offline YOLO model for all card crops.
- [x] **M4: OCR & Text Parsing** — Enhanced EasyOCR with unsharp masking and name lexicon.
- [x] **M5: Deterministic Rules** — Verhoeff check digit algorithm & PIN-to-state lookup.
- [x] **M3: Cryptographic Core** — V5 Secure QR decoding, 8-cert Trust Store, temporal key binding, RSA-2048 verification.
- [ ] **M7: Face Biometrics** — ArcFace 3-way identity verification (In Progress).
- [ ] **M9: Web Interface** — Interactive FastAPI drag-and-drop screening dashboard.

---

## ⚖️ License & Ethical Disclosure
This project is built for educational and research purposes in document security. All testing strictly uses synthetic samples or legally permissible masked documents. No personal identity data is stored or logged.
