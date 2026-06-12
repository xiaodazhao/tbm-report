from __future__ import annotations

import json
import math
from typing import Any

from llm.prompt_evidence_pack import (
    build_prompt_evidence_pack,
    render_prompt_evidence_pack_text,
)
from llm.summary_contract import build_prompt_payload


def _text(texts: dict, key: str, default: str = "无可用信息。") -> str:
    """Safely get text block from prompt payload."""
    value = texts.get(key, "")
    if value is None:
        return default
    value = str(value).strip()
    return value if value else default


def _as_dict(value: Any) -> dict:
    """Return value as dict if possible."""
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list:
    """Return value as list if possible."""
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return []


def _safe_str(value: Any, default: str = "") -> str:
    """Convert value to stripped string safely."""
    if value is None:
        return default
    text = str(value).strip()
    return text if text else default


def _safe_float(value: Any, default: float | None = None) -> float | None:
    """Convert to finite float safely."""
    try:
        if value is None:
            return default
        x = float(value)
        if not math.isfinite(x):
            return default
        return x
    except Exception:
        return default


def _fmt_float(value: Any, ndigits: int = 2, default: str = "未知") -> str:
    """Format numeric value safely."""
    x = _safe_float(value)
    if x is None:
        return default
    return f"{x:.{ndigits}f}"


def _fmt_int(value: Any, default: str = "未知") -> str:
    """Format integer-like value safely."""
    x = _safe_float(value)
    if x is None:
        return default
    return str(int(round(x)))


def _compact_join(items: Any, sep: str = "、", max_items: int = 8, default: str = "未明确") -> str:
    """Join list-like values with de-duplication."""
    if items is None:
        return default

    if isinstance(items, str):
        items = [x.strip() for x in items.replace(",", "、").split("、") if x.strip()]
    elif isinstance(items, dict):
        items = list(items.keys())
    elif not isinstance(items, (list, tuple, set)):
        items = [items]

    out: list[str] = []
    seen = set()
    for item in items:
        text = str(item).strip()
        if not text or text in {"nan", "None", "null", "[]", "{}"}:
            continue
        if text in seen:
            continue
        seen.add(text)
        out.append(text)
        if len(out) >= max_items:
            break

    return sep.join(out) if out else default


def _shorten(text: Any, max_chars: int = 500) -> str:
    """Shorten long text for prompt fallback."""
    if text is None:
        return ""
    s = str(text).strip()
    if len(s) <= max_chars:
        return s
    return s[:max_chars].rstrip() + "……"


def _find_first_dict_with_keys(obj: Any, required_any: list[str], max_depth: int = 5) -> dict:
    """Search nested object for first dict containing any required key."""
    if max_depth < 0:
        return {}

    if isinstance(obj, dict):
        if any(key in obj for key in required_any):
            return obj
        for value in obj.values():
            found = _find_first_dict_with_keys(value, required_any, max_depth=max_depth - 1)
            if found:
                return found

    if isinstance(obj, list):
        for value in obj:
            found = _find_first_dict_with_keys(value, required_any, max_depth=max_depth - 1)
            if found:
                return found

    return {}


def _find_first_list_of_dicts(obj: Any, required_any: list[str], max_depth: int = 5) -> list[dict]:
    """Search nested object for first list of dicts containing any required key."""
    if max_depth < 0:
        return []

    if isinstance(obj, list):
        dicts = [x for x in obj if isinstance(x, dict)]
        if dicts and any(any(key in d for key in required_any) for d in dicts):
            return dicts
        for value in obj:
            found = _find_first_list_of_dicts(value, required_any, max_depth=max_depth - 1)
            if found:
                return found

    if isinstance(obj, dict):
        for value in obj.values():
            found = _find_first_list_of_dicts(value, required_any, max_depth=max_depth - 1)
            if found:
                return found

    return []


def _extract_position(llm_summary: dict) -> dict:
    """Extract current position from available structured summaries."""
    context = _as_dict(llm_summary.get("geology_v2_context"))
    current_position = _as_dict(context.get("current_position"))
    if current_position:
        return current_position

    digital_twin = _as_dict(llm_summary.get("digital_twin_state"))
    position_state = _as_dict(digital_twin.get("position_state"))

    if position_state:
        return {
            "current_chainage": position_state.get("current_chainage"),
            "current_chainage_dk": position_state.get("current_chainage_dk"),
            "start_chainage_dk": position_state.get("start_chainage_dk"),
            "end_chainage_dk": position_state.get("end_chainage_dk"),
            "advance_length": position_state.get("advance_length"),
        }

    cst_state = _as_dict(llm_summary.get("cst_state"))
    pos = _find_first_dict_with_keys(
        cst_state,
        ["current_chainage", "current_chainage_dk", "end_chainage_dk"],
    )
    return pos


def _extract_geology_summary_from_v2(llm_summary: dict) -> dict:
    """Extract high-level geology_v2 summary."""
    data_summary = _as_dict(llm_summary.get("geology_v2_data_summary"))
    context = _as_dict(llm_summary.get("geology_v2_context"))

    geo_summary = _as_dict(context.get("current_window_summary"))
    if not geo_summary:
        geo_summary = _as_dict(data_summary.get("geo_states_summary"))
    if not geo_summary:
        geo_summary = _find_first_dict_with_keys(
            context,
            [
                "cell_count",
                "evidence_cell_count",
                "GRS_geo_base_max",
                "grade_counts",
                "main_hazard_counts",
                "attention_level_counts",
            ],
        )

    return geo_summary


def _extract_key_cells_from_v2(llm_summary: dict, max_cells: int = 5) -> list[dict]:
    """Extract key geology cells from geology_v2_context if present."""
    context = _as_dict(llm_summary.get("geology_v2_context"))

    direct = context.get("key_cells")
    if isinstance(direct, list):
        candidates = [x for x in direct if isinstance(x, dict)]
    else:
        candidates = []

    # Common possible names from report_context builders.
    if not candidates:
        for key in [
            "focus_cells",
            "important_cells",
            "top_cells",
            "cell_summaries",
            "geo_state_cells",
            "current_window_cells",
            "cells",
        ]:
            value = context.get(key)
            if isinstance(value, list):
                candidates = [x for x in value if isinstance(x, dict)]
                if candidates:
                    break

    if not candidates:
        candidates = _find_first_list_of_dicts(
            context,
            [
                "cell_id",
                "cell_start_dk",
                "cell_end_dk",
                "range_dk",
                "GRS_geo_base",
                "main_hazards",
                "fused_grade",
            ],
        )

    # Sort by available attention score if possible.
    def _score(row: dict) -> float:
        for key in [
            "GRS_geo_base",
            "grs_geo_base",
            "GRS",
            "attention_score",
            "geo_attention_score",
            "confidence",
        ]:
            val = _safe_float(row.get(key))
            if val is not None:
                return val
        return 0.0

    candidates = sorted(candidates, key=_score, reverse=True)

    out = []
    for row in candidates[:max_cells]:
        out.append(row)
    return out


def _extract_forward_segments_from_v2(llm_summary: dict, max_segments: int = 6) -> list[dict]:
    """Extract forward profile segments from geology_v2_forward_profile/context."""
    forward = llm_summary.get("geology_v2_forward_profile")
    context = _as_dict(llm_summary.get("geology_v2_context"))

    direct = context.get("forward_segments")
    if isinstance(direct, list):
        candidates: list[dict] = [x for x in direct if isinstance(x, dict)]
    else:
        candidates = []

    if not candidates and isinstance(forward, list):
        candidates = [x for x in forward if isinstance(x, dict)]
    elif not candidates and isinstance(forward, dict):
        for key in [
            "segments",
            "forward_segments",
            "profile",
            "items",
            "cells",
            "forward_profile",
        ]:
            value = forward.get(key)
            if isinstance(value, list):
                candidates = [x for x in value if isinstance(x, dict)]
                if candidates:
                    break
        if not candidates and any(
            key in forward
            for key in [
                "relative_range",
                "relative_start_m",
                "forward_start_dk",
                "attention_level",
                "main_hazards",
            ]
        ):
            candidates = [forward]

    if not candidates:
        for key in [
            "forward_profile",
            "forward_cells",
            "forward_items",
        ]:
            value = context.get(key)
            if isinstance(value, list):
                candidates = [x for x in value if isinstance(x, dict)]
                if candidates:
                    break

    if not candidates:
        candidates = _find_first_list_of_dicts(
            context,
            [
                "relative_range",
                "relative_start_m",
                "relative_end_m",
                "forward_start_dk",
                "forward_end_dk",
                "attention_level",
                "main_hazards",
            ],
        )

    return candidates[:max_segments]


def _extract_coupling_structured(llm_summary: dict) -> dict:
    """Extract coupling summary from old coupling chain and/or geology_v2 summary."""
    coupling_summary = _as_dict(llm_summary.get("coupling_summary"))
    if coupling_summary:
        return coupling_summary

    data_summary = _as_dict(llm_summary.get("geology_v2_data_summary"))
    coupled_summary = _as_dict(data_summary.get("coupled_summary"))
    return coupled_summary


def _extract_source_trace_summary_from_v2(llm_summary: dict) -> dict:
    """Extract top-level source trace summary from geology_v2_context."""
    context = _as_dict(llm_summary.get("geology_v2_context"))
    summary = _as_dict(context.get("source_trace_summary"))
    if summary:
        return summary
    return {}


def _format_source_trace_items(source_trace: Any, max_items: int = 2) -> str:
    """Format a short source trace summary for prompt use."""
    traces = [item for item in _as_list(source_trace) if isinstance(item, dict)]
    if not traces:
        return "证据来源摘要未展开"

    parts: list[str] = []
    for item in traces[:max_items]:
        source_type = _safe_str(item.get("source_type"), "未知来源")
        report_id = _safe_str(item.get("report_id"))
        excerpt = _shorten(
            item.get("raw_text_excerpt") or item.get("raw_text_snippet") or "",
            max_chars=80,
        )
        head = source_type if not report_id else f"{source_type}/{report_id}"
        if excerpt:
            parts.append(f"{head}: {excerpt}")
        else:
            parts.append(head)
    return "；".join(parts) if parts else "证据来源摘要未展开"


def _format_key_cell(row: dict) -> str:
    """Format one key geology cell into controlled prompt text."""
    range_dk = (
        row.get("range_dk")
        or row.get("cell_range_dk")
        or row.get("segment")
        or row.get("cell_label_dk")
        or row.get("cell_id")
        or "未知区段"
    )

    grade = (
        row.get("fused_grade")
        or row.get("grade")
        or row.get("grade_mode")
        or row.get("main_grade")
        or "未明确"
    )

    hazards = (
        row.get("main_hazards")
        or row.get("hazards")
        or row.get("hazard_tags")
        or row.get("main_hazard_tags")
        or row.get("hazard")
        or []
    )

    grs = (
        row.get("GRS_geo_base")
        or row.get("grs_geo_base")
        or row.get("GRS")
        or row.get("geo_attention_score")
        or row.get("attention_score")
    )

    confidence = (
        row.get("confidence")
        or row.get("fusion_confidence")
        or row.get("confidence_score")
        or row.get("source_confidence")
    )

    uncertainty = (
        row.get("uncertainty")
        or row.get("uncertainty_level")
        or row.get("evidence_uncertainty")
        or "未明确"
    )

    conflict = (
        row.get("conflict")
        or row.get("conflict_level")
        or row.get("evidence_conflict")
        or "未明确"
    )

    sources = (
        row.get("source_types")
        or row.get("sources")
        or row.get("active_sources")
        or row.get("source_summary")
        or []
    )

    return (
        f"- {range_dk}：围岩等级={grade}；"
        f"主要关注={_compact_join(hazards, max_items=6)}；"
        f"GRS_geo_base={_fmt_float(grs)}；"
        f"融合置信度={_fmt_float(confidence)}；"
        f"不确定性={uncertainty}；"
        f"证据冲突={conflict}；"
        f"证据来源={_compact_join(sources, max_items=5)}。"
    )


def _format_forward_segment(row: dict, index: int) -> str:
    """Format one forward segment into controlled prompt text."""
    rel = (
        row.get("relative_range")
        or row.get("range_relative")
        or row.get("relative_label")
        or None
    )

    if not rel:
        rs = row.get("relative_start_m", row.get("start_rel_m", row.get("start_m")))
        re = row.get("relative_end_m", row.get("end_rel_m", row.get("end_m")))
        if rs is not None and re is not None:
            rel = f"{_fmt_int(rs)}-{_fmt_int(re)}m"
        else:
            rel = f"分段{index + 1}"

    dk_range = (
        row.get("range_dk")
        or row.get("forward_range_dk")
        or row.get("cell_range_dk")
        or None
    )
    if not dk_range:
        start_dk = row.get("forward_start_dk") or row.get("start_dk") or row.get("cell_start_dk")
        end_dk = row.get("forward_end_dk") or row.get("end_dk") or row.get("cell_end_dk")
        if start_dk or end_dk:
            dk_range = f"{start_dk or '未知'}～{end_dk or '未知'}"
        else:
            dk_range = "未知里程范围"

    level = (
        row.get("attention_level")
        or row.get("forward_attention_level")
        or row.get("risk_level")
        or row.get("level")
        or "未明确"
    )

    hazards = (
        row.get("main_hazards")
        or row.get("hazards")
        or row.get("hazard_tags")
        or row.get("forward_main_hazard_tags")
        or []
    )

    evidence_count = (
        row.get("evidence_count")
        or row.get("forward_evidence_count")
        or row.get("source_count")
        or row.get("active_source_count")
    )

    sources = (
        row.get("source_types")
        or row.get("forward_source_types")
        or row.get("sources")
        or []
    )

    return (
        f"- 前方{rel}（{dk_range}）：关注等级={level}；"
        f"主要关注={_compact_join(hazards, max_items=6)}；"
        f"证据数量={_fmt_int(evidence_count)}；"
        f"来源={_compact_join(sources, max_items=5)}。"
    )


def build_geology_v2_structured_prompt_block(llm_summary: dict) -> str:
    """Build a structured geology evidence package for the LLM.

    这个函数是新的核心入口：
    - 优先使用 geology_v2_context / geology_v2_data_summary / geology_v2_forward_profile；
    - 不把 geology_v2_prompt_block 当作主要输入；
    - 文本只作为兜底提示，避免“二次改写半成品报告”。
    """
    if not isinstance(llm_summary, dict):
        return "未提供 geology_v2 结构化结果。"

    context = _as_dict(llm_summary.get("geology_v2_context"))
    data_summary = _as_dict(llm_summary.get("geology_v2_data_summary"))
    v2_texts = _as_dict(llm_summary.get("geology_v2_texts"))

    has_structured = bool(context or data_summary or llm_summary.get("geology_v2_forward_profile"))
    if not has_structured:
        fallback = (
            str(llm_summary.get("geology_v2_prompt_block", "") or "").strip()
            or str(v2_texts.get("prompt_block", "") or "").strip()
        )
        if fallback:
            return (
                "未检测到完整 geology_v2 结构化对象，仅提供自然语言兜底摘要。"
                "使用该摘要时必须保持审慎表述，不能将其写成现场确定事实。\n"
                + _shorten(fallback, max_chars=1800)
            )
        return "未提供 geology_v2 结构化结果。"

    position = _extract_position(llm_summary)
    geo_summary = _extract_geology_summary_from_v2(llm_summary)
    key_cells = _extract_key_cells_from_v2(llm_summary, max_cells=5)
    forward_segments = _extract_forward_segments_from_v2(llm_summary, max_segments=6)
    coupling = _extract_coupling_structured(llm_summary)

    normalized_summary = _as_dict(data_summary.get("normalized_summary"))
    forward_profile_summary = _as_dict(data_summary.get("forward_profile_summary"))

    current_dk = (
        position.get("current_chainage_dk")
        or context.get("current_chainage_dk")
        or "未知里程"
    )

    cell_count = (
        geo_summary.get("cell_count")
        or geo_summary.get("total_cell_count")
        or geo_summary.get("current_window_cell_count")
    )
    evidence_cell_count = (
        geo_summary.get("evidence_cell_count")
        or geo_summary.get("covered_cell_count")
        or geo_summary.get("has_evidence_cell_count")
    )

    grade_counts = (
        geo_summary.get("grade_counts")
        or geo_summary.get("fused_grade_counts")
        or geo_summary.get("grade_distribution")
        or {}
    )

    main_hazards = (
        geo_summary.get("main_hazard_counts")
        or geo_summary.get("main_hazards")
        or geo_summary.get("hazard_counts")
        or {}
    )

    attention_counts = (
        geo_summary.get("attention_level_counts")
        or geo_summary.get("grs_level_counts")
        or geo_summary.get("level_counts")
        or {}
    )

    lines: list[str] = []

    lines.append("【地质融合结构化证据包】")
    lines.append("说明：以下为结构化地质证据包，地质相关报告内容应优先依据本证据包，而不是直接复述自然语言摘要。")
    lines.append("解释约束：关注等级表示证据融合关注程度，不等同于灾害发生概率；前方提示不是当前掌子面已经发生的事实；无证据覆盖不得写成无风险。")
    lines.append("")

    lines.append("1. 当前空间位置")
    lines.append(f"- 当前掌子面里程：{current_dk}")
    if position.get("start_chainage_dk") or position.get("end_chainage_dk"):
        lines.append(
            f"- 本周期推进范围：{position.get('start_chainage_dk', '未知')}～"
            f"{position.get('end_chainage_dk', '未知')}；"
            f"推进长度={_fmt_float(position.get('advance_length'), 1)}m。"
        )

    lines.append("")
    lines.append("2. geology_v2 证据覆盖概况")
    lines.append(
        f"- 当前范围 cell 数：{_fmt_int(cell_count)}；"
        f"有证据覆盖 cell 数：{_fmt_int(evidence_cell_count)}。"
    )
    if grade_counts:
        lines.append(f"- 围岩等级分布：{_compact_join(grade_counts, max_items=8)}。")
    if main_hazards:
        lines.append(f"- 主要关注类型：{_compact_join(main_hazards, max_items=8)}。")
    if attention_counts:
        lines.append(f"- 关注等级统计：{_compact_join(attention_counts, max_items=8)}。")
    if normalized_summary:
        lines.append(
            f"- 可用证据数量：{_fmt_int(normalized_summary.get('evidence_count'))}；"
            f"来源类型：{_compact_join(normalized_summary.get('source_type_counts', {}), max_items=8)}；"
            f"空间类型：{_compact_join(normalized_summary.get('spatial_type_counts', {}), max_items=8)}。"
        )

    lines.append("")
    lines.append("3. 当前范围关键 cell")
    if key_cells:
        for row in key_cells:
            lines.append(_format_key_cell(row))
    else:
        lines.append("- 未提供关键 cell 明细；报告中只能使用整体概况，不得编造具体区段。")

    lines.append("")
    lines.append("4. 前方窗口结构化提示")
    if forward_segments:
        for i, row in enumerate(forward_segments):
            lines.append(_format_forward_segment(row, i))
    else:
        # forward_profile_summary may still have minimal info.
        if forward_profile_summary:
            lines.append(
                f"- 前方窗口摘要：{json.dumps(forward_profile_summary, ensure_ascii=False)}"
            )
        else:
            lines.append("- 未提供前方分段结构化结果；不得自行编造前方分段风险。")
    lines.append("- 前方窗口写作要求：只能写“关注提示、需监测、建议核查”，不得写成当前已经发生或必然发生。")

    lines.append("")
    lines.append("5. 地质-施工响应耦合复盘口径")
    if coupling:
        lines.append(
            f"- GRS_mean={_fmt_float(coupling.get('GRS_mean'))}，"
            f"GRS_max={_fmt_float(coupling.get('GRS_max'))}，"
            f"RAI_mean={_fmt_float(coupling.get('RAI_mean'))}，"
            f"RAI_max={_fmt_float(coupling.get('RAI_max'))}，"
            f"GRCI_mean={_fmt_float(coupling.get('GRCI_mean'))}，"
            f"GRCI_max={_fmt_float(coupling.get('GRCI_max'))}。"
        )
        if coupling.get("summary_text"):
            lines.append(f"- 耦合摘要：{_shorten(coupling.get('summary_text'), 300)}")
        if coupling.get("level_counts"):
            lines.append(f"- 耦合等级统计：{_compact_join(coupling.get('level_counts'), max_items=8)}。")
        if coupling.get("class_counts"):
            lines.append(f"- 耦合类型统计：{_compact_join(coupling.get('class_counts'), max_items=8)}。")
    else:
        lines.append("- 未提供 GRCI 结构化结果；不得自行解释地质-施工响应耦合。")

    lines.append("- GRCI 写作要求：GRCI 是复盘耦合关注指标，不是预测概率或灾害概率。")

    lines.append("")
    lines.append("6. 自然语言摘要使用限制")
    brief = str(v2_texts.get("geo_brief_text", "") or "").strip()
    forward_text = str(v2_texts.get("forward_text", "") or "").strip()
    if brief:
        lines.append(f"- 已开挖地质摘要兜底文本：{_shorten(brief, 500)}")
    if forward_text:
        lines.append(f"- 前方提示兜底文本：{_shorten(forward_text, 500)}")
    lines.append("- 上述自然语言摘要仅作表达兜底；若与结构化证据包冲突，以结构化证据包为准。")

    return "\n".join(lines)


def build_plc_structured_prompt_block(llm_summary: dict) -> str:
    """Build a concise PLC structured-evidence block without exposing raw tables."""
    if not isinstance(llm_summary, dict):
        return "未提供 PLC 结构化状态证据。"

    plc_quality_report = _as_dict(llm_summary.get("plc_quality_report"))
    operation_context = _as_dict(llm_summary.get("operation_context"))
    cluster_context = _as_dict(llm_summary.get("cluster_context"))
    gas_context = _as_dict(llm_summary.get("gas_context"))
    cell_response_summary = _as_dict(llm_summary.get("cell_response_summary"))

    if not any([plc_quality_report, operation_context, cluster_context, gas_context, cell_response_summary]):
        return "未提供 PLC 结构化状态证据。"

    lines = ["【PLC 结构化状态证据】"]

    if plc_quality_report:
        time_info = _as_dict(plc_quality_report.get("time"))
        chainage_info = _as_dict(plc_quality_report.get("chainage"))
        lines.append(
            f"- 数据质量：样本数={plc_quality_report.get('row_count', 0)}，"
            f"时间列={time_info.get('time_col') or '未知'}，"
            f"里程列={chainage_info.get('chainage_col') or '未知'}，"
            f"主 warnings={_compact_join(plc_quality_report.get('warnings', []), max_items=4)}。"
        )
        lines.append(
            "- 若 plc_quality_report 存在 warnings，施工响应解释必须写“需结合数据质量谨慎解释”。"
        )

    if operation_context:
        op_summary = _as_dict(operation_context.get("operation_mode_summary"))
        lines.append(
            f"- 基础工况：主导工况={op_summary.get('dominant_mode_cn') or op_summary.get('dominant_mode') or '暂无'}，"
            f"工作={op_summary.get('work_total_min', 0)} min，停机={op_summary.get('stop_total_min', 0)} min，"
            f"异常扭矩={op_summary.get('abnormal_total_min', 0)} min。"
        )
        lines.append("- operation_mode 是基础工况，不等同于 cluster_state。")

    if cluster_context:
        cluster_quality = _as_dict(cluster_context.get("cluster_quality"))
        lines.append(
            f"- 聚类状态：状态数={cluster_context.get('n_states', 0)}，"
            f"有效样本={cluster_quality.get('valid_sample_count', 0)}，"
            f"稳定性={'足够' if cluster_quality.get('is_stable_enough') else '有限'}。"
        )
        lines.append("- cluster_state 是施工参数聚类状态，不等同于真实地质状态。")

    if gas_context:
        exceed_summary = _as_dict(gas_context.get("exceed_summary"))
        gas_summaries = gas_context.get("gas_summaries", []) or []
        caution_types = sorted(
            {
                str(item.get("gas"))
                for item in gas_summaries
                if item.get("field_type_guess") in {"alarm_flag", "unknown"}
            }
        )
        lines.append(
            f"- 气体状态：超阈值字段={_compact_join(exceed_summary.get('exceed_gases', []), max_items=6)}，"
            f"超阈值事件总数={exceed_summary.get('exceed_event_count_total', 0)}。"
        )
        if caution_types:
            lines.append(
                f"- 以下气体字段存在 alarm_flag/unknown 语义，禁止写成确定浓度超限：{_compact_join(caution_types, max_items=8)}。"
            )

    if cell_response_summary:
        lines.append(
            f"- Cell 响应摘要：cell 总数={cell_response_summary.get('cell_count', 0)}，"
            f"高响应 cell 数={cell_response_summary.get('high_response_cell_count', 0)}。"
        )
        lines.append("- RAI_proxy 只是 PLC 侧响应异常预览，不替代正式 RAI/GRCI。")

    return "\n".join(lines)


def _format_key_cell(row: dict) -> str:
    """Format one key geology cell into controlled prompt text."""
    range_dk = (
        row.get("range_dk")
        or row.get("cell_range_dk")
        or row.get("segment")
        or row.get("cell_label_dk")
        or row.get("cell_id")
        or "未知区段"
    )
    grade = (
        row.get("fused_grade")
        or row.get("grade")
        or row.get("grade_mode")
        or row.get("main_grade")
        or "未明确"
    )
    hazards = (
        row.get("main_hazards")
        or row.get("hazards")
        or row.get("hazard_tags")
        or row.get("main_hazard_tags")
        or row.get("hazard")
        or []
    )
    grs = (
        row.get("GRS_geo_base")
        or row.get("grs_geo_base")
        or row.get("GRS")
        or row.get("geo_attention_score")
        or row.get("attention_score")
    )
    confidence = (
        row.get("confidence")
        or row.get("fusion_confidence")
        or row.get("confidence_score")
        or row.get("source_confidence")
    )
    uncertainty = (
        row.get("uncertainty")
        or row.get("uncertainty_level")
        or row.get("evidence_uncertainty")
        or "未明确"
    )
    conflict = (
        row.get("conflict")
        or row.get("conflict_level")
        or row.get("evidence_conflict")
        or "未明确"
    )
    sources = (
        row.get("source_types")
        or row.get("sources")
        or row.get("active_sources")
        or row.get("source_summary")
        or []
    )
    source_trace_text = _format_source_trace_items(row.get("source_trace"), max_items=3)
    return (
        f"- {range_dk}：围岩等级={grade}；"
        f"主要关注={_compact_join(hazards, max_items=6)}；"
        f"GRS_geo_base={_fmt_float(grs)}；"
        f"融合置信度={_fmt_float(confidence)}；"
        f"不确定性={uncertainty}；"
        f"证据冲突={conflict}；"
        f"来源类型={_compact_join(sources, max_items=5)}；"
        f"来源摘要={source_trace_text}。"
    )


def _format_forward_segment(row: dict, index: int) -> str:
    """Format one forward segment into controlled prompt text."""
    rel = (
        row.get("relative_range")
        or row.get("range_relative")
        or row.get("relative_label")
        or None
    )
    if not rel:
        rs = row.get("relative_start_m", row.get("start_rel_m", row.get("start_m")))
        re = row.get("relative_end_m", row.get("end_rel_m", row.get("end_m")))
        if rs is not None and re is not None:
            rel = f"{_fmt_int(rs)}-{_fmt_int(re)}m"
        else:
            rel = f"分段{index + 1}"

    dk_range = (
        row.get("range_dk")
        or row.get("forward_range_dk")
        or row.get("cell_range_dk")
        or None
    )
    if not dk_range:
        start_dk = row.get("forward_start_dk") or row.get("start_dk") or row.get("cell_start_dk")
        end_dk = row.get("forward_end_dk") or row.get("end_dk") or row.get("cell_end_dk")
        if start_dk or end_dk:
            dk_range = f"{start_dk or '未知'}～{end_dk or '未知'}"
        else:
            dk_range = "未知里程范围"

    level = (
        row.get("attention_level")
        or row.get("forward_attention_level")
        or row.get("risk_level")
        or row.get("level")
        or "未明确"
    )
    hazards = (
        row.get("main_hazards")
        or row.get("hazards")
        or row.get("hazard_tags")
        or row.get("forward_main_hazard_tags")
        or []
    )
    evidence_count = (
        row.get("evidence_count")
        or row.get("forward_evidence_count")
        or row.get("source_count")
        or row.get("active_source_count")
    )
    sources = (
        row.get("source_types")
        or row.get("forward_source_types")
        or row.get("sources")
        or []
    )
    confidence = (
        row.get("confidence")
        or row.get("confidence_score")
        or row.get("forward_confidence")
    )
    uncertainty = (
        row.get("uncertainty_level")
        or row.get("uncertainty")
        or row.get("forward_uncertainty_level")
        or "未知"
    )
    source_trace_text = _format_source_trace_items(row.get("source_trace"), max_items=2)
    return (
        f"- 前方{rel}（{dk_range}）：关注等级={level}；"
        f"主要关注={_compact_join(hazards, max_items=6)}；"
        f"证据数量={_fmt_int(evidence_count)}；"
        f"来源类型={_compact_join(sources, max_items=5)}；"
        f"置信度={_fmt_float(confidence)}；"
        f"不确定性={uncertainty}；"
        f"来源摘要={source_trace_text}。"
    )


def build_geology_v2_structured_prompt_block(llm_summary: dict) -> str:
    """Build a structured geology evidence package for the LLM."""
    if not isinstance(llm_summary, dict):
        return "未提供 geology_v2 结构化结果。"

    context = _as_dict(llm_summary.get("geology_v2_context"))
    data_summary = _as_dict(llm_summary.get("geology_v2_data_summary"))
    v2_texts = _as_dict(llm_summary.get("geology_v2_texts"))

    has_structured = bool(context or data_summary or llm_summary.get("geology_v2_forward_profile"))
    if not has_structured:
        fallback = (
            str(llm_summary.get("geology_v2_prompt_block", "") or "").strip()
            or str(v2_texts.get("prompt_block", "") or "").strip()
        )
        if fallback:
            return (
                "未检测到完整 geology_v2 结构化对象，仅提供自然语言兜底摘要。"
                "使用该摘要时必须保持审慎表述，不得写成当前已证实事实。\n"
                + _shorten(fallback, max_chars=1800)
            )
        return "未提供 geology_v2 结构化结果。"

    position = _extract_position(llm_summary)
    geo_summary = _extract_geology_summary_from_v2(llm_summary)
    key_cells = _extract_key_cells_from_v2(llm_summary, max_cells=5)
    forward_segments = _extract_forward_segments_from_v2(llm_summary, max_segments=6)
    source_trace_summary = _extract_source_trace_summary_from_v2(llm_summary)
    coupling = _extract_coupling_structured(llm_summary)

    normalized_summary = _as_dict(data_summary.get("normalized_summary"))
    forward_profile_summary = _as_dict(data_summary.get("forward_profile_summary"))
    structured_warnings = [item for item in _as_list(context.get("structured_warnings")) if item]

    metadata = _as_dict(context.get("metadata"))
    current_dk = (
        position.get("current_chainage_dk")
        or metadata.get("current_chainage_dk")
        or "未知里程"
    )
    cell_count = (
        geo_summary.get("cell_count")
        or geo_summary.get("total_cell_count")
        or geo_summary.get("current_window_cell_count")
    )
    evidence_cell_count = (
        geo_summary.get("evidence_cell_count")
        or geo_summary.get("covered_cell_count")
        or geo_summary.get("has_evidence_cell_count")
    )
    grade_counts = (
        geo_summary.get("grade_distribution")
        or geo_summary.get("grade_counts")
        or geo_summary.get("fused_grade_counts")
        or {}
    )
    main_hazards = (
        geo_summary.get("main_hazards")
        or geo_summary.get("hazard_counts")
        or geo_summary.get("main_hazard_counts")
        or {}
    )
    attention_counts = (
        geo_summary.get("attention_level_counts")
        or geo_summary.get("grs_level_counts")
        or geo_summary.get("level_counts")
        or {}
    )

    lines: list[str] = []
    lines.append("【地质融合结构化证据包】")
    lines.append("说明：以下为 geology_v2 结构化地质证据包，地质相关报告内容应优先依据本证据包，而不是复写自然语言摘要。")
    lines.append("解释约束：关注等级表示证据融合关注程度，不等同于灾害发生概率。")
    lines.append("解释约束：前方提示不是当前掌子面已经发生的事实。")
    lines.append("解释约束：GRCI 是复盘耦合关注指标，不是预测概率。")
    lines.append("解释约束：无证据覆盖不得写成无风险。")
    lines.append("解释约束：当前掌子面揭示只能来自明确的现场素描或掌子面地质编录。")
    lines.append("解释约束：source_trace 只是证据来源摘要，不可超出原文含义。")
    lines.append("")

    lines.append("1. 当前空间位置")
    lines.append(f"- 当前掌子面里程：{current_dk}")
    if position.get("review_back_m") is not None or position.get("review_forward_m") is not None:
        lines.append(
            f"- 当前复核窗口：后方{_fmt_float(position.get('review_back_m'), 0)}m，"
            f"前方{_fmt_float(position.get('review_forward_m'), 0)}m。"
        )

    lines.append("")
    lines.append("2. 当前窗口证据覆盖概况")
    lines.append(
        f"- 当前窗口 cell 数={_fmt_int(cell_count)}；"
        f"有证据覆盖 cell 数={_fmt_int(evidence_cell_count)}。"
    )
    if grade_counts:
        lines.append(f"- 围岩等级分布：{_compact_join(grade_counts, max_items=8)}。")
    if main_hazards:
        lines.append(f"- 主要关注类型：{_compact_join(main_hazards, max_items=8)}。")
    if attention_counts:
        lines.append(f"- 关注等级统计：{_compact_join(attention_counts, max_items=8)}。")
    if source_trace_summary:
        lines.append(
            f"- 来源摘要总览：trace_available={source_trace_summary.get('trace_available')}；"
            f"traced_evidence_count={_fmt_int(source_trace_summary.get('traced_evidence_count'))}；"
            f"report_id_count={_fmt_int(source_trace_summary.get('report_id_count'))}；"
            f"source_type_counts={_compact_join(source_trace_summary.get('source_type_counts', {}), max_items=8)}。"
        )
    if normalized_summary:
        lines.append(
            f"- 可用证据数量={_fmt_int(normalized_summary.get('evidence_count'))}；"
            f"来源类型={_compact_join(normalized_summary.get('source_type_counts', {}), max_items=8)}；"
            f"空间类型={_compact_join(normalized_summary.get('spatial_type_counts', {}), max_items=8)}。"
        )

    lines.append("")
    lines.append("3. 当前里程附近关键 cell")
    if key_cells:
        for row in key_cells:
            lines.append(_format_key_cell(row))
    else:
        lines.append("- 未提供关键 cell 明细；只能写整体概况，不得编造具体区段。")

    lines.append("")
    lines.append("4. 前方分段提示")
    if forward_segments:
        for i, row in enumerate(forward_segments):
            lines.append(_format_forward_segment(row, i))
    elif forward_profile_summary:
        lines.append(f"- 前方分段摘要：{json.dumps(forward_profile_summary, ensure_ascii=False)}")
    else:
        lines.append("- 未提供前方分段结构化结果，不得自行编造前方分段提示。")
    lines.append("- 若某分段关注等级较低，但证据数量低、置信度低或不确定性高，不得写成前方低风险。")
    lines.append("- 可改写为：当前融合关注较低，但不能据此判断为低风险。")

    lines.append("")
    lines.append("5. 地质-施工响应耦合复盘口径")
    if coupling:
        lines.append(
            f"- GRS_mean={_fmt_float(coupling.get('GRS_mean'))}；"
            f"GRS_max={_fmt_float(coupling.get('GRS_max'))}；"
            f"RAI_mean={_fmt_float(coupling.get('RAI_mean'))}；"
            f"RAI_max={_fmt_float(coupling.get('RAI_max'))}；"
            f"GRCI_mean={_fmt_float(coupling.get('GRCI_mean'))}；"
            f"GRCI_max={_fmt_float(coupling.get('GRCI_max'))}。"
        )
        if coupling.get("summary_text"):
            lines.append(f"- 耦合摘要：{_shorten(coupling.get('summary_text'), 300)}")
    else:
        lines.append("- 未提供 GRCI 结构化结果，不得自行解释地质-施工响应耦合。")
    lines.append("- GRCI 写作要求：只能写成复盘耦合关注指标，不得写成预测概率、灾害概率或必然发生。")

    lines.append("")
    lines.append("6. 写作边界")
    lines.append("- 报告地质部分应优先使用：当前里程附近已有地质证据提示；最近现场素描点记录显示；前方 0-10m / 10-20m / 20-30m 分段。")
    lines.append("- 若 source_trace 为空，只能写“证据来源摘要未展开”，不得编造报告编号、来源类型或原文内容。")
    lines.append("- 当前掌子面揭示只能来自明确的 face_sketch 或掌子面地质编录，不能把前方提示、历史证据或融合结果写成当前掌子面揭示。")
    lines.append("- 若 evidence 中未出现强灾害词，不得擅自写入突涌水、塌方、岩爆、瓦斯突出、防爆措施等内容。")
    if structured_warnings:
        lines.append(f"- geology_v2 结构化告警：{_compact_join(structured_warnings, max_items=8)}。")

    brief = str(v2_texts.get("geo_brief_text", "") or "").strip()
    forward_text = str(v2_texts.get("forward_text", "") or "").strip()
    if brief:
        lines.append(f"- 已开挖摘要兜底文本：{_shorten(brief, 500)}")
    if forward_text:
        lines.append(f"- 前方提示兜底文本：{_shorten(forward_text, 500)}")
    lines.append("- 自然语言兜底摘要仅作表达兜底；若与结构化证据包冲突，以结构化证据包为准。")

    return "\n".join(lines)


def build_prompt(
    seg_text: str,
    stats_text: str,
    state_text: str,
    eff_text: str,
    state_stats_text: str,
    gas_text: str,
    geo_text: str,
    face_geo_text: str,
    llm_summary: dict,
    risk_prob_text: str,
) -> str:
    """Build the daily TBM report prompt."""
    payload = build_prompt_payload(
        llm_summary,
        fallbacks={
            "seg_text": seg_text,
            "stats_text": stats_text,
            "state_text": state_text,
            "eff_text": eff_text,
            "state_stats_text": state_stats_text,
            "gas_text": gas_text,
            "geo_text": geo_text,
            "face_geo_text": face_geo_text,
            "risk_prob_text": risk_prob_text,
        },
    )
    texts = payload["texts"]
    summary_block = payload["summary_block"]
    normalized_summary = payload["normalized_summary"]
    twin_state = _as_dict(llm_summary.get("twin_state")) or _as_dict(normalized_summary.get("twin_state"))
    prompt_evidence_pack = _as_dict(llm_summary.get("prompt_evidence_pack")) or _as_dict(
        normalized_summary.get("prompt_evidence_pack")
    )
    if not prompt_evidence_pack:
        prompt_evidence_pack = build_prompt_evidence_pack(
            twin_state=twin_state,
            llm_summary=llm_summary,
        )
    evidence_pack_text = render_prompt_evidence_pack_text(prompt_evidence_pack)
    has_priority_pack = bool(prompt_evidence_pack.get("ok"))

    geology_v2_structured_block = (
        build_geology_v2_structured_prompt_block(llm_summary)
        if not has_priority_pack
        else "已提供 PromptEvidencePack，本轮报告应优先使用结构化证据包；旧 geology_v2 结构块仅作回退参考。"
    )
    plc_structured_block = (
        build_plc_structured_prompt_block(llm_summary)
        if not has_priority_pack
        else "已提供 PromptEvidencePack，本轮报告应优先使用结构化证据包；旧 PLC 结构块仅作回退参考。"
    )
    legacy_structured_input_block = (
        f"""
补充结构化 fallback：

结构化 CST 摘要：
{summary_block}

PLC 结构化状态证据：
{plc_structured_block}

地质融合结构化证据包：
{geology_v2_structured_block}
""".strip()
        if not has_priority_pack
        else "补充结构化 fallback：已省略，避免与 PromptEvidencePack 重复。"
    )

    return f"""
你现在要撰写一份正式的《TBM 综合施工工况分析报告》。

角色定位：
你是一名 TBM 施工分析工程师，面向项目管理、施工技术和安全管理人员输出正式工程报告。报告应体现工程分析口径、证据约束和谨慎判断，不能写成聊天回复。

====================
一、总写作原则
====================

1. 直接输出报告正文，不要写聊天式开场白，不要解释你如何写报告。
2. 只能依据给定信息写作，不要虚构数字、现场现象、灾害类型、时间、里程、原因或结论。
3. 所有数值必须来自输入材料；如果输入没有给出，不得自行估算。
4. 工程判断应使用“提示、关注、显示、表明、建议核查、需持续监测、需谨慎解释”等审慎措辞。
5. 不要输出程序字段名，不要把结构化对象解释成原始 JSON，不要出现“根据字段 xxx”这类表达。
6. 报告应优先使用 DK 里程格式。不要自行四舍五入生成不存在的里程。
7. 禁止使用“必然发生、已经证明、确定发生、灾害概率为、风险概率为”等过强表述，除非输入材料明确这样写。
8. 如果证据不足，必须写“资料不足 / 证据覆盖不足 / 需结合现场核查”，不能写成“无风险”“无异常”。

====================
二、地质输入优先级
====================

地质相关内容必须按以下优先级使用：

第一优先级：【结构化证据包】
- 这是 prompt_builder 根据 TwinState、PromptEvidencePack、geology_v2_context、coupling_summary 等结构化结果压缩生成的主输入。
- 地质结论、前方提示、GRCI 解释、PLC 施工状态解释应优先依据该证据包。

第二优先级：当前掌子面描述
- 只用于当前掌子面或最近邻掌子面现场揭示/素描信息。
- 如果没有明确现场揭示资料，不得写成“当前掌子面揭示”。

第三优先级：已开挖区段摘要、区段耦合分析、前方风险提示等自然语言摘要
- 这些摘要只作为表达兜底。
- 如果与结构化证据包冲突，以结构化证据包为准。

====================
三、地质语义边界，必须严格遵守
====================

必须严格区分三类空间语义：

1. 当前掌子面描述：
   - 只能写“当前掌子面”或“最近邻掌子面”的现场揭示/素描信息。
   - 如果输入没有明确掌子面现场揭示资料，必须写：
     “当前掌子面直接揭示资料不足，以下仅结合当前里程附近已有地质证据进行提示。”
   - 禁止把 TSP、HSP、超前钻、历史素描、融合结果写成“当前掌子面揭示”。

2. 已开挖区段摘要：
   - 只写已经掘进完成区段的回顾性地质与施工响应复核。
   - 可以描述“已开挖区段地质证据显示”“当前里程附近已有地质证据显示”“融合结果提示”。
   - 不要写成“现场已经发生灾害”，除非输入明确出现现场发生描述。

3. 前方风险提示：
   - 只写掌子面前方窗口内的关注提示。
   - 必须使用“前方窗口内提示 / 前方范围内需关注 / 建议加强监测”等表达。
   - 不能把前方提示写成当前已经发生的事实。
   - 不能把“关注等级”写成灾害发生概率。

推荐表达：
- “当前里程附近已有地质证据提示……”
- “融合结果显示……”
- “前方 30 m 范围内需重点关注……”
- “该关注等级表示证据融合关注程度，不等同于灾害发生概率。”

禁止表达：
- “当前掌子面揭示……”——除非当前掌子面描述输入中明确提供。
- “前方必然发生……”
- “灾害概率为高……”
- “无证据，因此无风险……”
- “系统确认发生塌方 / 突涌水 / 岩爆……”——除非输入明确出现。

====================
四、状态语义边界，必须严格遵守
====================

必须严格区分三类状态语义：

1. operation_mode：
   - 工作、停机、启动/过渡、异常扭矩等基础工况状态。
   - 用于描述 TBM 当日运行过程。

2. cluster_state：
   - 基于施工参数聚类得到的施工状态。
   - 不能直接等同于真实地质状态。

3. response_anomaly：
   - 区段级施工响应异常，包括 RAI、响应异常、效率异常、停机异常等。
   - 只能说明施工响应存在异常或波动，不能直接写成地质灾害已经发生。

4. RAI_proxy：
   - 只是 PLC 侧响应异常预览。
   - 不能替代正式 RAI 或 GRCI。

====================
五、GRS / RAI / GRCI 解释口径
====================

1. GRS 表示地质关注度或地质证据融合关注程度。
2. RAI 表示施工响应异常度。
3. GRCI 表示地质-施工响应耦合关注度，是用于复盘“地质证据与施工响应是否同步或相关”的指标。
4. GRCI 不能写成灾害概率、事故概率或未来风险概率。
5. 当 GRCI 较高时，应写：
   “地质证据与施工响应之间存在较明显耦合关注，建议结合现场记录复核。”
6. 当 GRCI 较低时，应写：
   “当前施工响应与地质关注之间耦合不强，仍需结合证据覆盖情况谨慎解释。”
7. 如果输入中说明 GRCI 是复盘口径，报告中必须体现“复核、复盘、耦合关注”，不要写成“预测”。

====================
六、地质灾害词使用约束
====================

只能使用输入中已经出现的灾害或关注类型。

如果输入只出现：
- 掉块
- 出水
- 裂隙发育
- 围岩破碎
- 围岩极破碎
- 明显反射异常
- 软硬不均

则报告中只能围绕这些表述展开。

禁止自行新增以下词语，除非输入明确出现：
- 突涌水
- 塌方
- 大变形
- 岩爆
- 断层破碎带
- 涌泥
- 瓦斯突出
- 掌子面失稳事故

如果确需表达风险，只能写：
“掉块关注”“出水关注”“围岩稳定性关注”“裂隙发育及岩体破碎关注”。

====================
七、强制措辞替换规则
====================

地质相关表达必须按以下规则收敛：

1. 如果信息来源不是明确的当前掌子面现场素描，不得使用“当前掌子面揭示”“掌子面存在……现象”“现场已出现……”。
   应改为：
   “当前里程附近已有地质证据提示……”
   “融合结果显示……”
   “已有证据中出现……关注提示”
   “需结合现场掌子面揭示情况复核”。

2. 对出水、掉块、围岩破碎等内容，如果输入来自超前预报或融合结果，不得写成“存在……现象”。
   应改为：
   “存在……相关关注提示”
   “需关注……问题”
   “提示……可能影响围岩稳定性”
   “建议现场核查……”。

3. “高风险”“风险段”“危险段”应尽量替换为：
   “高关注”
   “重点关注区段”
   “需加强监测区段”
   “前方关注窗口”。

4. 历史对比中的指标变化只能表述为“关注水平变化”或“耦合关注变化”，不得写成灾害风险必然升高。

5. “揭示”一词只能用于明确的现场掌子面素描、掌子面地质编录或现场观测记录。
   如果信息来自地质融合、超前预报、历史素描或结构化证据包，应改为：
   “已有地质证据提示……”
   “融合结果显示……”
   “最近现场素描点记录显示……”
   “当前里程附近已有资料显示……”
   不得写成“当前掌子面揭示……”。

6. 如果当前掌子面描述来自最近邻素描点，而不是当前里程精确素描，应写：
   “当前掌子面附近最近现场素描点记录显示……”
   或
   “距当前掌子面较近的现场记录显示……”
   不得直接写成“当前掌子面揭示”。

7. 对“低关注”区段，如果同时存在“低置信度、证据覆盖不足、高不确定性、来源较少”等信息，必须写：
   “当前融合关注等级较低，但由于证据覆盖不足或不确定性较高，不能据此判断为低风险。”
   不得简写为“前方低风险”或“无明显风险”。

8. 如果报告中出现“高风险提示段”“风险段”“危险段”，应优先替换为：
   “高关注区段”
   “重点关注区段”
   “前方关注窗口”
   “需加强监测区段”
   除非输入材料明确使用“高风险”。

====================
八、气体监测表述约束
====================

1. 气体异常只能依据输入中的气体分析。
2. 如果输入只说明 CH4 超限，不得扩展为瓦斯突出、爆炸风险或防爆处置结论。
3. 可以写：
   “需加强 CH4 监测、通风核查和报警记录复核”
   “建议按现场安全规程核查通风、报警及电气设备管理要求”
   “建议结合现场气体检测制度提高复核频次”
4. 不得自行推断通风系统故障、瓦斯突出风险、爆炸风险或需要立即采取防爆措施，除非输入明确给出。
5. 对气体建议应保持在“监测、复核、通风核查、报警记录核查、现场安全规程核查”层面，不要升级为专项处置结论。
6. 如果气体字段语义为 alarm_flag，不得写成浓度超限。
7. 如果气体字段语义为 unknown，不得写成确定超限。

====================
九、建议章节
====================

请按以下章节组织报告：

1. 综合结论摘要
2. 总体施工运行概况
3. 基础工况统计分析
4. 聚类施工状态与效率分析
5. 当前掌子面描述
6. 已开挖区段地质与响应异常复核
7. 气体监测分析
8. 前方风险提示
9. 结论与建议

章节写作要求：
- “当前掌子面描述”如果直接资料不足，必须明确说明资料不足。
- “已开挖区段地质与响应异常复核”重点写 GRS、RAI、GRCI 的复核意义。
- “前方风险提示”必须使用审慎措辞，不得写成确定灾害结论。
- “结论与建议”应给出施工监测、支护、排水、参数联动观察等建议，但不能超出输入证据。
- 建议措施必须与输入证据直接相关，或者属于通用监测、复核、核查类建议。
- 不得把一般关注提示升级为专项处置措施。
- 如果输入没有明确变形、大变形、收敛监测等信息，不得直接建议“增加收敛变形监测断面”；可改写为“必要时结合现场量测要求加强围岩稳定性跟踪”。
- 如果输入只提示出水或掉块关注，建议应限于“排水准备、支护时效、围岩稳定性观察、现场复核”等，不得扩展为未给出的灾害处置。

====================
十、输入资料
====================

结构化证据包：
{evidence_pack_text}

{legacy_structured_input_block}

以下自然语言摘要仅作为兜底表达，若与结构化证据包冲突，以结构化证据包为准。

基础工况分段：
{_text(texts, "operation_segments_text")}

基础工况统计：
{_text(texts, "operation_stats_text")}

聚类施工状态：
{_text(texts, "cluster_state_text")}

聚类状态效率：
{_text(texts, "cluster_efficiency_text")}

聚类状态统计：
{_text(texts, "cluster_state_stats_text")}

当前掌子面描述：
{_text(texts, "face_description_text")}

已开挖区段摘要：
{_text(texts, "excavated_segment_text")}

补充区段风险剖面：
{_text(texts, "risk_profile_text")}

区段响应异常摘要：
{_text(texts, "response_anomaly_text")}

区段耦合分析：
{_text(texts, "coupling_text")}

数字孪生快照：
{_text(texts, "digital_twin_text")}

历史对比：
{_text(texts, "history_comparison_text")}

气体分析：
{_text(texts, "gas_text")}

前方风险提示：
{_text(texts, "forward_risk_text")}
""".strip()
