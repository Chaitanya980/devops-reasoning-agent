"""Unit and integration tests for the DevOps Reasoning Agent core logic.

These tests are network-free and secret-free: they exercise the pure helpers
and the deterministic offline analyzer, so they can run in CI without Azure.
"""

from __future__ import annotations

import json

import pytest

from agent import _extract_json, _normalize_result
from error_types import canonicalize_error_type, get_error_label
from evaluator import run_evaluation
from guardrails import contains_unsafe_secrets, redact_secrets, validate_write_action
from log_parser import (
    extract_exit_code,
    extract_failing_step,
    extract_github_errors,
    strip_ansi,
)
from offline_analyzer import heuristic_analysis, offline_analysis


# --- error_types -----------------------------------------------------------

@pytest.mark.parametrize(
    "raw,expected",
    [
        ("ENOENT", "missing_file"),
        ("enoent", "missing_file"),
        ("build_error", "compile_error"),
        ("Connection refused", "network_error"),
        ("manifest unknown", "docker_error"),
        ("totally_unrecognized_value", "unknown"),
    ],
)
def test_canonicalize_error_type(raw, expected):
    assert canonicalize_error_type(raw) == expected


def test_get_error_label_known_and_unknown():
    assert get_error_label("missing_file") == "Missing File"
    assert get_error_label("unknown") == "Unknown"


# --- log_parser ------------------------------------------------------------

def test_strip_ansi_removes_color_codes():
    assert strip_ansi("\x1b[31mred\x1b[0m text") == "red text"


def test_extract_exit_code_returns_last():
    log = "Process completed with exit code 1.\nProcess completed with exit code 2."
    assert extract_exit_code(log) == 2


def test_extract_exit_code_none_when_missing():
    assert extract_exit_code("no exit code here") is None


def test_extract_github_errors():
    log = "##[error]Something broke\nnormal line\n##[error]And again"
    assert extract_github_errors(log) == ["Something broke", "And again"]


def test_extract_failing_step():
    log = "Run setup\nsome output\nRun npm ci\nnpm ERR! boom"
    assert "npm ci" in extract_failing_step(log)


# --- guardrails ------------------------------------------------------------

def test_redact_secrets_masks_github_token():
    redacted = redact_secrets("token=ghp_" + "a" * 36)
    assert "ghp_" + "a" * 36 not in redacted
    assert "[REDACTED]" in redacted


def test_contains_unsafe_secrets():
    assert contains_unsafe_secrets("ghp_" + "a" * 36) is True
    assert contains_unsafe_secrets("a perfectly safe fix") is False


def test_validate_write_action_requires_approval():
    allowed, msg = validate_write_action("safe content", user_approved=False)
    assert allowed is False and msg

    allowed, _ = validate_write_action("safe content", user_approved=True)
    assert allowed is True


def test_validate_write_action_blocks_secrets():
    allowed, msg = validate_write_action("ghp_" + "b" * 36, user_approved=True)
    assert allowed is False and "secret" in msg.lower()


# --- agent JSON parsing ----------------------------------------------------

def test_extract_json_plain():
    payload = {"error_type": "missing_file", "confidence_score": 0.9}
    assert _extract_json(json.dumps(payload))["error_type"] == "missing_file"


def test_extract_json_fenced():
    text = "Here you go:\n```json\n{\"error_type\": \"timeout\"}\n```"
    assert _extract_json(text)["error_type"] == "timeout"


def test_extract_json_fallback_on_unescaped_newlines():
    # Malformed: literal newline inside a string value (invalid strict JSON).
    text = (
        '{"error_type": "test_failure", "error_subtype": "x", "summary": "s", '
        '"location": "tests/a.py", "root_cause": "line one\nline two", '
        '"fix": "do the thing", "confidence_score": 0.8}'
    )
    parsed = _extract_json(text)
    assert parsed["error_type"] == "test_failure"


def test_normalize_result_clamps_confidence_and_fills_defaults():
    normalized = _normalize_result({"error_type": "ENOENT", "confidence_score": 5})
    assert normalized["error_type"] == "missing_file"
    assert normalized["confidence_score"] == 1.0
    assert normalized["error_label"] == "Missing File"


# --- offline analyzer ------------------------------------------------------

def test_offline_analysis_curated_match():
    log = "npm ERR! enoent Could not read package-lock.json"
    result = offline_analysis(log)
    assert result["error_type"] == "missing_file"
    assert result["confidence_score"] > 0.5


def test_heuristic_analysis_handles_unknown():
    result = heuristic_analysis("something totally undiagnosable happened")
    assert result["error_type"] == "unknown"
    assert result["fix"]


# --- evaluator integration (dogfooding) ------------------------------------

def test_offline_analyzer_passes_full_evaluation():
    report = run_evaluation(lambda log: offline_analysis(log), export_path=None)
    # The deterministic analyzer must perfectly classify every taxonomy case.
    assert report["error_type_accuracy"] == 100.0
    assert report["accuracy"] >= 90.0
