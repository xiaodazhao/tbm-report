from __future__ import annotations

from typing import Any

from llm.llm_provider import LLMProvider
from llm.prompts.report_revision_prompt import build_revision_prompt


def revise_llm_report(
    *,
    provider: LLMProvider,
    prompt_evidence_pack: dict[str, Any],
    draft_report: str,
    quality_before_revision: dict[str, Any],
    trace_before_revision: dict[str, Any],
) -> dict[str, Any]:
    """Run one constrained report revision call."""
    revision_prompt = build_revision_prompt(
        prompt_evidence_pack=prompt_evidence_pack,
        draft_report=draft_report,
        quality_before_revision=quality_before_revision,
        trace_before_revision=trace_before_revision,
    )
    response = provider.generate(revision_prompt, purpose="report_revision")
    return {
        "revision_prompt": revision_prompt,
        "revision_request": response.get("request", {}),
        "revision_response": response.get("raw_response", ""),
        "revised_report": response.get("text", "") if response.get("ok") else "",
        "ok": bool(response.get("ok")),
        "error_message": response.get("error_message"),
        "warnings": response.get("warnings", []),
    }
