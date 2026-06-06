"""Sample failure logs for demo and quick testing."""

from __future__ import annotations

from evaluator import TEST_CASES

SAMPLE_FAILURES: list[dict[str, str]] = [
    {
        "id": case["name"].lower().replace(" ", "_"),
        "label": case["name"],
        "log_text": case["log_text"],
    }
    for case in TEST_CASES[:5]
]
