"""Canonical error type taxonomy for the DevOps Reasoning Agent."""

from __future__ import annotations

ERROR_TYPE_DEFINITIONS: list[dict[str, str | list[str]]] = [
    {
        "id": "missing_file",
        "label": "Missing File",
        "description": "Required file or path not found (ENOENT, missing lockfile, bad path).",
        "aliases": ["enoent", "file_not_found", "missing_file", "dependency_issue"],
    },
    {
        "id": "test_failure",
        "label": "Test Failure",
        "description": "Unit, integration, or E2E test assertion failed.",
        "aliases": ["test_failure", "assertion_error", "unit_test_failure"],
    },
    {
        "id": "flaky_test",
        "label": "Flaky Test",
        "description": "Intermittent test failure after retries or unstable test run.",
        "aliases": ["flaky_test", "flaky_failure", "retry_exhausted"],
    },
    {
        "id": "matrix_failure",
        "label": "Matrix Job Failure",
        "description": "One or more jobs in a strategy/matrix workflow failed.",
        "aliases": ["matrix_failure", "matrix_job_failure"],
    },
    {
        "id": "compile_error",
        "label": "Compile / Build Error",
        "description": "TypeScript, Java, Go, or other compilation/build step failed.",
        "aliases": ["build_error", "compile_error", "compilation_error", "typescript_error"],
    },
    {
        "id": "lint_error",
        "label": "Lint / Format Error",
        "description": "ESLint, Prettier, Ruff, or formatting checks failed.",
        "aliases": ["lint_error", "lint_failure", "format_error", "eslint"],
    },
    {
        "id": "dependency_error",
        "label": "Dependency Error",
        "description": "Package install, version conflict, or dependency resolution failed.",
        "aliases": ["dependency_error", "dependency_issue", "npm_error", "pip_error"],
    },
    {
        "id": "timeout",
        "label": "Timeout",
        "description": "Job, step, or service did not finish within the allowed time.",
        "aliases": ["timeout", "timed_out", "cancelled", "job_timeout"],
    },
    {
        "id": "service_container_error",
        "label": "Service Container Error",
        "description": "Postgres, Redis, or other service container failed to start or become healthy.",
        "aliases": ["service_container_error", "container_health", "service_unavailable"],
    },
    {
        "id": "permission_denied",
        "label": "Permission Denied",
        "description": "Script, file, or workflow step lacks required permissions.",
        "aliases": ["permission_denied", "eacces", "permission", "access_denied"],
    },
    {
        "id": "authentication_error",
        "label": "Authentication Error",
        "description": "Login, token, credential, or cloud auth failed.",
        "aliases": ["authentication_error", "auth_error", "unauthorized", "401", "403_auth"],
    },
    {
        "id": "secrets_exposure",
        "label": "Secrets Exposure",
        "description": "Secrets printed in logs or insecure secret handling detected.",
        "aliases": ["secrets_exposure", "secret_leak", "secrets", "credential_leak"],
    },
    {
        "id": "docker_error",
        "label": "Docker / Container Error",
        "description": "Image pull, manifest, registry, or container runtime failure.",
        "aliases": ["docker_error", "manifest_unknown", "docker", "container_error"],
    },
    {
        "id": "deployment_error",
        "label": "Deployment Error",
        "description": "Deploy script, release, Helm, or rollout step failed.",
        "aliases": ["deployment_error", "deploy_error", "release_failure", "helm_error"],
    },
    {
        "id": "network_error",
        "label": "Network Error",
        "description": "Connection refused, DNS failure, unreachable host, or HTTP/network issue.",
        "aliases": ["network_error", "connection_refused", "dns_error", "econnrefused"],
    },
    {
        "id": "checkout_error",
        "label": "Checkout / Git Error",
        "description": "Repository checkout, clone, submodule, or git operation failed.",
        "aliases": ["checkout_error", "git_error", "clone_error", "submodule_error"],
    },
    {
        "id": "config_error",
        "label": "Configuration Error",
        "description": "Invalid workflow YAML, env var, input, or misconfigured step.",
        "aliases": ["config_error", "configuration_error", "invalid_config", "env_var"],
    },
    {
        "id": "out_of_memory",
        "label": "Out of Memory",
        "description": "Process or runner ran out of memory (OOM, heap limit).",
        "aliases": ["out_of_memory", "resource_error", "oom", "heap", "memory_error"],
    },
    {
        "id": "infrastructure_error",
        "label": "Infrastructure Error",
        "description": "Runner, cloud quota, disk space, or platform infrastructure issue.",
        "aliases": ["infrastructure_error", "runner_error", "disk_full", "quota_exceeded"],
    },
    {
        "id": "unknown",
        "label": "Unknown",
        "description": "Failure category could not be determined confidently.",
        "aliases": ["unknown", "other"],
    },
]

ERROR_TYPE_ENUM = [str(item["id"]) for item in ERROR_TYPE_DEFINITIONS]
ERROR_TYPE_LABELS = {str(item["id"]): str(item["label"]) for item in ERROR_TYPE_DEFINITIONS}
ERROR_TYPE_DESCRIPTIONS = {str(item["id"]): str(item["description"]) for item in ERROR_TYPE_DEFINITIONS}
ERROR_TYPE_COLORS = {
    "missing_file": "#e74c3c",
    "test_failure": "#f39c12",
    "flaky_test": "#e67e22",
    "matrix_failure": "#d35400",
    "compile_error": "#9b59b6",
    "lint_error": "#8e44ad",
    "dependency_error": "#c0392b",
    "timeout": "#3498db",
    "service_container_error": "#2980b9",
    "permission_denied": "#e67e22",
    "authentication_error": "#e84393",
    "secrets_exposure": "#fd79a8",
    "docker_error": "#00b894",
    "deployment_error": "#6c5ce7",
    "network_error": "#0984e3",
    "checkout_error": "#636e72",
    "config_error": "#b2bec3",
    "out_of_memory": "#a29bfe",
    "infrastructure_error": "#2d3436",
    "unknown": "#95a5a6",
    "analysis_error": "#95a5a6",
    "invalid_input": "#7f8c8d",
}

_ALIAS_TO_CANONICAL: dict[str, str] = {}
for definition in ERROR_TYPE_DEFINITIONS:
    canonical_id = str(definition["id"])
    _ALIAS_TO_CANONICAL[canonical_id.lower()] = canonical_id
    for alias in definition.get("aliases", []):
        _ALIAS_TO_CANONICAL[str(alias).lower()] = canonical_id

_KEYWORD_HINTS: list[tuple[str, str]] = [
    ("enoent", "missing_file"),
    ("file_not_found", "missing_file"),
    ("manifest", "docker_error"),
    ("docker", "docker_error"),
    ("secret", "secrets_exposure"),
    ("heap", "out_of_memory"),
    ("out_of_memory", "out_of_memory"),
    ("oom", "out_of_memory"),
    ("eslint", "lint_error"),
    ("prettier", "lint_error"),
    ("connection refused", "network_error"),
    ("econnrefused", "network_error"),
    ("unauthorized", "authentication_error"),
    ("checkout", "checkout_error"),
    ("submodule", "checkout_error"),
    ("matrix", "matrix_failure"),
    ("flaky", "flaky_test"),
    ("service container", "service_container_error"),
    ("deploy", "deployment_error"),
    ("helm", "deployment_error"),
]


def canonicalize_error_type(raw_error_type: str) -> str:
    """Map raw model output to a canonical error type id."""
    normalized = raw_error_type.strip().lower().replace("-", "_").replace(" ", "_") or "unknown"

    if normalized in _ALIAS_TO_CANONICAL:
        return _ALIAS_TO_CANONICAL[normalized]

    for alias, canonical in _ALIAS_TO_CANONICAL.items():
        if alias in normalized or normalized in alias:
            return canonical

    for keyword, canonical in _KEYWORD_HINTS:
        if keyword in normalized:
            return canonical

    return "unknown"


def get_error_label(error_type: str) -> str:
    """Return a user-friendly label for an error type id."""
    canonical = canonicalize_error_type(error_type)
    return ERROR_TYPE_LABELS.get(canonical, canonical.replace("_", " ").title())


def get_error_color(error_type: str) -> str:
    """Return a badge color hex code for an error type."""
    canonical = canonicalize_error_type(error_type)
    return ERROR_TYPE_COLORS.get(canonical, "#34495e")


def get_eval_aliases(expected_type: str) -> set[str]:
    """Return alias tokens used when scoring evaluation cases."""
    canonical = canonicalize_error_type(expected_type)
    aliases = {canonical.lower()}
    for definition in ERROR_TYPE_DEFINITIONS:
        if definition["id"] == canonical:
            aliases.update(str(alias).lower() for alias in definition.get("aliases", []))
            break
    return aliases


def format_error_type_prompt_list() -> str:
    """Format error types for inclusion in the system prompt."""
    lines = []
    for definition in ERROR_TYPE_DEFINITIONS:
        lines.append(f"- {definition['id']}: {definition['description']}")
    return "\n".join(lines)
