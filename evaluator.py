"""Evaluation harness for the DevOps Reasoning Agent."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from error_types import canonicalize_error_type, get_eval_aliases

TEST_CASES: list[dict[str, str]] = [
    {
        "name": "ENOENT file not found",
        "log_text": """
Run npm ci
npm ERR! code ENOENT
npm ERR! syscall open
npm ERR! path /home/runner/work/my-app/my-app/package-lock.json
npm ERR! errno -2
npm ERR! enoent Could not read package-lock.json
Error: Process completed with exit code 1.
""".strip(),
        "expected_error_type": "missing_file",
        "location_keywords": ["package-lock.json", "npm ci"],
    },
    {
        "name": "Unit test failure",
        "log_text": """
Run pytest tests/
tests/test_auth.py::test_login_invalid_password FAILED
E       AssertionError: Expected status 401, got 200
E       assert 200 == 401
=========================== short test summary info ============================
FAILED tests/test_auth.py::test_login_invalid_password - AssertionError
Error: Process completed with exit code 1.
""".strip(),
        "expected_error_type": "test_failure",
        "location_keywords": ["test_auth.py", "test_login_invalid_password"],
    },
    {
        "name": "Build compilation error",
        "log_text": """
Run npm run build
src/utils/parser.ts(42,17): error TS2345: Argument of type 'string' is not assignable to parameter of type 'number'.
src/utils/parser.ts(58,9): error TS2322: Type 'undefined' is not assignable to type 'User'.
Error: Process completed with exit code 2.
""".strip(),
        "expected_error_type": "compile_error",
        "location_keywords": ["parser.ts", "TS2345"],
    },
    {
        "name": "Job timeout",
        "log_text": """
Run integration-tests
Waiting for service container postgres to be ready...
Service container did not become healthy within 600 seconds.
##[error]The job was not acquired by a runner within 600 seconds and was cancelled.
Error: The operation was canceled.
""".strip(),
        "expected_error_type": "timeout",
        "location_keywords": ["600 seconds", "service container"],
    },
    {
        "name": "Permission denied",
        "log_text": """
Run ./scripts/deploy.sh
chmod: changing permissions of './scripts/deploy.sh': Operation not permitted
./scripts/deploy.sh: line 12: ./scripts/deploy.sh: Permission denied
Error: Process completed with exit code 126.
""".strip(),
        "expected_error_type": "permission_denied",
        "location_keywords": ["deploy.sh", "Permission denied"],
    },
    {
        "name": "Docker pull failure",
        "log_text": """
Run docker pull myregistry.azurecr.io/app:latest
Error response from daemon: manifest for myregistry.azurecr.io/app:latest not found: manifest unknown
Error: Process completed with exit code 1.
""".strip(),
        "expected_error_type": "docker_error",
        "location_keywords": ["docker pull", "manifest unknown"],
    },
    {
        "name": "Secret leak warning",
        "log_text": """
Run echo "Deploying with credentials"
##[warning]Secrets detected in log output. Avoid printing tokens in CI logs.
echo: ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
Error: Process completed with exit code 1.
""".strip(),
        "expected_error_type": "secrets_exposure",
        "location_keywords": ["Secrets detected", "log output"],
    },
    {
        "name": "Flaky test failure",
        "log_text": """
Run npm test
tests/e2e/checkout.test.js (attempt 1/3) FAILED
tests/e2e/checkout.test.js (attempt 2/3) FAILED
tests/e2e/checkout.test.js (attempt 3/3) FAILED
Error: Flaky test exceeded retry limit: checkout.test.js
Error: Process completed with exit code 1.
""".strip(),
        "expected_error_type": "flaky_test",
        "location_keywords": ["checkout.test.js", "retry"],
    },
    {
        "name": "Out of memory",
        "log_text": """
Run npm run build
FATAL ERROR: Reached heap limit Allocation failed - JavaScript heap out of memory
Aborted (core dumped)
Error: Process completed with exit code 134.
""".strip(),
        "expected_error_type": "out_of_memory",
        "location_keywords": ["heap out of memory", "npm run build"],
    },
    {
        "name": "Matrix job failure",
        "log_text": """
Run tests (node-version: 18, os: ubuntu-latest)
FAIL src/server.test.ts
Error: Expected server to start on port 3000 but connection was refused
Error: Process completed with exit code 1.
Run tests (node-version: 20, os: ubuntu-latest)
All tests passed.
Error: One or more matrix jobs failed.
""".strip(),
        "expected_error_type": "matrix_failure",
        "location_keywords": ["matrix", "server.test.ts"],
    },
    {
        "name": "Network connection refused",
        "log_text": """
Run npm test
Error: connect ECONNREFUSED 127.0.0.1:3000
Error: Process completed with exit code 1.
""".strip(),
        "expected_error_type": "network_error",
        "location_keywords": ["ECONNREFUSED", "127.0.0.1"],
    },
    {
        "name": "Authentication failure",
        "log_text": """
Run az login --service-principal
ERROR: AADSTS700016: Application with identifier was not found in the directory
Error: Process completed with exit code 1.
""".strip(),
        "expected_error_type": "authentication_error",
        "location_keywords": ["az login", "AADSTS"],
    },
    {
        "name": "Lint failure",
        "log_text": """
Run npm run lint
src/app.ts
  12:5  error  'user' is defined but never used  @typescript-eslint/no-unused-vars
Error: Process completed with exit code 1.
""".strip(),
        "expected_error_type": "lint_error",
        "location_keywords": ["eslint", "no-unused-vars"],
    },
    {
        "name": "Missing environment variable",
        "log_text": """
Run deploy
Error: Input required and not supplied: AZURE_CREDENTIALS
Error: Process completed with exit code 1.
""".strip(),
        "expected_error_type": "config_error",
        "location_keywords": ["AZURE_CREDENTIALS", "Input required"],
    },
    {
        "name": "Service container unhealthy",
        "log_text": """
Run docker run postgres
Waiting for postgres service container to be ready...
Service container postgres did not become healthy within 120 seconds.
Error: Process completed with exit code 1.
""".strip(),
        "expected_error_type": "service_container_error",
        "location_keywords": ["service container", "did not become healthy"],
    },
]

ACTIONABLE_FIX_KEYWORDS = [
    "run ",
    "npm ",
    "git ",
    "chmod ",
    "docker ",
    "yaml",
    "workflow",
    "install",
    "commit",
    "update",
    "change",
    "add ",
]


def _normalize_error_type(value: str) -> str:
    """Normalize error type strings for comparison."""
    return value.strip().lower().replace("-", "_").replace(" ", "_")


def _score_error_type(predicted: str, expected: str) -> bool:
    """Return True when predicted error type matches expected category."""
    predicted_canonical = canonicalize_error_type(predicted)
    expected_canonical = canonicalize_error_type(expected)
    if predicted_canonical == expected_canonical:
        return True

    predicted_norm = _normalize_error_type(predicted_canonical)
    expected_aliases = get_eval_aliases(expected_canonical)
    return any(alias in predicted_norm or predicted_norm in alias for alias in expected_aliases)


def _score_location(analysis: dict[str, Any], keywords: list[str]) -> bool:
    """Return True when analysis mentions expected keywords in location or root cause."""
    haystack = _normalize_error_type(
        " ".join(
            [
                str(analysis.get("location", "")),
                str(analysis.get("root_cause", "")),
                str(analysis.get("fix", "")),
            ]
        )
    )
    return any(_normalize_error_type(keyword) in haystack for keyword in keywords)


def _score_fix_quality(fix: str) -> bool:
    """Return True when the suggested fix looks actionable."""
    if not fix or len(fix.strip()) < 20:
        return False
    fix_lower = fix.lower()
    return any(keyword in fix_lower for keyword in ACTIONABLE_FIX_KEYWORDS)


def run_demo_evaluation(
    analyze_fn: Callable[[str], dict[str, Any]],
    *,
    export_path: str | Path | None = None,
) -> dict[str, Any]:
    """Run evaluation on the five built-in demo failure cases only."""

    def _analyze_without_verifier(log_text: str) -> dict[str, Any]:
        try:
            return analyze_fn(log_text, run_verifier=False)
        except TypeError:
            return analyze_fn(log_text)

    return run_evaluation(
        _analyze_without_verifier,
        cases=TEST_CASES[:5],
        export_path=export_path,
    )


def run_evaluation(
    analyze_fn: Callable[[str], dict[str, Any]],
    *,
    cases: list[dict[str, str]] | None = None,
    export_path: str | Path | None = "eval_report.json",
) -> dict[str, Any]:
    """Run evaluation test cases against an analysis function."""
    selected_cases = cases or TEST_CASES
    results: list[dict[str, Any]] = []
    error_type_passed = 0
    location_passed = 0
    fix_passed = 0
    overall_passed = 0

    for case in selected_cases:
        analysis = analyze_fn(case["log_text"])
        error_type_ok = _score_error_type(
            str(analysis.get("error_type", "")),
            case["expected_error_type"],
        )
        location_ok = _score_location(analysis, case.get("location_keywords", []))
        fix_ok = _score_fix_quality(str(analysis.get("fix", "")))
        overall_ok = error_type_ok and (location_ok or fix_ok)

        if error_type_ok:
            error_type_passed += 1
        if location_ok:
            location_passed += 1
        if fix_ok:
            fix_passed += 1
        if overall_ok:
            overall_passed += 1

        results.append(
            {
                "name": case["name"],
                "expected_error_type": case["expected_error_type"],
                "predicted_error_type": analysis.get("error_type", "unknown"),
                "passed": overall_ok,
                "error_type_passed": error_type_ok,
                "location_passed": location_ok,
                "fix_passed": fix_ok,
                "confidence_score": analysis.get("confidence_score", 0.0),
                "location": analysis.get("location", ""),
                "root_cause": analysis.get("root_cause", ""),
                "fix": analysis.get("fix", ""),
            }
        )

    total = len(selected_cases)
    accuracy = round((overall_passed / total) * 100, 2) if total else 0.0
    error_type_accuracy = round((error_type_passed / total) * 100, 2) if total else 0.0
    location_accuracy = round((location_passed / total) * 100, 2) if total else 0.0
    fix_accuracy = round((fix_passed / total) * 100, 2) if total else 0.0

    report = {
        "accuracy": accuracy,
        "error_type_accuracy": error_type_accuracy,
        "location_accuracy": location_accuracy,
        "fix_accuracy": fix_accuracy,
        "passed": overall_passed,
        "total": total,
        "results": results,
    }

    if export_path is not None:
        Path(export_path).write_text(json.dumps(report, indent=2), encoding="utf-8")

    return report
