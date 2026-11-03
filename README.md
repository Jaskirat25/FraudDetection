# Aadhaar Authenticity Screening System (v1)

> **A deterministic, layered document authenticity screening pipeline for Indian Aadhaar cards.**
>
> Prioritizes cryptographic verification and mathematical validation over opaque deep learning classifiers to identify potential document tampering through explainable, rule-based verification.

---

## Key Features and Current Progress

### 1. Cryptographic Core — RSA-2048 and Secure QR Verification

- Decodes high-density **UIDAI V5 Secure QR Codes** (2,894-digit Big-Integer decimal streams) in less than 0.1 seconds using native `zxing-cpp`.
- Extracts signed demographic information, including:
  - Name
  - Date of Birth
  - Gender
  - Address
  - Care-of details
  - PIN Code
- Extracts embedded JPEG2000 facial photographs.
- **Certificate Authority Trust Store:** Includes UIDAI signing certificates spanning 2017 to 2029.
- **Deterministic Temporal Key Binding:** Parses issue timestamps (`YYYYMMDDHHMMSS`) from Reference IDs and associates them with the relevant certificate validity period.
- **QR-to-Print Cross-Verification:** Detects discrepancies between printed card information and cryptographically signed digital payloads, including unauthorized changes to dates of birth and other demographic fields.

### 2. Mathematical Rule Engine — Verhoeff Checksum

- Implements the **Verhoeff Checksum Algorithm** using the mathematical structure of the dihedral group \(D_5\).
- Validates the Aadhaar number's check digit to identify structurally invalid or fabricated numbers.
- Performs PIN-to-State geographic consistency checks.

### 3. AI-Based Field Localization — YOLO

- Runs entirely offline on local CPU/GPU hardware using fine-tuned model weights (`card_detection_better/9`).
- Automatically identifies and extracts the following document regions:
  - `photo`
  - `qr_code`
  - `aadhaar_no`
  - `dob`
  - `gender`
  - `name_en`

### 4. Targeted OCR and Text Extraction

- Implements field-specific OCR with customized image preprocessing.
- Uses 20-pixel padding and unsharp masking to improve character recognition and resolve ambiguous digits (e.g., `5` vs. `6`).
- Includes an Indian surname lexicon for contextual text correction (e.g., `Slngh` → `Singh`).
- Average execution time: approximately 2.5 seconds.

### 5. Calibrated Two-Tier Risk Fusion Engine

Combines cryptographic verification, mathematical validation, OCR results, and diagnostic findings into a unified risk assessment.

**Tier 1 — Hard Fail**

- Immediate rejection for conclusive cryptographic signature mismatches.
- Rejection for invalid Verhoeff checksum results.

**Tier 2 — Weighted Risk Assessment**

- Accumulates weighted diagnostic flags.
- Evaluates suspicious inconsistencies without automatically rejecting documents based on individual soft indicators.
- Generates explainable findings in plain language.

---

## System Architecture

```text
                 Input Image (Physical Card Photo)
                               |
                               v
              [M2] AI Field Localization (YOLO)
             Isolates Photo, QR, Number, DOB, Name
                               |
          +--------------------+--------------------+
          |                                         |
          v                                         v
[M3] Secure QR Engine (L1)              [M4] Targeted OCR (L4)
- Decodes V5 BigInt Stream               - Unsharp masking on numbers
- Binds Temporal Certificate             - Surname lexicon correction
- Validates RSA-2048 Signature                    |
          |                                         v
          |                              [M5] Deterministic Rules (L2)
          |                              - Verhoeff Checksum (D5 Group)
          |                              - PIN-to-State Consistency
          |                                         |
          +--------------------+--------------------+
                               |
                               v
              [M8] Two-Tier Risk Fusion Engine
             - Tier 1: Hard Reject
             - Tier 2: Weighted Risk Assessment
                               |
                               v
                  Final Risk Classification
                       LOW / MEDIUM / HIGH
                               |
                               v
                   Explainable Audit Log
```

---

## Repository Structure

```text
FraudDetection/
|
├── core/
│   ├── types.py            # Standard dataclasses (FieldCrop, QRResult, RiskReport)
│   └── config.py           # Canonical dimensions, bounding boxes, risk weights
|
├── modules/
│   ├── register/           # M2 (L3): Offline YOLO field detector
│   ├── qr/                 # M3 (L1): V5 Secure QR decoder, Trust Store, RSA verifier
│   ├── ocr/                # M4 (L4): Field-specific OCR with unsharp masking
│   ├── validate/           # M5 (L2): Verhoeff checksum and deterministic rules
│   ├── tamper/             # M6 (L4): Spatial forensic anomaly checks
│   ├── face/               # M7 (L5): Three-way biometric face matcher
│   └── scoring/            # M8: Two-tier risk fusion and explainability engine
|
├── data/
│   ├── certs/              # UIDAI Root Certificate Trust Store (2017–2029)
│   ├── templates/          # Canonical layout templates and bounding boxes
│   └── test_crops/         # Extracted visual crops and debug outputs
|
├── test_qr.py              # Secure QR and cryptographic test runner
├── test_ocr.py             # OCR and Verhoeff validation test runner
├── run_pipeline.py         # End-to-end screening CLI
└── requirements.txt        # Python dependencies
```

---

## Installation and Quick Start

### 1. Prerequisites and Virtual Environment

Clone the repository:

```bash
git clone https://github.com/your-username/FraudDetection.git

cd FraudDetection
```

Create and activate a virtual environment:

**Windows:**

```bash
python -m venv venv

venv\Scripts\activate
```

**macOS / Linux:**

```bash
python3 -m venv venv

source venv/bin/activate
```

Install the required dependencies:

```bash
pip install -r requirements.txt
```

### 2. Run Individual Verification Modules

**Secure QR Decoding and RSA Signature Verification**

```bash
python test_qr.py "path/to/card_image.jpg"
```

**OCR and Verhoeff Checksum Validation**

```bash
python test_ocr.py "path/to/card_image.jpg"
```

**Three-Way Face Biometric Verification (M7)**

```bash
python test_face.py "path/to/card_image.jpg" --live "path/to/selfie.jpg"
```

**Complete End-to-End Screening Pipeline**

```bash
python run_pipeline.py "path/to/card_image.jpg" --live "path/to/selfie.jpg"
```

### 3. Launch the Interactive Web Dashboard (M9)

Start the FastAPI application:

```bash
python run_web.py
```

Open the following URL in your browser:

```text
http://127.0.0.1:8000
```

The dashboard provides an interactive interface for document uploads and webcam-based live capture.

---

## Development Milestones

| Milestone | Module | Status | Description |
|---|---|---|---|
| M0 | Foundation | Completed | Standard types, configuration, and CLI runner |
| M2 | Field Localization | Completed | Offline YOLO-based document field detection |
| M4 | OCR and Text Parsing | Completed | Enhanced EasyOCR, unsharp masking, and surname lexicon |
| M5 | Deterministic Validation | Completed | Verhoeff checksum and PIN-to-State lookup |
| M3 | Cryptographic Core | Completed | V5 Secure QR decoding, 8-certificate Trust Store, temporal key binding, and RSA-2048 verification |
| M7 | Face Biometrics | Completed | Three-way identity verification using card photo, QR photo, and live selfie with YuNet alignment and SFace cosine similarity |
| M9 | Web Interface | Completed | Interactive FastAPI screening dashboard with drag-and-drop uploads and webcam capture |

---

## License and Ethical Disclosure

This project is developed for educational and research purposes in document security, cryptographic verification, and digital identity fraud detection.

All testing is conducted using synthetic samples or legally permissible masked documents.

The system is designed to minimize exposure of sensitive identity information. No personal identity data is stored or logged.

**Disclaimer:** This system provides automated document authenticity screening and risk assessment. Its outputs should not be treated as definitive legal proof of identity or as a substitute for official UIDAI verification procedures.
