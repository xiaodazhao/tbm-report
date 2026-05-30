from __future__ import annotations

import re
from typing import Any


BANNED_PHRASES: dict[str, tuple[str, str]] = {
    "灾害概率": ("error", "建议改为“证据融合关注程度”或“关注提示”。"),
    "风险概率": ("error", "建议改为“关注程度”或“复核关注”。"),
    "必然发生": ("error", "建议改为“需关注”或“需现场复核”。"),
    "已证实灾害": ("error", "建议改为“已有证据提示”或“记录显示”。"),
    "确定发生塌方": ("error", "建议改为“存在塌方相关关注提示，需现场复核”。"),
    "突涌水": ("error", "除非输入明确出现，否则不要写该词。"),
    "岩爆": ("error", "除非输入明确出现，否则不要写该词。"),
    "瓦斯突出": ("error", "除非输入明确出现，否则不要写该词。"),
    "防爆措施": ("warning", "建议改为“按现场安全规程复核相关措施”。"),
}

GRCI_RISK_PATTERN = re.compile(
    r"(GRCI.{0,24}(概率|预测|必然|灾害发生)|"
    r"(概率|预测|必然|灾害发生).{0,24}GRCI)"
)

SECTION_TITLES = [
    "综合结论摘要",
    "总体施工运行概况",
    "基础工况统计分析",
    "聚类施工状态与效率分析",
    "当前掌子面描述",
    "已开挖区段地质与响应异常复核",
    "气体监测分析",
    "前方风险提示",
    "结论与建议",
]

STRONG_HAZARD_TERMS = [
    "突涌水",
    "塌方",
    "岩爆",
    "瓦斯突出",
]


def _as_dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return []


def _safe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        x = float(value)
        return x
    except Exception:
        return None


def _add_violation(
    violations: list[dict[str, Any]],
    *,
    type_: str,
    severity: str,
    phrase: str,
    message: str,
    suggestion: str,
) -> None:
    violations.append(
        {
            "type": type_,
            "severity": severity,
            "phrase": phrase,
            "message": message,
            "suggestion": suggestion,
        }
    )


def _get_current_face_context(geology_context: dict | None) -> dict:
    context = _as_dict(geology_context)
    current_face = _as_dict(context.get("current_face"))
    if current_face:
        return current_face
    sections = _as_dict(context.get("sections"))
    return _as_dict(sections.get("current_face"))


def _collect_allowed_hazards(geology_context: dict | None) -> set[str]:
    context = _as_dict(geology_context)
    allowed: set[str] = set()

    current_window_summary = _as_dict(context.get("current_window_summary"))
    for item in _as_list(current_window_summary.get("main_hazards")):
        if item:
            allowed.add(str(item))

    for cell in _as_list(context.get("key_cells")):
        if not isinstance(cell, dict):
            continue
        for item in _as_list(cell.get("main_hazards")):
            if item:
                allowed.add(str(item))

    for segment in _as_list(context.get("forward_segments")):
        if not isinstance(segment, dict):
            continue
        for item in _as_list(segment.get("main_hazards")):
            if item:
                allowed.add(str(item))

    return allowed


def _has_low_coverage_forward_segments(geology_context: dict | None) -> bool:
    context = _as_dict(geology_context)
    for segment in _as_list(context.get("forward_segments")):
        if not isinstance(segment, dict):
            continue
        evidence_count = int(segment.get("evidence_count") or 0)
        confidence = _safe_float(segment.get("confidence"))
        uncertainty = str(segment.get("uncertainty_level") or "").lower()
        if evidence_count <= 1:
            return True
        if confidence is None or confidence < 0.45:
            return True
        if uncertainty in {"high", "unknown"}:
            return True
    return False


def _score_from_violations(violations: list[dict[str, Any]]) -> int:
    score = 100
    for item in violations:
        if item.get("severity") == "error":
            score -= 15
        else:
            score -= 5
    return max(0, score)


def check_report_quality(
    report_text: str,
    llm_summary: dict | None = None,
    geology_context: dict | None = None,
) -> dict:
    text = str(report_text or "")
    context = _as_dict(geology_context)
    summary = _as_dict(llm_summary)
    if not context:
        context = _as_dict(summary.get("geology_v2_context"))

    violations: list[dict[str, Any]] = []
    warnings: list[str] = []

    for phrase, (severity, suggestion) in BANNED_PHRASES.items():
        if phrase in text:
            _add_violation(
                violations,
                type_="banned_phrase",
                severity=severity,
                phrase=phrase,
                message=f"报告中出现禁用或高风险表述：{phrase}",
                suggestion=suggestion,
            )

    current_face = _get_current_face_context(context)
    has_direct_face_observation = bool(current_face.get("has_direct_face_observation"))
    if "当前掌子面揭示" in text and not has_direct_face_observation:
        _add_violation(
            violations,
            type_="spatial_semantics",
            severity="error",
            phrase="当前掌子面揭示",
            message="报告使用了“当前掌子面揭示”，但 geology_context 中没有直接掌子面观测依据。",
            suggestion="改为“当前里程附近已有地质证据提示”或“最近现场素描点记录显示”。",
        )

    for match in GRCI_RISK_PATTERN.finditer(text):
        phrase = match.group(0)
        severity = "error" if "必然" in phrase else "warning"
        _add_violation(
            violations,
            type_="grci_semantics",
            severity=severity,
            phrase=phrase,
            message="GRCI 被表述为概率或预测语义。",
            suggestion="改为“GRCI 为复盘耦合关注指标”。",
        )

    if "前方低风险" in text or "无风险" in text:
        phrase = "前方低风险" if "前方低风险" in text else "无风险"
        severity = "warning"
        message = "前方提示不宜直接写成低风险或无风险。"
        if _has_low_coverage_forward_segments(context):
            message = "前方窗口存在低覆盖或高不确定性分段，不宜直接写成低风险或无风险。"
        _add_violation(
            violations,
            type_="forward_hint",
            severity=severity,
            phrase=phrase,
            message=message,
            suggestion="改为“当前融合关注较低，但不能据此判断为低风险”。",
        )

    allowed_hazards = _collect_allowed_hazards(context)
    for term in STRONG_HAZARD_TERMS:
        if term in text and term not in allowed_hazards:
            _add_violation(
                violations,
                type_="hazard_overreach",
                severity="warning",
                phrase=term,
                message=f"报告出现了证据包中未明确支持的强灾害词：{term}",
                suggestion="删除该词，或改为证据中实际出现的关注表述。",
            )

    missing_sections = [title for title in SECTION_TITLES if title not in text]
    if missing_sections:
        warnings.append(f"报告缺少章节标题：{', '.join(missing_sections)}")
        for title in missing_sections:
            _add_violation(
                violations,
                type_="missing_section",
                severity="warning",
                phrase=title,
                message=f"报告未包含建议章节：{title}",
                suggestion="补齐标准章节结构。",
            )

    score = _score_from_violations(violations)
    error_count = sum(1 for item in violations if item.get("severity") == "error")
    warning_count = sum(1 for item in violations if item.get("severity") == "warning")

    return {
        "ok": error_count == 0 and score >= 80,
        "score": score,
        "violations": violations,
        "warnings": warnings,
        "stats": {
            "report_length": len(text),
            "violation_count": len(violations),
            "error_count": error_count,
            "warning_count": warning_count,
            "required_section_count": len(SECTION_TITLES),
            "missing_section_count": len(missing_sections),
            "allowed_hazard_count": len(allowed_hazards),
        },
    }
