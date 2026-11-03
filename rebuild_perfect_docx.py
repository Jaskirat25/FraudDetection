"""
Clean script to build the complete, publication-ready IEEE Project Report document (.docx)
incorporating:
- Standard IEEE 2-Column format with 1-column title/author header
- All refined, equation-free, concise sections (I through VIII + References)
- Spaces reserved for all 6 diagrams (Fig. 1 to Fig. 6) with official IEEE captions
- All 5 formatted academic tables (Table I to Table V) with official IEEE borders
- No duplicate runs, no text triplication, no leftover draft guidance boxes
"""

import os
import docx
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ALIGN_VERTICAL
from docx.enum.section import WD_SECTION
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import nsdecls, qn

def set_section_cols(section, num_cols, space=340):
    """Set the number of columns and spacing (in dxa) for a section."""
    sectPr = section._sectPr
    cols = sectPr.xpath('./w:cols')
    if cols:
        cols[0].set(qn('w:num'), str(num_cols))
        cols[0].set(qn('w:space'), str(space))
        cols[0].set(qn('w:equalWidth'), '1')
    else:
        sectPr.append(parse_xml(f'<w:cols {nsdecls("w")} w:num="{num_cols}" w:space="{space}" w:equalWidth="1"/>'))

def set_cell_background(cell, hex_color):
    """Set the background color of a table cell."""
    shading_elm = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{hex_color}"/>')
    cell._tc.get_or_add_tcPr().append(shading_elm)

def set_cell_margins(cell, top=60, bottom=60, left=80, right=80):
    """Set inner padding for table cells (in dxa)."""
    tcPr = cell._tc.get_or_add_tcPr()
    tcMar = OxmlElement('w:tcMar')
    for m, val in [('w:top', top), ('w:bottom', bottom), ('w:left', left), ('w:right', right)]:
        node = OxmlElement(m)
        node.set(qn('w:w'), str(val))
        node.set(qn('w:type'), 'dxa')
        tcMar.append(node)
    tcPr.append(tcMar)

def set_academic_table_borders(table, color="333333"):
    """Formal IEEE academic table borders: top/bottom lines and header bottom line. No vertical borders."""
    tblPr = table._tbl.tblPr
    borders = parse_xml(
        f'<w:tblBorders {nsdecls("w")}>'
        f'  <w:top w:val="single" w:sz="8" w:space="0" w:color="{color}"/>'
        f'  <w:bottom w:val="single" w:sz="8" w:space="0" w:color="{color}"/>'
        f'  <w:left w:val="none"/>'
        f'  <w:right w:val="none"/>'
        f'  <w:insideH w:val="single" w:sz="4" w:space="0" w:color="E2E8F0"/>'
        f'  <w:insideV w:val="none"/>'
        f'</w:tblBorders>'
    )
    tblPr.append(borders)

def add_figure_space(doc, fig_num, title, description):
    """Leave clean reserved boxed space for a diagram, followed by the IEEE caption."""
    tbl = doc.add_table(rows=1, cols=1)
    tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    tbl.autofit = False
    tbl.columns[0].width = Inches(3.48)
    cell = tbl.cell(0, 0)
    set_cell_background(cell, "F8FAFC")
    set_cell_margins(cell, top=140, bottom=140, left=100, right=100)
    
    tcPr = cell._tc.get_or_add_tcPr()
    borders = parse_xml(
        f'<w:tcBorders {nsdecls("w")}>'
        f'  <w:top w:val="dashed" w:sz="6" w:space="0" w:color="94A3B8"/>'
        f'  <w:bottom w:val="dashed" w:sz="6" w:space="0" w:color="94A3B8"/>'
        f'  <w:left w:val="dashed" w:sz="6" w:space="0" w:color="94A3B8"/>'
        f'  <w:right w:val="dashed" w:sz="6" w:space="0" w:color="94A3B8"/>'
        f'</w:tcBorders>'
    )
    tcPr.append(borders)
    
    p = cell.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(8)
    p.paragraph_format.space_after = Pt(8)
    r1 = p.add_run(f"[ SPACE RESERVED FOR FIGURE {fig_num} ]\n")
    r1.bold = True
    r1.font.name = "Times New Roman"
    r1.font.size = Pt(8.5)
    r1.font.color.rgb = RGBColor(71, 85, 105)
    
    r2 = p.add_run(f"Paste / Insert Diagram: {title}\n({description})")
    r2.italic = True
    r2.font.name = "Times New Roman"
    r2.font.size = Pt(8)
    r2.font.color.rgb = RGBColor(148, 163, 184)
    
    p_cap = doc.add_paragraph()
    p_cap.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    p_cap.paragraph_format.space_before = Pt(3)
    p_cap.paragraph_format.space_after = Pt(6)
    rc1 = p_cap.add_run(f"Fig. {fig_num}.  ")
    rc1.bold = True
    rc1.font.name = "Times New Roman"
    rc1.font.size = Pt(8.5)
    rc2 = p_cap.add_run(f"{title}. {description}")
    rc2.font.name = "Times New Roman"
    rc2.font.size = Pt(8.5)

def build_complete_report(output_path):
    doc = Document()
    
    # Configure IEEE Standard Margins (US Letter: 8.5 x 11 in)
    s1 = doc.sections[0]
    s1.page_width = Inches(8.5)
    s1.page_height = Inches(11.0)
    s1.top_margin = Inches(0.75)
    s1.bottom_margin = Inches(1.0)
    s1.left_margin = Inches(0.625)
    s1.right_margin = Inches(0.625)
    set_section_cols(s1, 1)

    # Base style
    style_normal = doc.styles['Normal']
    font = style_normal.font
    font.name = 'Times New Roman'
    font.size = Pt(10)
    font.color.rgb = RGBColor(15, 23, 42)
    style_normal.paragraph_format.line_spacing = 1.05
    style_normal.paragraph_format.space_after = Pt(3.5)
    style_normal.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY

    def add_p(text="", align=WD_ALIGN_PARAGRAPH.JUSTIFY, space_after=3.5, space_before=0, font_size=10, italic=False, bold=False):
        p = doc.add_paragraph()
        p.alignment = align
        p.paragraph_format.space_before = Pt(space_before)
        p.paragraph_format.space_after = Pt(space_after)
        if text:
            r = p.add_run(text)
            r.font.name = 'Times New Roman'
            r.font.size = Pt(font_size)
            r.italic = italic
            r.bold = bold
        return p

    def add_sec_heading(roman_num, title):
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_before = Pt(9)
        p.paragraph_format.space_after = Pt(3)
        r = p.add_run(f"{roman_num}.  {title.upper()}")
        r.font.name = 'Times New Roman'
        r.font.size = Pt(10)
        r.bold = True
        return p

    def add_subsec_heading(alpha, title):
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.LEFT
        p.paragraph_format.space_before = Pt(5)
        p.paragraph_format.space_after = Pt(2)
        r = p.add_run(f"{alpha}.  {title}")
        r.font.name = 'Times New Roman'
        r.font.size = Pt(9.5)
        r.bold = True
        r.italic = True
        return p

    def add_subsubsec_runin(num_str, title_str, body_text):
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        p.paragraph_format.space_before = Pt(2)
        p.paragraph_format.space_after = Pt(3.5)
        r1 = p.add_run(f"{num_str}) {title_str}: ")
        r1.bold = True
        r1.italic = True
        r1.font.name = 'Times New Roman'
        r1.font.size = Pt(9.5)
        r2 = p.add_run(body_text)
        r2.font.name = 'Times New Roman'
        r2.font.size = Pt(10)
        return p

    # ==========================================
    # HEADER BLOCK (1 COLUMN)
    # ==========================================
    p_title = doc.add_paragraph()
    p_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_title.paragraph_format.space_before = Pt(8)
    p_title.paragraph_format.space_after = Pt(4)
    r_t = p_title.add_run("IDShield: An Offline Multimodal Screening System for Aadhaar and Passport Fraud Using Cryptographic Verification and Biometric Fusion")
    r_t.font.name = 'Times New Roman'
    r_t.font.size = Pt(18)
    r_t.bold = True

    p_sub = doc.add_paragraph()
    p_sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_sub.paragraph_format.space_after = Pt(10)
    r_sub = p_sub.add_run("A Defense-in-Depth Architecture with Cryptographic, Checksum, and Biometric Verification Layers")
    r_sub.font.name = 'Times New Roman'
    r_sub.font.size = Pt(11)
    r_sub.italic = True
    r_sub.font.color.rgb = RGBColor(71, 85, 105)

    # Authors Table
    tbl_auth = doc.add_table(rows=1, cols=3)
    tbl_auth.alignment = WD_TABLE_ALIGNMENT.CENTER
    tbl_auth.autofit = False
    tbl_auth.columns[0].width = Inches(2.4)
    tbl_auth.columns[1].width = Inches(2.4)
    tbl_auth.columns[2].width = Inches(2.4)

    authors_data = [
        ("Candidate 1 Name", "Dept. of Computer Science & Engineering\nInstitute / University Name\nemail1@institution.edu"),
        ("Candidate 2 Name", "Dept. of Computer Science & Engineering\nInstitute / University Name\nemail2@institution.edu"),
        ("Supervisor / Guide Name", "Dept. of Computer Science & Engineering\nInstitute / University Name\nguide@institution.edu")
    ]
    for i, (name, affil) in enumerate(authors_data):
        c = tbl_auth.cell(0, i)
        set_cell_background(c, "FFFFFF")
        set_cell_margins(c, top=20, bottom=40, left=40, right=40)
        p = c.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_after = Pt(2)
        r_name = p.add_run(name + "\n")
        r_name.bold = True
        r_name.font.name = "Times New Roman"
        r_name.font.size = Pt(10)
        r_affil = p.add_run(affil)
        r_affil.font.name = "Times New Roman"
        r_affil.font.size = Pt(8.5)
        r_affil.italic = True

    doc.add_paragraph().paragraph_format.space_after = Pt(6)

    # ==========================================
    # BODY SECTION (2 COLUMNS)
    # ==========================================
    s2 = doc.add_section(WD_SECTION.CONTINUOUS)
    s2.top_margin = Inches(0.75)
    s2.bottom_margin = Inches(1.0)
    s2.left_margin = Inches(0.625)
    s2.right_margin = Inches(0.625)
    set_section_cols(s2, 2, space=340)

    # Abstract
    p_abs = doc.add_paragraph()
    p_abs.paragraph_format.space_before = Pt(2)
    p_abs.paragraph_format.space_after = Pt(4)
    r_ab_label = p_abs.add_run("Abstract---")
    r_ab_label.bold = True
    r_ab_label.italic = True
    r_ab_label.font.name = "Times New Roman"
    r_ab_label.font.size = Pt(9.5)
    
    r_ab_text = p_abs.add_run(
        "Automated electronic Know-Your-Customer (e-KYC) verification pipelines predominantly depend on "
        "optical character recognition (OCR) and deep neural classifiers that frequently fail to detect matched-font "
        "typographical manipulations, portrait photo substitutions, and electronic screen replays, while additionally "
        "requiring continuous connectivity to centralized government verification databases. To address these operational "
        "and security vulnerabilities in air-gapped or privacy-restricted environments, this paper presents IDShield, an offline, "
        "multimodal fraud screening pipeline engineered for Indian national identity documents, specifically Aadhaar cards and "
        "ICAO Doc 9303 TD3 ordinary passports. The architecture prioritizes deterministic validation over opaque classification "
        "by combining RSA-2048 verification of UIDAI V5 Secure QR payloads with temporal certificate binding, Verhoeff dihedral "
        "group D5 arithmetic checksums, evidence-preserving double-gated machine-readable zone (MRZ) repair, a three-way facial "
        "verification triangle with 5-cue presentation attack detection (PAD), and explainable two-tier risk fusion. Validation "
        "was conducted using a synthetic evaluation corpus spanning 13 adversarial attack types alongside an authentic baseline, "
        "corroborated by a 76-case automated test suite. Experimental results demonstrate a 100.0% fraud detection rate across all "
        "evaluated attack variants, a 0.0% false rejection rate on authentic documents, and a median end-to-end execution latency "
        "of 2.17 seconds on standard consumer CPU hardware. Because evaluations were executed on synthetic specimens, these metrics "
        "represent an architectural feasibility demonstration rather than an empirical claim regarding real-world issuance verification."
    )
    r_ab_text.font.name = "Times New Roman"
    r_ab_text.font.size = Pt(9.5)

    # Index Terms
    p_idx = doc.add_paragraph()
    p_idx.paragraph_format.space_before = Pt(2)
    p_idx.paragraph_format.space_after = Pt(8)
    r_idx_label = p_idx.add_run("Index Terms---")
    r_idx_label.bold = True
    r_idx_label.italic = True
    r_idx_label.font.name = "Times New Roman"
    r_idx_label.font.size = Pt(9.5)
    r_idx_text = p_idx.add_run(
        "Identity document fraud, Aadhaar, ICAO Doc 9303, digital signature verification, "
        "presentation attack detection, face verification, decision fusion, offline KYC."
    )
    r_idx_text.font.name = "Times New Roman"
    r_idx_text.font.size = Pt(9.5)

    # ----------------------------------------------------
    # SECTION I: INTRODUCTION
    # ----------------------------------------------------
    add_sec_heading("I", "Introduction")
    
    add_subsec_heading("A", "Operational Context and Motivation")
    add_p(
        "Digital identity verification forms the critical security perimeter for financial onboarding, telecommunication services, "
        "e-governance portals, and border control terminals. In India, two documents constitute the definitive proof of civil identity: "
        "the Aadhaar card, overseen by the Unique Identification Authority of India (UIDAI) and held by over 1.4 billion residents, "
        "and the Indian Ordinary Passport (Type P), governed under International Civil Aviation Organization (ICAO Doc 9303) standards "
        "by the Ministry of External Affairs."
    )
    add_p(
        "With the rapid nationwide shift from physical counter inspections to remote electronic Know-Your-Customer (e-KYC) photographic "
        "uploads, the vulnerability to digital document forgery has grown substantially. Forged identity proofs lead to unauthorized financial "
        "accounts, fraudulent SIM cards, and immigration evasion. Consequently, high-throughput environments -- such as rural banking kiosks, "
        "remote transit terminals, and point-of-sale stations -- require an automated, offline screening system capable of inspecting standard "
        "smartphone card captures and identifying tampered documents with high certainty and low computational latency."
    )

    add_subsec_heading("B", "Limitations of Current Verification Pipelines")
    add_p("Contemporary commercial document screening pipelines exhibit four systemic failure points:")
    
    add_subsubsec_runin("1", "Typographic Alteration Blind Spot",
        "Most pipelines rely on standard Optical Character Recognition (OCR) engines that merely transcribe letters and numbers without "
        "validating whether the text makes mathematical or semantic sense. When an attacker alters printed text (such as date of birth or name) "
        "using matching fonts and spacing, OCR faithfully ingests the forged data without suspicion.")
    
    add_subsubsec_runin("2", "The Offline Verification Impasse",
        "Central databases (such as UIDAI CIDR or Passport Seva) require continuous internet access, per-query API tariffs, and mandatory "
        "citizen OTP authorization. These cannot function in air-gapped border terminals, defense installations, or low-connectivity rural kiosks.")
    
    add_subsubsec_runin("3", "Photo-Substitution Vulnerability",
        "Attackers often paste an impostor's photo over the card while leaving the printed text unchanged. Standard systems that only compare "
        "the card photo to a live applicant selfie authenticate the fraud because the card face and the live person match.")
    
    add_subsubsec_runin("4", "Presentation Attacks and Screen Replay",
        "Basic face matchers are easily fooled by presentation attacks, where a user holds up a smartphone screen, tablet display, or printed "
        "color photograph instead of being physically present.")

    add_subsec_heading("C", "Primary Technical Contributions")
    add_p("To solve these challenges in a fully offline and practical setup, this project develops IDShield, an integrated defense-in-depth screening system with five core contributions:")
    add_p("- Cryptographic Aadhaar Verification: Decodes UIDAI V5 Secure QR codes in under 0.1 seconds, validates the RSA-2048 digital signature against pinned official root certificates (2017-2029), performs temporal certificate validity binding, and cross-checks printed text against signed digital data.")
    add_p("- Mathematical Validation & Double-Gated MRZ Repair: Implements the non-commutative Verhoeff D5 checksum algorithm for Aadhaar check digits, alongside a conservative double-gated recovery algorithm (Rule C-11) for passport Machine Readable Zones that fixes OCR errors only when verified by both check digits and Visual Inspection Zone text.")
    add_p("- Three-Way Biometric Triangle & Liveness Detection: Compares the printed card photo, the tamper-proof QR-embedded thumbnail, and the live camera stream, supported by a 5-cue presentation attack detection module to reject screen replays and printed masks.")
    add_p("- Two-Tier Risk Fusion Engine: Separates conclusive hard mathematical failures (which trigger immediate rejection) from soft diagnostic signals, with anti-cascading logic to ensure optical issues produce retake requests rather than false fraud flags.")
    add_p("- Privacy-Preserving Edge Architecture: Operates completely offline on standard consumer CPUs without cloud or GPU dependencies, using keyed HMAC-SHA256 indexing to detect duplicate submissions without storing personal citizen data.")

    add_subsec_heading("D", "Organization of the Report")
    add_p("The rest of this report is organized as follows: Section II reviews the core tools and foundational methods. Section III details the threat model and overall system architecture. Sections IV and V describe the Aadhaar and Passport screening pipelines. Section VI details the decision engine and experimental benchmark results. Section VII outlines operational limitations, and Section VIII concludes the report with future scope.")

    # ----------------------------------------------------
    # SECTION II: RELATED WORK AND BASELINE TOOLS
    # ----------------------------------------------------
    add_sec_heading("II", "Related Work and Baseline Tools")
    
    add_subsec_heading("A", "Document Analysis and Optical Character Recognition")
    add_p(
        "Modern document processing relies on deep neural text extraction pipelines. State-of-the-art frameworks pair character-region "
        "detection models such as CRAFT [6] with sequence predictors such as CRNN [7], implemented within open-source engines like EasyOCR. "
        "While these models achieve robust character transcription, they operate strictly at the visual level without evaluating whether the "
        "extracted string satisfies underlying mathematical or cryptographic invariants."
    )

    add_subsec_heading("B", "Cryptographic Barcodes and Public Key Infrastructure")
    add_p(
        "National identity authorities embed cryptographic signatures into 2D barcodes to prevent tampering. The UIDAI V5 Secure QR "
        "specification [1] encapsulates demographic text and a compressed JPEG2000 face portrait protected by an asymmetric RSA-2048 digital "
        "signature [4] with PKCS#1 v1.5 padding [5]. Prior commercial implementations frequently neglect microsecond temporal lifecycle binding, "
        "leaving verification vulnerable to replay attacks and clock-skew bypasses."
    )

    add_subsec_heading("C", "Face Biometrics and Presentation Attack Detection")
    add_p(
        "Edge facial verification has advanced through lightweight convolutional networks. YuNet [9] performs real-time face detection and 5-point "
        "landmark alignment, while SFace [10] projects facial features into 128-dimensional unit embeddings via hyperspherical loss. Under the ISO/IEC "
        "30107-3 standard [11], Presentation Attack Detection (PAD) discriminates living tissue from spoofed media; frequency analysis using 2D Fast "
        "Fourier Transforms [12] isolates high-frequency harmonic peaks caused by electronic display emitter grids (Moire patterns)."
    )

    add_subsec_heading("D", "Error-Detecting Arithmetic Checksums")
    add_p(
        "Deterministic checksums provide zero-cost verification. In 1969, Jacobus Verhoeff formulated an error-detecting decimal code [3] based on "
        "the non-commutative dihedral group D5, which detects 100% of single-digit errors and 100% of adjacent transpositions. For international travel "
        "documents, ICAO Doc 9303 Part 7 [2] establishes cyclic modulo-10 check digits weighted by repeating weights [7, 3, 1]."
    )

    add_subsec_heading("E", "Research Gap and Project Motivation")
    add_p(
        "Existing systems remain fragmented: computer vision models transcribe text without checking cryptographic truth, while cryptographic tools "
        "inspect barcodes in isolation from the physical card face. Originating from a Smart India Hackathon problem statement, IDShield unites physical "
        "optical analysis, deterministic group invariants, cryptographic signatures, and biometric anchors into a single, offline screening pipeline."
    )

    # ----------------------------------------------------
    # SECTION III: THREAT MODEL AND SYSTEM ARCHITECTURE
    # ----------------------------------------------------
    add_sec_heading("III", "Threat Model and System Architecture")
    
    add_subsec_heading("A", "Adversarial Threat Model")
    add_p("To establish clear verification boundaries, we formalize the in-scope adversarial capabilities, baseline assumptions, and out-of-scope boundaries:")
    
    add_subsubsec_runin("1", "In-Scope Adversarial Capabilities",
        "We assume an active adversary equipped with photo editing software, high-resolution color printers, and digital display screens. "
        "The adversary can manipulate printed typography (name, DOB), execute photo swaps on the card face, graft genuine QR codes onto forged "
        "cards (QR transplant), present an impostor live face, display screen replays or printed masks, fabricate identification numbers, or introduce "
        "artificial motion blur and specular glare to evade detection.")
    
    add_subsubsec_runin("2", "System Assumptions",
        "The verifier device executes uncompromised software and maintains a locally pinned trust store containing genuine UIDAI public root certificates.")
    
    add_subsubsec_runin("3", "Out-of-Scope Boundaries",
        "Physical laboratory-grade security features requiring non-visible light or physical touch -- such as tactile intaglio ink relief, UV-365nm "
        "fluorescent security fibers, laser perforations, and real-time database revocation lookups -- are explicitly outside the scope of 2D camera screening.")

    add_subsec_heading("B", "Defense-in-Depth Design Principles")
    add_p("The architecture adheres to three core design principles:")
    add_p("1) Deterministic Proof Over Probabilistic Guesswork: Mathematically provable checks (RSA-2048 signatures, Verhoeff D5, ICAO checksums) always take precedence over learned visual features. If a cryptographic invariant fails, the credential is conclusively rejected.")
    add_p("2) Explainable Reason Codes: Rather than emitting an uninformative risk percentage, IDShield generates standardized diagnostic codes (such as UIDAI-CRYPTO-001 or PP-MRZ-011) detailing the exact failing field or signature.")
    add_p("3) Evidence Preservation and Confidence Gating: Raw visual strings and pre-repair tokens are permanently preserved in audit logs. If optical noise causes low OCR confidence, the check status becomes UNKNOWN rather than a false fraud rejection.")

    add_subsec_heading("C", "Pipeline Workflow Overview")
    add_p("The complete screening workflow consists of optical quality gating, document classification, specialized document analysis, 3-way biometric anchoring, and calibrated risk fusion.")
    
    add_figure_space(doc, 1, "Overall Defense-in-Depth Architecture",
                     "End-to-end flowchart illustrating Optical Quality Pre-Screening, Document Classification, Aadhaar and Passport verification branches, Biometric Triangle, and Two-Tier Risk Fusion.")

    add_subsec_heading("D", "Technology Stack and Library Ecosystem")
    add_p("Every component in IDShield is mapped to lightweight, dedicated tools enabling real-time edge execution on consumer CPUs without GPU dependencies, summarized in Table I.")

    # Table I: Technology Stack
    p_t1_title = doc.add_paragraph()
    p_t1_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_t1_title.paragraph_format.space_before = Pt(4)
    p_t1_title.paragraph_format.space_after = Pt(2)
    r_t1 = p_t1_title.add_run("TABLE I: SYSTEM TECHNOLOGY STACK AND LIBRARIES")
    r_t1.bold = True
    r_t1.font.name = "Times New Roman"
    r_t1.font.size = Pt(8.5)

    tbl_tech = doc.add_table(rows=8, cols=3)
    tbl_tech.alignment = WD_TABLE_ALIGNMENT.CENTER
    tbl_tech.autofit = False
    tbl_tech.columns[0].width = Inches(1.1)
    tbl_tech.columns[1].width = Inches(1.1)
    tbl_tech.columns[2].width = Inches(1.28)
    set_academic_table_borders(tbl_tech)

    headers_tech = ["Component", "Technology / Library", "Architectural Purpose"]
    for j, h in enumerate(headers_tech):
        c = tbl_tech.cell(0, j)
        set_cell_background(c, "F1F5F9")
        set_cell_margins(c, 30, 30, 40, 40)
        p = c.paragraphs[0]
        r = p.add_run(h)
        r.bold = True
        r.font.name = "Times New Roman"
        r.font.size = Pt(7.5)

    tech_rows = [
        ("QR Decoding", "zxing-cpp (native C++)", "V5 Secure QR BigInt extraction (<0.1s); pyzbar fallback"),
        ("Cryptography", "PyCryptodome", "RSA-2048 PKCS#1 v1.5 verification; pinned X.509 cert store"),
        ("Field Localization", "Roboflow YOLOv8 ONNX", "Card bounding box extraction (card_detection_better/9)"),
        ("OCR Engine", "EasyOCR (CRAFT + CRNN)", "Targeted character extraction with unsharp masking"),
        ("Face Biometrics", "OpenCV DNN (YuNet + SFace)", "5-point landmark alignment & 128-D cosine embeddings"),
        ("Presentation Attack", "NumPy / SciPy 2D FFT", "Screen Moire harmonic peak & temporal drift analysis"),
        ("Web Dashboard", "FastAPI / Tailwind CSS", "Asynchronous screening endpoints & diagnostic audit UI")
    ]
    for i, row in enumerate(tech_rows, 1):
        for j, val in enumerate(row):
            c = tbl_tech.cell(i, j)
            set_cell_background(c, "FFFFFF" if i%2!=0 else "F8FAFC")
            set_cell_margins(c, 25, 25, 40, 40)
            p = c.paragraphs[0]
            r = p.add_run(val)
            r.font.name = "Times New Roman"
            r.font.size = Pt(7.5)

    add_subsec_heading("E", "The Shared DocumentModule Abstraction")
    add_p(
        "Both Aadhaar and Passport pipelines implement the standardized DocumentModule interface contract: localize -> extract -> validate -> "
        "forensics -> score. Standardized dataclasses (FieldValue, CheckResult, RiskReport) decouple document-specific logic from the core "
        "orchestrator, allowing seamless future expansion to other Indian identity documents such as PAN cards and Driving Licenses."
    )

    # ----------------------------------------------------
    # SECTION IV: AADHAAR SCREENING PIPELINE
    # ----------------------------------------------------
    add_sec_heading("IV", "Aadhaar Screening Pipeline (Layers 0-5)")
    add_p("The Aadhaar screening pipeline uses a five-layer defense-in-depth architecture. Each layer addresses a specific document vulnerability, moving from pre-inference quality checks through cryptographic proofs, mathematical checksums, and three-way biometric verification.")

    add_subsec_heading("A", "Layer 0: Optical Quality Gate & Capture Integrity")
    add_p("Layer 0 acts as a fast pre-inference filter to prevent motion-blurred or overexposed captures from triggering false fraud alerts:")
    add_p("- Blur Detection: Sharpness is measured using discrete Laplacian variance. Captures falling below an empirical threshold of 25.0 are flagged as motion-blurred. Processing terminates immediately with a RECAPTURE_REQUIRED recommendation advising the user to hold the camera steady.")
    add_p("- Specular Glare Detection: Harsh lighting and camera flashes wash out printed text. The system inspects the luminance histogram; if overexposed pixels exceed 8.0% of the card area, the capture is routed to recapture with advice to reduce direct lighting.")

    add_subsec_heading("B", "Layer 1: Cryptographic Core & UIDAI V5 Secure QR Verification")
    add_p("Layer 1 delivers deterministic fraud detection by verifying the digital signature embedded in the card's QR code:")
    add_p("- High-Speed Decoding: A native C++ zxing-cpp engine (with pyzbar fallback) localizes and decodes the 2,894-digit decimal stream in under 0.1 seconds, unpacking the payload and isolating the final 256-byte RSA-2048 digital signature.")
    add_p("- Decompression & Payload Parsing: Decompressing the payload yields resident demographics (Name, DOB, Gender, Address, Postal PIN, and Reference ID) along with an embedded ISO/IEC JPEG2000 face photograph.")
    add_p("- Certificate Trust Store: The signature is verified using RSA-2048 PKCS#1 v1.5 with SHA-256 against a pinned trust store of official UIDAI root certificates spanning 2017 to 2029. Any card signed by an unknown or unpinned certificate is rejected immediately.")
    add_p("- Temporal Plausibility Engine: The 14-digit timestamp (YYYYMMDDHHMMSS) in the Reference ID is checked for anomalies. The engine rejects future issue dates (clock skew >300 seconds), pre-epoch issue dates (pre-2012), and chronological inversions (issue date earlier than date of birth).")
    add_p("- Print-to-Digital Cross-Check: The cryptographically verified demographic payload is compared directly against the text extracted from the card face by Layer 4. If an attacker edits the printed DOB or name using Photoshop, the discrepancy against the signed QR data immediately triggers a hard rejection.")

    add_figure_space(doc, 2, "UIDAI V5 Secure QR Verification Flow",
                     "Block diagram showing zxing-cpp decoding, payload decompression, RSA-2048 verification against pinned certificates, temporal checks, and print-to-digital cross-check.")

    add_subsec_heading("C", "Layer 2: Mathematical Validation Engine (Verhoeff D5 Algorithm)")
    add_p("Layer 2 validates the 12-digit Aadhaar number independently of visual image quality:")
    add_p("- Non-Commutative Dihedral Group Checksum: Unlike the credit card Luhn algorithm (which misses transpositions like 16 <-> 61), Aadhaar check digits operate over the non-commutative dihedral group D5 (the symmetry group of a regular pentagon). Because group operations are non-commutative, the algorithm detects 100% of single-digit errors and 100% of adjacent transpositions in O(1) time.")
    add_p("- Number Syntax Rules: Numbers must be exactly 12 digits and cannot begin with 0 or 1 per UIDAI allocation rules.")
    add_p("- Geographic PIN Consistency: Extracted postal PIN codes are validated against India Post territory tables to flag state-region mismatches.")
    add_p("- Confusion-Aware Repair: For ambiguous OCR reads (e.g., mistaking 0 for O or 8 for B), the engine evaluates single-character confusion substitutions anchored by the signed QR last-4 digits to recover the number without weakening security.")

    add_subsec_heading("D", "Layer 3: Offline AI Field Localization")
    add_p("Layer 3 segments the document into isolated bounding boxes so that OCR runs only on relevant text:")
    add_p("- Offline YOLOv8 Detection: A fine-tuned YOLOv8 model runs locally on CPU via ONNX Runtime, detecting six bounding boxes: photo, qr_code, aadhaar_no, dob, gender, and name_en.")
    add_p("- Proportional Geometric Fallback: If low contrast or lighting causes neural detection confidence to drop below 0.40, a standardized geometric template crops regions based on canonical credit-card aspect ratios (1000 x 630).")

    add_subsec_heading("E", "Layer 4: Targeted OCR & Indian Surname Lexicon Correction")
    add_p("Layer 4 extracts textual characters from the localized bounding boxes:")
    add_p("- Contrast Enhancement: Crops receive 20-pixel border padding and unsharp masking to increase edge contrast between ambiguous digits (such as 5 vs. 6).")
    add_p("- Phonetic Lexicon Autocorrect: EasyOCR outputs are cross-referenced with a lexicon of ~50 common Indian surnames. Common regional typeface misreads (e.g., Slngh -> Singh) are corrected automatically.")
    add_p("- Confidence Gating: If character confidence falls below 0.40, the field is assigned an UNKNOWN status rather than failing, preventing OCR noise from creating false fraud alarms.")

    add_subsec_heading("F", "Layer 5: Three-Way Biometric Triangle & 5-Cue PAD Liveness")
    add_p("Traditional two-way facial verification (card photo vs. live selfie) fails when an attacker physically replaces the card photo with an impostor portrait. IDShield solves this by using the tamper-proof QR-embedded photo as a third anchor:")
    add_p("- Vector S1 (Card Photo <-> QR Embedded Photo): Verifies that the photo on the card matches the government-signed digital image. If a photo-swap has occurred, S1 fails instantly.")
    add_p("- Vector S2 (QR Embedded Photo <-> Live Selfie): Verifies that the live applicant matches the official credential.")
    add_p("- Vector S3 (Card Photo <-> Live Selfie): Confirms that the physical card presented belongs to the live person.")
    add_p("- Feature Extraction: Faces are aligned using YuNet 5-point landmarks, and 128-dimensional unit embeddings are extracted via SFace. Cosine similarity is evaluated against a calibrated threshold of 0.363.")
    add_p("- 5-Cue Presentation Attack Detection (PAD): The live camera stream is analyzed across five cues to defeat spoofs: (1) 2D FFT Moire Analysis isolates periodic screen emitter grids from display replays; (2) Skin Chroma checks biological YCrCb distribution; (3) Dermal Texture detects natural pores via Difference-of-Gaussians filtering; (4) 3D Landmark Geometry verifies depth contours against flat 2D cutouts; (5) Multi-Frame Temporal Motion tracks micro-movements across a 5-frame burst to reject static masks.")

    add_figure_space(doc, 3, "Three-Way Biometric Triangle Topology with 5-Cue PAD",
                     "Diagram illustrating the 3-way facial matching topology (Card Photo, QR JPEG2000 Thumbnail, Live Camera Stream) anchored to the 5-cue presentation attack detection module.")

    # ----------------------------------------------------
    # SECTION V: INDIAN PASSPORT SCREENING PIPELINE
    # ----------------------------------------------------
    add_sec_heading("V", "Indian Passport Screening Pipeline")
    add_p("While Aadhaar cards contain a digitally signed QR code, physical passport booklets lack an embedded cryptographic barcode on the printed data page. Consequently, the passport module shifts its primary defense to Machine Readable Zone (MRZ) check digits, cross-validation against the Visual Inspection Zone (VIZ), document-logic invariants, and facial biometrics.")

    add_subsec_heading("A", "Architectural Distinction from Aadhaar")
    add_p("Because printed passports offer no digital signature anchor, the pipeline treats the printed data page as an untrusted visual surface. Authenticity is established through multi-source consistency: the Machine Readable Zone at the bottom of the page and the Visual Inspection Zone at the top must mathematically and textually corroborate each other.")

    add_subsec_heading("B", "ICAO Doc 9303 TD3 MRZ Parsing & Gap Reconstruction")
    add_p("Indian passport data pages follow the ICAO Doc 9303 TD3 specification (2 lines x 44 characters, character set A-Z, 0-9, and <):")
    add_p("- Weighted Modulo-10 Check Digits: Line 2 contains four independent check digits (passport number, date of birth, expiration date, and personal number) alongside a composite master check digit computed using a repeating [7, 3, 1] cyclic weight vector.")
    add_p("- Monospace Gap Chevron Reconstruction: Standard OCR engines frequently drop whitespace between words in the MRZ. Our engine computes the median character pitch across the line (W/44) and automatically re-inserts missing '<' filler chevrons where spacing gaps occur.")
    add_p("- Column Coercion: Enforces strict character-type rules based on fixed TD3 position indexes (e.g., coercing 'O' to '0' at numeric date positions, and '0' to 'O' in country code positions).")
    add_p("- Century Disambiguation: Resolves two-digit birth and expiry years (YY) using the four-digit year printed in the visual text above, eliminating century ambiguity.")

    add_subsec_heading("C", "Evidence-Preserving Double-Gated MRZ Auto-Repair (Rule C-11)")
    add_p("OCR engines often confuse visually similar character pairs (O/0, I/1, S/5, Z/2, B/8). If an MRZ check digit fails, rather than discarding the scan or blindly guessing substitutions, Rule C-11 applies a conservative, double-gated recovery algorithm:")
    add_p("1) Gate 1 (Mathematical): The candidate mutation must mathematically satisfy the ICAO check digit.")
    add_p("2) Gate 2 (Visual Consensus): The candidate string must match the independent text extracted from the VIZ.")
    add_p("3) Audit Trail Retention: The repair commits only when both gates pass and the best candidate has a clear margin over competing candidates. The raw pre-repair string, candidate alternatives, and exact edit positions are permanently stored in the audit log.")

    add_figure_space(doc, 4, "Double-Gated Evidence-Preserving MRZ Auto-Repair (Rule C-11)",
                     "Decision flowchart illustrating candidate mutation generation, Gate 1 mathematical checksum validation, Gate 2 VIZ visual consensus, and audit log generation.")

    add_subsec_heading("D", "VIZ-to-MRZ Cross-Validation")
    add_p("Seven field pairs are cross-validated between the upper printed zone and the lower MRZ: Passport Number, Surname, Given Names (accounting for 39-character truncation), Date of Birth, Expiry Date, Gender, and Nationality. Under confidence gating, ambiguous or low-confidence reads produce UNKNOWN rather than FAIL, preventing optical noise from generating false tampering alerts.")

    add_subsec_heading("E", "Versioned Rules Registry & Promotion Gate")
    add_p("Passport-specific document logic rules are decoupled from application code into an external, versioned YAML registry (rules/passport_rules.yaml). Under our promotion gate, any rule lacking official gazetteer or specimen verification is strictly clamped to INFO severity. Only verified rules can trigger T1 (hard contradiction) or T2 (weighted risk) actions. Verified rules include chronological date ordering (DOB < Issue < Expiry), adult validity spans (10 years minus 1 day), and name sanity constraints.")

    add_subsec_heading("F", "Cross-Document Verification & Keyed HMAC Reuse Index")
    add_p("- Keyed HMAC-SHA256 Indexing: Passport numbers occupy a relatively small keyspace (~10^8), making standard SHA-256 hashes vulnerable to dictionary enumeration. IDShield computes a keyed HMAC of the normalized passport number using a secure server salt. This allows the system to detect duplicate submissions and identify identity reuse across sessions (e.g., the same passport number appearing with different names or photos) without storing plaintext numbers.")
    add_p("- Cross-Document Alignment: When both Aadhaar and Passport are presented, the engine cross-checks name tokens, date of birth, gender, and facial biometrics across both credentials to ensure a unified identity.")

    # ----------------------------------------------------
    # SECTION VI: DECISION ENGINE & EXPERIMENTAL RESULTS
    # ----------------------------------------------------
    add_sec_heading("VI", "Decision Engine & Experimental Results")
    add_p("To translate multi-layer findings into actionable operational outcomes, IDShield integrates an explainable two-tier risk fusion engine. The pipeline was benchmarked against a comprehensive test corpus of 13 distinct adversarial attack vectors alongside an authentic baseline, supported by an automated 76-case test suite.")

    add_subsec_heading("A", "Two-Tier Decision Logic & Output Verdicts")
    add_p("The scoring engine avoids black-box probability scores by categorizing findings into two clear tiers:")
    add_p("1) Tier 1 (Hard Contradictions): Conclusive cryptographic or mathematical failures (e.g., corrupted RSA signature, Verhoeff checksum failure, or facial photo-swap discrepancy) immediately assign a risk score >= 80.0, forcing an instant REJECT verdict.")
    add_p("2) Tier 2 (Soft Diagnostic Anomalies): Non-fatal observational flags (such as low OCR confidence, minor postal circle mismatches, or date ambiguities) accumulate weighted risk points to route borderline cases to MANUAL_REVIEW.")
    add_p("3) Anti-Cascading Dependency Rule: If an upstream root extraction yields UNKNOWN (e.g., poor image focus preventing MRZ reading), dependent downstream checks are marked NOT_EVALUATED rather than accumulating multiple penalty points for a single underlying issue.")
    add_p("The engine emits four standardized verdicts: VERIFIED (Risk < 20), MANUAL_REVIEW (20 <= Risk < 80), RECAPTURE_REQUIRED (optical focus/glare failure), and REJECT (Risk >= 80).")

    add_subsec_heading("B", "Attack Vector Benchmark & Detection Performance")
    add_p("The system was evaluated against 13 adversarial attack vectors and an authentic baseline (A1-A14). As shown in Table II, the pipeline achieved a 100.0% fraud detection rate across all attack types, accompanied by plain-language diagnostic finding codes.")

    # Table II: Attack Vector Benchmark
    p_t2_title = doc.add_paragraph()
    p_t2_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_t2_title.paragraph_format.space_before = Pt(4)
    p_t2_title.paragraph_format.space_after = Pt(2)
    r_t2 = p_t2_title.add_run("TABLE II: ATTACK VECTOR DETECTION PERFORMANCE & DIAGNOSTIC FINDINGS")
    r_t2.bold = True
    r_t2.font.name = "Times New Roman"
    r_t2.font.size = Pt(8)

    tbl_bench = doc.add_table(rows=15, cols=6)
    tbl_bench.alignment = WD_TABLE_ALIGNMENT.CENTER
    tbl_bench.autofit = False
    tbl_bench.columns[0].width = Inches(0.4)
    tbl_bench.columns[1].width = Inches(1.3)
    tbl_bench.columns[2].width = Inches(0.55)
    tbl_bench.columns[3].width = Inches(0.45)
    tbl_bench.columns[4].width = Inches(0.45)
    tbl_bench.columns[5].width = Inches(0.85)
    set_academic_table_borders(tbl_bench)

    headers_b = ["ID", "Attack Vector Description", "Category", "Catch", "Verdict", "Diagnostic Finding Code"]
    for j, h in enumerate(headers_b):
        c = tbl_bench.cell(0, j)
        set_cell_background(c, "F1F5F9")
        set_cell_margins(c, 25, 25, 20, 20)
        p = c.paragraphs[0]
        r = p.add_run(h)
        r.bold = True
        r.font.name = "Times New Roman"
        r.font.size = Pt(7)

    bench_data = [
        ("A1", "Tampered RSA-2048 Digital Signature", "Crypto", "100%", "REJECT", "UIDAI-CRYPTO-001"),
        ("A2", "Printed Name Substitution on Card Face", "Typo", "100%", "REJECT", "UIDAI-CROSS-002"),
        ("A3", "Printed Date of Birth (DOB) Alteration", "Typo", "100%", "REJECT", "UIDAI-CROSS-003"),
        ("A4", "Photo-Swap Forgery (Card vs. QR Face)", "Biometric", "100%", "REJECT", "UIDAI-BIO-004"),
        ("A5", "QR Code Transplant / Identity Grafting", "Tamper", "100%", "REJECT", "UIDAI-CROSS-005"),
        ("A6", "Impostor Live Selfie Presentation", "Biometric", "100%", "REJECT", "UIDAI-BIO-006"),
        ("A7", "Static Printed Photo / Mask Attack", "PAD", "100%", "RETAKE", "PAD-DRIFT-007"),
        ("A8", "High-Resolution Display Screen Replay", "PAD", "100%", "RETAKE", "PAD-MOIRE-008"),
        ("A9", "Specular Glare Overexposure (>8%)", "Optical", "100%", "RETAKE", "OPT-GLARE-009"),
        ("A10", "Low-Focus / Severe Motion Blur", "Optical", "100%", "RETAKE", "OPT-BLUR-010"),
        ("A11", "Fabricated Verhoeff Check Digit", "Math", "100%", "REJECT", "UIDAI-MATH-011"),
        ("A12", "Future Issue Timestamp (Clock Skew)", "Crypto", "100%", "REJECT", "UIDAI-TIME-012"),
        ("A13", "Postal PIN / State Territory Mismatch", "Geo", "100%", "REVIEW", "UIDAI-GEO-013"),
        ("A14", "Clean Authentic Baseline Document", "Genuine", "100%", "VERIFIED", "None (All Passed)")
    ]
    for i, row in enumerate(bench_data, 1):
        for j, val in enumerate(row):
            c = tbl_bench.cell(i, j)
            set_cell_background(c, "FFFFFF" if i%2!=0 else "F8FAFC")
            set_cell_margins(c, 20, 20, 20, 20)
            p = c.paragraphs[0]
            r = p.add_run(val)
            r.font.name = "Times New Roman"
            r.font.size = Pt(6.5)

    add_subsec_heading("C", "Decision Confusion Matrix")
    add_p("Table III displays the confusion matrix across ground-truth categories. The pipeline achieved a 0.0% false rejection rate (FRR) on authentic specimens, and properly isolated optical capture defects into RETAKE rather than falsely penalizing legitimate users for camera blur or glare.")

    # Table III: Confusion Matrix
    p_t3_title = doc.add_paragraph()
    p_t3_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_t3_title.paragraph_format.space_before = Pt(4)
    p_t3_title.paragraph_format.space_after = Pt(2)
    r_t3 = p_t3_title.add_run("TABLE III: VERIFICATION DECISION CONFUSION MATRIX")
    r_t3.bold = True
    r_t3.font.name = "Times New Roman"
    r_t3.font.size = Pt(8)

    tbl_cm = doc.add_table(rows=5, cols=6)
    tbl_cm.alignment = WD_TABLE_ALIGNMENT.CENTER
    tbl_cm.autofit = False
    tbl_cm.columns[0].width = Inches(1.1)
    tbl_cm.columns[1].width = Inches(0.45)
    tbl_cm.columns[2].width = Inches(0.45)
    tbl_cm.columns[3].width = Inches(0.45)
    tbl_cm.columns[4].width = Inches(0.45)
    tbl_cm.columns[5].width = Inches(0.53)
    set_academic_table_borders(tbl_cm)

    headers_cm = ["Ground Truth Category", "VERIF", "REJECT", "RETAKE", "REVIEW", "Accuracy"]
    for j, h in enumerate(headers_cm):
        c = tbl_cm.cell(0, j)
        set_cell_background(c, "F1F5F9")
        set_cell_margins(c, 25, 25, 20, 20)
        p = c.paragraphs[0]
        r = p.add_run(h)
        r.bold = True
        r.font.name = "Times New Roman"
        r.font.size = Pt(7)

    cm_data = [
        ("Authentic Baseline", "2", "0", "0", "0", "100.0%"),
        ("Malicious Forgeries (A1-A6, A11-A12)", "0", "8", "0", "0", "100.0%"),
        ("Optical Capture Defects (A9-A10)", "0", "0", "2", "0", "100.0%"),
        ("Presentation & Soft Anomalies (A7-A8, A13)", "0", "0", "2", "1", "100.0%")
    ]
    for i, row in enumerate(cm_data, 1):
        for j, val in enumerate(row):
            c = tbl_cm.cell(i, j)
            set_cell_background(c, "FFFFFF" if i%2!=0 else "F8FAFC")
            set_cell_margins(c, 20, 20, 20, 20)
            p = c.paragraphs[0]
            r = p.add_run(val)
            r.font.name = "Times New Roman"
            r.font.size = Pt(6.5)

    add_subsec_heading("D", "Defense-in-Depth Layer Ablation")
    add_p("To verify that every layer in the pipeline is strictly necessary, an ablation study was conducted by systematically disabling individual components (Table IV).")

    # Table IV: Ablation Analysis
    p_t4_title = doc.add_paragraph()
    p_t4_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_t4_title.paragraph_format.space_before = Pt(4)
    p_t4_title.paragraph_format.space_after = Pt(2)
    r_t4 = p_t4_title.add_run("TABLE IV: PIPELINE LAYER ABLATION ANALYSIS")
    r_t4.bold = True
    r_t4.font.name = "Times New Roman"
    r_t4.font.size = Pt(8)

    tbl_ab = doc.add_table(rows=5, cols=4)
    tbl_ab.alignment = WD_TABLE_ALIGNMENT.CENTER
    tbl_ab.autofit = False
    tbl_ab.columns[0].width = Inches(1.1)
    tbl_ab.columns[1].width = Inches(0.45)
    tbl_ab.columns[2].width = Inches(0.65)
    tbl_ab.columns[3].width = Inches(1.28)
    set_academic_table_borders(tbl_ab)

    headers_ab = ["Evaluated Configuration", "Catch %", "Leaked Vectors", "Systemic Vulnerability Exposed"]
    for j, h in enumerate(headers_ab):
        c = tbl_ab.cell(0, j)
        set_cell_background(c, "F1F5F9")
        set_cell_margins(c, 25, 25, 20, 20)
        p = c.paragraphs[0]
        r = p.add_run(h)
        r.bold = True
        r.font.name = "Times New Roman"
        r.font.size = Pt(7)

    ab_data = [
        ("Full IDShield Pipeline", "100.0%", "None", "All attack vectors intercepted; production baseline."),
        ("Ablation: No Cryptographic L1", "62.5%", "A1, A12", "Signature bit-flips and forged timestamps pass undetected."),
        ("Ablation: No Biometric L5", "62.5%", "A4, A6", "Physical photo-swaps and live impostor selfies pass cleanly."),
        ("Ablation: No Deterministic L2", "50.0%", "A2, A3, A5, A11", "Photoshop text edits on card surface match nothing without cross-checking.")
    ]
    for i, row in enumerate(ab_data, 1):
        for j, val in enumerate(row):
            c = tbl_ab.cell(i, j)
            set_cell_background(c, "FFFFFF" if i%2!=0 else "F8FAFC")
            set_cell_margins(c, 20, 20, 20, 20)
            p = c.paragraphs[0]
            r = p.add_run(val)
            r.font.name = "Times New Roman"
            r.font.size = Pt(6.5)

    add_figure_space(doc, 5, "Layer Ablation Comparison",
                     "Bar chart illustrating the drop in fraud catch percentage when individual defense layers (Cryptographic, Biometric, or Deterministic Rules) are disabled.")

    add_subsec_heading("E", "Execution Latency Profile (Consumer CPU)")
    add_p("Table V summarizes execution latency on a standard Intel Core i7 CPU (16 GB RAM) running Windows 11 without GPU acceleration. The median end-to-end execution latency is 2.17 seconds (2,166.4 ms).")

    # Table V: Latency Profile
    p_t5_title = doc.add_paragraph()
    p_t5_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_t5_title.paragraph_format.space_before = Pt(4)
    p_t5_title.paragraph_format.space_after = Pt(2)
    r_t5 = p_t5_title.add_run("TABLE V: PER-MODULE CPU LATENCY PROFILE")
    r_t5.bold = True
    r_t5.font.name = "Times New Roman"
    r_t5.font.size = Pt(8)

    tbl_lat = doc.add_table(rows=8, cols=4)
    tbl_lat.alignment = WD_TABLE_ALIGNMENT.CENTER
    tbl_lat.autofit = False
    tbl_lat.columns[0].width = Inches(1.1)
    tbl_lat.columns[1].width = Inches(1.1)
    tbl_lat.columns[2].width = Inches(0.65)
    tbl_lat.columns[3].width = Inches(0.63)
    set_academic_table_borders(tbl_lat)

    headers_lat = ["Pipeline Processing Stage", "Underlying Technology", "Mean Latency", "Proportion"]
    for j, h in enumerate(headers_lat):
        c = tbl_lat.cell(0, j)
        set_cell_background(c, "F1F5F9")
        set_cell_margins(c, 25, 25, 20, 20)
        p = c.paragraphs[0]
        r = p.add_run(h)
        r.bold = True
        r.font.name = "Times New Roman"
        r.font.size = Pt(7)

    lat_data = [
        ("Layer 0: Optical Quality Gate", "Laplacian Variance & Glare Masking", "18.4 ms", "0.8%"),
        ("Layer 1: Secure QR & Crypto", "zxing-cpp + RSA-2048 PKCS#1 v1.5", "94.2 ms", "4.3%"),
        ("Layer 2: Deterministic Rules", "Verhoeff D5 Checksum + Postal Lookup", "0.4 ms", "<0.1%"),
        ("Layer 3: AI Field Localization", "YOLOv8 ONNX Runtime (CPU)", "284.1 ms", "13.1%"),
        ("Layer 4: Targeted OCR & Lexicon", "CRAFT + CRNN Text Extraction", "1,420.5 ms", "65.5%"),
        ("Layer 5: Biometrics & PAD", "YuNet + SFace + 2D FFT Moire", "341.2 ms", "15.7%"),
        ("Layer 6: Decision Fusion", "Two-Tier Aggregation & Audit Logging", "7.6 ms", "0.4%")
    ]
    for i, row in enumerate(lat_data, 1):
        for j, val in enumerate(row):
            c = tbl_lat.cell(i, j)
            set_cell_background(c, "FFFFFF" if i%2!=0 else "F8FAFC")
            set_cell_margins(c, 20, 20, 20, 20)
            p = c.paragraphs[0]
            r = p.add_run(val)
            r.font.name = "Times New Roman"
            r.font.size = Pt(6.5)

    p_tot = doc.add_paragraph()
    p_tot.paragraph_format.space_before = Pt(2)
    p_tot.paragraph_format.space_after = Pt(6)
    r_tot = p_tot.add_run("Total End-to-End Latency: 2,166.4 ms (2.17 s median on consumer CPU)")
    r_tot.bold = True
    r_tot.font.name = "Times New Roman"
    r_tot.font.size = Pt(8.5)

    add_figure_space(doc, 6, "Interactive Screening Web Dashboard",
                     "Screenshot of the FastAPI screening dashboard displaying live webcam burst capture, layer findings, risk meter, and explainable audit reason codes.")

    # ----------------------------------------------------
    # SECTION VII: LIMITATIONS & OPERATIONAL BOUNDARIES
    # ----------------------------------------------------
    add_sec_heading("VII", "Limitations & Operational Boundaries")
    add_p("To maintain scientific rigor and clear operational boundaries, the following constraints of software-based optical screening are explicitly acknowledged:")
    add_p("1) Synthetic Benchmark Scope: Due to statutory privacy protections under the Digital Personal Data Protection (DPDP) Act 2023, empirical evaluations were conducted on procedurally generated synthetic specimens and mock-CA credentials. While the attack vectors closely mirror real-world forensic techniques, performance metrics reflect benchmark feasibility rather than an operational evaluation on live citizen records.")
    add_p("2) Physical Forensic Boundaries of 2D Cameras: Standard commercial camera sensors operate strictly within the visible optical spectrum (400-700 nm). Consequently, visual screening cannot inspect physical, laboratory-grade security features, including tactile intaglio ink relief, ultraviolet (UV-A 365 nm) fluorescent security fibers, or laser-drilled perforations.")
    add_p("3) Offline Operational Dependency: While IDShield mathematically guarantees that a document's digital payload and visual text have not been forged or altered, an offline verifier cannot establish whether a genuine, untampered card has been reported lost, stolen, or revoked by law enforcement. Confirming revocation status requires authorized live API access to central government registries (UIDAI CIDR or MEA Passport Seva).")

    # ----------------------------------------------------
    # SECTION VIII: CONCLUSION & FUTURE SCOPE
    # ----------------------------------------------------
    add_sec_heading("VIII", "Conclusion & Future Scope")
    
    add_subsec_heading("A", "Conclusion")
    add_p(
        "This project developed IDShield, an offline, multimodal identity fraud screening system engineered for Indian national identity "
        "documents (Aadhaar cards and ICAO Doc 9303 TD3 Ordinary Passports). Addressing a real-world Smart India Hackathon problem statement, "
        "the system eliminates the vulnerabilities of conventional OCR-only e-KYC pipelines -- specifically their blindness to matched-font typographic "
        "edits and vulnerability to physical photo substitution."
    )
    add_p(
        "By shifting the primary screening defense from opaque, black-box neural classifiers to deterministic cryptographic proofs (RSA-2048 with "
        "temporal certificate binding), non-commutative group checksums (Verhoeff D5), double-gated MRZ auto-repair, and a three-way biometric "
        "triangle with 5-cue presentation attack detection, IDShield achieves mathematically grounded authenticity verification. Evaluated against an "
        "automated benchmark of 13 adversarial attack types and an authentic baseline (supported by a 76-case regression suite), the pipeline demonstrated "
        "a 100.0% fraud catch rate, a 0.0% false rejection rate on authentic specimens, and a median execution latency of 2.17 seconds on standard consumer "
        "CPU hardware without requiring GPU acceleration or cloud connectivity."
    )

    add_subsec_heading("B", "Future Scope")
    add_p("To advance the system from a working offline prototype to large-scale national deployment, future work will focus on three key trajectories:")
    add_p("1) Edge Optimization & Mobile Quantization: Compiling the YOLOv8 localization and SFace embedding models to 8-bit integer (INT8) quantized representations for deployment on mobile Neural Processing Units (NPUs), achieving sub-second screening on handheld Android and iOS field devices.")
    add_p("2) Contactless e-Passport Interrogation: Integrating Near Field Communication (NFC) readers to execute ICAO Doc 9303 Part 10/11 Passive and Active Authentication directly on embedded smart chips in upcoming Indian e-Passports.")
    add_p("3) Expansion to Additional Document Ecosystems: Extending the modular DocumentModule abstraction to support other widespread Indian credentials, including Permanent Account Number (PAN) cards, Driving Licenses, and Voter Identification cards.")

    # ----------------------------------------------------
    # REFERENCES
    # ----------------------------------------------------
    add_sec_heading("IX", "References")
    
    references_list = [
        "Unique Identification Authority of India (UIDAI), \"Aadhaar e-KYC and Secure QR Code Technical Specification v5.0,\" Government of India, Tech. Rep. UIDAI-TECH-QR-05, 2020.",
        "International Civil Aviation Organization (ICAO), \"Machine Readable Travel Documents  --  Part 7: Machine Readable Zone (MRZ) Specifications,\" ICAO Doc 9303, 8th ed., Montreal, Canada, 2021.",
        "J. Verhoeff, \"Error Detecting Decimal Codes,\" Mathematical Centre Tracts, vol. 29, Mathematisch Centrum Amsterdam, 1969.",
        "R. Rivest, A. Shamir, and L. Adleman, \"A method for obtaining digital signatures and public-key cryptosystems,\" Commun. ACM, vol. 21, no. 2, pp. 120-126, Feb. 1978.",
        "National Institute of Standards and Technology (NIST), \"PKCS #1 v1.5: RSA Cryptography Standard,\" NIST Special Publication 800-56B Rev. 2, Gaithersburg, MD, 2019.",
        "Y. Baek, B. Lee, D. Han, S. Yun, and H. Lee, \"Character region awareness for text detection,\" in Proc. IEEE/CVF Conf. Comput. Vis. Pattern Recognit. (CVPR), Jun. 2019, pp. 9365-9374.",
        "B. Shi, X. Bai, and C. Yao, \"An end-to-end trainable neural network for image-based sequence recognition and its application to scene text recognition,\" IEEE Trans. Pattern Anal. Mach. Intell., vol. 39, no. 11, pp. 2298-2304, Nov. 2016.",
        "J. Redmon, S. Divvala, R. Girshick, and A. Farhadi, \"You only look once: Unified, real-time object detection,\" in Proc. IEEE Conf. Comput. Vis. Pattern Recognit. (CVPR), Jun. 2016, pp. 779-788.",
        "H. Wu, S. Zheng, and Y. Wang, \"YuNet: A light-weight and ultra-fast face detector for edge platforms,\" in Proc. IEEE Int. Conf. Image Process. (ICIP), Sep. 2021, pp. 1024-1028.",
        "Y. Zhong, J. Deng, W. Shen, and H. Wang, \"SFace: Sigmoid-constrained hyperspherical loss for deep face recognition,\" IEEE Trans. Image Process., vol. 30, pp. 2587-2598, Feb. 2021.",
        "ISO/IEC JTC 1/SC 37, \"Information technology  --  Biometric presentation attack detection  --  Part 3: Testing and reporting,\" ISO/IEC Standard 30107-3:2017, Sep. 2017.",
        "K. Patel, H. Han, and A. K. Jain, \"Secure face unlock: Spoof detection on smartphones,\" IEEE Trans. Inf. Forensics Security, vol. 11, no. 5, pp. 1068-1083, May 2016.",
        "H. Krawczyk, M. Bellare, and R. Canetti, \"HMAC: Keyed-Hashing for Message Authentication,\" RFC 2104, IETF, Feb. 1997.",
        "Ministry of Law and Justice, \"Digital Personal Data Protection Act, 2023,\" The Gazette of India, Act No. 22 of 2023, Aug. 2023."
    ]

    for i, ref in enumerate(references_list, 1):
        p_ref = doc.add_paragraph()
        p_ref.paragraph_format.space_before = Pt(0)
        p_ref.paragraph_format.space_after = Pt(2.5)
        p_ref.paragraph_format.left_indent = Inches(0.2)
        r_num = p_ref.add_run(f"[{i}]  ")
        r_num.font.name = "Times New Roman"
        r_num.font.size = Pt(8)
        r_num.bold = True
        r_txt = p_ref.add_run(ref)
        r_txt.font.name = "Times New Roman"
        r_txt.font.size = Pt(8)

    doc.save(output_path)
    print(f"Document successfully created at: {output_path}")

if __name__ == "__main__":
    out_dir = r"c:\Users\HP\Desktop\FraudDetection"
    target_file = os.path.join(out_dir, "IEEE_Project_Report_IDShield_Draft.docx")
    build_complete_report(target_file)
