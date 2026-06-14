from __future__ import annotations

import json
from typing import Any

from llm.evidence_pack import render_evidence_pack_text


REQUIRED_SECTIONS = [
    "1. 综合结论摘要",
    "2. 今日施工运行概况",
    "3. PLC 工况统计分析",
    "4. 气体监测分析",
    "5. 已掘区段地质-施工响应复核",
    "6. 当前掌子面前方关注提示",
    "7. 结论与建议",
]

FORBIDDEN_EXPRESSIONS = [
    "将前方关注章节命名为风险类提示",
    "GRCI 与概率绑定的表述",
    "灾害概率",
    "风险概率",
    "前方已经发生",
    "TSP/HSP 结论一定真实",
    "stop_ratio 说明异常原因",
    "excluded_by_distance evidence 支撑正文结论",
]

METHOD_BOUNDARY_STATEMENTS = [
    "只能依据 Prompt Evidence Pack 生成报告，不得补充 Evidence Pack 之外的工程事实。",
    "LLM 不得自行计算 RAI、GRS 或 GRCI。",
    "GRCI 不是灾害概率，不是风险概率，也不是前方风险。",
    "GRCI 只用于具备 GRS、RAI 和 PLC response 的已掘区段复核 cell。",
    "前方关注提示来自 forward_profile / forward_attention_cells，只表示关注或复核，不表示已发生事实。",
    "local_background 只能作为背景地质上下文，不能写成当日施工响应异常。",
    "当前 PLC 字段未区分计划停机与非计划停机，stop_ratio 仅作为施工响应关注信号。",
    "如无当日可用掌子面素描，不把前方证据写成已揭露事实。",
]


def build_generation_prompt(
    prompt_evidence_pack: dict[str, Any],
    report_plan: dict[str, Any] | None = None,
    plan_validation: dict[str, Any] | None = None,
) -> str:
    """Build a strict Evidence-Pack-only report generation prompt."""
    scope = prompt_evidence_pack.get("report_scope") or {}
    excluded = prompt_evidence_pack.get("excluded_evidence_summary") or {}
    safe_excluded_summary = {
        "excluded_evidence_count": excluded.get("excluded_evidence_count"),
        "excluded_by_distance_evidence_count": excluded.get("excluded_by_distance_evidence_count"),
        "excluded_by_missing_geometry_evidence_count": excluded.get("excluded_by_missing_geometry_evidence_count"),
    }
    prompt_payload = {
        "date": scope.get("date"),
        "current_chainage": scope.get("current_chainage"),
        "daily_plc_range": scope.get("daily_plc_range") or scope.get("daily_chainage_raw"),
        "daily_chainage_raw": scope.get("daily_chainage_raw") or scope.get("daily_plc_range"),
        "daily_advance_m": (scope.get("daily_plc_range") or {}).get("daily_advance_m", scope.get("daily_advance_m")),
        "daily_excavated_scope": scope.get("daily_excavated_scope"),
        "forward_scope": scope.get("forward_scope"),
        "local_background_scope": scope.get("local_background_scope"),
        "required_sections": REQUIRED_SECTIONS,
        "forbidden_expressions": FORBIDDEN_EXPRESSIONS,
        "method_boundary_statements": METHOD_BOUNDARY_STATEMENTS,
        "excluded_evidence_summary_counts_only": safe_excluded_summary,
    }
    evidence_text = render_evidence_pack_text(prompt_evidence_pack)
    parts = [
            "你是 TBM 施工日报撰写助手。",
            "任务：只能依据下方 Prompt Evidence Pack 生成 TBM 施工日报。",
            "",
            "硬性约束：",
            "1. 不允许补充 Evidence Pack 之外的工程事实。",
            "2. 不允许自行计算 RAI、GRS、GRCI。",
            "3. 不允许自行筛选 TSP/HSP 或读取原始 evidence_db。",
            "4. 不允许把 GRCI 写成概率、灾害概率、风险概率或前方风险。",
            "5. 不允许把 forward_attention 写成已发生事实。",
            "6. 不允许把 local_background 写成当日施工异常。",
            "7. 不允许把 stop_ratio 高直接解释为异常原因。",
            "8. 不允许引用 excluded evidence 作为正文结论支撑。",
            "9. 证据不足时必须写“未形成判断”或“建议结合现场记录复核”。",
            "10. 统一使用章节名“当前掌子面前方关注提示”，不要使用风险类标题。",
            "11. 不得将 daily_excavated_scope 写成实际推进范围。",
            "12. 不得根据 daily_excavated_scope 自行计算推进量。",
            "13. 实际推进量只能使用 daily_plc_range.daily_advance_m。",
            "14. 实际推进起止只能使用 daily_plc_range.start_chainage 和 daily_plc_range.end_chainage。",
            "15. daily_excavated_scope 只能写作“10m cell 对齐后的已掘复核范围”。",
            "16. 推荐表达：PLC 实测推进范围为 daily_plc_range.start_chainage 至 daily_plc_range.end_chainage，日推进约 daily_plc_range.daily_advance_m m；系统按 10m cell 将已掘复核范围对齐为 daily_excavated_scope.start 至 daily_excavated_scope.end。",
            "",
            "推进范围语义边界：",
            "- daily_plc_range / daily_chainage_raw 表示 PLC 实测当日推进范围。",
            "- daily_advance_m 表示 PLC 实测日推进量。",
            "- daily_excavated_scope 表示 10m cell 对齐后的已掘复核范围，只用于状态建模和区段复核，不等同于实际推进范围。",
            "- 不得用 daily_excavated_scope.start/end 的差值计算日推进量。",
            "",
            "方法边界必须遵守：",
            *[f"- {item}" for item in METHOD_BOUNDARY_STATEMENTS],
            "",
            "输出章节必须包含：",
            *[f"- {item}" for item in REQUIRED_SECTIONS],
            "",
            "禁止表达：",
            *[f"- {item}" for item in FORBIDDEN_EXPRESSIONS],
            "",
            "报告范围与审计摘要：",
            json.dumps(prompt_payload, ensure_ascii=False, indent=2, default=str),
            "",
            evidence_text,
            "",
    ]
    if report_plan:
        parts.extend(
            [
                "LLM Report Plan（必须遵循）：",
                "1. 按照 report_plan.sections 的章节用途、allowed_cell_roles、allowed_metrics 和 forbidden_metrics 撰写。",
                "2. 如果 report_plan 与 Evidence Pack 或硬性约束冲突，以 Evidence Pack 和硬性约束为准。",
                "3. 前方关注章节不得使用 RAI/GRCI；已掘复核章节才可使用 GRCI。",
                "4. local_background 只能作为背景上下文，不能写成当日施工异常。",
                "Plan validation:",
                json.dumps(plan_validation or {}, ensure_ascii=False, indent=2, default=str),
                "Report plan:",
                json.dumps(report_plan, ensure_ascii=False, indent=2, default=str),
                "",
            ]
        )
    parts.append("请输出完整中文报告正文，不要输出 JSON。")
    return "\n".join(parts)
