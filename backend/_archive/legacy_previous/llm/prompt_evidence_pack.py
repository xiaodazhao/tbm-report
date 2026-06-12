from __future__ import annotations

from datetime import date, datetime
import math
from typing import Any

import numpy as np
import pandas as pd

from schemas.twin_state_schema import PROMPT_EVIDENCE_PACK_VERSION


SCHEMA_VERSION = PROMPT_EVIDENCE_PACK_VERSION
NO_TEXT = "未提供"
GENERATION_CONSTRAINTS = [
    "关注等级表示证据融合关注程度，不等同于灾害发生概率。",
    "前方提示不是当前掌子面已经发生的事实。",
    "GRCI 是地质-施工响应耦合关注指标，是复盘解释指标，不是预测概率。",
    "无证据覆盖不得写成无风险。",
    "operation_mode 是基础工况，不等同于 cluster_state。",
    "cluster_state 是施工参数聚类状态，不等同于真实地质状态。",
    "气体字段若为 alarm_flag，不得写成浓度超限。",
    "气体字段若为 unknown，不得写成确定超限。",
    "source_trace 只是证据摘要，不可超出原文含义。",
]


def _as_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return list(value)
    if isinstance(value, (tuple, set)):
        return list(value)
    return []


def _safe_float(value: Any, default: float | None = None) -> float | None:
    try:
        if value is None:
            return default
        x = float(value)
        if not math.isfinite(x):
            return default
        return float(x)
    except Exception:
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    x = _safe_float(value, default=None)
    if x is None:
        return int(default)
    return int(round(x))


def _safe_text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    if isinstance(value, dict):
        for key in ("text", "summary_text", "advice_text", "forward_advice_text", "message"):
            text = _safe_text(value.get(key), default="")
            if text:
                return text
        return default
    if isinstance(value, (list, tuple, set)):
        parts = [str(item).strip() for item in value if str(item).strip()]
        return "、".join(parts) if parts else default
    text = str(value).strip()
    return text or default


def _dedup_text(items: list[str] | tuple[str, ...] | set[str] | None) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in items or []:
        text = _safe_text(item)
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out


def _trim_excerpt(value: Any, max_chars: int = 200) -> str:
    text = _safe_text(value)
    if not text:
        return ""
    text = " ".join(text.replace("\r", "\n").split())
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3].rstrip() + "..."


def _json_clean(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        x = float(value)
        return x if math.isfinite(x) else None
    if isinstance(value, (datetime, date, pd.Timestamp)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_clean(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_clean(item) for item in value]
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    if hasattr(value, "item"):
        try:
            return _json_clean(value.item())
        except Exception:
            pass
    return str(value)


def _compact_join(items: Any, max_items: int = 6, default: str = NO_TEXT) -> str:
    values: list[str] = []
    if isinstance(items, dict):
        values = [f"{key}:{value}" for key, value in items.items()]
    elif isinstance(items, str):
        values = [part.strip() for part in items.replace(",", "、").split("、") if part.strip()]
    else:
        values = [str(item).strip() for item in _as_list(items) if str(item).strip()]
    values = _dedup_text(values)
    return "、".join(values[:max_items]) if values else default


def _fmt_num(value: Any, default: str = NO_TEXT) -> str:
    x = _safe_float(value, default=None)
    if x is None:
        return default
    return f"{x:.2f}"


def _clone_trace_item(item: dict[str, Any]) -> dict[str, Any]:
    return _json_clean(
        {
            "evidence_id": _safe_text(item.get("evidence_id")) or None,
            "report_id": _safe_text(item.get("report_id")) or None,
            "source_type": _safe_text(item.get("source_type")) or None,
            "evidence_role": _safe_text(item.get("evidence_role")) or None,
            "spatial_type": _safe_text(item.get("spatial_type")) or None,
            "hazard_tags": _dedup_text(_as_list(item.get("hazard_tags"))),
            "confidence": _safe_float(item.get("confidence"), default=None),
            "raw_text_excerpt": _trim_excerpt(item.get("raw_text_excerpt") or item.get("raw_text_snippet")),
        }
    )


def _normalize_source_trace(items: Any, max_items: int) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in _as_list(items):
        if not isinstance(item, dict):
            continue
        out.append(_clone_trace_item(item))
        if len(out) >= max(int(max_items), 0):
            break
    return _json_clean(out)


def _build_pack_from_twin_state(
    twin_state: dict[str, Any],
    *,
    max_key_cells: int,
    max_forward_segments: int,
    max_source_trace: int,
) -> tuple[dict[str, Any], list[str]]:
    warnings = _dedup_text(_as_list(twin_state.get("warnings")))

    position_state = _as_dict(twin_state.get("position_state"))
    operation_state = _as_dict(twin_state.get("operation_state"))
    cluster_state = _as_dict(twin_state.get("cluster_state"))
    gas_state = _as_dict(twin_state.get("gas_state"))
    geology_state = _as_dict(twin_state.get("geology_state"))
    response_state = _as_dict(twin_state.get("response_state"))
    coupling_state = _as_dict(twin_state.get("coupling_state"))
    forward_state = _as_dict(twin_state.get("forward_state"))
    quality_state = _as_dict(twin_state.get("quality_state"))
    source_refs = _as_dict(twin_state.get("source_refs"))

    key_cells = []
    for item in _as_list(geology_state.get("key_cells"))[: max(int(max_key_cells), 0)]:
        if not isinstance(item, dict):
            continue
        row = dict(item)
        row["source_trace"] = _normalize_source_trace(item.get("source_trace"), max_items=2)
        key_cells.append(_json_clean(row))

    forward_segments = []
    for item in _as_list(forward_state.get("segments"))[: max(int(max_forward_segments), 0)]:
        if not isinstance(item, dict):
            continue
        row = dict(item)
        row["source_trace"] = _normalize_source_trace(item.get("source_trace"), max_items=2)
        forward_segments.append(_json_clean(row))

    source_trace: list[dict[str, Any]] = []
    for cell in key_cells:
        for trace in _as_list(_as_dict(cell).get("source_trace")):
            source_trace.append(trace)
            if len(source_trace) >= max(int(max_source_trace), 0):
                break
        if len(source_trace) >= max(int(max_source_trace), 0):
            break
    if len(source_trace) < max(int(max_source_trace), 0):
        for segment in forward_segments:
            for trace in _as_list(_as_dict(segment).get("source_trace")):
                source_trace.append(trace)
                if len(source_trace) >= max(int(max_source_trace), 0):
                    break
            if len(source_trace) >= max(int(max_source_trace), 0):
                break

    pack = {
        "schema_version": SCHEMA_VERSION,
        "ok": bool(twin_state.get("ok")),
        "report_scope": {
            "date": twin_state.get("date"),
            "analysis_mode": twin_state.get("analysis_mode"),
            "current_chainage_dk": position_state.get("current_chainage_dk"),
            "advance_length_m": position_state.get("advance_length_m"),
            "start_chainage_dk": position_state.get("start_chainage_dk"),
            "end_chainage_dk": position_state.get("end_chainage_dk"),
        },
        "operation_evidence": {
            "dominant_mode": _as_dict(operation_state.get("summary")).get("dominant_mode"),
            "dominant_mode_cn": _as_dict(operation_state.get("summary")).get("dominant_mode_cn"),
            "work_total_min": _as_dict(operation_state.get("summary")).get("work_total_min"),
            "stop_total_min": _as_dict(operation_state.get("summary")).get("stop_total_min"),
            "work_ratio": _as_dict(operation_state.get("summary")).get("work_ratio"),
            "stop_ratio": _as_dict(operation_state.get("summary")).get("stop_ratio"),
            "key_segments": _as_list(operation_state.get("key_segments")),
            "routine_stop_summary": _as_dict(operation_state.get("routine_stop_summary")),
            "quality_warnings": _dedup_text(
                _as_list(operation_state.get("warnings"))
                + _as_list(quality_state.get("data_quality_warnings"))
            ),
        },
        "cluster_evidence": {
            "has_cluster": bool(cluster_state.get("has_cluster", False)),
            "cluster_quality": _as_dict(cluster_state.get("cluster_quality")),
            "state_summaries": _as_list(cluster_state.get("state_summaries")),
            "warnings": _dedup_text(_as_list(cluster_state.get("warnings"))),
        },
        "gas_evidence": {
            "exceed_summary": _as_dict(gas_state.get("exceed_summary")),
            "gas_summaries": _as_list(gas_state.get("gas_summaries")),
            "gas_field_diagnostics": _as_dict(gas_state.get("gas_field_diagnostics")),
            "warnings": _dedup_text(_as_list(gas_state.get("warnings"))),
        },
        "geology_evidence": {
            "current_window_summary": _as_dict(geology_state.get("current_window_summary")),
            "key_cells": key_cells,
            "source_trace_summary": _as_dict(geology_state.get("source_trace_summary")),
            "warnings": _dedup_text(_as_list(geology_state.get("warnings"))),
        },
        "forward_evidence": {
            "lookahead_m": forward_state.get("lookahead_m"),
            "segments": forward_segments,
            "attention_summary": _as_dict(forward_state.get("attention_summary")),
            "warnings": _dedup_text(_as_list(forward_state.get("warnings"))),
        },
        "coupling_evidence": {
            "GRS_summary": {
                "GRS_mean": _as_dict(coupling_state.get("GRCI_summary")).get("GRS_mean"),
                "GRS_max": _as_dict(coupling_state.get("GRCI_summary")).get("GRS_max"),
            },
            "RAI_summary": _as_dict(response_state.get("RAI_summary")),
            "GRCI_summary": _as_dict(coupling_state.get("GRCI_summary")),
            "top_grci_segments": _as_list(coupling_state.get("top_grci_segments")),
            "warnings": _dedup_text(
                _as_list(coupling_state.get("warnings"))
                + _as_list(response_state.get("warnings"))
            ),
        },
        "quality_evidence": {
            "plc_quality_warnings": _dedup_text(_as_list(_as_dict(quality_state.get("plc_quality")).get("warnings"))),
            "geology_warnings": _dedup_text(_as_list(quality_state.get("geology_warnings"))),
            "fallback_flags": _dedup_text(_as_list(quality_state.get("fallback_flags"))),
            "data_quality_warnings": _dedup_text(_as_list(quality_state.get("data_quality_warnings"))),
        },
        "source_trace": source_trace[: max(int(max_source_trace), 0)],
        "generation_constraints": list(GENERATION_CONSTRAINTS),
        "warnings": warnings,
        "source_refs": source_refs,
    }
    return _json_clean(pack), warnings


def _build_pack_from_summary(
    llm_summary: dict[str, Any],
    *,
    max_key_cells: int,
    max_forward_segments: int,
    max_source_trace: int,
) -> tuple[dict[str, Any], list[str]]:
    warnings = ["PromptEvidencePack 使用了 llm_summary fallback，未直接读取 twin_state。"]
    operation_context = _as_dict(llm_summary.get("operation_context"))
    cluster_context = _as_dict(llm_summary.get("cluster_context"))
    gas_context = _as_dict(llm_summary.get("gas_context"))
    geology_context = _as_dict(llm_summary.get("geology_v2_context"))
    forward_context = _as_dict(llm_summary.get("geology_v2_forward_profile"))
    coupling_summary = _as_dict(llm_summary.get("coupling_summary"))
    plc_quality_report = _as_dict(llm_summary.get("plc_quality_report"))
    cell_response_summary = _as_dict(llm_summary.get("cell_response_summary"))
    run_metadata = _as_dict(llm_summary.get("run_metadata"))

    twin_like = {
        "schema_version": "twin_state_fallback_v1",
        "ok": bool(operation_context or geology_context),
        "date": run_metadata.get("analysis_date"),
        "analysis_mode": run_metadata.get("analysis_mode"),
        "position_state": {
            "current_chainage_dk": _as_dict(geology_context.get("current_position")).get("current_chainage_dk"),
            "advance_length_m": _as_dict(operation_context.get("position")).get("advance_length_m"),
            "start_chainage_dk": _as_dict(operation_context.get("position")).get("start_chainage_dk"),
            "end_chainage_dk": _as_dict(operation_context.get("position")).get("end_chainage_dk"),
        },
        "operation_state": {
            "summary": _as_dict(operation_context.get("operation_mode_summary")),
            "key_segments": _as_list(operation_context.get("key_operation_segments")),
            "routine_stop_summary": _as_dict(operation_context.get("routine_stop_summary")),
            "warnings": _as_list(operation_context.get("warnings")),
        },
        "cluster_state": {
            "has_cluster": bool(cluster_context.get("has_cluster", False)),
            "cluster_quality": _as_dict(cluster_context.get("cluster_quality")),
            "state_summaries": _as_list(cluster_context.get("state_summaries")),
            "warnings": _as_list(cluster_context.get("warnings")),
        },
        "gas_state": {
            "exceed_summary": _as_dict(gas_context.get("exceed_summary")),
            "gas_summaries": _as_list(gas_context.get("gas_summaries")),
            "gas_field_diagnostics": _as_dict(gas_context.get("gas_field_diagnostics")),
            "warnings": _as_list(gas_context.get("warnings")),
        },
        "geology_state": {
            "current_window_summary": _as_dict(geology_context.get("current_window_summary")),
            "key_cells": _as_list(geology_context.get("key_cells")),
            "source_trace_summary": _as_dict(geology_context.get("source_trace_summary")),
            "warnings": _as_list(geology_context.get("warnings")) + _as_list(geology_context.get("structured_warnings")),
        },
        "response_state": {
            "cell_response_summary": cell_response_summary,
            "RAI_summary": {
                "top_rai_segment_count": len(_as_list(coupling_summary.get("top_rai_segments"))),
                "summary_text": _safe_text(coupling_summary.get("summary_text")) or None,
            },
            "warnings": _as_list(cell_response_summary.get("warnings")),
        },
        "coupling_state": {
            "GRCI_summary": {
                "GRS_mean": coupling_summary.get("GRS_mean"),
                "GRS_max": coupling_summary.get("GRS_max"),
                "RAI_mean": coupling_summary.get("RAI_mean"),
                "RAI_max": coupling_summary.get("RAI_max"),
                "GRCI_mean": coupling_summary.get("GRCI_mean"),
                "GRCI_max": coupling_summary.get("GRCI_max"),
                "coupling_level_counts": _as_dict(coupling_summary.get("coupling_level_counts", coupling_summary.get("level_counts"))),
                "grci_class_counts": _as_dict(coupling_summary.get("grci_class_counts", coupling_summary.get("class_counts"))),
                "summary_text": _safe_text(coupling_summary.get("summary_text")) or None,
            },
            "top_grci_segments": _as_list(coupling_summary.get("top_grci_segments", coupling_summary.get("high_attention_segments"))),
            "warnings": _as_list(coupling_summary.get("warnings")),
        },
        "forward_state": {
            "lookahead_m": forward_context.get("lookahead_m", run_metadata.get("lookahead_m")),
            "segments": _as_list(geology_context.get("forward_segments")) or _as_list(forward_context.get("profile")),
            "attention_summary": _as_dict(_as_dict(geology_context.get("data_summary")).get("forward_profile_summary"))
            or {
                "has_forward_evidence": bool(forward_context.get("has_forward_evidence", forward_context.get("has_forward_risk"))),
                "overall_attention_level": _safe_text(forward_context.get("overall_attention_level", forward_context.get("forward_advice_level"))) or None,
                "forward_evidence_count": _safe_int(forward_context.get("forward_evidence_count", forward_context.get("forward_segment_count")), default=0),
            },
            "warnings": _as_list(geology_context.get("warnings")) + _as_list(geology_context.get("structured_warnings")),
        },
        "quality_state": {
            "plc_quality": plc_quality_report,
            "geology_warnings": _as_list(geology_context.get("warnings")) + _as_list(geology_context.get("structured_warnings")),
            "fallback_flags": ["missing_twin_state"],
            "data_quality_warnings": _as_list(plc_quality_report.get("warnings")),
        },
        "source_refs": {
            "used_evidence_ids": [],
            "source_type_counts": _as_dict(_as_dict(geology_context.get("source_trace_summary")).get("source_type_counts")),
        },
        "warnings": warnings,
    }
    return _build_pack_from_twin_state(
        twin_like,
        max_key_cells=max_key_cells,
        max_forward_segments=max_forward_segments,
        max_source_trace=max_source_trace,
    )


def build_prompt_evidence_pack(
    twin_state: dict | None = None,
    llm_summary: dict | None = None,
    max_key_cells: int = 5,
    max_forward_segments: int = 3,
    max_source_trace: int = 12,
) -> dict:
    """Build a compact structured evidence pack for prompt generation."""
    twin_state = _as_dict(twin_state)
    llm_summary = _as_dict(llm_summary)

    if twin_state.get("position_state") or twin_state.get("operation_state") or twin_state.get("geology_state"):
        pack, warnings = _build_pack_from_twin_state(
            twin_state,
            max_key_cells=max_key_cells,
            max_forward_segments=max_forward_segments,
            max_source_trace=max_source_trace,
        )
    else:
        pack, warnings = _build_pack_from_summary(
            llm_summary,
            max_key_cells=max_key_cells,
            max_forward_segments=max_forward_segments,
            max_source_trace=max_source_trace,
        )

    if not _as_dict(pack.get("report_scope")).get("current_chainage_dk"):
        warnings.append("PromptEvidencePack 缺少 current_chainage_dk。")
    if not _as_list(_as_dict(pack.get("geology_evidence")).get("key_cells")):
        warnings.append("PromptEvidencePack 未提供 key_cells。")
    if not _as_list(_as_dict(pack.get("forward_evidence")).get("segments")):
        warnings.append("PromptEvidencePack 未提供 forward_segments。")
    pack["warnings"] = _dedup_text(_as_list(pack.get("warnings")) + warnings)
    pack["ok"] = bool(
        _as_dict(pack.get("operation_evidence")).get("dominant_mode")
        or _as_list(_as_dict(pack.get("geology_evidence")).get("key_cells"))
        or _as_list(_as_dict(pack.get("forward_evidence")).get("segments"))
    )
    return _json_clean(pack)


def render_prompt_evidence_pack_text(pack: dict) -> str:
    """Render PromptEvidencePack into concise prompt text instead of raw JSON."""
    pack = _as_dict(pack)
    if not pack:
        return "【结构化证据包】未提供。"

    scope = _as_dict(pack.get("report_scope"))
    operation = _as_dict(pack.get("operation_evidence"))
    cluster = _as_dict(pack.get("cluster_evidence"))
    gas = _as_dict(pack.get("gas_evidence"))
    geology = _as_dict(pack.get("geology_evidence"))
    forward = _as_dict(pack.get("forward_evidence"))
    coupling = _as_dict(pack.get("coupling_evidence"))
    quality = _as_dict(pack.get("quality_evidence"))

    lines: list[str] = []
    lines.append("【结构化证据包】")
    lines.append("1. 报告范围")
    lines.append(
        f"- 日期={_safe_text(scope.get('date'), NO_TEXT)}；分析模式={_safe_text(scope.get('analysis_mode'), NO_TEXT)}；当前里程={_safe_text(scope.get('current_chainage_dk'), NO_TEXT)}。"
    )
    lines.append(
        f"- 推进范围={_safe_text(scope.get('start_chainage_dk'), NO_TEXT)}～{_safe_text(scope.get('end_chainage_dk'), NO_TEXT)}；推进长度={_fmt_num(scope.get('advance_length_m'))} m。"
    )

    lines.append("")
    lines.append("2. PLC 施工状态证据")
    lines.append(
        f"- 主导工况={_safe_text(operation.get('dominant_mode_cn') or operation.get('dominant_mode'), NO_TEXT)}；工作={_fmt_num(operation.get('work_total_min'))} min；停机={_fmt_num(operation.get('stop_total_min'))} min。"
    )
    key_segments = _as_list(operation.get("key_segments"))
    if key_segments:
        for item in key_segments[:3]:
            row = _as_dict(item)
            lines.append(
                f"- 关键工况段：{_safe_text(row.get('start'), NO_TEXT)}~{_safe_text(row.get('end'), NO_TEXT)}；工况={_safe_text(row.get('operation_mode_cn') or row.get('operation_mode'), NO_TEXT)}；持续={_fmt_num(row.get('duration_min'))} min；原因={_safe_text(row.get('reason'), NO_TEXT)}。"
            )
    else:
        lines.append("- 关键工况段：未提供。")
    lines.append(
        f"- 质量提醒：{_compact_join(operation.get('quality_warnings'), max_items=6, default='无明显补充告警')}。"
    )

    lines.append("")
    lines.append("3. 聚类施工状态证据")
    lines.append(
        f"- 是否形成聚类={ '是' if cluster.get('has_cluster') else '否' }；稳定性={ '足够' if _as_dict(cluster.get('cluster_quality')).get('is_stable_enough') else '有限' }；有效样本={_safe_int(_as_dict(cluster.get('cluster_quality')).get('valid_sample_count'), 0)}。"
    )
    state_summaries = _as_list(cluster.get("state_summaries"))
    if state_summaries:
        for item in state_summaries[:3]:
            row = _as_dict(item)
            lines.append(
                f"- 聚类状态：state_id={_safe_int(row.get('state_id'), 0)}；语义={_safe_text(row.get('semantic_label'), NO_TEXT)}；占比={_fmt_num(row.get('ratio'))}；平均推进速度={_fmt_num(row.get('mean_advance_speed'))}。"
            )
    else:
        lines.append("- 聚类状态：未提供。")
    lines.append("- 说明：state_id 只在当天内部有效。")

    lines.append("")
    lines.append("4. 气体监测证据")
    exceed_summary = _as_dict(gas.get("exceed_summary"))
    lines.append(
        f"- 超阈值字段={_compact_join(exceed_summary.get('exceed_gases'), max_items=6, default='无')}；超阈值事件总数={_safe_int(exceed_summary.get('exceed_event_count_total'), 0)}。"
    )
    gas_summaries = _as_list(gas.get("gas_summaries"))
    if gas_summaries:
        for item in gas_summaries[:4]:
            row = _as_dict(item)
            lines.append(
                f"- 气体字段：{_safe_text(row.get('gas'), NO_TEXT)}；类型={_safe_text(row.get('field_type_guess'), NO_TEXT)}；最大值={_fmt_num(row.get('max'))}；解释限制={_safe_text(row.get('interpretation_caution'), NO_TEXT)}。"
            )
    else:
        lines.append("- 气体字段：未提供。")

    lines.append("")
    lines.append("5. 地质融合证据")
    current_window = _as_dict(geology.get("current_window_summary"))
    lines.append(
        f"- 当前窗口 cell 数={_safe_int(current_window.get('cell_count'), 0)}；有证据覆盖 cell 数={_safe_int(current_window.get('evidence_cell_count'), 0)}；主要关注={_compact_join(current_window.get('main_hazards'), max_items=6)}。"
    )
    key_cells = _as_list(geology.get("key_cells"))
    if key_cells:
        for item in key_cells[:3]:
            row = _as_dict(item)
            lines.append(
                f"- key_cell：{_safe_text(row.get('range_dk'), NO_TEXT)}；围岩等级={_safe_text(row.get('fused_grade'), NO_TEXT)}；GRS_geo_base={_fmt_num(row.get('GRS_geo_base'))}；关注={_compact_join(row.get('main_hazards'), max_items=4)}。"
            )
            traces = _as_list(row.get("source_trace"))
            if traces:
                for trace in traces[:2]:
                    trace_row = _as_dict(trace)
                    lines.append(
                        f"  来源摘要：source_type={_safe_text(trace_row.get('source_type'), NO_TEXT)}；report_id={_safe_text(trace_row.get('report_id'), NO_TEXT)}；摘录={_safe_text(trace_row.get('raw_text_excerpt'), NO_TEXT)}。"
                    )
    else:
        lines.append("- key_cell：未提供。")
    lines.append("- 说明：关注等级只表示融合关注程度，不等同于灾害概率。")

    lines.append("")
    lines.append("6. 前方窗口证据")
    lines.append(
        f"- 前方窗口长度={_fmt_num(forward.get('lookahead_m'))} m；整体关注={_safe_text(_as_dict(forward.get('attention_summary')).get('overall_attention_level'), NO_TEXT)}。"
    )
    forward_segments = _as_list(forward.get("segments"))
    if forward_segments:
        for item in forward_segments[:3]:
            row = _as_dict(item)
            lines.append(
                f"- 前方分段：{_safe_text(row.get('relative_range') or row.get('range_dk'), NO_TEXT)}；关注等级={_safe_text(row.get('attention_level'), NO_TEXT)}；主要关注={_compact_join(row.get('main_hazards'), max_items=4)}；不确定性={_safe_text(row.get('uncertainty_level'), NO_TEXT)}。"
            )
    else:
        lines.append("- 前方分段：未提供。")
    lines.append("- 说明：若低关注但证据不足或不确定性高，不得写成低风险。")

    lines.append("")
    lines.append("7. 地质-施工响应耦合证据")
    grci_summary = _as_dict(coupling.get("GRCI_summary"))
    rai_summary = _as_dict(coupling.get("RAI_summary"))
    lines.append(
        f"- GRS_mean={_fmt_num(_as_dict(coupling.get('GRS_summary')).get('GRS_mean'))}；RAI_max={_fmt_num(rai_summary.get('RAI_max'))}；GRCI_max={_fmt_num(grci_summary.get('GRCI_max'))}。"
    )
    lines.append(
        f"- 耦合摘要：{_safe_text(grci_summary.get('summary_text'), default='未提供')}。"
    )
    lines.append("- 说明：GRCI 只能作为复盘耦合关注指标，不得写成预测概率。")

    lines.append("")
    lines.append("8. 生成约束")
    for item in _as_list(pack.get("generation_constraints")):
        lines.append(f"- {item}")

    quality_warnings = _dedup_text(
        _as_list(quality.get("plc_quality_warnings"))
        + _as_list(quality.get("geology_warnings"))
        + _as_list(quality.get("fallback_flags"))
        + _as_list(quality.get("data_quality_warnings"))
        + _as_list(pack.get("warnings"))
    )
    if quality_warnings:
        lines.append("")
        lines.append("9. 额外告警")
        for item in quality_warnings[:10]:
            lines.append(f"- {item}")

    return "\n".join(lines)
