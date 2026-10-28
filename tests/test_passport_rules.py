import sys
from pathlib import Path
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from modules.passport.rules import PassportRulesRegistry
from modules.passport.types import CheckClass


def test_rules_registry_loads_successfully():
    registry = PassportRulesRegistry()
    assert len(registry.list_rule_ids()) >= 8
    assert "C-1-mrz-structure" in registry.list_rule_ids()
    assert "C-2-state-nationality" in registry.list_rule_ids()
    assert "D-1-passport-number-format" in registry.list_rule_ids()


def test_rule_schema_completeness():
    registry = PassportRulesRegistry()
    for rule_id in registry.list_rule_ids():
        rule = registry.get_rule(rule_id)
        assert rule is not None
        missing = PassportRulesRegistry.REQUIRED_RULE_FIELDS - set(rule.keys())
        assert not missing, f"Rule '{rule_id}' missing required fields: {missing}"
        assert isinstance(rule["version"], int)
        assert isinstance(rule["tests"], list)


def test_unverified_rule_promotion_gate():
    """
    Any rule where source or last_verified is None MUST be clamped to INFO severity,
    protecting against unverified rules driving fraud escalations.
    """
    registry = PassportRulesRegistry()
    
    # D-1 is explicitly marked source: null, last_verified: null
    assert not registry.is_verified("D-1-passport-number-format")
    effective_severity = registry.get_effective_severity("D-1-passport-number-format")
    assert effective_severity == CheckClass.INFO

    # C-6 is currently unverified for Indian blank personal numbers
    assert not registry.is_verified("C-6-personal-number-blank")
    assert registry.get_effective_severity("C-6-personal-number-blank") == CheckClass.INFO


def test_verified_rule_retains_severity():
    """
    Rules with verified official sources retain their T1 or T2 severity.
    """
    registry = PassportRulesRegistry()
    
    # C-1 is verified against ICAO Doc 9303 Part 4
    assert registry.is_verified("C-1-mrz-structure")
    assert registry.get_effective_severity("C-1-mrz-structure") == CheckClass.T1

    # C-2 is verified
    assert registry.is_verified("C-2-state-nationality")
    assert registry.get_effective_severity("C-2-state-nationality") == CheckClass.T1

    # C-8 is verified
    assert registry.is_verified("C-8-name-field-parse")
    assert registry.get_effective_severity("C-8-name-field-parse") == CheckClass.T2
