"""
modules/passport/repair.py - Evidence-Preserving MRZ Repair Engine (Check C-11).
Implements Section 5.3 of passport_module_plan_v2.md:
Conservative repair of OCR confusion characters gated by checksums AND mandatory VIZ corroboration.
"""

import re
from dataclasses import dataclass, field as dc_field
from typing import Optional, Dict, List, Tuple, Any
from itertools import combinations

from modules.passport.mrz import calculate_icao_check_digit
from modules.passport.types import CheckStatus, Finding, CheckClass

# Strict OCR confusion pairs
CONFUSION_MAP = {
    "O": ["0"],
    "0": ["O"],
    "I": ["1"],
    "1": ["I"],
    "S": ["5"],
    "5": ["S"],
    "B": ["8"],
    "8": ["B"],
    "Z": ["2"],
    "2": ["Z"],
    "<": ["K", "C"],
    "K": ["<"],
    "C": ["<"],
}


@dataclass
class RepairCandidate:
    candidate_text: str
    edits: List[Tuple[int, str, str]]  # list of (index, original_char, replacement_char)
    field_check_valid: bool = False
    viz_matches: bool = False
    score: float = 0.0


@dataclass
class FieldRepairResult:
    repaired: bool = False
    original_text: str = ""
    repaired_text: str = ""
    applied_edits: List[Tuple[int, str, str]] = dc_field(default_factory=list)
    viz_corroborated: bool = False
    candidates_evaluated: int = 0
    pre_repair_checksum_valid: bool = False
    post_repair_checksum_valid: bool = False
    evidence: Dict[str, Any] = dc_field(default_factory=dict)
    finding: Optional[Finding] = None


def generate_candidate_strings(
    raw_text: str,
    target_indices: Optional[List[int]] = None,
    max_edits: int = 2,
) -> List[Tuple[str, List[Tuple[int, str, str]]]]:
    """
    Generates string variations by applying up to `max_edits` substitutions
    from the CONFUSION_MAP at target_indices.
    """
    candidates = []
    # If no target indices specified, consider all characters that have confusion alternatives
    if target_indices is None:
        target_indices = [i for i, ch in enumerate(raw_text) if ch in CONFUSION_MAP]
    else:
        target_indices = [i for i in target_indices if i < len(raw_text) and raw_text[i] in CONFUSION_MAP]

    if not target_indices:
        return candidates

    # 1 edit candidates
    for idx in target_indices:
        orig_char = raw_text[idx]
        for repl in CONFUSION_MAP.get(orig_char, []):
            cand_str = raw_text[:idx] + repl + raw_text[idx + 1:]
            candidates.append((cand_str, [(idx, orig_char, repl)]))

    # 2 edits candidates
    if max_edits >= 2 and len(target_indices) >= 2:
        for idx1, idx2 in combinations(target_indices, 2):
            char1 = raw_text[idx1]
            char2 = raw_text[idx2]
            for repl1 in CONFUSION_MAP.get(char1, []):
                for repl2 in CONFUSION_MAP.get(char2, []):
                    cand_chars = list(raw_text)
                    cand_chars[idx1] = repl1
                    cand_chars[idx2] = repl2
                    cand_str = "".join(cand_chars)
                    candidates.append((cand_str, [(idx1, char1, repl1), (idx2, char2, repl2)]))

    return candidates


def normalize_viz_for_field(field_name: str, viz_value: str) -> str:
    """
    Normalizes VIZ value to match expected MRZ format for cross-checking.
    For dates (DD/MM/YYYY), converts to YYMMDD.
    """
    cleaned = viz_value.strip().replace(" ", "").replace("<", "").upper()
    if field_name.lower() in ("dob", "expiry", "doe", "doi"):
        m = re.match(r"^(\d{2})[/-](\d{2})[/-](\d{4})$", cleaned)
        if m:
            dd = m.group(1)
            mm = m.group(2)
            yy = m.group(3)[2:4]
            return f"{yy}{mm}{dd}"
    return cleaned.replace("/", "").replace("-", "")


def repair_mrz_field(
    field_name: str,
    raw_field_text: str,
    expected_check_digit: str,
    viz_value: Optional[str] = None,
    line2_context: Optional[str] = None,
    field_slice: Optional[Tuple[int, int]] = None,
    max_edits: int = 2,
) -> FieldRepairResult:
    """
    Safely attempts to repair a corrupted MRZ field using OCR confusion candidates.
    Auto-accepts ONLY if:
    1. Check digit passes on the candidate.
    2. VIZ corroboration matches (mandatory).
    3. If full Line 2 context is provided, composite check digit also passes.
    """
    # 1. Pre-repair status snapshot
    try:
        initial_cd_int = calculate_icao_check_digit(raw_field_text)
        pre_checksum_valid = (str(initial_cd_int) == expected_check_digit)
    except Exception:
        pre_checksum_valid = False

    result = FieldRepairResult(
        repaired=False,
        original_text=raw_field_text,
        repaired_text=raw_field_text,
        pre_repair_checksum_valid=pre_checksum_valid,
        post_repair_checksum_valid=pre_checksum_valid,
    )

    norm_viz = normalize_viz_for_field(field_name, viz_value) if viz_value else None

    # If checksum already valid and matches VIZ (or no VIZ contradiction), no repair needed
    if pre_checksum_valid:
        if norm_viz is None or raw_field_text.replace("<", "").upper() == norm_viz:
            return result

    # 2. Candidate generation
    raw_candidates = generate_candidate_strings(raw_field_text, max_edits=max_edits)
    result.candidates_evaluated = len(raw_candidates)

    passing_candidates: List[RepairCandidate] = []

    for cand_str, edits in raw_candidates:
        # Check digit test
        try:
            cand_cd = str(calculate_icao_check_digit(cand_str))
            cd_valid = (cand_cd == expected_check_digit)
        except Exception:
            cd_valid = False

        if not cd_valid:
            continue

        # If line2 context provided, also check master composite check digit
        if line2_context and field_slice and len(line2_context) == 44:
            s_start, s_end = field_slice
            cand_line2 = line2_context[:s_start] + cand_str + line2_context[s_end:]
            composite_data = cand_line2[0:10] + cand_line2[13:20] + cand_line2[21:43]
            try:
                comp_cd = str(calculate_icao_check_digit(composite_data))
                if comp_cd != cand_line2[43]:
                    continue  # Composite failed, reject candidate
            except Exception:
                continue

        # VIZ corroboration test (MANDATORY per Section 5.3)
        viz_matched = False
        if norm_viz:
            norm_cand = cand_str.replace("<", "").upper()
            if norm_cand == norm_viz:
                viz_matched = True

        candidate = RepairCandidate(
            candidate_text=cand_str,
            edits=edits,
            field_check_valid=cd_valid,
            viz_matches=viz_matched,
            score=1.0 if viz_matched else 0.5,
        )

        passing_candidates.append(candidate)

    # 3. Decision Gate
    # Only accept if at least one candidate passes checksum AND matches VIZ
    corroborated_candidates = [c for c in passing_candidates if c.viz_matches]

    result.evidence = {
        "pre_text": raw_field_text,
        "pre_checksum_valid": pre_checksum_valid,
        "candidates_evaluated": len(raw_candidates),
        "passing_checksum_count": len(passing_candidates),
        "viz_corroborated_count": len(corroborated_candidates),
        "viz_value_provided": viz_value,
    }

    if corroborated_candidates:
        best = corroborated_candidates[0]
        result.repaired = True
        result.repaired_text = best.candidate_text
        result.applied_edits = best.edits
        result.viz_corroborated = True
        result.post_repair_checksum_valid = True
        result.evidence["applied_edits"] = best.edits
        result.evidence["post_text"] = best.candidate_text

        result.finding = Finding(
            code="PP-MRZ-011",
            check_id="C-11",
            status=CheckStatus.PASS,
            check_class=CheckClass.INFO,
            field=field_name,
            message=f"MRZ field '{field_name}' successfully repaired with VIZ corroboration: '{raw_field_text}' -> '{best.candidate_text}'.",
            evidence=result.evidence,
        )
    else:
        # Checksum might have passed for some candidate, but VIZ corroboration failed or was absent
        result.repaired = False
        result.repaired_text = raw_field_text
        result.viz_corroborated = False
        result.finding = Finding(
            code="PP-MRZ-011",
            check_id="C-11",
            status=CheckStatus.UNKNOWN,
            check_class=CheckClass.INFO,
            field=field_name,
            message=f"MRZ field '{field_name}' could not be repaired safely (VIZ corroboration unverified).",
            evidence=result.evidence,
        )

    return result
