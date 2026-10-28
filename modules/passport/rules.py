"""
modules/passport/rules.py - Versioned Passport Rules Registry Loader with Promotion Gate.
Implements Section 7 of passport_module_plan_v2.md.
"""

from pathlib import Path
from typing import Dict, Any, Optional, List
import yaml

from modules.passport.types import CheckClass

DEFAULT_RULES_PATH = Path(__file__).resolve().parent.parent.parent / "rules" / "passport_rules.yaml"


class PassportRulesRegistry:
    """
    Loads and provides structured access to the versioned passport rules registry.
    Enforces the Promotion Gate: any unverified rule (source=None or last_verified=None)
    cannot contribute at T1 or T2 severity, automatically clamped to INFO.
    """

    REQUIRED_RULE_FIELDS = {
        "id",
        "description",
        "source",
        "last_verified",
        "supported_editions",
        "severity",
        "tests",
        "owner",
        "version",
    }

    def __init__(self, rules_path: Optional[Path] = None):
        self.rules_path = Path(rules_path) if rules_path else DEFAULT_RULES_PATH
        self.ruleset_version: str = "unknown"
        self.updated_at: str = "unknown"
        self._rules_by_id: Dict[str, Dict[str, Any]] = {}
        self.load_rules()

    def load_rules(self) -> None:
        """Loads and validates the YAML rules registry from disk."""
        if not self.rules_path.exists():
            raise FileNotFoundError(f"Passport rules file not found: {self.rules_path}")

        with open(self.rules_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        if not isinstance(data, dict):
            raise ValueError("Rules file root must be a YAML mapping.")

        self.ruleset_version = data.get("ruleset_version", "unknown")
        self.updated_at = data.get("updated_at", "unknown")

        rules_list = data.get("rules", [])
        if not isinstance(rules_list, list):
            raise ValueError("'rules' key must contain a list of rule definitions.")

        self._rules_by_id.clear()
        for idx, rule in enumerate(rules_list):
            if not isinstance(rule, dict):
                raise ValueError(f"Rule at index {idx} is not a valid dictionary.")

            missing = self.REQUIRED_RULE_FIELDS - set(rule.keys())
            if missing:
                raise ValueError(f"Rule '{rule.get('id', f'index_{idx}')}' missing required fields: {missing}")

            rule_id = rule["id"]
            if rule_id in self._rules_by_id:
                raise ValueError(f"Duplicate rule id '{rule_id}' found in {self.rules_path}")

            self._rules_by_id[rule_id] = rule

    def get_rule(self, rule_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves raw rule dictionary by rule ID."""
        return self._rules_by_id.get(rule_id)

    def is_verified(self, rule_id: str) -> bool:
        """
        A rule is verified if and only if both 'source' and 'last_verified'
        are non-empty strings (not None or empty).
        """
        rule = self.get_rule(rule_id)
        if not rule:
            return False

        source = rule.get("source")
        last_verified = rule.get("last_verified")
        return bool(source and str(source).strip() and last_verified and str(last_verified).strip())

    def get_effective_severity(self, rule_id: str) -> CheckClass:
        """
        Returns the effective CheckClass severity for a rule.
        Enforces Promotion Gate: unverified rules are clamped to INFO.
        """
        rule = self.get_rule(rule_id)
        if not rule:
            return CheckClass.INFO

        raw_severity_str = str(rule.get("severity", "INFO")).upper()
        try:
            declared_severity = CheckClass(raw_severity_str)
        except ValueError:
            declared_severity = CheckClass.INFO

        if not self.is_verified(rule_id):
            # Clamped by promotion gate
            return CheckClass.INFO

        return declared_severity

    def list_rule_ids(self) -> List[str]:
        """Returns all loaded rule IDs."""
        return list(self._rules_by_id.keys())


# Singleton instance for application-wide use
default_registry = PassportRulesRegistry()
