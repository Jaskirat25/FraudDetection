"""
modules/passport - Indian Passport Screening & Verification Module.
"""

from modules.passport.types import (
    CheckStatus,
    RecommendedAction,
    CheckClass,
    FieldObject,
    Finding,
    MRZParseResult,
)
from modules.passport.rules import (
    PassportRulesRegistry,
    default_registry,
)
from modules.passport.mrz import (
    TD3MRZParser,
    calculate_icao_check_digit,
    is_valid_calendar_date,
)
from modules.passport.repair import (
    repair_mrz_field,
    FieldRepairResult,
    generate_candidate_strings,
    CONFUSION_MAP,
)
from modules.passport.viz import (
    VIZLogicValidator,
    VIZLogicResult,
    parse_viz_date,
)
from modules.passport.cross_val import (
    CrossValidator,
    CrossValidationResult,
    transliterate_viz_text,
)
from modules.passport.quality import (
    assess_passport_image_quality,
    QualityGateResult,
)
from modules.passport.privacy import (
    compute_keyed_hmac,
    PassportReuseIndex,
    ReuseCheckResult,
    default_reuse_index,
)
from modules.passport.fusion import (
    PassportDecision,
    PassportPriority,
    PassportScreeningReport,
    PassportDecisionEngine,
)
from modules.passport.register import (
    register_passport_page,
    rectify_passport_perspective,
    locate_mrz_strip_morphological,
    CANONICAL_PASSPORT_FIELDS,
    PASSPORT_CANONICAL_WIDTH,
    PASSPORT_CANONICAL_HEIGHT,
)
from modules.passport.ocr import (
    extract_mrz_text,
    extract_viz_fields,
)
from modules.passport.pipeline import (
    screen_passport,
)

__all__ = [
    "CheckStatus",
    "RecommendedAction",
    "CheckClass",
    "FieldObject",
    "Finding",
    "MRZParseResult",
    "PassportRulesRegistry",
    "default_registry",
    "TD3MRZParser",
    "calculate_icao_check_digit",
    "is_valid_calendar_date",
    "repair_mrz_field",
    "FieldRepairResult",
    "generate_candidate_strings",
    "CONFUSION_MAP",
    "VIZLogicValidator",
    "VIZLogicResult",
    "parse_viz_date",
    "CrossValidator",
    "CrossValidationResult",
    "transliterate_viz_text",
    "assess_passport_image_quality",
    "QualityGateResult",
    "compute_keyed_hmac",
    "PassportReuseIndex",
    "ReuseCheckResult",
    "default_reuse_index",
    "PassportDecision",
    "PassportPriority",
    "PassportScreeningReport",
    "PassportDecisionEngine",
    "register_passport_page",
    "rectify_passport_perspective",
    "locate_mrz_strip_morphological",
    "CANONICAL_PASSPORT_FIELDS",
    "PASSPORT_CANONICAL_WIDTH",
    "PASSPORT_CANONICAL_HEIGHT",
    "extract_mrz_text",
    "extract_viz_fields",
    "screen_passport",
]
