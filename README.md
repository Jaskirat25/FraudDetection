# Aadhaar Authenticity Screening System (v1)

A layered document authenticity screening pipeline combining cryptographic verification, deterministic document rules, geometric template registration, forensic tamper anomaly detection, and biometric face verification.

---

## Architecture: 5-Layer Defense-in-Depth

| Layer | Method | Certainty | Primary Target |
|---|---|---|---|
| **L1** | Secure QR RSA Signature & Payload Cross-Check | Cryptographic | 2019+ cards with readable QR |
| **L2** | Deterministic Rules (Verhoeff checksum, PIN-to-state, Indic transliteration) | High | All cards |
| **L3** | Geometric Template Registration & Homography Rectification | High | Fixed nationwide template |
| **L4** | Per-Field Forensic Anomaly & Tamper Detection | Probabilistic | Cards where L1 is unreadable/pre-2019 |
| **L5** | 3-Way Face Verification (Card Photo $\leftrightarrow$ Live $\leftrightarrow$ QR Photo) | Probabilistic | Identity binding |

---

## Directory Layout

```
aadhaar-screen/
  core/          # Data contracts (types.py), canonical dimensions & config (config.py)
  modules/       # L1-L5 implementation packages
    register/    # M2: Geometric registration and field cropping
    qr/          # M3: Secure QR decoding and RSA signature verification
    ocr/         # M4: Dual-engine OCR field text extraction
    validate/    # M5: Verhoeff algorithm and deterministic rules
    tamper/      # M6: Per-crop forensic & ML anomaly detection
    face/        # M7: ArcFace 3-way identity verification
    scoring/     # M8: Two-tier risk fusion and explainability
  datagen/       # M1: Synthetic card generation & print-scan degradation
  data/          # Templates, certs, synthetic samples, and benchmarks
  api/           # M9: FastAPI screening endpoint
  run_pipeline.py# End-to-end CLI runner
```

---

## Quick Start

### 1. Run Pipeline
```bash
python run_pipeline.py sample.jpg
```
