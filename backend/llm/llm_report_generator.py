from __future__ import annotations

from typing import Any

from llm.evidence_pack import build_template_report
from llm.llm_provider import LLMProvider, resolve_llm_provider_config
from llm.llm_report_planner import generate_report_plan
from llm.llm_revision import revise_llm_report
from llm.prompts.report_generation_prompt import build_generation_prompt
from llm.prompts.report_revision_prompt import build_revision_prompt
from llm.report_quality_checker import check_report_quality
from llm.report_trace_builder import build_report_trace, summarize_report_trace


GENERATION_MODE_TEMPLATE = "template"
GENERATION_MODE_LLM = "evidence_pack_llm"
GENERATION_MODE_LLM_WITH_REVISION = "evidence_pack_llm_with_revision"
GENERATION_MODE_PLANNER_LLM = "evidence_pack_planner_llm"
GENERATION_MODE_PLANNER_LLM_WITH_REVISION = "evidence_pack_planner_llm_with_revision"
SUPPORTED_GENERATION_MODES = {
    GENERATION_MODE_TEMPLATE,
    GENERATION_MODE_LLM,
    GENERATION_MODE_LLM_WITH_REVISION,
    GENERATION_MODE_PLANNER_LLM,
    GENERATION_MODE_PLANNER_LLM_WITH_REVISION,
}


def generate_llm_report(
    *,
    date: str,
    prompt_evidence_pack: dict[str, Any],
    twin_state: dict[str, Any] | None = None,
    generation_mode: str = GENERATION_MODE_LLM,
    provider_name: str | None = None,
    model: str | None = None,
    mock_llm: bool = False,
    enable_revision: bool | None = None,
    enable_planner: bool | None = None,
    planner_provider_name: str | None = None,
    planner_model: str | None = None,
    max_revision_rounds: int = 1,
    fallback_report: str | None = None,
) -> dict[str, Any]:
    """Generate an Evidence-Pack-constrained LLM report and optional revision."""
    mode = normalize_generation_mode(generation_mode)
    revision_enabled = (
        mode in {GENERATION_MODE_LLM_WITH_REVISION, GENERATION_MODE_PLANNER_LLM_WITH_REVISION}
        if enable_revision is None
        else bool(enable_revision)
    )
    planner_enabled = (
        mode in {GENERATION_MODE_PLANNER_LLM, GENERATION_MODE_PLANNER_LLM_WITH_REVISION}
        if enable_planner is None
        else bool(enable_planner)
    )
    if max_revision_rounds <= 0:
        revision_enabled = False

    if mode == GENERATION_MODE_TEMPLATE:
        report = fallback_report or build_template_report(prompt_evidence_pack)
        quality, trace = _evaluate(report, prompt_evidence_pack, twin_state)
        return _template_result(date, report, quality, trace)

    planner_result: dict[str, Any] = {}
    report_plan = None
    plan_validation = None
    if planner_enabled:
        planner_result = generate_report_plan(
            date=date,
            prompt_evidence_pack=prompt_evidence_pack,
            provider_name=planner_provider_name or provider_name,
            model=planner_model or model,
            mock_llm=mock_llm,
        )
        report_plan = planner_result.get("report_plan")
        plan_validation = planner_result.get("plan_validation")

    provider = LLMProvider(
        resolve_llm_provider_config(
            provider="mock" if mock_llm else provider_name,
            model=model,
        )
    )
    prompt = build_generation_prompt(
        prompt_evidence_pack,
        report_plan=report_plan,
        plan_validation=plan_validation,
    )
    provider_result = provider.generate(prompt, purpose="report_generation")
    if provider.provider == "mock" and fallback_report:
        provider_result["text"] = fallback_report
        provider_result["raw_response"] = fallback_report

    error_message = provider_result.get("error_message")
    warnings = list(planner_result.get("warnings") or []) + list(provider_result.get("warnings") or [])
    if provider_result.get("ok"):
        draft = clean_llm_report_text(str(provider_result.get("text") or ""))
    else:
        draft = fallback_report or build_template_report(prompt_evidence_pack)
        warnings.append("LLM generation failed; fallback report was used for draft evaluation.")

    quality_before, trace_before = _evaluate(draft, prompt_evidence_pack, twin_state)
    final_report = draft
    quality_after = quality_before
    trace_after = trace_before
    revision_prompt = ""
    revision_request: dict[str, Any] = {}
    revision_response = ""
    revision_executed = False

    if revision_enabled and provider_result.get("ok"):
        if provider.provider == "mock" and fallback_report:
            revision_prompt = build_revision_prompt(
                prompt_evidence_pack=prompt_evidence_pack,
                draft_report=draft,
                quality_before_revision=quality_before,
                trace_before_revision=trace_before,
            )
            revision_request = {"provider": "mock", "purpose": "report_revision"}
            revision_response = fallback_report
            revision_executed = True
            final_report = clean_llm_report_text(fallback_report)
            quality_after, trace_after = _evaluate(final_report, prompt_evidence_pack, twin_state)
        else:
            revision = revise_llm_report(
                provider=provider,
                prompt_evidence_pack=prompt_evidence_pack,
                draft_report=draft,
                quality_before_revision=quality_before,
                trace_before_revision=trace_before,
            )
            revision_prompt = revision.get("revision_prompt", "")
            revision_request = revision.get("revision_request", {})
            revision_response = revision.get("revision_response", "")
            revision_executed = bool(revision.get("ok"))
            warnings.extend(revision.get("warnings") or [])
            if revision.get("ok") and revision.get("revised_report"):
                final_report = clean_llm_report_text(str(revision.get("revised_report") or ""))
                quality_after, trace_after = _evaluate(final_report, prompt_evidence_pack, twin_state)
            else:
                error_message = error_message or revision.get("error_message")

    summary = _summary(
        date=date,
        generation_mode=mode,
        provider=provider.provider,
        model=provider.model,
        revision_enabled=revision_enabled,
        revision_executed=revision_executed,
        quality_before=quality_before,
        trace_before=trace_before,
        quality_after=quality_after,
        trace_after=trace_after,
        error_message=error_message,
        planner_result=planner_result,
    )
    return {
        "date": date,
        "generation_mode": mode,
        "provider": provider.provider,
        "model": provider.model,
        "prompt": prompt,
        "request": provider_result.get("request", {}),
        "raw_response": provider_result.get("raw_response", ""),
        "report_draft": draft,
        "report_final": final_report,
        "quality_before_revision": quality_before,
        "trace_before_revision": trace_before,
        "revision_enabled": revision_enabled,
        "revision_executed": revision_executed,
        "revision_prompt": revision_prompt,
        "revision_request": revision_request,
        "revision_response": revision_response,
        "quality_after_revision": quality_after,
        "trace_after_revision": trace_after,
        "error_type_counts": quality_after.get("error_type_counts", {}),
        "support_type_distribution": trace_after.get("support_type_distribution", {}),
        "llm_report_plan_prompt": planner_result.get("planning_prompt", ""),
        "llm_report_plan_request": planner_result.get("planning_request", {}),
        "llm_report_plan_raw_response": planner_result.get("planning_raw_response", ""),
        "llm_report_plan": planner_result.get("report_plan", {}),
        "llm_report_plan_validation": planner_result.get("plan_validation", {}),
        "summary": summary,
        "error_message": error_message,
        "warnings": warnings,
        "passed": bool(summary.get("passed")),
    }


def normalize_generation_mode(value: str | None) -> str:
    mode = (value or GENERATION_MODE_TEMPLATE).strip()
    if mode not in SUPPORTED_GENERATION_MODES:
        raise ValueError(f"unsupported generation_mode: {value}")
    return mode


def clean_llm_report_text(text: str) -> str:
    """Remove conversational wrappers and markdown separators from LLM output."""
    cleaned = str(text or "").strip()
    prefixes = [
        "好的，遵照您的指示",
        "好的，以下是",
        "以下是",
        "遵照您的要求",
        "遵照您的指示",
    ]
    changed = True
    while changed:
        changed = False
        for prefix in prefixes:
            if cleaned.startswith(prefix):
                cleaned = cleaned[len(prefix):].lstrip(" ：:\n\r\t，,。")
                changed = True
    report_markers = ["# TBM 施工日报", "TBM 施工日报", "1. 综合结论摘要"]
    marker_positions = [cleaned.find(marker) for marker in report_markers if cleaned.find(marker) >= 0]
    if marker_positions:
        cleaned = cleaned[min(marker_positions):]
    lines = []
    for line in cleaned.splitlines():
        stripped = line.strip()
        if stripped in {"***", "---"}:
            continue
        lines.append(line.rstrip())
    return "\n".join(lines).strip()


def _evaluate(
    report_text: str,
    prompt_evidence_pack: dict[str, Any],
    twin_state: dict[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    quality = check_report_quality(
        report_text,
        twin_state=twin_state or {},
        prompt_evidence_pack=prompt_evidence_pack,
        include_claim_results=True,
    )
    trace = build_report_trace(
        report_text,
        grounding_result={
            "claim_results": quality.get("claim_results") or [],
            **(quality.get("grounding_summary") or {}),
        },
        twin_state=twin_state or {},
        prompt_evidence_pack=prompt_evidence_pack,
    )
    return quality, trace


def _summary(
    *,
    date: str,
    generation_mode: str,
    provider: str,
    model: str,
    revision_enabled: bool,
    revision_executed: bool,
    quality_before: dict[str, Any],
    trace_before: dict[str, Any],
    quality_after: dict[str, Any],
    trace_after: dict[str, Any],
    error_message: str | None,
    planner_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    draft_summary = _quality_trace_values(quality_before, trace_before)
    final_summary = _quality_trace_values(quality_after, trace_after)
    planner_result = planner_result or {}
    return {
        "date": date,
        "generation_mode": generation_mode,
        "provider": provider,
        "model": model,
        "revision_enabled": revision_enabled,
        "revision_executed": revision_executed,
        "draft_quality_score": draft_summary["quality_score"],
        "final_quality_score": final_summary["quality_score"],
        "draft_grounding_rate": draft_summary["grounding_rate"],
        "final_grounding_rate": final_summary["grounding_rate"],
        "draft_unsupported_claim_count": draft_summary["unsupported_claim_count"],
        "final_unsupported_claim_count": final_summary["unsupported_claim_count"],
        "draft_error_type_counts": quality_before.get("error_type_counts", {}),
        "final_error_type_counts": quality_after.get("error_type_counts", {}),
        "draft_support_type_distribution": trace_before.get("support_type_distribution", {}),
        "final_support_type_distribution": trace_after.get("support_type_distribution", {}),
        "planner_enabled": bool(planner_result.get("planner_enabled")),
        "planner_provider": planner_result.get("planner_provider"),
        "plan_generated": bool(planner_result.get("plan_generated")),
        "plan_validation_passed": bool(planner_result.get("plan_validation_passed")),
        "plan_fallback_used": bool(planner_result.get("plan_fallback_used")),
        "error_message": error_message,
        "passed": not error_message,
    }


def _quality_trace_values(quality: dict[str, Any], trace: dict[str, Any]) -> dict[str, Any]:
    trace_summary = summarize_report_trace(trace)
    return {
        "quality_score": quality.get("score", quality.get("quality_score")),
        "grounding_rate": quality.get("grounding_rate"),
        "unsupported_claim_count": quality.get("unsupported_claim_count"),
        "trace_coverage": trace_summary.get("trace_coverage"),
    }


def _template_result(
    date: str,
    report: str,
    quality: dict[str, Any],
    trace: dict[str, Any],
) -> dict[str, Any]:
    summary = _summary(
        date=date,
        generation_mode=GENERATION_MODE_TEMPLATE,
        provider="disabled",
        model="template",
        revision_enabled=False,
        revision_executed=False,
        quality_before=quality,
        trace_before=trace,
        quality_after=quality,
        trace_after=trace,
        error_message=None,
    )
    return {
        "date": date,
        "generation_mode": GENERATION_MODE_TEMPLATE,
        "provider": "disabled",
        "model": "template",
        "prompt": "",
        "request": {},
        "raw_response": "",
        "report_draft": report,
        "report_final": report,
        "quality_before_revision": quality,
        "trace_before_revision": trace,
        "revision_enabled": False,
        "revision_executed": False,
        "revision_prompt": "",
        "revision_request": {},
        "revision_response": "",
        "quality_after_revision": quality,
        "trace_after_revision": trace,
        "error_type_counts": quality.get("error_type_counts", {}),
        "support_type_distribution": trace.get("support_type_distribution", {}),
        "summary": summary,
        "error_message": None,
        "warnings": [],
        "passed": True,
    }
