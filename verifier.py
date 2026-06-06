"""Critic / verifier agent for validating DevOps failure analysis."""

from __future__ import annotations

import json
from typing import Any

from agent import SYSTEM_PROMPT, _extract_json, _normalize_result, create_client
import os

VERIFIER_PROMPT = """You are a Critic/Verifier agent for DevOps workflow failure analysis.

Review the draft analysis against the original log. Check:
1. error_type matches the log evidence
2. location is specific and accurate
3. root_cause explains the failure correctly
4. fix is actionable and safe (no secrets, no destructive commands)

Return ONLY valid JSON:
{
  "approved": true,
  "issues": ["list of problems found, empty if approved"],
  "revised_analysis": {
    "error_type": "string",
    "error_subtype": "string",
    "summary": "string",
    "location": "string",
    "root_cause": "string",
    "fix": "string",
    "confidence_score": 0.0,
    "suggested_file_path": ".github/workflows/ci.yml"
  }
}

Set approved=false if the draft is materially wrong. Otherwise approved=true and copy or lightly improve the draft in revised_analysis.
"""


def verify_analysis(log_text: str, draft: dict[str, Any]) -> dict[str, Any]:
    """Run a second-pass verifier agent on a draft analysis.

    Args:
        log_text: Original or cleaned workflow log text.
        draft: Draft analysis dictionary from the primary agent.

    Returns:
        Verifier result with approved flag, issues list, and revised_analysis.
    """
    try:
        client = create_client()
        model = os.getenv("AZURE_MODEL", "o4-mini").strip() or "o4-mini"
        payload = json.dumps(draft, indent=2)

        response = client.responses.create(
            model=model,
            input=[
                {"type": "message", "role": "system", "content": VERIFIER_PROMPT},
                {
                    "type": "message",
                    "role": "user",
                    "content": (
                        f"Original log:\n{log_text}\n\n"
                        f"Draft analysis:\n{payload}\n\n"
                        "Verify the draft analysis."
                    ),
                },
            ],
        )

        output_text = getattr(response, "output_text", None) or str(response)
        parsed = _extract_json(output_text)
        revised = _normalize_result(parsed.get("revised_analysis", draft))
        approved = bool(parsed.get("approved", False))
        issues = parsed.get("issues") or []
        if not isinstance(issues, list):
            issues = [str(issues)]

        if draft.get("confidence_score", 0.0) < 0.7:
            issues.append("Primary analysis confidence below 70% — review recommended.")

        return {
            "approved": approved,
            "issues": [str(item) for item in issues],
            "revised_analysis": revised,
        }

    except Exception as exc:
        return {
            "approved": False,
            "issues": [f"Verifier failed: {exc}"],
            "revised_analysis": draft,
        }
