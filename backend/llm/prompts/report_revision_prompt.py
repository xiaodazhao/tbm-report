from __future__ import annotations

import json
from typing import Any

from llm.prompts.report_generation_prompt import (
    FORBIDDEN_EXPRESSIONS,
    METHOD_BOUNDARY_STATEMENTS,
    REQUIRED_SECTIONS,
)


def build_revision_prompt(
    *,
    prompt_evidence_pack: dict[str, Any],
    draft_report: str,
    quality_before_revision: dict[str, Any],
    trace_before_revision: dict[str, Any],
) -> str:
    """Build a constrained revision prompt using Quality/Trace feedback."""
    quality_payload = {
        "score": quality_before_revision.get("score") or quality_before_revision.get("quality_score"),
        "error_type_counts": quality_before_revision.get("error_type_counts", {}),
        "violations_by_error_type": quality_before_revision.get("violations_by_error_type", {}),
        "unsupported_claim_count": quality_before_revision.get("unsupported_claim_count"),
        "grounding_rate": quality_before_revision.get("grounding_rate"),
        "unsupported_claims": [
            item
            for item in (quality_before_revision.get("claim_results") or [])
            if isinstance(item, dict) and not item.get("grounded")
        ],
    }
    trace_payload = {
        "support_type_distribution": trace_before_revision.get("support_type_distribution", {}),
        "unsupported_by_claim_type": trace_before_revision.get("unsupported_by_claim_type", {}),
        "trace_coverage": trace_before_revision.get("trace_coverage"),
    }
    constraints = prompt_evidence_pack.get("generation_constraints") or []
    return "\n".join(
        [
            "你是 TBM 日报修订助手。",
            "任务：根据 Quality / Trace 反馈修订下面的 LLM 初稿，输出完整修订后报告。",
            "",
            "修订规则：",
            "1. 只能删除、降级或改写初稿中不被 Evidence Pack 支撑的内容。",
            "2. 不得新增 Evidence Pack 之外的新事实。",
            "3. 修复 GRCI 概率误用、前方提示写成事实、背景证据写成当日响应、stop_ratio 过度解释等问题。",
            "4. 保留初稿中已经合规且有证据支撑的内容。",
            "5. 章节必须完整，且使用“当前掌子面前方关注提示”。",
            "6. 不要使用风险类标题替代“当前掌子面前方关注提示”。",
            "",
            "必须保留的章节：",
            *[f"- {item}" for item in REQUIRED_SECTIONS],
            "",
            "禁止表达：",
            *[f"- {item}" for item in FORBIDDEN_EXPRESSIONS],
            "",
            "方法边界：",
            *[f"- {item}" for item in METHOD_BOUNDARY_STATEMENTS],
            "",
            "Evidence Pack generation_constraints：",
            *[f"- {item}" for item in constraints],
            "",
            "Quality 反馈：",
            json.dumps(quality_payload, ensure_ascii=False, indent=2, default=str),
            "",
            "Trace 反馈：",
            json.dumps(trace_payload, ensure_ascii=False, indent=2, default=str),
            "",
            "LLM 初稿：",
            draft_report,
            "",
            "请输出完整修订后中文报告正文，不要输出 JSON。",
        ]
    )
