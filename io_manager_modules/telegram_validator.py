"""Validation, normalization, and credential utilities for Telegram I/O."""
import hashlib
import secrets
from typing import Any, Dict, List, Optional, Tuple

PRIORITY_WEIGHTS: Dict[str, int] = {
    "must": 4,
    "important": 3,
    "nice": 2,
    "can consider": 1,
    "reject": 0,
}


class TelegramValidator:
    """Encapsulates validation, normalization, and auth formatting rules."""

    MIN_RULE_LENGTH = 5
    MAX_RULE_LENGTH = 300
    MIN_SET_NAME_LENGTH = 2
    MAX_SET_NAME_LENGTH = 60
    MIN_COMPANY_NAME_LENGTH = 2
    MIN_PASSCODE_LENGTH = 4
    PRIORITY_WEIGHTS: Dict[str, int] = dict(PRIORITY_WEIGHTS)

    @classmethod
    def validate_and_normalize_rule(cls, text: str, priority: str) -> Dict[str, Any]:
        """Validates rule text length, priority key, and assigns canonical numeric weight."""
        clean_text = (text or "").strip()
        if len(clean_text) < cls.MIN_RULE_LENGTH or len(clean_text) > cls.MAX_RULE_LENGTH:
            raise ValueError(
                f"Rule text must be {cls.MIN_RULE_LENGTH}-{cls.MAX_RULE_LENGTH} characters."
            )

        clean_prio = (priority or "").strip().lower()
        if clean_prio not in cls.PRIORITY_WEIGHTS:
            valid_list = ", ".join(cls.PRIORITY_WEIGHTS.keys())
            raise ValueError(f"Invalid rule priority '{priority}'. Must be one of: {valid_list}.")

        return {
            "text": clean_text,
            "priority": clean_prio,
            "weight": cls.PRIORITY_WEIGHTS[clean_prio],
        }

    @classmethod
    def normalize_rules_list(
        cls,
        rules: Optional[List[Dict[str, Any]]],
        strict: bool = False,
    ) -> List[Dict[str, Any]]:
        """Normalizes (and optionally strictly validates) rules with verified priority & weight."""
        normalized: List[Dict[str, Any]] = []
        for rule in rules or []:
            if not isinstance(rule, dict):
                if strict:
                    raise ValueError("Each rule must be a dictionary with 'text' and 'priority'.")
                continue
            text = str(rule.get("text", "")).strip()
            prio = str(rule.get("priority", "reject")).strip().lower()
            if strict:
                normalized.append(cls.validate_and_normalize_rule(text, prio))
            else:
                if prio not in cls.PRIORITY_WEIGHTS:
                    prio = "reject"
                if not text:
                    continue
                normalized.append(
                    {
                        "text": text,
                        "priority": prio,
                        "weight": cls.PRIORITY_WEIGHTS[prio],
                    }
                )
        return normalized

    @classmethod
    def validate_set_name(cls, set_name: str) -> str:
        """Validates a business rule set name and returns the trimmed string."""
        clean_name = (set_name or "").strip()
        if len(clean_name) < cls.MIN_SET_NAME_LENGTH or len(clean_name) > cls.MAX_SET_NAME_LENGTH:
            raise ValueError(
                f"Rule Set name must be {cls.MIN_SET_NAME_LENGTH}-{cls.MAX_SET_NAME_LENGTH} characters."
            )
        return clean_name

    @classmethod
    def validate_company_name(cls, name: str) -> str:
        """Validates a company folder name and returns the trimmed string."""
        clean_name = (name or "").strip()
        if len(clean_name) < cls.MIN_COMPANY_NAME_LENGTH:
            raise ValueError(
                f"Company name must be at least {cls.MIN_COMPANY_NAME_LENGTH} characters."
            )
        return clean_name

    @classmethod
    def validate_passcode(cls, passcode: str) -> str:
        """Validates a company passcode and returns the trimmed string."""
        clean_pass = (passcode or "").strip()
        if len(clean_pass) < cls.MIN_PASSCODE_LENGTH:
            raise ValueError(
                f"Passcode must be at least {cls.MIN_PASSCODE_LENGTH} characters."
            )
        return clean_pass

    @staticmethod
    def hash_passcode(passcode: str) -> str:
        """Returns the SHA-256 hex digest of a passcode."""
        return hashlib.sha256(passcode.encode("utf-8")).hexdigest()

    @classmethod
    def verify_passcode(cls, passcode: str, target_hash: Optional[str]) -> bool:
        """Checks whether a plaintext passcode matches its stored SHA-256 hash."""
        if not target_hash:
            return False
        return cls.hash_passcode((passcode or "").strip()) == target_hash

    @staticmethod
    def generate_invite_code(company_name: str) -> str:
        """Builds a team invite code from the company prefix and a random 4-digit suffix."""
        prefix = "".join(c for c in company_name.upper() if c.isalnum())[:4] or "COMP"
        return f"{prefix}-{secrets.randbelow(9000) + 1000}"

    @staticmethod
    def cap_top_n(requested_n: int, resume_count: int) -> Tuple[int, bool]:
        """Caps top_n to resume_count when resumes exist (>= 1). Returns (effective_n, was_capped)."""
        val = max(1, min(int(requested_n), 100))
        if resume_count > 0 and val > resume_count:
            return resume_count, True
        return val, False

