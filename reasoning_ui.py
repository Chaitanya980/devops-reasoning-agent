"""Streamlit UI components for the 4-step reasoning chain."""

from __future__ import annotations

from typing import Any

import streamlit as st

from error_types import ERROR_TYPE_DESCRIPTIONS, get_error_color, get_error_label

REASONING_STEPS = [
    ("CLASSIFY", "Step 1 — ERROR TYPE"),
    ("LOCATE", "Step 2 — LOCATION"),
    ("ROOT CAUSE", "Step 3 — ROOT CAUSE"),
    ("FIX", "Step 4 — FIX"),
]


def badge_color(error_type: str) -> str:
    """Return a badge color for the given error type."""
    return get_error_color(error_type)


def render_reasoning_chain_sidebar(active_step: int = 4) -> None:
    """Render the reasoning chain progress in the sidebar."""
    st.markdown("**Reasoning Chain**")
    for index, (label, _) in enumerate(REASONING_STEPS, start=1):
        if index <= active_step:
            st.success(f"{index}. {label}")
        else:
            st.info(f"{index}. {label}")


def render_analysis_progressive(analysis: dict[str, Any], verifier: dict[str, Any] | None = None) -> None:
    """Render analysis results as progressive expandable step cards."""
    error_type = analysis.get("error_type", "unknown")
    error_label = analysis.get("error_label") or get_error_label(error_type)
    error_subtype = analysis.get("error_subtype", "")
    summary = analysis.get("summary", "")
    color = badge_color(error_type)
    confidence = analysis.get("confidence_score", 0.0)
    description = ERROR_TYPE_DESCRIPTIONS.get(error_type, "")

    st.markdown("### Analysis Results")
    if summary:
        st.info(summary)

    with st.expander("Step 1 — ERROR TYPE", expanded=True):
        st.markdown(
            f"""
            <span style="background:{color}; color:white; padding:0.35rem 0.75rem;
            border-radius:999px; font-weight:600;">{error_label.upper()}</span>
            <span style="margin-left:0.75rem; color:#666;">Confidence: {confidence:.0%}</span>
            """,
            unsafe_allow_html=True,
        )
        st.caption(f"Category id: `{error_type}`")
        if error_subtype:
            st.write(f"**Specific issue:** {error_subtype}")
        if description:
            st.caption(description)

    with st.expander("Step 2 — LOCATION", expanded=True):
        st.code(analysis.get("location", "Unknown location"))

    with st.expander("Step 3 — ROOT CAUSE", expanded=True):
        st.write(analysis.get("root_cause", "No root cause identified."))

    with st.expander("Step 4 — FIX", expanded=True):
        st.code(analysis.get("fix", "No fix suggested."), language="yaml")

    if verifier is not None:
        if verifier.get("approved"):
            st.success("Verifier approved this analysis.")
        else:
            st.warning("Needs review — verifier flagged this analysis.")
            for issue in verifier.get("issues", []):
                st.write(f"- {issue}")


def run_analysis_with_progress(analyze_fn, log_text: str) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Run analysis with visible multi-step progress indicators."""
    with st.status("Running 4-step DevOps reasoning...", expanded=True) as status:
        st.write("Step 1/4 — CLASSIFY: identifying error category...")
        st.progress(0.25)
        result = analyze_fn(log_text)
        st.write("Step 2/4 — LOCATE: pinpointing failure location...")
        st.progress(0.5)
        st.write("Step 3/4 — ROOT CAUSE: explaining why it failed...")
        st.progress(0.75)
        st.write("Step 4/4 — FIX: generating remediation...")
        st.progress(1.0)
        verifier = result.get("verifier")
        if verifier and verifier.get("approved"):
            status.update(label="Analysis complete — verifier approved", state="complete")
        elif verifier:
            status.update(label="Analysis complete — needs review", state="complete")
        else:
            status.update(label="Analysis complete", state="complete")
    return result, verifier
