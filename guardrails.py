"""Safety guardrails for secret redaction and write-action validation."""

from __future__ import annotations

import re

SECRET_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"ghp_[A-Za-z0-9]{20,}"), "ghp_[REDACTED]"),
    (re.compile(r"gho_[A-Za-z0-9]{20,}"), "gho_[REDACTED]"),
    (re.compile(r"github_pat_[A-Za-z0-9_]{20,}"), "github_pat_[REDACTED]"),
    (re.compile(r"AKIA[0-9A-Z]{16}"), "AKIA[REDACTED]"),
    (re.compile(r"(?i)bearer\s+[A-Za-z0-9\-._~+/]+=*"), "Bearer [REDACTED]"),
    (re.compile(r"(?i)(api[_-]?key\s*[:=]\s*)[^\s'\"]+"), r"\1[REDACTED]"),
    (re.compile(r"(?i)(password\s*[:=]\s*)[^\s'\"]+"), r"\1[REDACTED]"),
    (re.compile(r"(?i)(secret\s*[:=]\s*)[^\s'\"]+"), r"\1[REDACTED]"),
    (re.compile(r"-----BEGIN [A-Z ]+PRIVATE KEY-----[\s\S]*?-----END [A-Z ]+PRIVATE KEY-----"), "[REDACTED_PRIVATE_KEY]"),
]

UNSAFE_FIX_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"ghp_[A-Za-z0-9]{10,}"),
    re.compile(r"github_pat_"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"(?i)password\s*[:=]\s*[^\s\[REDACTED\]]"),
]


def redact_secrets(text: str) -> str:
    """Redact common secret patterns from text before LLM or GitHub calls."""
    redacted = text
    for pattern, replacement in SECRET_PATTERNS:
        redacted = pattern.sub(replacement, redacted)
    return redacted


def contains_unsafe_secrets(text: str) -> bool:
    """Return True if text still appears to contain raw secrets."""
    return any(pattern.search(text) for pattern in UNSAFE_FIX_PATTERNS)


def validate_write_action(content: str, user_approved: bool) -> tuple[bool, str]:
    """Validate whether a GitHub write action is allowed."""
    if not user_approved:
        return False, "You must approve the fix before creating an issue or pull request."
    if contains_unsafe_secrets(content):
        return False, "Suggested fix appears to contain secrets. Remove secrets before proceeding."
    return True, ""
