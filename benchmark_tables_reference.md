# Benchmark Tables Reference — IDShield Project

This file preserves all formatted benchmark tables from Section VI for easy copy-pasting or automated insertion into your final report document.

---

### TABLE II: ATTACK VECTOR DETECTION PERFORMANCE & DIAGNOSTIC FINDINGS

| ID | Attack Vector Description | Category | Detection Rate | Primary Verdict | Diagnostic Finding Code |
| :---: | :--- | :--- | :---: | :---: | :--- |
| **A1** | Tampered RSA-2048 Digital Signature | Cryptographic | **100.0%** | `REJECT` | `UIDAI-CRYPTO-001` (Signature Invalidation) |
| **A2** | Printed Name Substitution on Card Face | Typographic | **100.0%** | `REJECT` | `UIDAI-CROSS-002` (Print vs. QR Mismatch) |
| **A3** | Printed Date of Birth (DOB) Alteration | Typographic | **100.0%** | `REJECT` | `UIDAI-CROSS-003` (DOB Discrepancy) |
| **A4** | Photo-Swap Forgery (Card vs. QR Face) | Biometric | **100.0%** | `REJECT` | `UIDAI-BIO-004` (SFace Cosine $< 0.363$) |
| **A5** | QR Code Transplant / Identity Grafting | Tampering | **100.0%** | `REJECT` | `UIDAI-CROSS-005` (Demographic Conflict) |
| **A6** | Impostor Live Selfie Presentation | Biometric | **100.0%** | `REJECT` | `UIDAI-BIO-006` (Live Face Mismatch) |
| **A7** | Static Printed Photo / Mask Attack | Presentation | **100.0%** | `RETAKE` | `PAD-DRIFT-007` (Zero Temporal Motion) |
| **A8** | High-Resolution Display Screen Replay | Presentation | **100.0%** | `RETAKE` | `PAD-MOIRE-008` (2D FFT Moiré Grid Peak) |
| **A9** | Specular Glare Overexposure ($>8\%$) | Optical Quality | **100.0%** | `RETAKE` | `OPT-GLARE-009` (Dynamic Saturation) |
| **A10**| Low-Focus / Severe Motion Blur | Optical Quality | **100.0%** | `RETAKE` | `OPT-BLUR-010` (Laplacian Var $< 25.0$) |
| **A11**| Fabricated Verhoeff Check Digit | Mathematical | **100.0%** | `REJECT` | `UIDAI-MATH-011` (D5 Group Violation) |
| **A12**| Future Issue Timestamp (Clock Skew) | Cryptographic | **100.0%** | `REJECT` | `UIDAI-TIME-012` (Issue $>$ Current Time) |
| **A13**| Postal PIN / State Territory Mismatch | Geographic | **100.0%** | `REVIEW` | `UIDAI-GEO-013` (Soft Diagnostic Flag) |
| **A14**| Clean Authentic Baseline Document | Genuine | **100.0%** | `VERIFIED` | *None* (All Anchors Validated) |

---

### TABLE III: VERIFICATION DECISION CONFUSION MATRIX

| Ground Truth Category | VERIFIED | REJECT | RETAKE | REVIEW | Class Accuracy |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Authentic Baseline** | 2 | 0 | 0 | 0 | **100.0%** |
| **Malicious Forgeries (A1–A6, A11–A12)** | 0 | 8 | 0 | 0 | **100.0%** |
| **Optical Capture Defects (A9–A10)** | 0 | 0 | 2 | 0 | **100.0%** |
| **Presentation & Soft Anomalies (A7–A8, A13)** | 0 | 0 | 2 | 1 | **100.0%** |

---

### TABLE IV: PIPELINE LAYER ABLATION ANALYSIS

| Evaluated Configuration | Fraud Catch % | Leaked Attack Vectors | Systemic Vulnerability Exposed |
| :--- | :---: | :--- | :--- |
| **Full IDShield Pipeline** | **100.0%** | *None (Full Catch)* | All attack vectors intercepted; production baseline. |
| **Ablation: No Cryptographic L1** | **62.5%** | A1, A12 | Signature bit-flips and forged timestamps pass undetected. |
| **Ablation: No Biometric L5** | **62.5%** | A4, A6 | Physical photo-swaps and live impostor selfies pass cleanly. |
| **Ablation: No Deterministic L2** | **50.0%** | A2, A3, A5, A11 | Photoshop text edits on card surface match nothing without cross-checking. |
| **Ablation: No Forensic PAD** | **87.5%** | A8 | Smartphone screen replays deceive facial recognition thresholds. |

---

### TABLE V: PER-MODULE CPU LATENCY PROFILE

| Pipeline Processing Stage | Underlying Technology | Mean Latency | Proportion |
| :--- | :--- | :---: | :---: |
| **Layer 0: Optical Quality Gate** | Laplacian Variance & Glare Masking | 18.4 ms | 0.8% |
| **Layer 1: Secure QR & Cryptography** | `zxing-cpp` + RSA-2048 PKCS#1 v1.5 | 94.2 ms | 4.3% |
| **Layer 2: Deterministic Rules** | Verhoeff $D_5$ Checksum + Postal Lookup | 0.4 ms | $<0.1\%$ |
| **Layer 3: AI Field Localization** | YOLOv8 ONNX Runtime (CPU) | 284.1 ms | 13.1% |
| **Layer 4: Targeted OCR & Lexicon** | CRAFT + CRNN Text Extraction | 1,420.5 ms | 65.5% |
| **Layer 5: Biometrics & PAD** | YuNet + SFace + 2D FFT Moiré | 341.2 ms | 15.7% |
| **Layer 6: Decision Fusion** | Two-Tier Aggregation & Audit Logging | 7.6 ms | 0.4% |
| **Total End-to-End Latency** | **Full Offline Multi-Layer Pipeline** | **2,166.4 ms** | **100.0%** |
