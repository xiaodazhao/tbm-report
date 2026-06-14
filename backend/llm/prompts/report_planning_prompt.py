from __future__ import annotations

import json
from typing import Any

from llm.prompts.report_generation_prompt import (
    FORBIDDEN_EXPRESSIONS,
    METHOD_BOUNDARY_STATEMENTS,
    REQUIRED_SECTIONS,
)


def build_planning_prompt(prompt_evidence_pack: dict[str, Any]) -> str:
    """Build the prompt used to produce a strict report plan JSON."""
    scope = prompt_evidence_pack.get("report_scope") or {}
    payload = {
        "report_scope": {
            "date": scope.get("date"),
            "current_chainage": scope.get("current_chainage"),
            "daily_plc_range": scope.get("daily_plc_range") or scope.get("daily_chainage_raw"),
            "daily_excavated_scope": scope.get("daily_excavated_scope"),
            "forward_scope": scope.get("forward_scope"),
            "local_background_scope": scope.get("local_background_scope"),
        },
        "required_sections": REQUIRED_SECTIONS,
        "forbidden_expressions": FORBIDDEN_EXPRESSIONS,
        "method_boundary_statements": METHOD_BOUNDARY_STATEMENTS,
        "available_evidence_groups": {
            "operation_evidence": bool(prompt_evidence_pack.get("operation_evidence")),
            "gas_evidence": bool(prompt_evidence_pack.get("gas_evidence")),
            "daily_review_evidence": bool(prompt_evidence_pack.get("daily_review_evidence")),
            "forward_attention_evidence": bool(prompt_evidence_pack.get("forward_attention_evidence")),
            "local_background_evidence": bool(prompt_evidence_pack.get("local_background_evidence")),
            "coupling_evidence": bool(prompt_evidence_pack.get("coupling_evidence")),
        },
        "daily_review_cells": _cell_ids(prompt_evidence_pack, "daily_review_evidence"),
        "forward_attention_cells": _cell_ids(prompt_evidence_pack, "forward_attention_evidence"),
        "local_background_cells": _cell_ids(prompt_evidence_pack, "local_background_evidence"),
        "generation_constraints": prompt_evidence_pack.get("generation_constraints") or {},
    }
    return "\n".join(
        [
            "你是 TBM 施工日报的报告规划器。",
            "任务：只根据 Prompt Evidence Pack 生成 report plan JSON，不生成报告正文。",
            "",
            "必须输出一个 JSON object，字段至少包括：",
            "- date",
            "- plan_version",
            "- sections",
            "- global_constraints",
            "- fallback_required",
            "- plan_validation",
            "",
            "每个 sections 元素必须包括：",
            "- section_id",
            "- section_title",
            "- purpose",
            "- allowed_cell_roles",
            "- allowed_metrics",
            "- forbidden_metrics",
            "- must_include_boundary",
            "- forbidden_expressions",
            "- evidence_use_policy",
            "",
            "规划硬约束：",
            "1. 必须包含全部 required_sections。",
            "2. 当前掌子面前方关注提示章节不得允许 RAI 或 GRCI。",
            "3. 只有 daily_review 角色可以使用 GRCI；forward_attention 和 local_background 不得使用 GRCI。",
            "4. local_background 只能作为背景上下文，不能写成当日施工异常判断。",
            "5. 不得引用 excluded evidence。",
            "6. 必须包含 GRCI 不是概率的边界。",
            "7. 必须包含前方关注提示不是已发生事实的边界。",
            "8. 必须包含 daily_excavated_scope 只是 10m cell 对齐复核范围、不是实际推进范围的边界。",
            "9. 如果无法满足约束，应设置 fallback_required=true。",
            "",
            "Evidence Pack 摘要：",
            json.dumps(payload, ensure_ascii=False, indent=2, default=str),
            "",
            "请只输出 JSON，不要输出解释文字。",
        ]
    )


def _cell_ids(prompt_evidence_pack: dict[str, Any], section: str) -> list[str]:
    data = prompt_evidence_pack.get(section) or {}
    cells = data.get("cells") or data.get("key_cells") or data.get("selected_cells") or []
    out = []
    for item in cells:
        if isinstance(item, dict) and item.get("cell_id"):
            out.append(str(item.get("cell_id")))
    return out
