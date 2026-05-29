"""
geology_v2.report_renderer

统一渲染 geology_v2 报告文字。

输入：
    report_context:
        report_context_builder.build_geology_v2_report_context 输出。

输出：
    render_geology_v2_report_context:
        工程报告风格文本。

注意：
1. 本模块负责长文本生成；
2. 分析模块不要分散生成大段文字；
3. 不把 GRCI 写成概率；
4. 不把无证据写成无风险；
5. 当前掌子面、已开挖区段、前方预报分开写。
"""

from __future__ import annotations

from typing import Any, Dict, List
from utils.chainage_utils import format_chainage_dk


# ============================================================
# 1. 基础工具
# ============================================================

def _dk(value: Any) -> str:
    return format_chainage_dk(value, unknown="未知里程", prefix="DK")


def _dk_range(start: Any, end: Any) -> str:
    return f"{_dk(start)}～{_dk(end)}"


# ============================================================
# 1. 基础工具
# ============================================================

def _as_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    return {}


def _as_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple) or isinstance(value, set):
        return list(value)
    return [value]


def _safe_text(value: Any, default: str = "暂无有效信息。") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text if text else default


def _section_text(report_context: Dict[str, Any], section_key: str, default: str = "暂无有效信息。") -> str:
    sections = _as_dict(report_context.get("sections"))
    section = _as_dict(sections.get(section_key))
    return _safe_text(section.get("text"), default=default)


def _normalize_note_text(text: str) -> str:
    text = str(text).strip()
    text = text.replace(
        "GRCI 表示地质-施工响应耦合关注度，不表示灾害发生概率。",
        "GRCI 表示复盘窗口内提前地质证据与实际施工响应的对应程度，不表示灾害发生概率或在线预测概率。",
    )
    text = text.replace(
        "GRCI 表示地质-施工响应耦合关注度，不表示灾害发生概率",
        "GRCI 表示复盘窗口内提前地质证据与实际施工响应的对应程度，不表示灾害发生概率或在线预测概率",
    )
    return text


def _section_notes(report_context: Dict[str, Any], section_key: str) -> List[str]:
    sections = _as_dict(report_context.get("sections"))
    section = _as_dict(sections.get(section_key))
    return [
        _normalize_note_text(str(x))
        for x in _as_list(section.get("notes"))
        if str(x).strip()
    ]


def _constraints_text(report_context: Dict[str, Any]) -> str:
    sections = _as_dict(report_context.get("sections"))
    conclusion = _as_dict(sections.get("conclusion"))
    constraints = [str(x) for x in _as_list(conclusion.get("constraints")) if str(x).strip()]

    if not constraints:
        return "结论应依据结构化证据审慎表述，不外推到未覆盖里程或未覆盖时段。"

    return "\n".join([f"- {item}" for item in constraints])


def _metadata_line(report_context: Dict[str, Any]) -> str:
    metadata = _as_dict(report_context.get("metadata"))

    date = metadata.get("date") or metadata.get("report_date") or metadata.get("time_window") or "未指定"

    current_chainage_text = metadata.get("current_chainage_dk")
    if not current_chainage_text:
        current_chainage = metadata.get("current_chainage")
        current_chainage_text = _dk(current_chainage) if current_chainage is not None else "未指定"

    chainage_range_text = metadata.get("chainage_range_text")
    if not chainage_range_text or str(chainage_range_text).strip() in {"", "未指定"}:
        chainage_min = metadata.get("chainage_min")
        chainage_max = metadata.get("chainage_max")
        if chainage_min is not None and chainage_max is not None:
            chainage_range_text = _dk_range(chainage_min, chainage_max)
        else:
            chainage_range_text = "未指定"

    parts = [
        f"报告日期/时间窗：{date}",
        f"当前里程：{current_chainage_text}",
        f"复核范围：{chainage_range_text}",
    ]

    return "；".join(parts) + "。"


# ============================================================
# 2. 主渲染函数
# ============================================================

def render_geology_v2_report_context(
    report_context: Dict[str, Any],
    include_operation: bool = True,
    include_gas: bool = True,
) -> str:
    """
    将 geology_v2_report_context 渲染为报告文本。

    该文本可以：
    1. 直接作为调试报告；
    2. 作为 LLM prompt 中的结构化上下文；
    3. 后续进一步交给大模型润色。

    注意：
        这里是“确定性模板渲染”，不是 LLM 生成。
    """
    if not isinstance(report_context, dict):
        return "地质融合 v2 报告上下文为空，无法生成报告文本。"

    warnings = [str(x) for x in _as_list(report_context.get("warnings")) if str(x).strip()]

    lines: List[str] = []

    lines.append("TBM 地质融合 v2 报告上下文")
    lines.append("=" * 40)
    lines.append(_metadata_line(report_context))
    lines.append("")

    lines.append("一、写作约束")
    lines.append(
        "本报告上下文基于多源地质证据、前方分段剖面和地质-施工响应耦合结果构建。"
        "其中 GRCI 表示复盘窗口内提前地质证据与实际施工响应的对应程度，不表示灾害发生概率或在线预测概率；"
        "缺少证据覆盖时只能说明证据不足，不得表述为无风险或无异常。"
    )
    if warnings:
        lines.append("上下文警告：")
        for item in warnings:
            lines.append(f"- {item}")
    lines.append("")

    if include_operation:
        lines.append("二、基础工况上下文")
        lines.append(_section_text(report_context, "operation", default="本阶段未接入基础工况结构化上下文。"))
        lines.append("")

    lines.append("三、当前掌子面描述")
    lines.append(_section_text(report_context, "current_face", default="当前掌子面描述暂未形成有效结构化结果。"))
    for note in _section_notes(report_context, "current_face"):
        lines.append(f"说明：{note}")
    lines.append("")

    lines.append("四、已开挖区段地质复核")
    lines.append(_section_text(report_context, "excavated_review", default="当前范围未形成可用地质融合状态。"))
    for note in _section_notes(report_context, "excavated_review"):
        lines.append(f"说明：{note}")
    lines.append("")

    lines.append("五、前方 30m 分段提示")
    lines.append(_section_text(report_context, "forward_profile", default="前方地质剖面未形成有效结构化结果。"))
    for note in _section_notes(report_context, "forward_profile"):
        lines.append(f"说明：{note}")
    lines.append("")

    lines.append("六、地质-施工响应耦合分析")
    lines.append(_section_text(report_context, "coupling", default="当前范围未形成地质-施工响应耦合结果。"))
    for note in _section_notes(report_context, "coupling"):
        lines.append(f"说明：{note}")
    lines.append("")

    if include_gas:
        lines.append("七、气体监测上下文")
        lines.append(_section_text(report_context, "gas", default="本阶段未接入气体监测结构化上下文。"))
        lines.append("")

    lines.append("八、结论与建议约束")
    lines.append(_constraints_text(report_context))

    return "\n".join(lines)


def render_prompt_block_from_context(report_context: Dict[str, Any]) -> str:
    """
    输出给 LLM prompt 使用的文本块。
    """
    if not isinstance(report_context, dict):
        return ""

    texts = _as_dict(report_context.get("texts"))
    return _safe_text(texts.get("prompt_block"), default="")