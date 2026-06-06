"""DevOps Reasoning Agent — Azure AI Foundry integration."""

from __future__ import annotations

import json
import os
import re
from typing import Any

from dotenv import load_dotenv
from openai import AzureOpenAI

from error_types import (
    canonicalize_error_type,
    format_error_type_prompt_list,
    get_error_label,
)
from guardrails import redact_secrets
from log_parser import build_log_context, format_context_for_agent

load_dotenv()

SYSTEM_PROMPT = f"""You are a DevOps Reasoning Agent specialized in analyzing GitHub Actions workflow failure logs.

Follow this exact 4-step reasoning process before answering:

1. CLASSIFY — Pick exactly one error_type from the taxonomy below.
2. LOCATE — Pinpoint the exact file, workflow step, and line number where the failure occurred.
3. ROOT CAUSE — Explain why the failure happened in plain language.
4. FIX — Provide a concrete, actionable fix with a code or config snippet when applicable.

Error type taxonomy (use the id exactly):
{format_error_type_prompt_list()}

Also provide:
- error_subtype: a short, user-friendly phrase describing the specific failure
- summary: one sentence a developer can read at a glance

Prioritize evidence from:
- `##[error]` lines
- exit code
- failed job name
- the error snippet and truncated log

Return ONLY valid JSON on a single line with these exact keys:
{{
  "error_type": "string",
  "error_subtype": "string",
  "summary": "string",
  "location": "string",
  "root_cause": "string",
  "fix": "string",
  "confidence_score": 0.0,
  "suggested_file_path": ".github/workflows/ci.yml"
}}

Important JSON rules:
- Use double quotes for all strings
- Escape newlines inside strings as \\n (do not use literal line breaks inside JSON string values)
- For missing file/path failures, set error_type to "missing_file"

confidence_score must be a float between 0.0 and 1.0 representing your confidence in the analysis.
suggested_file_path should be the most likely workflow or config file to change, when applicable.
"""

JSON_FIELD_ORDER = [
    "error_type",
    "error_subtype",
    "summary",
    "location",
    "root_cause",
    "fix",
    "confidence_score",
    "suggested_file_path",
]


def _get_required_env(name: str) -> str:
    """Return a required environment variable or raise a clear error."""
    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(f"Missing required environment variable: {name}")
    return value


def create_client() -> AzureOpenAI:
    """Create an AzureOpenAI client configured for Azure AI Foundry."""
    endpoint = _get_required_env("AZURE_ENDPOINT").rstrip("/")
    api_key = _get_required_env("AZURE_API_KEY")
    agent_id = os.getenv("AZURE_AGENT_ID", "").strip()
    api_version = os.getenv("AZURE_API_VERSION", "v1").strip()

    if agent_id:
        base_url = f"{endpoint}/agents/{agent_id}/endpoint/protocols/openai"
        default_headers = {"Foundry-Features": "agents"}
    else:
        base_url = f"{endpoint}/openai/v1"
        default_headers = None

    return AzureOpenAI(
        api_key=api_key,
        api_version=api_version,
        base_url=base_url,
        default_headers=default_headers,
    )


def _decode_json_string(value: str) -> str:
    """Decode escaped characters from a JSON string fragment."""
    try:
        return json.loads(f'"{value}"')
    except json.JSONDecodeError:
        return value.replace("\\n", "\n").replace('\\"', '"').replace("\\\\", "\\")


def _extract_field_between_keys(text: str, field: str, next_field: str | None) -> str | None:
    """Extract a JSON string field value even when the payload is malformed."""
    marker = f'"{field}"'
    start = text.find(marker)
    if start == -1:
        return None

    colon = text.find(":", start + len(marker))
    if colon == -1:
        return None

    quote = text.find('"', colon + 1)
    if quote == -1:
        return None

    value_start = quote + 1
    if next_field:
        end_marker = f'"{next_field}"'
        end = text.find(end_marker, value_start)
        if end == -1:
            return None
        segment = text[value_start:end].rstrip()
        if segment.endswith(","):
            segment = segment[:-1]
        if segment.endswith('"'):
            segment = segment[:-1]
    else:
        segment = text[value_start:]
        if segment.endswith('"'):
            segment = segment[:-1]
        if segment.endswith("}"):
            segment = segment[:-1].rstrip()
            if segment.endswith('"'):
                segment = segment[:-1]

    return _decode_json_string(segment)


def _extract_json_fallback(text: str) -> dict[str, Any]:
    """Best-effort JSON extraction when strict parsing fails."""
    result: dict[str, Any] = {}
    for index, field in enumerate(JSON_FIELD_ORDER):
        next_field = JSON_FIELD_ORDER[index + 1] if index + 1 < len(JSON_FIELD_ORDER) else None
        if field == "confidence_score":
            match = re.search(r'"confidence_score"\s*:\s*([0-9.]+)', text)
            if match:
                result[field] = float(match.group(1))
            continue

        value = _extract_field_between_keys(text, field, next_field)
        if value is not None:
            result[field] = value

    if not result.get("error_type"):
        raise ValueError("Could not parse model JSON output.")
    return result


def _extract_json(text: str) -> dict[str, Any]:
    """Parse JSON from model output, including fenced code blocks."""
    text = text.strip()
    if not text:
        raise ValueError("Empty response from model")

    candidates = [text]
    fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence_match:
        candidates.insert(0, fence_match.group(1).strip())

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidates.append(text[start : end + 1])

    last_error: Exception | None = None
    for candidate in candidates:
        try:
            return json.loads(candidate)
        except json.JSONDecodeError as exc:
            last_error = exc

    try:
        return _extract_json_fallback(candidates[0])
    except ValueError as exc:
        if last_error is not None:
            raise last_error from exc
        raise


def _canonical_error_type(raw_error_type: str) -> str:
    """Map model error types to canonical enum values."""
    return canonicalize_error_type(raw_error_type)


def _normalize_result(raw: dict[str, Any]) -> dict[str, Any]:
    """Ensure the analysis result contains all expected fields."""
    confidence = raw.get("confidence_score", 0.0)
    try:
        confidence = float(confidence)
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))

    error_type = _canonical_error_type(str(raw.get("error_type", "unknown")))
    error_subtype = str(raw.get("error_subtype", "")).strip() or get_error_label(error_type)
    summary = str(raw.get("summary", "")).strip() or str(raw.get("root_cause", "")).strip()[:160]

    suggested_file_path = str(raw.get("suggested_file_path", "")).strip()
    if not suggested_file_path:
        suggested_file_path = ".github/devops-agent-suggested-fix.md"

    return {
        "error_type": error_type,
        "error_subtype": error_subtype,
        "summary": summary,
        "error_label": get_error_label(error_type),
        "location": str(raw.get("location", "Unknown location")).strip(),
        "root_cause": str(raw.get("root_cause", "Unable to determine root cause.")).strip(),
        "fix": str(raw.get("fix", "Review the workflow logs manually.")).strip(),
        "confidence_score": confidence,
        "suggested_file_path": suggested_file_path,
    }


def _run_primary_analysis(client: AzureOpenAI, model: str, prompt_text: str) -> dict[str, Any]:
    """Call the primary Foundry agent for failure analysis."""
    response = client.responses.create(
        model=model,
        input=[
            {"type": "message", "role": "system", "content": SYSTEM_PROMPT},
            {
                "type": "message",
                "role": "user",
                "content": (
                    "Analyze the following GitHub Actions workflow failure log "
                    "using the 4-step reasoning process:\n\n"
                    f"{prompt_text}"
                ),
            },
        ],
    )
    output_text = getattr(response, "output_text", None) or str(response)
    parsed = _extract_json(output_text)
    return _normalize_result(parsed)


def analyze_failure(
    log_text: str,
    *,
    run_verifier: bool = True,
    workflow_yaml: str | None = None,
    workflow_path: str | None = None,
    failed_job_names: list[str] | None = None,
) -> dict[str, Any]:
    """Send workflow log text to the Foundry agent and return structured analysis."""
    if not log_text or not log_text.strip():
        return {
            "error_type": "invalid_input",
            "location": "N/A",
            "root_cause": "No log text was provided for analysis.",
            "fix": "Paste a workflow log or fetch logs from a GitHub Actions run.",
            "confidence_score": 0.0,
            "suggested_file_path": "",
            "verifier": {"approved": False, "issues": ["No input provided"], "revised_analysis": {}},
            "log_context": {},
        }

    try:
        redacted_log = redact_secrets(log_text)
        context = build_log_context(redacted_log, failed_job_names=failed_job_names)
        prompt_text = format_context_for_agent(
            context,
            workflow_yaml=workflow_yaml,
            workflow_path=workflow_path,
        )

        client = create_client()
        model = os.getenv("AZURE_MODEL", "o4-mini").strip() or "o4-mini"
        draft = _run_primary_analysis(client, model, prompt_text)

        verifier_result: dict[str, Any] | None = None
        final_analysis = draft

        if run_verifier:
            from verifier import verify_analysis

            verifier_result = verify_analysis(prompt_text, draft)
            final_analysis = verifier_result.get("revised_analysis", draft)

        result = {
            **final_analysis,
            "verifier": verifier_result,
            "log_context": context,
        }
        return result

    except Exception as exc:
        return {
            "error_type": "analysis_error",
            "location": "N/A",
            "root_cause": f"Failed to analyze log: {exc}",
            "fix": "Verify AZURE_ENDPOINT, AZURE_API_KEY, AZURE_AGENT_ID, and AZURE_MODEL in your .env file.",
            "confidence_score": 0.0,
            "suggested_file_path": "",
            "verifier": {"approved": False, "issues": [str(exc)], "revised_analysis": {}},
            "log_context": {},
        }
