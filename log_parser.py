"""Log parsing and context extraction for GitHub Actions workflow logs."""

from __future__ import annotations

import re
from typing import Any

ANSI_ESCAPE = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")
GITHUB_NOISE = re.compile(r"^##\[(group|endgroup|command|warning|notice|debug)\]", re.MULTILINE)
GITHUB_ERROR = re.compile(r"^##\[error\](.*)$", re.MULTILINE)
EXIT_CODE_PATTERN = re.compile(
    r"(?:exit code|Process completed with exit code)\s*(\d+)",
    re.IGNORECASE,
)
STEP_PATTERN = re.compile(
    r"^(?:Run |##\[group\]Run |##\[group\])(.+)$",
    re.MULTILINE,
)
ERROR_LINE_PATTERN = re.compile(
    r"(##\[error\]|error|failed|errno|ERR!|AssertionError|Permission denied|timeout|cancelled)",
    re.IGNORECASE,
)

DEFAULT_MAX_LOG_CHARS = 12000


def strip_ansi(text: str) -> str:
    """Remove ANSI color codes from log text."""
    return ANSI_ESCAPE.sub("", text)


def clean_log_text(text: str) -> str:
    """Strip ANSI codes and collapse excessive blank lines."""
    cleaned = strip_ansi(text)
    cleaned = GITHUB_NOISE.sub("", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def truncate_log(text: str, max_chars: int = DEFAULT_MAX_LOG_CHARS) -> str:
    """Keep the last N characters of a log, where errors usually appear."""
    if len(text) <= max_chars:
        return text
    truncated = text[-max_chars:]
    return f"... [truncated {len(text) - max_chars} chars] ...\n{truncated}"


def extract_exit_code(text: str) -> int | None:
    """Extract the workflow exit code from log text."""
    matches = EXIT_CODE_PATTERN.findall(text)
    if not matches:
        return None
    try:
        return int(matches[-1])
    except ValueError:
        return None


def extract_github_errors(text: str) -> list[str]:
    """Extract native GitHub Actions ##[error] lines."""
    return [match.strip() for match in GITHUB_ERROR.findall(text) if match.strip()]


def extract_failing_step(text: str) -> str:
    """Extract the most likely failing workflow step name."""
    steps = STEP_PATTERN.findall(text)
    if steps:
        return steps[-1].strip()
    for line in reversed(text.splitlines()):
        stripped = line.strip()
        if stripped.lower().startswith("run "):
            return stripped[4:].strip()
    return "Unknown step"


def extract_error_snippet(text: str, max_lines: int = 200) -> str:
    """Extract the most relevant error lines from a log."""
    github_errors = extract_github_errors(text)
    lines = text.splitlines()
    error_lines = [line for line in lines if ERROR_LINE_PATTERN.search(line)]

    snippet_parts: list[str] = []
    if github_errors:
        snippet_parts.append("GitHub error markers:")
        snippet_parts.extend(f"- {item}" for item in github_errors[-20:])
    if error_lines:
        snippet_parts.append("Matching error lines:")
        snippet_parts.extend(error_lines[-max_lines:])
    elif lines:
        snippet_parts.extend(lines[-max_lines:])

    return "\n".join(snippet_parts)


def build_log_context(
    text: str,
    *,
    failed_job_names: list[str] | None = None,
    max_log_chars: int = DEFAULT_MAX_LOG_CHARS,
) -> dict[str, Any]:
    """Build structured context from raw workflow log text."""
    cleaned = clean_log_text(text)
    truncated = truncate_log(cleaned, max_chars=max_log_chars)
    return {
        "exit_code": extract_exit_code(cleaned),
        "failing_step": extract_failing_step(cleaned),
        "failed_job_names": failed_job_names or [],
        "github_errors": extract_github_errors(cleaned),
        "error_snippet": extract_error_snippet(cleaned),
        "cleaned_log": cleaned,
        "truncated_log": truncated,
    }


def format_context_for_agent(
    context: dict[str, Any],
    *,
    workflow_yaml: str | None = None,
    workflow_path: str | None = None,
) -> str:
    """Format parsed log context for the reasoning agent prompt."""
    exit_code = context.get("exit_code")
    exit_display = exit_code if exit_code is not None else "unknown"
    failed_jobs = context.get("failed_job_names") or []
    failed_jobs_display = ", ".join(failed_jobs) if failed_jobs else "unknown"

    sections = [
        f"Exit code: {exit_display}",
        f"Failing step: {context.get('failing_step', 'Unknown step')}",
        f"Failed job(s): {failed_jobs_display}",
        f"Error snippet:\n{context.get('error_snippet', '')}",
        f"Relevant log (truncated):\n{context.get('truncated_log', context.get('cleaned_log', ''))}",
    ]

    if workflow_yaml:
        path_display = workflow_path or ".github/workflows/workflow.yml"
        yaml_preview = truncate_log(workflow_yaml, max_chars=4000)
        sections.append(f"Workflow definition ({path_display}):\n{yaml_preview}")

    return "\n\n".join(sections)
