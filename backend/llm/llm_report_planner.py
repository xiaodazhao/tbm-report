from __future__ import annotations

import json
import re
from typing import Any

from llm.llm_provider import LLMProvider, resolve_llm_provider_config
from llm.prompts.report_generation_prompt import (
    FORBIDDEN_EXPRESSIONS,
    METHOD_BOUNDARY_STATEMENTS,
    REQUIRED_SECTIONS,
)
from llm.prompts.report_planning_prompt import build_planning_prompt


PLAN_VERSION = "report_plan_v1"


def generate_report_plan(
    *,
    date: str,
    prompt_evidence_pack: dict[str, Any],
    provider_name: str | None = None,
    model: str | None = None,
    mock_llm: bool = False,
) -> dict[str, Any]:
    """Generate and validate an LLM report plan, with deterministic fallback."""
    prompt = build_planning_prompt(prompt_evidence_pack)
    provider = LLMProvider(
        resolve_llm_provider_config(
            provider="mock" if mock_llm else provider_name,
            model=model,
        )
    )
    provider_result = provider.generate(prompt, purpose="report_planning")

    if provider.provider == "mock":
        raw_response = json.dumps(
            build_rule_based_report_plan(date=date, prompt_evidence_pack=prompt_evidence_pack),
            ensure_ascii=False,
            indent=2,
            default=str,
        )
        provider_result["text"] = raw_response
        provider_result["raw_response"] = raw_response
        provider_result["ok"] = True
    else:
        raw_response = str(provider_result.get("text") or provider_result.get("raw_response") or "")

    warnings = list(provider_result.get("warnings") or [])
    parsed_plan: dict[str, Any] | None = None
    parse_error = None
    if provider_result.get("ok"):
        try:
            parsed_plan = parse_report_plan(raw_response)
        except Exception as exc:
            parse_error = str(exc)
            warnings.append(f"report plan parse failed: {parse_error}")
    else:
        warnings.append("report planner LLM failed; fallback rule-based plan was used.")

    validation = validate_report_plan(parsed_plan or {}, prompt_evidence_pack=prompt_evidence_pack)
    fallback_used = bool(parse_error or not validation.get("passed"))
    if fallback_used:
        plan = build_rule_based_report_plan(date=date, prompt_evidence_pack=prompt_evidence_pack)
        validation = validate_report_plan(plan, prompt_evidence_pack=prompt_evidence_pack)
        validation["fallback_used"] = True
    else:
        plan = parsed_plan or {}
        validation["fallback_used"] = False

    plan["plan_validation"] = {
        "passed": bool(validation.get("passed")),
        "violations": list(validation.get("violations") or []),
    }
    return {
        "planner_enabled": True,
        "planner_provider": provider.provider,
        "planner_model": provider.model,
        "planning_prompt": prompt,
        "planning_request": provider_result.get("request", {}),
        "planning_raw_response": raw_response,
        "report_plan": plan,
        "plan_validation": validation,
        "plan_generated": bool(parsed_plan is not None and not fallback_used),
        "plan_validation_passed": bool(validation.get("passed")),
        "plan_fallback_used": fallback_used,
        "error_message": parse_error or provider_result.get("error_message"),
        "warnings": warnings,
    }


def parse_report_plan(text: str) -> dict[str, Any]:
    """Parse a planner JSON response, accepting fenced JSON blocks."""
    content = str(text or "").strip()
    if not content:
        raise ValueError("empty planner response")
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, flags=re.S)
    if fenced:
        content = fenced.group(1)
    elif not content.startswith("{"):
        start = content.find("{")
        end = content.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("planner response does not contain a JSON object")
        content = content[start:end + 1]
    parsed = json.loads(content)
    if not isinstance(parsed, dict):
        raise ValueError("planner response JSON must be an object")
    return parsed


def validate_report_plan(plan: dict[str, Any], *, prompt_evidence_pack: dict[str, Any]) -> dict[str, Any]:
    """Validate that a report plan preserves the Evidence Pack method boundaries."""
    violations: list[dict[str, str]] = []
    sections = plan.get("sections") if isinstance(plan, dict) else None
    if not isinstance(sections, list) or not sections:
        violations.append({"code": "missing_sections", "message": "report plan has no sections"})
        sections = []

    title_map = {str(item.get("section_title", "")): item for item in sections if isinstance(item, dict)}
    for title in REQUIRED_SECTIONS:
        if title not in title_map:
            violations.append({"code": "missing_required_section", "message": title})

    by_id = {str(item.get("section_id", "")): item for item in sections if isinstance(item, dict)}
    forward_section = by_id.get("section_6") or _find_section(sections, "前方")
    if forward_section:
        allowed_metrics = _lower_set(forward_section.get("allowed_metrics"))
        if "rai" in allowed_metrics or "grci" in allowed_metrics:
            violations.append({
                "code": "forward_attention_allows_rai_or_grci",
                "message": "forward_attention section must not allow RAI or GRCI",
            })

    for section in sections:
        if not isinstance(section, dict):
            continue
        section_id = str(section.get("section_id", ""))
        roles = _lower_set(section.get("allowed_cell_roles"))
        metrics = _lower_set(section.get("allowed_metrics"))
        if "grci" in metrics and "daily_review" not in roles:
            violations.append({
                "code": "grci_without_daily_review_role",
                "message": section_id or str(section.get("section_title", "")),
            })
        if "local_background" in roles:
            policy_text = str(section.get("evidence_use_policy", "")) + str(section.get("purpose", ""))
            if "当日施工异常" in policy_text and "不能" not in policy_text and "不得" not in policy_text:
                violations.append({
                    "code": "local_background_as_daily_abnormal",
                    "message": section_id or str(section.get("section_title", "")),
                })

    plan_text = json.dumps(plan, ensure_ascii=False, default=str)
    excluded_ids = _excluded_evidence_ids(prompt_evidence_pack)
    if any(evidence_id and evidence_id in plan_text for evidence_id in excluded_ids):
        violations.append({"code": "quotes_excluded_evidence", "message": "plan must not quote excluded evidence"})
    if not _contains_any(plan_text, ["GRCI 不是", "GRCI 不表示", "GRCI 不能表示", "GRCI is not"]):
        violations.append({"code": "missing_grci_non_probability_boundary", "message": "GRCI boundary missing"})
    if not _contains_any(plan_text, ["前方关注提示不是已发生事实", "不表示已发生事实", "不能写成已发生事实"]):
        violations.append({"code": "missing_forward_non_fact_boundary", "message": "forward boundary missing"})
    if not _contains_any(plan_text, ["daily_excavated_scope", "10m cell 对齐"]):
        violations.append({"code": "missing_aligned_scope_boundary", "message": "aligned scope boundary missing"})

    return {
        "passed": not violations,
        "violations": violations,
        "fallback_used": False,
    }


def build_rule_based_report_plan(*, date: str, prompt_evidence_pack: dict[str, Any]) -> dict[str, Any]:
    """Build the deterministic fallback plan used when LLM planning is invalid."""
    scope = prompt_evidence_pack.get("report_scope") or {}
    global_constraints = [
        "Only use Prompt Evidence Pack facts.",
        "GRCI 不是灾害概率，也不是风险概率。",
        "前方关注提示不是已发生事实，不得写成已揭露或已发生异常。",
        "daily_excavated_scope 是 10m cell 对齐后的已掘复核范围，不是实际 PLC 推进范围。",
        "实际推进起止和推进量只能使用 daily_plc_range / daily_chainage_raw。",
        "local_background 只作为背景上下文，不能写成当日施工响应异常。",
        "stop_ratio 仅作为施工响应关注信号，不能直接写成异常原因。",
        "Do not quote excluded evidence.",
    ]
    return {
        "date": date or scope.get("date"),
        "plan_version": PLAN_VERSION,
        "sections": [
            _section(
                "section_1",
                REQUIRED_SECTIONS[0],
                "Summarize operation, reviewed coupling, forward attention, and background context without mixing their roles.",
                ["operation", "gas", "daily_review", "forward_attention", "local_background"],
                ["daily_plc_range", "daily_advance_m", "GRS", "RAI", "GRCI", "forward_profile", "gas_summary"],
                ["GRCI_probability", "forward_as_fact", "local_background_as_daily_abnormal"],
                [
                    "GRCI 不是灾害概率，也不是风险概率。",
                    "前方关注提示不是已发生事实。",
                    "daily_excavated_scope 不是实际推进范围。",
                ],
                "Use concise conclusions, explicitly separating reviewed cells, forward attention cells, and background context.",
            ),
            _section(
                "section_2",
                REQUIRED_SECTIONS[1],
                "Describe measured PLC daily operation and actual advance.",
                ["operation"],
                ["daily_plc_range", "daily_advance_m", "dominant_mode", "work_total_min", "stop_total_min", "abnormal_total_min"],
                ["daily_excavated_scope_as_actual_advance", "stop_ratio_as_abnormal_cause"],
                ["daily_excavated_scope 是 10m cell 对齐后的已掘复核范围，不是实际 PLC 推进范围。"],
                "Actual start, end, and advance must come from daily_plc_range only.",
            ),
            _section(
                "section_3",
                REQUIRED_SECTIONS[2],
                "Explain PLC response indicators and RAI components.",
                ["daily_review"],
                ["RAI", "stop_ratio", "abnormal_ratio", "speed_drop_score", "torque_volatility_score", "speed_volatility_score"],
                ["PLC_response_as_geological_disaster_cause", "stop_ratio_as_abnormal_cause", "GRCI_probability"],
                ["stop_ratio 仅作为施工响应关注信号，不能直接写成异常原因。"],
                "Use RAI components as response attention indicators, not as direct cause attribution.",
            ),
            _section(
                "section_4",
                REQUIRED_SECTIONS[3],
                "Summarize gas monitoring evidence.",
                ["gas"],
                ["gas_summary", "exceed_summary", "gas_summaries"],
                ["external_ventilation_or_treatment_fact"],
                ["Only use gas_evidence facts."],
                "Do not add field interpretation or treatment measures outside the Evidence Pack.",
            ),
            _section(
                "section_5",
                REQUIRED_SECTIONS[4],
                "Review excavated daily cells where geology evidence and PLC response can be coupled.",
                ["daily_review"],
                ["GRS", "RAI", "GRCI", "review_level", "main_hazards", "source_trace"],
                ["forward_attention_GRCI", "local_background_daily_response", "GRCI_probability"],
                ["GRCI 不是灾害概率，也不是风险概率。"],
                "Only daily_review cells may use GRCI; quote source_trace when explaining key reviewed cells.",
            ),
            _section(
                "section_6",
                REQUIRED_SECTIONS[5],
                "Describe current face forward attention using geology evidence only.",
                ["forward_attention"],
                ["GRS", "forward_profile", "attention_level", "monitoring_focus", "support_actions", "source_trace"],
                ["RAI", "GRCI", "occurred_fact", "abnormal_fact", "risk_probability"],
                ["前方关注提示不是已发生事实，不使用 GRCI。"],
                "Use GRS and forward_profile only; do not say forward evidence has occurred or been exposed.",
            ),
            _section(
                "section_7",
                REQUIRED_SECTIONS[6],
                "Give evidence-bounded conclusions and suggestions.",
                ["daily_review", "forward_attention", "local_background", "operation", "gas"],
                ["monitoring_focus", "support_actions", "method_boundary_statements", "quality_evidence"],
                ["external_engineering_measure", "overcertain_claim", "GRCI_probability"],
                [
                    "GRCI 不是灾害概率，也不是风险概率。",
                    "前方关注提示不是已发生事实。",
                    "stop_ratio 仅作为施工响应关注信号。",
                ],
                "Suggestions must stay within Evidence Pack monitoring and support actions.",
            ),
        ],
        "global_constraints": global_constraints,
        "fallback_required": False,
        "plan_validation": {"passed": True, "violations": []},
    }


def _section(
    section_id: str,
    section_title: str,
    purpose: str,
    allowed_cell_roles: list[str],
    allowed_metrics: list[str],
    forbidden_metrics: list[str],
    must_include_boundary: list[str],
    evidence_use_policy: str,
) -> dict[str, Any]:
    return {
        "section_id": section_id,
        "section_title": section_title,
        "purpose": purpose,
        "allowed_cell_roles": allowed_cell_roles,
        "allowed_metrics": allowed_metrics,
        "forbidden_metrics": forbidden_metrics,
        "must_include_boundary": must_include_boundary,
        "forbidden_expressions": FORBIDDEN_EXPRESSIONS,
        "evidence_use_policy": evidence_use_policy,
    }


def _find_section(sections: list[Any], keyword: str) -> dict[str, Any] | None:
    for item in sections:
        if isinstance(item, dict) and keyword in str(item.get("section_title", "")):
            return item
    return None


def _lower_set(value: Any) -> set[str]:
    if not isinstance(value, list):
        return set()
    return {str(item).strip().lower() for item in value}


def _contains_any(text: str, candidates: list[str]) -> bool:
    return any(candidate in text for candidate in candidates)


def _excluded_evidence_ids(prompt_evidence_pack: dict[str, Any]) -> list[str]:
    summary = prompt_evidence_pack.get("excluded_evidence_summary") or {}
    examples = summary.get("examples") or []
    ids = []
    for item in examples:
        if isinstance(item, dict) and item.get("evidence_id"):
            ids.append(str(item.get("evidence_id")))
    return ids
