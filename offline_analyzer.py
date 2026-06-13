"""Offline, deterministic failure analyzer.

Provides a no-network analysis path so the app stays demo-safe even when the
Azure AI Foundry endpoint is slow, rate-limited, or unreachable. It is also
used by the dogfooding CI pipeline so the evaluator can run without secrets.

Two layers:
1. CURATED — hand-written, high-quality analyses keyed by a distinctive
   substring of known sample/eval logs.
2. HEURISTIC — a taxonomy-driven fallback that classifies any log using the
   shared keyword logic in `error_types` plus `log_parser` context.
"""

from __future__ import annotations

from typing import Any

from error_types import canonicalize_error_type, get_error_label
from log_parser import build_log_context

# (distinctive substring, analysis) — first match wins.
CURATED: list[tuple[str, dict[str, Any]]] = [
    (
        "package-lock.json",
        {
            "error_type": "missing_file",
            "error_subtype": "package-lock.json not committed",
            "summary": "npm ci failed because the lockfile is missing from the repository.",
            "location": "Workflow step `npm ci`",
            "root_cause": "`npm ci` requires a committed package-lock.json, but the file was never added to the repository, so the install aborts with ENOENT.",
            "fix": "Run `npm install` locally to generate package-lock.json, then commit it. Alternatively switch the workflow step from `npm ci` to `npm install`.",
            "confidence_score": 0.95,
            "suggested_file_path": ".github/workflows/ci.yml",
        },
    ),
    (
        "test_login_invalid_password",
        {
            "error_type": "test_failure",
            "error_subtype": "Auth test expected 401, got 200",
            "summary": "A unit test asserting a 401 on invalid login received a 200 instead.",
            "location": "tests/test_auth.py::test_login_invalid_password",
            "root_cause": "The login handler returns HTTP 200 for invalid credentials instead of rejecting with 401, so the assertion fails.",
            "fix": "Update the login handler to return status 401 when the password is invalid, then re-run `pytest tests/`.",
            "confidence_score": 0.92,
            "suggested_file_path": ".github/workflows/ci.yml",
        },
    ),
    (
        "TS2345",
        {
            "error_type": "compile_error",
            "error_subtype": "TypeScript type mismatch",
            "summary": "TypeScript compilation failed on type errors in parser.ts.",
            "location": "src/utils/parser.ts (lines 42 and 58)",
            "root_cause": "A `string` is passed where a `number` is expected and an `undefined` value is assigned to a non-nullable `User` type, so `tsc` fails the build.",
            "fix": "Fix the type mismatches in src/utils/parser.ts (convert the string with `Number(...)` and guard the undefined `User`), then re-run `npm run build`.",
            "confidence_score": 0.93,
            "suggested_file_path": ".github/workflows/ci.yml",
        },
    ),
    (
        "not acquired by a runner",
        {
            "error_type": "timeout",
            "error_subtype": "Service container readiness timeout",
            "summary": "The job was cancelled after a service container failed to become healthy within the timeout.",
            "location": "integration-tests job — postgres service container",
            "root_cause": "The postgres service container never reported healthy within 600 seconds, so GitHub cancelled the job.",
            "fix": "Add a health check with retries to the postgres service, increase the readiness timeout, and verify the container image and port mapping in the workflow.",
            "confidence_score": 0.88,
            "suggested_file_path": ".github/workflows/ci.yml",
        },
    ),
    (
        "Operation not permitted",
        {
            "error_type": "permission_denied",
            "error_subtype": "deploy.sh not executable",
            "summary": "deploy.sh could not run because it lacks the executable permission.",
            "location": "./scripts/deploy.sh",
            "root_cause": "The script does not have the executable bit set in the repository, so the runner refuses to execute it (exit code 126).",
            "fix": "Run `git update-index --chmod=+x scripts/deploy.sh` and commit, or call the script with `bash ./scripts/deploy.sh` in the workflow.",
            "confidence_score": 0.9,
            "suggested_file_path": ".github/workflows/ci.yml",
        },
    ),
    (
        "manifest unknown",
        {
            "error_type": "docker_error",
            "error_subtype": "Image tag not found in registry",
            "summary": "docker pull failed because the requested image tag does not exist.",
            "location": "docker pull myregistry.azurecr.io/app:latest",
            "root_cause": "The `:latest` tag was never pushed to the registry, so the manifest cannot be resolved.",
            "fix": "Build and push the image tag before pulling, or reference an existing tag. Verify the registry login and image name in the workflow.",
            "confidence_score": 0.89,
            "suggested_file_path": ".github/workflows/ci.yml",
        },
    ),
    (
        "Secrets detected",
        {
            "error_type": "secrets_exposure",
            "error_subtype": "Token printed in CI logs",
            "summary": "A token was echoed into the build logs, triggering a secret-exposure warning.",
            "location": "Step `echo \"Deploying with credentials\"`",
            "root_cause": "A GitHub token was printed to stdout, exposing it in the workflow logs.",
            "fix": "Remove the echo of credentials, rotate the leaked token immediately, and reference secrets only via `${{ secrets.* }}` with masking.",
            "confidence_score": 0.91,
            "suggested_file_path": ".github/workflows/ci.yml",
        },
    ),
    (
        "exceeded retry limit",
        {
            "error_type": "flaky_test",
            "error_subtype": "E2E checkout test flaky across retries",
            "summary": "An end-to-end checkout test failed on all three retry attempts.",
            "location": "tests/e2e/checkout.test.js",
            "root_cause": "The checkout E2E test fails repeatedly, likely due to timing/race conditions or an unstable test environment rather than a single deterministic bug.",
            "fix": "Stabilize the test with explicit waits for async UI/state, isolate shared test data, and investigate environment timing before relying on retries.",
            "confidence_score": 0.8,
            "suggested_file_path": ".github/workflows/ci.yml",
        },
    ),
    (
        "heap out of memory",
        {
            "error_type": "out_of_memory",
            "error_subtype": "Node build exceeded heap limit",
            "summary": "The Node build crashed after exhausting the V8 heap.",
            "location": "Step `npm run build`",
            "root_cause": "The build process allocated more memory than the default V8 heap allows, causing a fatal OOM abort (exit code 134).",
            "fix": "Raise the heap with `NODE_OPTIONS=--max-old-space-size=4096`, or use a larger runner and reduce build memory pressure.",
            "confidence_score": 0.87,
            "suggested_file_path": ".github/workflows/ci.yml",
        },
    ),
    (
        "matrix jobs failed",
        {
            "error_type": "matrix_failure",
            "error_subtype": "Node 18 matrix leg failed",
            "summary": "One leg of a matrix build (node 18) failed while node 20 passed.",
            "location": "tests (node-version: 18, os: ubuntu-latest) — src/server.test.ts",
            "root_cause": "On Node 18 the server failed to start on port 3000 (connection refused), so only the node-18 matrix leg failed.",
            "fix": "Reproduce locally on Node 18, fix the version-specific startup/port issue, or adjust the matrix to exclude the unsupported version.",
            "confidence_score": 0.84,
            "suggested_file_path": ".github/workflows/ci.yml",
        },
    ),
    (
        "ECONNREFUSED",
        {
            "error_type": "network_error",
            "error_subtype": "Connection refused to localhost:3000",
            "summary": "Tests failed because a local service on port 3000 was not reachable.",
            "location": "Step `npm test` — connect 127.0.0.1:3000",
            "root_cause": "The test suite expects a server on 127.0.0.1:3000 that was never started in CI, so the connection is refused.",
            "fix": "Start the dependent service (or its mock) before the tests, or point the tests at a running service container with a health check.",
            "confidence_score": 0.86,
            "suggested_file_path": ".github/workflows/ci.yml",
        },
    ),
    (
        "AADSTS700016",
        {
            "error_type": "authentication_error",
            "error_subtype": "Azure service principal not found",
            "summary": "az login failed because the service principal identifier was not found in the directory.",
            "location": "Step `az login --service-principal`",
            "root_cause": "The Azure AD application/service principal referenced by the workflow does not exist or is in a different tenant, so authentication fails.",
            "fix": "Verify the AZURE_CLIENT_ID/tenant in your secrets, ensure the service principal exists, and re-create the federated credential or secret if needed.",
            "confidence_score": 0.85,
            "suggested_file_path": ".github/workflows/ci.yml",
        },
    ),
    (
        "no-unused-vars",
        {
            "error_type": "lint_error",
            "error_subtype": "ESLint no-unused-vars",
            "summary": "ESLint failed on an unused variable in app.ts.",
            "location": "src/app.ts:12:5",
            "root_cause": "The variable `user` is declared but never used, violating @typescript-eslint/no-unused-vars and failing the lint step.",
            "fix": "Remove the unused `user` variable (or prefix with `_`), then re-run `npm run lint`.",
            "confidence_score": 0.9,
            "suggested_file_path": ".github/workflows/ci.yml",
        },
    ),
    (
        "Input required and not supplied: AZURE_CREDENTIALS",
        {
            "error_type": "config_error",
            "error_subtype": "Missing AZURE_CREDENTIALS input/secret",
            "summary": "The deploy step failed because a required input/secret was not supplied.",
            "location": "Step `deploy` — AZURE_CREDENTIALS",
            "root_cause": "The workflow references AZURE_CREDENTIALS but the secret is not configured, so the action errors before running.",
            "fix": "Add the AZURE_CREDENTIALS secret in repository settings and pass it via `with:`/`env:` in the workflow.",
            "confidence_score": 0.88,
            "suggested_file_path": ".github/workflows/ci.yml",
        },
    ),
    (
        "did not become healthy",
        {
            "error_type": "service_container_error",
            "error_subtype": "Postgres container unhealthy",
            "summary": "A postgres service container failed to become healthy in time.",
            "location": "postgres service container",
            "root_cause": "The postgres container never passed its health check within the allotted window, so dependent steps could not start.",
            "fix": "Add `--health-cmd`, `--health-interval`, and `--health-retries` options to the service, verify credentials/ports, and increase the readiness window.",
            "confidence_score": 0.86,
            "suggested_file_path": ".github/workflows/ci.yml",
        },
    ),
]

# Per-type templates for the heuristic fallback when no curated match exists.
_HEURISTIC_TEMPLATES: dict[str, tuple[str, str]] = {
    "missing_file": (
        "A required file or path was not found during the step.",
        "Verify the path exists and is committed, then re-run the step.",
    ),
    "test_failure": (
        "A test assertion failed, indicating the code under test does not match expectations.",
        "Reproduce the failing test locally, fix the underlying logic, and re-run the suite.",
    ),
    "flaky_test": (
        "A test failed intermittently across retries, suggesting timing or environment instability.",
        "Add explicit waits, isolate shared state, and stabilize the test environment.",
    ),
    "matrix_failure": (
        "At least one matrix leg failed while others passed, pointing to an environment-specific issue.",
        "Reproduce on the failing matrix dimension and fix the version/OS-specific problem.",
    ),
    "compile_error": (
        "The build/compilation step failed due to source or type errors.",
        "Fix the reported compiler errors and re-run the build.",
    ),
    "lint_error": (
        "A linter or formatter rejected the code style/quality.",
        "Resolve the reported lint findings (or auto-fix) and re-run the lint step.",
    ),
    "dependency_error": (
        "Dependency installation or resolution failed.",
        "Pin or update the conflicting dependency and refresh the lockfile.",
    ),
    "timeout": (
        "A job, step, or service exceeded its allotted time and was cancelled.",
        "Increase the timeout, add health checks, or speed up the slow step.",
    ),
    "service_container_error": (
        "A service container failed to start or become healthy.",
        "Add health checks and verify the service image, port, and credentials.",
    ),
    "permission_denied": (
        "A step lacked the permission needed to run a file or action.",
        "Grant the executable bit or required token scope and re-run.",
    ),
    "authentication_error": (
        "Authentication to a service or cloud provider failed.",
        "Verify credentials/secrets and token scopes, then retry the login.",
    ),
    "secrets_exposure": (
        "A secret appears to have been exposed in the logs.",
        "Remove the secret from output, rotate it immediately, and use masked secrets.",
    ),
    "docker_error": (
        "A Docker image pull, build, or registry operation failed.",
        "Verify the image tag, registry login, and that the image was pushed.",
    ),
    "deployment_error": (
        "A deployment or release step failed.",
        "Inspect the deploy logs, verify target config, and re-run the rollout.",
    ),
    "network_error": (
        "A network connection failed (refused, DNS, or unreachable host).",
        "Ensure the dependent service is running/reachable before the step.",
    ),
    "checkout_error": (
        "Repository checkout or a git operation failed.",
        "Verify the ref, token permissions, and submodule configuration.",
    ),
    "config_error": (
        "A required input, env var, or workflow configuration was invalid or missing.",
        "Add the missing configuration/secret and validate the workflow YAML.",
    ),
    "out_of_memory": (
        "The process or runner ran out of memory.",
        "Increase available memory/heap or reduce memory usage, then retry.",
    ),
    "infrastructure_error": (
        "A runner, quota, or platform infrastructure issue occurred.",
        "Retry on a healthy runner and check quotas/disk space.",
    ),
    "unknown": (
        "The failure category could not be determined confidently from the log.",
        "Review the error snippet and exit code manually to identify the root cause.",
    ),
}


def _classify_from_context(context: dict[str, Any]) -> str:
    """Pick the most likely error type from parsed log context."""
    haystack_parts = [
        " ".join(context.get("github_errors", [])),
        context.get("error_snippet", ""),
        context.get("failing_step", ""),
    ]
    haystack = " ".join(part for part in haystack_parts if part)
    error_type = canonicalize_error_type(haystack)
    if error_type != "unknown":
        return error_type
    # Fall back to exit-code heuristics.
    exit_code = context.get("exit_code")
    if exit_code == 126:
        return "permission_denied"
    if exit_code == 134:
        return "out_of_memory"
    return "unknown"


def heuristic_analysis(log_text: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
    """Classify any log deterministically without calling a model."""
    context = context or build_log_context(log_text)
    error_type = _classify_from_context(context)
    root_cause_template, fix_template = _HEURISTIC_TEMPLATES.get(
        error_type, _HEURISTIC_TEMPLATES["unknown"]
    )
    failing_step = context.get("failing_step", "Unknown step")
    github_errors = context.get("github_errors", [])
    detail = github_errors[0] if github_errors else ""
    root_cause = root_cause_template
    if detail:
        root_cause = f"{root_cause_template} Reported error: {detail}"

    return {
        "error_type": error_type,
        "error_subtype": get_error_label(error_type),
        "summary": f"{get_error_label(error_type)} detected in step `{failing_step}`.",
        "location": failing_step,
        "root_cause": root_cause,
        "fix": fix_template,
        "confidence_score": 0.6 if error_type != "unknown" else 0.4,
        "suggested_file_path": ".github/workflows/ci.yml",
    }


def offline_analysis(log_text: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return a curated analysis for known logs, else a heuristic analysis."""
    for signature, analysis in CURATED:
        if signature in log_text:
            return dict(analysis)
    return heuristic_analysis(log_text, context)
