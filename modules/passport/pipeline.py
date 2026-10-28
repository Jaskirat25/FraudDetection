"""
modules/passport/pipeline.py - Unified End-to-End Indian Passport Screening Pipeline.
Chains: Quality Gate -> Registration -> OCR -> MRZ Parsing -> C-11 Repair ->
        VIZ Logic -> Cross-Validation -> Privacy Index -> Decision Fusion.
"""

from typing import Union, Optional, Tuple, Dict, Any
from datetime import date
import numpy as np
import cv2

from modules.passport.quality import assess_passport_image_quality
from modules.passport.register import register_passport_page
from modules.passport.ocr import extract_mrz_text, extract_viz_fields
from modules.passport.mrz import TD3MRZParser
from modules.passport.repair import repair_mrz_field
from modules.passport.viz import VIZLogicValidator
from modules.passport.cross_val import CrossValidator
from modules.passport.privacy import default_reuse_index, PassportReuseIndex
from modules.passport.fusion import (
    PassportDecisionEngine,
    PassportScreeningReport,
    PassportDecision,
)
from modules.passport.rules import default_registry, PassportRulesRegistry


def screen_passport(
    image_or_path: Union[str, np.ndarray],
    reference_date: Optional[date] = None,
    reuse_index: Optional[PassportReuseIndex] = None,
    rules_registry: Optional[PassportRulesRegistry] = None,
    provided_mrz: Optional[Tuple[str, str]] = None,
    provided_viz: Optional[Dict[str, str]] = None,
    return_artifacts: bool = False,
) -> Union[PassportScreeningReport, Tuple[PassportScreeningReport, Dict[str, Any]]]:
    """
    Executes the complete, multi-stage Indian Passport Screening Pipeline.
    Returns: PassportScreeningReport conforming to Section 6.4 schema,
             or (PassportScreeningReport, artifacts_dict) if return_artifacts=True.
    """
    ref_date = reference_date or date.today()
    registry = rules_registry or default_registry
    history_index = reuse_index or default_reuse_index
    decision_engine = PassportDecisionEngine(registry=registry)

    # 1. Load image input
    if isinstance(image_or_path, str):
        image = cv2.imread(image_or_path)
        if image is None:
            raise FileNotFoundError(f"Could not load image from path: {image_or_path}")
    elif isinstance(image_or_path, np.ndarray):
        image = image_or_path
    else:
        raise ValueError("Input must be a valid file path string or numpy image array.")

    # =========================================================================
    # Stage 1: Quality Gate & Capture Pre-Screening (Checks A-1, A-2)
    # =========================================================================
    quality_res = assess_passport_image_quality(image)
    if not quality_res.passed:
        # Fail fast directly to RECAPTURE_REQUIRED
        rep = decision_engine.fuse(quality_res=quality_res)
        if return_artifacts:
            return rep, {"quality_res": quality_res, "crops": {}, "rectified_image": None}
        return rep

    # =========================================================================
    # Stage 2: Geometric Registration & Perspective Rectification
    # =========================================================================
    rectified_img, crops, reg_quality = register_passport_page(image)

    # =========================================================================
    # Stage 3: OCR Extraction (MRZ + VIZ)
    # =========================================================================
    if provided_mrz:
        line1, line2 = provided_mrz
        ocr_conf = 1.0
    else:
        mrz_crop = crops.get("mrz")
        line1, line2, ocr_conf = extract_mrz_text(mrz_crop.image) if mrz_crop else ("", "", 0.0)

    if provided_viz:
        viz_data = provided_viz
    else:
        viz_extracted = extract_viz_fields(crops)
        viz_data = {k: v[0] for k, v in viz_extracted.items()}

    # Extract 4-digit VIZ year hints for century resolution
    viz_dob_year = None
    if viz_data.get("dob") and len(viz_data["dob"]) >= 10:
        try:
            viz_dob_year = int(viz_data["dob"][-4:])
        except ValueError:
            pass

    viz_exp_year = None
    if viz_data.get("doe") and len(viz_data["doe"]) >= 10:
        try:
            viz_exp_year = int(viz_data["doe"][-4:])
        except ValueError:
            pass

    # =========================================================================
    # Stage 4: MRZ Parsing & Checksum Verification (Checks C-1..C-10)
    # =========================================================================
    mrz_parser = TD3MRZParser(registry=registry)
    mrz_res = mrz_parser.parse(
        line1=line1,
        line2=line2,
        viz_dob_year=viz_dob_year,
        viz_expiry_year=viz_exp_year,
        reference_date=ref_date,
    )

    # =========================================================================
    # Stage 5: Conditional C-11 Safe MRZ Repair (if check digit failed & VIZ corroborates)
    # =========================================================================
    repair_findings = []
    if mrz_res.valid_structure and len(line2) == 44:
        # Check passport number repair
        if not mrz_res.check_digits.get("passport_no", True):
            p_rep = repair_mrz_field(
                field_name="passport_no",
                raw_field_text=line2[0:9],
                expected_check_digit=line2[9],
                viz_value=viz_data.get("passport_no"),
                line2_context=line2,
                field_slice=(0, 9),
            )
            if p_rep.repaired:
                line2 = p_rep.repaired_text + line2[9:]
                if p_rep.finding:
                    repair_findings.append(p_rep.finding)

        # Check DOB repair
        if not mrz_res.check_digits.get("dob", True):
            dob_rep = repair_mrz_field(
                field_name="dob",
                raw_field_text=line2[13:19],
                expected_check_digit=line2[19],
                viz_value=viz_data.get("dob"),
                line2_context=line2,
                field_slice=(13, 19),
            )
            if dob_rep.repaired:
                line2 = line2[:13] + dob_rep.repaired_text + line2[19:]
                if dob_rep.finding:
                    repair_findings.append(dob_rep.finding)

        # Check Expiry repair
        if not mrz_res.check_digits.get("expiry", True):
            exp_rep = repair_mrz_field(
                field_name="expiry",
                raw_field_text=line2[21:27],
                expected_check_digit=line2[27],
                viz_value=viz_data.get("doe"),
                line2_context=line2,
                field_slice=(21, 27),
            )
            if exp_rep.repaired:
                line2 = line2[:21] + exp_rep.repaired_text + line2[27:]
                if exp_rep.finding:
                    repair_findings.append(exp_rep.finding)

        # If any field was repaired, re-parse with repaired MRZ
        if repair_findings:
            mrz_res = mrz_parser.parse(
                line1=line1,
                line2=line2,
                viz_dob_year=viz_dob_year,
                viz_expiry_year=viz_exp_year,
                reference_date=ref_date,
            )
            mrz_res.findings.extend(repair_findings)

    # =========================================================================
    # Stage 6: VIZ Document-Logic Rules (Checks D-2..D-7, D-10)
    # =========================================================================
    viz_validator = VIZLogicValidator(registry=registry)
    viz_res = viz_validator.validate(viz_data, reference_date=ref_date)

    # =========================================================================
    # Stage 7: VIZ <-> MRZ Cross-Validation (Checks E-1..E-7)
    # =========================================================================
    cross_validator = CrossValidator(registry=registry)
    xval_res = cross_validator.cross_validate(viz_res, mrz_res)

    # =========================================================================
    # Stage 8: Privacy-Preserving History & Reuse Index (Check I-6)
    # =========================================================================
    candidate_pass_no = mrz_res.passport_number or viz_data.get("passport_no", "")
    full_holder_name = f"{mrz_res.given_names} {mrz_res.surname}".strip()
    dob_holder = mrz_res.dob or viz_data.get("dob", "")

    reuse_res = history_index.check_and_record(
        passport_no=candidate_pass_no,
        full_name=full_holder_name,
        dob=dob_holder,
    )

    # =========================================================================
    # Stage 9: Multi-Group Decision Fusion & Explainable Verdict
    # =========================================================================
    report = decision_engine.fuse(
        quality_res=quality_res,
        mrz_res=mrz_res,
        viz_res=viz_res,
        xval_res=xval_res,
        reuse_res=reuse_res,
    )

    if return_artifacts:
        artifacts = {
            "quality_res": quality_res,
            "rectified_image": rectified_img,
            "crops": crops,
            "mrz_res": mrz_res,
            "viz_res": viz_res,
            "xval_res": xval_res,
            "reuse_res": reuse_res,
            "raw_mrz": (line1, line2),
            "viz_data": viz_data,
        }
        return report, artifacts

    return report
