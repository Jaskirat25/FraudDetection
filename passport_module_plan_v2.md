# Passport Module: Check Plan v2 (IDShield AI)

Status: revised plan for the Indian Passport module, to sit beside the finished Aadhaar module.
Scope v1 of the module: Indian **ordinary** passport (type `P`), **data page** (required) + **last page** (optional). Visa pages, diplomatic/official passports and foreign passports are out of scope and return `UNSUPPORTED`.

> Items marked **[VERIFY]** are assumptions I am not certain of. Per section 7, **no [VERIFY] rule may drive an escalation until it is verified against an official source or specimens and has passing tests.**

---

## 0. TL;DR

1. **The printed passport has no cryptographic anchor** like Aadhaar's Secure QR. The module therefore rests on MRZ integrity, VIZ↔MRZ consistency, verified document-logic rules, face/identity checks and image forensics. The only cryptographic anchor is the chip (stretch goal).
2. **v2 principle: separate "could not read it" from "it contradicts itself".** Every check has an explicit status, every field carries confidence, and a poor scan produces `RECAPTURE_REQUIRED`, not suspicion.
3. **Edge features for the submission:** chip Passive Authentication (stretch), cross-document checks with your Aadhaar module, evidence-preserving MRZ repair, and a keyed-HMAC reuse/duplicate index.
4. **Deterministic checks carry the decision.** Forensics and the tamper CNN are provisional, low-weight signals until an ablation on held-out data shows they help.
5. **Output wording:** the module reports "no material anomaly found among the checks that ran", never "genuine". It cannot see issuance, cancellation or lost/stolen status offline.

### 0.1 What changed from v1

| Area | v1 | v2 |
|---|---|---|
| Check outcome | `HARD`/`SOFT` severity only | Runtime status (`PASS/FAIL/UNKNOWN/NOT_EVALUATED/NOT_APPLICABLE`) + separate recommended action |
| Bad scan handling | Mixed into risk | Quality gate before analysis → `RECAPTURE_REQUIRED` |
| C-8 name rule | "exactly one `<<`" | Structural parse (first `<<`, strip trailing filler) |
| C-10 century | Compare YY to current year | Use VIZ 4-digit year; else candidate set; ambiguous → `UNKNOWN` |
| C-11 repair | Accept the only checksum-passing candidate | Ranked candidates, VIZ corroboration required, full evidence kept, incorrect-repair rate measured |
| Rules | Constants in code | Versioned rules registry with provenance; unverified → `INFO` |
| Fusion | Sum of weighted checks | Evidence groups, dependency suppression, no double counting |
| Output | `ACCEPT/REVIEW/REJECT` | `LOW_RISK_SCREEN/MANUAL_REVIEW/RECAPTURE_REQUIRED/UNSUPPORTED`; `EXPIRED` is a flag |
| Face | Reuse Aadhaar thresholds, lower threshold for ghost | Calibrate on passport crops; ghost is optional, quality-gated, no threshold lowering |
| Forensics | Weighted from the start | Provisional weight 0 until ablation; store evidence regions |
| Identifier privacy | Plain hash | Keyed HMAC, log redaction, consent log, retention setting |
| Data splits | By tamper type and template | Also grouped by source specimen / face identity / capture session |
| Chip | J-1…J-6 | Split into read / signature+trust chain / hashes / DG1 / DG2 / active auth / era |

---

## 1. Revised pipeline (mapped to your Aadhaar stages)

| # | Stage | Aadhaar equivalent | Passport notes | Reuse? |
|---|---|---|---|---|
| 1 | **Intake & consent**: file type/size, consent + purpose logged, original stored immutably (hash) | Stage 1 | Never modify the original; all enhancement happens on working copies | Reuse + extend |
| 2 | **Quality gate**: blur, glare, crop, resolution, skew | Stage 1 | Fails → `RECAPTURE_REQUIRED` with a targeted hint ("reduce glare", "include full MRZ") | New |
| 3 | **Page & template identification**: data page / last page / unsupported; template registration | Stage 2 | Uncertain template → lower confidence / `UNSUPPORTED`, never a forced match | New |
| 4 | **Localisation & extraction**: field boxes; separate VIZ and MRZ readers; keep raw outputs + confidence | Stages 2, 4 | MRZ uses a restricted charset reader; VIZ uses EasyOCR | Partly new |
| 5 | **MRZ parsing & repair**: structure, check digits, ranked alternatives, evidence preserved | Stage 5 (Verhoeff) | No printed crypto, so MRZ math replaces the QR check | New |
| 6 | **Consistency & document logic**: VIZ↔MRZ, verified date/number rules | Stage 5 | Rules come from the registry | New |
| 7 | **Identity checks**: calibrated face match, liveness hook, cross-document | Stage 6 | Reuse the engine, **not** the Aadhaar thresholds | Reuse + calibrate |
| 8 | **Forensics** on original + rectified copy | none | Provisional weight, evidence regions kept | New |
| 9 | **Optional chip checks** | Stage 3 analogue | Stretch | New |
| 10 | **Evidence fusion**: groups, uncertainty, coverage | Stage 7 | Calibrated on independent data | Reuse + extend |
| 11 | **Decision & explanation** | Stage 7 | Reason codes, evidence, next action | Reuse |
| 12 | **Audit & privacy controls**: redaction, retention, versioned thresholds | Stage 8 | HMAC identifiers | Reuse + extend |

Design tip: keep the `DocumentModule` interface (`localize → extract → validate → forensics → score`) so Aadhaar, Passport and later Driving Licence share one orchestrator, one decision enum and one audit log.

---

## 2. What you are reading (anatomy)

### 2.1 Data page, visual inspection zone (VIZ) **[VERIFY layout on specimens]**
Type, country code, passport number, surname, given name(s), nationality, sex, DOB, place of birth, place of issue, date of issue, date of expiry, photo, holder's signature (if present), possibly a ghost image. Dates printed `DD/MM/YYYY`.

### 2.2 MRZ, ICAO 9303 TD3 (2 lines × 44 characters, charset `A-Z0-9<`)
**Line 1:** `P` + type char + issuing state (`IND`) + name field (positions 6-44).

**Line 2 (1-indexed):**

| Pos | Field | Check digit |
|---|---|---|
| 1-9 | Passport number (letter + 7 digits, padded with `<`) | pos 10 |
| 11-13 | Nationality | none |
| 14-19 | DOB `YYMMDD` | pos 20 |
| 21 | Sex | none |
| 22-27 | Expiry `YYMMDD` | pos 28 |
| 29-42 | Personal number (often blank on Indian passports **[VERIFY]**) | pos 43 |
| 44 | Composite check over 1-10, 14-20, 22-43 | itself |

Check digit: weights `7,3,1` repeating; `0-9` = value, `A-Z` = 10-35, `<` = 0; sum mod 10.

**Checksum blind spot:** swapping a digit with a letter whose value differs by a multiple of 10 (e.g., `5` ↔ `F`) leaves the digit unchanged. Position-based format rules (D-1) therefore catch things the checksum cannot.

### 2.3 Last page **[VERIFY on specimens]**
Parent/guardian names, spouse name, address with PIN, old passport number, file number, barcode.

### 2.4 Chip (e-passport)
Press reports of MEA statements say e-passport issuance began as a pilot in April 2024 (Nagpur and Bhubaneswar) and reached all 37 passport offices by May 2025 **[VERIFY against Passport Seva FAQ]**. Older non-chip passports stay valid until expiry, so **both chip and non-chip booklets are legitimate**.

---

## 3. Conventions used by every check

### 3.1 Field object
Every important field (passport number, surname, given names, DOB, expiry, nationality, sex, MRZ line 1/2) is stored as:

```json
{
  "field": "dob",
  "raw": {"viz": "14/03/1998", "mrz_reader_a": "980314", "mrz_reader_b": "980314"},
  "normalized": "1998-03-14",
  "confidence": 0.93,
  "reader_agreement": true,
  "repaired": false,
  "repair_evidence": null,
  "status": "PASS"
}
```

Low OCR confidence **never** adds risk by itself. It makes the field `UNKNOWN`, which leads to recapture or another extraction attempt.

### 3.2 Check status (what happened)
| Status | Meaning |
|---|---|
| `PASS` | Ran and passed |
| `FAIL` | Ran on reliable inputs and found a contradiction |
| `UNKNOWN` | Evidence insufficient or ambiguous (low OCR confidence, ambiguous date, unverified rule) |
| `NOT_EVALUATED` | Could not run (missing input, dependency `UNKNOWN`, no trust store) |
| `NOT_APPLICABLE` | Does not apply to this page, template or capture mode |

### 3.3 Recommended action (what to do next; separate from status)
`CONTINUE` · `RECAPTURE_REQUIRED` · `MANUAL_REVIEW`

### 3.4 Check class (how a `FAIL` is treated)
- **T1 (contradiction):** a `FAIL` on reliable inputs forces `MANUAL_REVIEW` with `priority=HIGH`. On unreliable inputs the check becomes `UNKNOWN`.
- **T2 (signal):** contributes to a weighted group score.
- **INFO:** logged only. Includes any check whose rule is not yet verified (section 7).

### 3.5 Dependency rule (stops cascading false alarms)
If MRZ extraction is `UNKNOWN`, then C-3…C-7, D, E-1…E-7 that depend on it become `NOT_EVALUATED`, and **one** finding is emitted: "MRZ unreliable". A single OCR error must not appear as three independent anomalies.

---

## 4. Threat model → what catches what

| # | Forgery / abuse | Primary | Backup |
|---|---|---|---|
| T1 | Photo substitution (most common) | Face vs selfie, photo-boundary forensics | Ghost image (if usable), chip DG2 |
| T2 | VIZ edited only | VIZ↔MRZ mismatch | Local forensics, chip DG1 |
| T3 | MRZ edited only | MRZ checksum, VIZ↔MRZ | MRZ glyph check |
| T4 | Both edited consistently, checksums recomputed | Verified date/number rules, glyph/font inconsistency, cross-doc with Aadhaar | **Chip passive authentication** (only real defence) |
| T5 | Fabricated / template-based fake | Template registration, number format, place-of-issue list | Reuse index, forensics |
| T6 | Screen replay / photocopy / print-scan | Recapture indicators (soft) | Policy flag "not an original capture" |
| T7 | Genuine passport, wrong person | Face match + liveness | Cross-doc face with Aadhaar |
| T8 | Cancelled / lost / reported passport | **Not detectable offline.** Expose an `issuer_lookup` adapter stub and state the limitation | n/a |

---

## 5. Check catalogue

Class: **T1** contradiction, **T2** signal, **INFO** logged only, **Prov.** = provisional (weight 0 until ablation shows value).
Effort: S ≤1 day, M 2-4 days, L ≥1 week.

### A. Quality gate and capture integrity (runs first; failures → `RECAPTURE_REQUIRED`, not risk)

| ID | Check | How | Class | Effort |
|---|---|---|---|---|
| A-1 | Page type: data page / last page / unsupported | Classifier or MRZ-presence heuristic + template score | gate (`UNSUPPORTED`) | S |
| A-2 | Blur, glare, crop, resolution | Laplacian variance, specular mask, min resolution, MRZ fully inside frame | gate | S |
| A-3 | Skew / perspective | Corner detection → homography on a **working copy**; MRZ lines horizontal | n/a | M |
| A-4 | Screen recapture | FFT/moiré, pixel-grid periodicity | T2, Prov. | M |
| A-5 | Photocopy / print-scan | Colour distribution, halftone frequency | T2, Prov. | M |
| A-6 | Re-save traces (EXIF, double JPEG) | Metadata, quantisation tables | INFO (EXIF may be missing for legitimate reasons) | S |

Recapture hints are specific: "reduce glare", "include full MRZ", "hold camera parallel".

### B. Page, template and localisation

| ID | Check | How | Class | Effort |
|---|---|---|---|---|
| B-1 | Field localisation | **Template registration (homography + geometric checks) as baseline**; YOLOv8 where it adds robustness (`photo`, `ghost`, `mrz`, `signature`, `barcode`) | n/a | M |
| B-2 | Template conformity | Registration residual / IoU vs expected layout | T2 | S |
| B-3 | Required elements | Exactly one photo, MRZ present | T1 if reliable, else `UNKNOWN` | S |
| B-4 | Uncertain template | Score below threshold → `UNSUPPORTED` or reduced coverage. **Never force the nearest template** | gate | S |
| B-5 | Edition classification | Only if you obtain ≥2 specimen layouts | INFO | L (stretch) |

### C. MRZ core (do first)

| ID | Check | How | Class | Effort |
|---|---|---|---|---|
| C-1 | Structure | 2 lines × 44, charset `A-Z0-9<`, line 1 starts `P` | T1 | S |
| C-2 | State / nationality | `IND` in both places | T1 | S |
| C-3 | Passport-number check digit | 7-3-1 | T1 | S |
| C-4 | DOB check digit | same | T1 | S |
| C-5 | Expiry check digit | same | T1 | S |
| C-6 | Personal-number check digit | same; blank-field behaviour (`<` vs `0`) comes from the registry | INFO until verified, then T1 | S |
| C-7 | Composite check digit | same | T1 | S |
| C-8 | **Name field parse** | See 5.1 | T2 | S |
| C-9 | Sex field | `M`, `F` or `<` | T1 | S |
| C-10 | **Date validity and century** | See 5.2 | T1 / `UNKNOWN` | S |
| C-11 | **Evidence-preserving repair** | See 5.3 | n/a | M |
| C-12 | MRZ glyph conformity (OCR-B) | Template-match each character crop on supported templates only | T2, Prov. | M |
| C-13 | Multi-reader agreement | Two readers (e.g., PassportEye/Tesseract-MRZ and EasyOCR with `A-Z0-9<` allowlist); disagreement positions feed C-11 | confidence input | M |

#### 5.1 C-8 name parsing (replaces the "exactly one `<<`" rule)
1. Take MRZ line 1, positions 6-44; strip **trailing** `<` filler.
2. Split at the **first** `<<`: left = primary identifier (surname), right = secondary identifier (given names, may be empty).
3. Within each identifier, a single `<` is a word separator (becomes a space).
4. A further `<<` inside the secondary identifier after stripping filler (an empty component) → low-weight anomaly (T2).
5. Empty primary identifier (single-name holder) is **permitted only if the registry says so**; otherwise `UNKNOWN`.
6. Allow truncation at the field limit when comparing with the VIZ (E-3).

Unit tests required: multiple given names; hyphens and apostrophes (hyphen → `<`, apostrophe removed); maximum-length names; single-name holder; missing given names; heavy trailing filler.

#### 5.2 C-10 date interpretation
- **DOB:** the VIZ prints a 4-digit year. If the VIZ date is readable, the MRZ `YY` must equal `YYYY mod 100` (otherwise E-4 fails). If the VIZ date is unreadable, build candidates `{19YY, 20YY}` and filter by: not in the future, DOB < issue date, plausible age at issue/today. If more than one candidate survives → `UNKNOWN` / `AMBIGUOUS_DATE`, never silently pick one.
- **Expiry:** candidates `{19YY, 20YY, 21YY}` filtered by expiry > issue date and expiry − issue ≤ maximum validity from the registry.
- Always check calendar validity (including leap years) before century logic.

Unit tests required: leap days (valid and invalid), impossible dates (e.g., month 13), expired documents, century boundaries (`YY` = 00, 26, 99), issue/birth/expiry ordering violations.

#### 5.3 C-11 repair procedure (evidence preserved, conservative)
1. **Record before touching anything:** raw text per reader, per-character confidence, reader-disagreement positions, check digits **before** repair.
2. **Candidate generation:** only at positions that are low-confidence or where readers disagree (or inside the field a failed check digit covers); substitutions limited to the confusion set (`O/0 I/1 B/8 S/5 Z/2 <` vs `K/C`); at most 2 edits; rank by OCR alternative scores.
3. **Score each candidate:** all affected check digits pass, **and** the independent VIZ value agrees, **and** format rules are satisfied.
4. **Auto-accept only if** the best candidate satisfies all of the above **and** has a clear margin over the second best. (A check digit is a single mod-10 digit, so a wrong candidate passes by chance roughly 1 in 10; that is why checksum alone is not enough.)
5. Otherwise: the field becomes `UNKNOWN`; action is `RECAPTURE_REQUIRED` if image quality is the likely cause, else `MANUAL_REVIEW`.
6. **Persist:** candidates and scores, applied substitutions with positions, pre/post check-digit results, VIZ comparison, final confidence and the accept/escalate decision.

If the VIZ field is itself unreadable there is no independent corroboration, so no automatic repair.

**Metrics:** repair accuracy **and incorrect-automatic-repair rate** (not only "checksum failures fixed").

### D. VIZ extraction and document-logic rules (all driven by the rules registry, section 7)

| ID | Check | How | Class | Effort |
|---|---|---|---|---|
| D-1 | Passport-number format | Pattern from registry (candidate pattern, **[VERIFY]**: letter excluding Q/X/Z + 7 digits, first digit non-zero). Position rules also catch the digit↔letter checksum blind spot. Not matching a verified pattern → anomaly/`UNKNOWN`, **not** an immediate fraud conclusion | INFO until verified, then T1/T2 by rule severity | S |
| D-2 | Date formats | Parse `DD/MM/YYYY`, real-date test | T1 if reliable | S |
| D-3 | DOB plausibility | Not in the future; age at issue and today plausible | T1 | S |
| D-4 | Date ordering | DOB < issue < expiry | T1 | S |
| D-5 | Issue date not in future | vs today | T1 | S |
| D-6 | Validity-period rule | Registry **table** (adult / minor / limited-validity), e.g., commonly expiry = issue + 10 y − 1 d for adults **[VERIFY]** | T2; T1 only for impossible spans | S |
| D-7 | Expiry status | Sets `document_status = EXPIRED`. **Not a decision and not a risk contribution** | flag | S |
| D-8 | Place-of-issue gazetteer | Passport office jurisdictions / PSK cities / Indian missions, fuzzy match **[VERIFY list]** | T2 | S |
| D-9 | Place-of-birth plausibility | Fuzzy match to gazetteer | T2 (low) | S |
| D-10 | Nationality literal | `INDIAN` | T1 if reliable | S |
| D-11 | Name sanity | Charset, length, single-name case allowed | T2 | S |
| D-12 | Era/edition consistency | Issue date vs layout version; needs ≥2 specimen editions | INFO | L (stretch) |

### E. VIZ ↔ MRZ cross-validation

| ID | Pair | Rule |
|---|---|---|
| E-1 | Passport number | exact after stripping `<` |
| E-2 | Surname | MRZ-transliterated VIZ == MRZ |
| E-3 | Given names | same; allow truncation at field limit |
| E-4 | DOB | `DD/MM/YYYY` ↔ `YYMMDD`, with century from VIZ year |
| E-5 | Expiry | same |
| E-6 | Sex | `M/F` ↔ MRZ |
| E-7 | Nationality | `INDIAN` ↔ `IND` |

Class: T1, **but only when both sides' field status is reliable**; otherwise `UNKNOWN`. Each pair outputs a similarity score so a 1-character difference with low OCR confidence becomes `UNKNOWN`, while a confident full mismatch is `FAIL`.
Transliteration rules: uppercase, strip diacritics, drop apostrophes, spaces/hyphens → `<`.

### F. Photo and face (signals kept conceptually separate)

| ID | Signal | How | Class | Effort |
|---|---|---|---|---|
| F-1 | Exactly one face in the photo region | YuNet | T1 if reliable | S |
| F-2 | **Identity:** passport photo ↔ selfie | SFace engine reused, **threshold calibrated on passport-style crops**; report FMR/FNMR at chosen threshold with confidence intervals | T2 (T1 only if far beyond calibrated margin) | M |
| F-3 | Ghost portrait similarity | **Optional.** Run only if the ghost passes a quality gate (size, contrast). Supporting evidence only. **Do not lower the threshold to compensate for a small image** | T2, Prov. | M |
| F-4 | Photo placement geometry | vs template | T2 | S |
| F-5 | Photo-boundary forensics | Edge/blur/noise discontinuity, background continuity; evidence region stored | T2, Prov. | M |
| F-6 | Photo quality | Frontal, plain background | INFO | S |
| F-7 | **Liveness / presentation-attack on the selfie** | Reuse the Aadhaar module's mechanism; evidence about the capture, not about the passport | T2 | S |

None of these proves genuine issuance.

### G. Forensics (all provisional until the ablation shows value)

| ID | Check | How | Class | Effort |
|---|---|---|---|---|
| G-1 | ELA / double-JPEG per field box | Compare to page-wide statistics; affected by ordinary processing, so low trust | Prov. | S |
| G-2 | Noise-residual inconsistency | High-pass residual variance per region | Prov. | M |
| G-3 | Copy-move | ORB/SIFT matches within the page; **must be corroborated by another signal** | Prov. | M |
| G-4 | Text-region consistency | Stroke width, ink colour, baseline, spacing vs neighbours, on supported templates | Prov. | M |
| G-5 | VIZ font conformity | Glyph statistics with tolerances | Prov. | M |
| G-6 | Local CNN on field crops | Trained on synthetic tampers; must be evaluated on **unseen templates, source documents, faces and tamper-generation methods** | Prov., time-boxed | L |
| G-7 | Visible security-feature presence | What a flat scan can show only; do not claim hologram/OVD checks | INFO | L (stretch) |

Rules for all of G and A-4…A-6:
- Run on the **original** and, where appropriate, the rectified copy.
- Every finding records the **suspicious region and the supporting evidence** (box/heatmap, measured values), not only a score.
- A provisional check moves from weight 0 to a calibrated weight only if the ablation shows a held-out improvement.

### H. Last page (optional input)

| ID | Check | How | Class | Effort |
|---|---|---|---|---|
| H-1 | Barcode decode | `pyzbar` / `zxing-cpp` **[VERIFY symbology]** | T2 | S |
| H-2 | Barcode ↔ printed file number | Equality when both readable | T1 if reliable | S |
| H-3 | File-number format | Pattern learned from specimens, in registry **[VERIFY]** | INFO until verified | M |
| H-4 | PIN ↔ state/city | India Post dataset lookup | T2 | M |
| H-5 | Parent/spouse surname vs holder | Fuzzy, culturally aware | INFO | S |
| H-6 | Data page ↔ last page consistency | Repeated identifiers match | T2 | S |

When no last page is supplied, H becomes `NOT_EVALUATED` (or `NOT_APPLICABLE` for single-page capture mode) and is excluded from coverage's denominator accordingly.

### I. Cross-document and history (uses the finished Aadhaar module)

| ID | Check | How | Class | Effort |
|---|---|---|---|---|
| I-1 | Name match Aadhaar ↔ passport | Token-set fuzzy match (initials, order, transliteration) | T2 | M |
| I-2 | DOB match | Compare **only at the precision both documents share** (Aadhaar may carry year only). Genuine records do sometimes disagree, so a full-precision mismatch → `MANUAL_REVIEW`, never automatic adverse action | T1 → review `priority=HIGH` | S |
| I-3 | Gender match | direct | T2 | S |
| I-4 | State/city consistency | Aadhaar address vs last page vs place of birth/issue (people move) | INFO | S |
| I-5 | Face: Aadhaar photo ↔ passport photo ↔ selfie | Extend existing 3-way match; thresholds calibrated separately for this pairing | T2 | S |
| I-6 | **Reuse detection** | Index perceptual hash, face embedding and **HMAC(passport number)**; flag same photo/different identity, same number/different DOB or name, same MRZ/different photo. **Duplicates are review signals, not proof of fraud** | T1 for number clash, T2 for photo | M |
| I-7 | Velocity | Many identities from one submitter | INFO/T2 | S |

### J. Chip authentication (optional advanced path; each step is reported separately)

| ID | Step | How | Class | Effort |
|---|---|---|---|---|
| J-1 | **Read chip** | Access key from MRZ (passport no., DOB, expiry) → NFC (BAC/PACE) | n/a | L |
| J-2 | **SOD signature + trust chain** | Parse SOD (CMS SignedData); verify Document Signer cert chains to the issuer's CSCA from the configured trust store | T1 | L |
| J-3 | **Data-group hash check** | Hash each data group read; compare with SOD | T1 | M |
| J-4 | DG1 ↔ scan | Chip MRZ data vs OCR'd MRZ and VIZ | T1 | S |
| J-5 | DG2 ↔ printed photo | Face-embedding comparison | T1/T2 by margin | S |
| J-6 | Active / chip authentication | Clone-detection challenge-response, if supported | T2 | L |
| J-7 | Era plausibility | A chip passport whose issue date precedes the first e-passport issuance is anomalous; **absence of a chip is `INFO` / `NOT_EVALUATED`** because rollout was phased. Use office-specific rollout data only if verified | T2 / INFO | S |

**What a successful passive authentication means:** the chip data is intact and signed by a key that chains to the configured trust anchor. It does **not** show the passport is currently valid, has not been cancelled, or is held by the person presenting it. Issuer/status verification is a separate capability that this module does not have.

Report explicitly when the trust store is missing or a step was not performed (`NOT_EVALUATED`, never a silent pass).

**Feasibility:**
- Needs an NFC-capable Android phone (JMRTD-based app) or a contactless PC/SC reader, and a **consenting holder's own e-passport**. Do not store data groups beyond what the test requires.
- The Indian CSCA certificates may not be freely obtainable. Build against a **pluggable trust store** and demo with test material or sample SOD data, stating this clearly.
- If NFC is not feasible, still deliver J-2/J-3 as code verified on a sample SOD.

---

## 6. Evidence fusion and decision

### 6.1 Evidence groups (no double counting)

| Group | Members | Treatment |
|---|---|---|
| G1 Extraction & MRZ integrity | A gate results, C-1…C-13 | Produces `extraction_confidence`; failures here usually mean recapture |
| G2 Consistency & document logic | D, E, H | Skipped (`NOT_EVALUATED`) when G1 is `UNKNOWN` |
| G3 Face & identity | F-1…F-7, I-5 | |
| G4 Forensics & recapture | A-4…A-6, B-2, G | Provisional weights until ablation |
| G5 Cross-document & history | I-1…I-4, I-6, I-7 | |
| G6 Chip | J | Not additive; a verified failure is a T1 contradiction, a pass is positive evidence |

**Aggregation:** within a group, combine member scores with max or noisy-OR (never a plain sum), then weight the groups. Document known dependencies between checks in the registry so the same underlying failure is not penalised twice.

### 6.2 Decision logic
1. Page/template unsupported → `UNSUPPORTED`.
2. Quality gate failed, or critical fields `UNKNOWN` because of image quality → `RECAPTURE_REQUIRED`.
3. Any **T1 `FAIL` on reliable inputs**, or a chip T1 failure → `MANUAL_REVIEW`, `priority=HIGH`.
4. Group-weighted score above the calibrated review threshold, or unresolved contradictions → `MANUAL_REVIEW`, `priority=NORMAL`.
5. Otherwise → `LOW_RISK_SCREEN` ("no material anomaly among the checks that ran; not proof of genuineness").

`document_status = EXPIRED` is a separate flag and can accompany any decision.
`REJECT` is not an output by default (offline image analysis cannot establish issuance status). If your rubric requires it, configure it as an alias for `MANUAL_REVIEW` + `priority=HIGH`, and keep human oversight in the loop.

### 6.3 Starting group weights (placeholders, to be replaced by calibration)

| Group | Placeholder |
|---|---|
| G2 Consistency & logic | 30 |
| G3 Face & identity | 25 |
| G5 Cross-doc & history | 20 |
| G4 Forensics (provisional checks at 0 until ablation) | 15 |
| Template/layout (B-2, F-4) | 10 |

Calibrate on a validation set (logistic regression or grid search) and **freeze thresholds before touching the test set**. Do not call the output a fraud probability unless it has been calibrated and evaluated as one; call it `risk_index`.

### 6.4 Output schema

```json
{
  "document": "indian_passport",
  "decision": "MANUAL_REVIEW",
  "priority": "NORMAL",
  "document_status": ["EXPIRED"],
  "risk_index": 58,
  "risk_band": null,
  "extraction_confidence": 0.88,
  "image_quality": {"blur": "ok", "glare": "high", "crop": "ok", "recapture": "unlikely"},
  "coverage": 0.78,
  "findings": [
    {"code": "PP-XVAL-004", "check": "E-4", "status": "PASS", "field": "dob"},
    {"code": "PP-FACE-002", "check": "F-2", "status": "FAIL", "class": "T2",
     "similarity": 0.41, "threshold": 0.50, "threshold_version": "face-passport-v1"},
    {"code": "PP-MRZ-011", "check": "C-11", "status": "PASS", "repaired": true,
     "evidence": {"positions": ["L2[8]"], "viz_corroborated": true, "margin": 0.31}}
  ],
  "not_evaluated": ["H-1", "H-2", "J-2"],
  "rules_version": "ruleset-2026-10",
  "recommended_action": "MANUAL_REVIEW"
}
```

`risk_band` stays `null` until thresholds are calibrated. **Coverage** = checks with `PASS` or `FAIL` ÷ checks that were applicable and planned (`NOT_APPLICABLE` excluded). `UNKNOWN` and `NOT_EVALUATED` lower coverage, so missing data is never counted as passing.

Reason-code convention: `PP-<GROUP>-<NNN>` (e.g., `PP-MRZ-003` passport-number check digit failed, `PP-XVAL-004` DOB mismatch, `PP-FACE-002` photo/selfie below threshold, `PP-CHIP-001` SOD signature invalid).

---

## 7. Rules registry (provenance for every passport-specific rule)

One versioned file (`rules/passport_rules.yaml`), loaded at startup, versioned in git. Code reads rules from it; passport-specific constants do not live in code.

```yaml
- id: D-1-passport-number-format
  description: Indian passport number format (letter + 7 digits)
  pattern: '^[A-PR-WY][1-9]\d{6}$'     # candidate, unverified
  source: null                          # official spec or specimen IDs once verified
  last_verified: null
  supported_editions: []                # fill after specimen check
  severity: INFO                        # promoted to T1/T2 only after verification
  tests: []                             # links to positive / negative / edge tests
  owner: <team member>
  version: 1
- id: C-6-personal-number-blank
  description: Check-digit value when personal-number field is blank
  source: null
  last_verified: null
  severity: INFO
  ...
```

Required fields per rule: **ID + description, source, last-verified date, supported editions, severity, test cases, owner/version.**

**Promotion gate:** no rule marked `[VERIFY]` may become T1/T2 until its source is recorded, `last_verified` is filled, and its tests pass. Until then it logs as `INFO`/anomaly. Rules to verify first: D-1, C-6, D-6, D-8, H-1/H-3, J-7.

---

## 8. Privacy, retention and audit

This is a design requirement, not an afterthought. It is a project-level design, not legal advice or a compliance claim; check the current Digital Personal Data Protection Rules with your guide/legal contact if the system moves beyond a college demo.

| Control | Implementation |
|---|---|
| Consent and purpose | Log consent + stated purpose per submission before processing |
| Original protection | Store original bytes read-only with a content hash; work on copies |
| Identifier matching | Store a **keyed HMAC** of normalised passport number/other identifiers for exact-match indexing, key held outside the DB. A plain hash is unsafe because passport numbers are a small, predictable space (order of 10⁸) and can be enumerated |
| Biometrics | Face embeddings and original scans: restricted access (simple role flag on the dashboard), encrypted at rest if stored |
| Log redaction | MRZ lines, names, DOB and biometric details are redacted/masked in application logs; evidence views are role-gated |
| Retention | Configurable retention period with scheduled deletion of originals, embeddings and crops |
| Test data | Own passport only with consent; blur personal details in anything stored or published; never commit real scans to the repo; specimens/synthetic data marked `SPECIMEN` |
| Duplicates | Treated as review signals, never as proof |
| Audit record | Timestamp, input hash, module + rules version, thresholds used, decision, reason codes |

---

## 9. Data plan and evaluation

### 9.1 Data
Public datasets (MIDV-500/2019/2020, DocXPand-25k) contain passports of other countries or fictional designs, not Indian ones. Use them for MRZ OCR, quality and recapture experiments. For Indian layout:
1. **Genuine specimens:** official samples; your own passports only with consent and personal details blurred.
2. **Synthetic Indian-style data page generator:** template + fake data from your gazetteers + programmatic MRZ with correct check digits + synthetic or consented faces; watermark `SPECIMEN`; keep it private. Every generated page gets a **source-group ID** (template, face identity, document ID, capture session).
3. **Augmentation:** rotation, perspective, blur, glare, recompression, screen-recapture and print-scan simulation.

### 9.2 Synthetic tamper generator

| Tamper type | Generator |
|---|---|
| Photo swap | Replace face, with/without edge blending |
| VIZ field edit | Inpaint + re-render in a similar font |
| MRZ edit (no checksum update) | Change one character |
| MRZ + VIZ consistent edit (T4) | Recompute checksums |
| Copy-move | Duplicate a digit/region |
| Recapture / print-scan | Photograph screen/printout |

### 9.3 Train / validation / test separation
- Hold out entire **tamper types** and entire **templates**.
- Keep **all derivatives** of the same original document, face identity, source specimen or capture session in the **same split** (group-aware splitting, e.g., grouped k-fold). Otherwise near-duplicates leak between train and test.
- Thresholds and weights are fitted on validation only; the test set is touched once.
- Synthetic-only results are reported as synthetic-only. **They are not claims about real-world passport authentication accuracy.**

### 9.4 Metrics to report
**MRZ / OCR:** character error rate, exact MRZ-line accuracy, exact critical-field accuracy, repair accuracy, **incorrect-repair rate**.
**Screening:** false-positive and false-negative rates **per attack type**, precision/recall at the chosen operating point, **confidence intervals** (Wilson or bootstrap, since test sets are small), results on genuine-but-degraded scans, recapture rate, unresolved/manual-review rate.
**Identity:** false-match and false-non-match rates at the chosen face threshold (passport crops, and Aadhaar↔passport pairing separately).
**System:** latency per stage and total, memory use. Failure rate by capture condition using your augmentation categories (not by real device).
**Ablation:** MRZ only → + rules → + identity → + forensics → + cross-doc → + chip (where available). Shows what each layer adds and justifies the weights of provisional checks.
**Release criteria:** choose target values for the main metrics **after** the baseline run, record them before the final test run, and report pass/fail against them.

### 9.5 Limitations section (state it in the report)
T4 without chip; T8 offline; no hologram/OVD or tactile checks; synthetic-data bias; rules marked unverified; image-only screening is not issuer verification.

---

## 10. Build order (4 people, ~4 weeks)

| Week | Stream A (MRZ, rules, fusion) | Stream B (vision/OCR/capture) | Stream C (face, cross-doc, privacy) | Stream D (data, forensics, eval) |
|---|---|---|---|---|
| 1 **(P0 foundations)** | Check-status model, `FieldValue`, rules registry skeleton, C-1…C-10 with unit tests (name, date, century cases) | Quality gate (A-1…A-3), immutable original storage, template registration baseline (B-1/B-2/B-4) | Plug passport photo into face engine; consent log, HMAC scaffold, log redaction | Synthetic passport generator v1 with source-group IDs; split protocol |
| 2 | C-11 repair redesign, E-1…E-7 with confidence gating, dependency suppression | MRZ multi-reader (C-13), VIZ OCR, YOLO only if registration is insufficient | F-1/F-2 calibration set + FMR/FNMR, I-1…I-5 | Tamper generator; G-1/G-3 baselines with evidence overlays |
| 3 | Evidence groups, fusion, reason codes; verify rules and promote from `INFO`; H checks | Recapture indicators (A-4/A-5), F-5, dashboard passport tab with evidence view | I-6 reuse index (HMAC), F-3 ghost (optional, gated), liveness hook | G-2/G-4/G-5; **G-6 CNN time-boxed** |
| 4 | Calibrate weights/thresholds on validation, freeze | Latency/memory profiling | Cross-doc and identity metrics | Test-set run, ablation, CIs, report (threat matrix, limitations), **J-2/J-3 stretch on sample SOD** |

**Minimum viable module (if time shrinks to ~2 weeks):**
status model + `FieldValue` + registry, quality gate, C-1…C-11, D-2…D-5 (verified-independent rules), E-1…E-7, F-1/F-2 (calibrated), I-1/I-2/I-5/I-6, fusion with reason codes, dashboard tab, evaluation on synthetic tampers with group-aware splits.
**Drop first:** G-6 CNN, G-7, B-5, D-12, J-1…J-6 (keep a design note for J-2), F-3.

---

## 11. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Few Indian specimens | Synthetic generator + official samples; state bias in the report |
| CNN overfits generator artefacts | Hold out tamper types/templates/identities; provisional weight; deterministic checks carry decisions |
| OCR errors cause false alarms | Quality gate, field confidence, dependency suppression, conservative repair, recapture path |
| Incorrect automatic repair hides a real mismatch | VIZ corroboration + margin required; incorrect-repair rate tracked |
| Remembered rules may be wrong | Registry with provenance; promotion gate; `INFO` until verified |
| Forced template match gives false confidence | B-4: uncertain template → `UNSUPPORTED` / reduced coverage |
| T4 forgeries pass everything | Be upfront; only chip PA closes it; show it as designed/partially implemented |
| NFC or trust store unavailable | Pluggable trust store; sample-SOD demo |
| Privacy exposure of scans/biometrics | Section 8 controls |
| Over-claiming | `LOW_RISK_SCREEN` wording; never "genuine"; list T8 as out of reach offline |

---

## 12. Library cheat-sheet

| Need | Options |
|---|---|
| MRZ extraction/OCR | `PassportEye`, `fastmrz`, Tesseract MRZ model, EasyOCR/PaddleOCR with `A-Z0-9<` allowlist |
| MRZ parse/generate/check | `mrz` package, or your own (~20 lines for check digits) |
| Barcode | `pyzbar`, `zxing-cpp` |
| Template registration | OpenCV (ORB/SIFT + homography) |
| Face | YuNet + SFace (existing) |
| Forensics | OpenCV, scikit-image, NumPy/SciPy (FFT), `imagehash` |
| Chip/SOD | `cryptography` + `asn1crypto`; JMRTD (Android) for the NFC read |
| Fuzzy matching | `rapidfuzz`, `unidecode`/`anyascii` |
| Keyed identifiers | stdlib `hmac` + `hashlib` |
| Evaluation | `scikit-learn` (calibration, grouped splits), `scipy`/`statsmodels` (Wilson/bootstrap intervals) |
| PIN/place data | India Post PIN dataset, own gazetteer CSVs |

---

## 13. First-hour verification checklist

1. Collect 3-5 official Indian passport specimen images; confirm field positions, ghost image, signature, last-page contents, barcode type, MRZ personal-number content.
2. Verify the passport-number and file-number formats; record sources in the registry.
3. Verify adult/minor validity rules (Passport Seva / MEA) and encode the table.
4. Get the passport-office and PSK city list for the place-of-issue gazetteer.
5. Verify e-passport rollout dates against the Passport Seva e-passport FAQ.
6. Decide now whether NFC is in scope (phone/reader + consenting e-passport holder). If not, plan J as design + sample-SOD demo.
7. Skim ICAO Doc 9303 Part 4 (TD3 MRZ and check digits) and implement tests directly from its rules.

**References to verify during implementation**
- ICAO Doc 9303, Machine Readable Travel Documents: https://www.icao.int/publications/Documents/9303_p4_cons_en.pdf
- Passport Seva e-passport FAQ: https://services1.passportindia.gov.in/psp/FaqEPassport
- MeitY, Digital Personal Data Protection Rules, 2025: https://www.meity.gov.in/static/uploads/2025/11/c56ceae6c383460ca69577428d36828b.pdf

*This plan is a design for an image-screening prototype. It is not an issuer-level verification method and not a substitute for official passport specifications or legal review.*
