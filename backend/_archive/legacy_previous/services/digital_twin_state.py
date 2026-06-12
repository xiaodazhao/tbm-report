from __future__ import annotations

from typing import Any

import pandas as pd

from schemas.twin_contract import dedup_text, safe_float, safe_int, split_tags
from utils.chainage_utils import format_chainage_dk


def _safe_timestamp(value: Any) -> str | None:
    try:
        if pd.isna(value):
            return None
        return pd.to_datetime(value).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return None


def _collect_gas_exceed_types(gas_stats: dict) -> list[str]:
    gas_all = gas_stats.get("all", {}) if isinstance(gas_stats, dict) else {}
    out = []
    for gas, stat in gas_all.items():
        if isinstance(stat, dict) and safe_int(stat.get("exceed_event_count")) > 0:
            out.append(gas)
    return dedup_text(out)


def _dominant_operation_state(stats: dict) -> str | None:
    candidates = {
        "work": safe_float(stats.get("work_total_min"), 0.0) or 0.0,
        "stop": safe_float(stats.get("stop_total_min"), 0.0) or 0.0,
        "transition": safe_float(stats.get("transition_total_min"), 0.0) or 0.0,
        "abnormal": safe_float(stats.get("abnormal_total_min"), 0.0) or 0.0,
    }
    if not any(value > 0 for value in candidates.values()):
        return None
    return max(candidates.items(), key=lambda item: item[1])[0]


def _chainage_series(df_geo: pd.DataFrame) -> pd.Series:
    if df_geo is None or df_geo.empty:
        return pd.Series(dtype=float)
    for col in ["chainage", "导向盾首里程", "开累进尺", "当前里程"]:
        if col in df_geo.columns:
            return pd.to_numeric(df_geo[col], errors="coerce").dropna()
    return pd.Series(dtype=float)


def _time_series(df_geo: pd.DataFrame) -> pd.Series:
    if df_geo is None or df_geo.empty:
        return pd.Series(dtype="datetime64[ns]")
    for col in ["运行时间-time", "timestamp", "time", "datetime", "date_time"]:
        if col in df_geo.columns:
            return pd.to_datetime(df_geo[col], errors="coerce").dropna()
    return pd.Series(dtype="datetime64[ns]")


def _last_value(df: pd.DataFrame, columns: list[str]) -> Any:
    if df is None or df.empty:
        return None
    for col in columns:
        if col in df.columns:
            series = df[col].dropna()
            if not series.empty:
                return series.iloc[-1]
    return None


def build_digital_twin_state(
    *,
    df_geo: pd.DataFrame,
    stats: dict,
    state_stats: dict,
    gas_stats: dict,
    geo_summary_segment: dict,
    forward_risk_summary: dict,
    coupling_summary: dict | None = None,
) -> dict[str, Any]:
    """Build a lightweight structured digital-twin display state.

    This object is intentionally a *display/source state* used by the canonical
    CST/TwinState builder.  It keeps compatibility keys such as ``time_state``
    and ``position_state`` but does not embed prompt text or LLM summaries.
    """
    df = df_geo.copy() if isinstance(df_geo, pd.DataFrame) else pd.DataFrame()
    chainage = _chainage_series(df)
    times = _time_series(df)
    current_chainage = safe_float(chainage.iloc[-1]) if not chainage.empty else None
    start_chainage = safe_float(chainage.min()) if not chainage.empty else None
    end_chainage = safe_float(chainage.max()) if not chainage.empty else None
    advance_length = safe_float(chainage.max() - chainage.min()) if len(chainage) >= 2 else 0.0
    start_time = _safe_timestamp(times.min()) if not times.empty else None
    end_time = _safe_timestamp(times.max()) if not times.empty else None
    duration_min = 0.0
    if not times.empty and len(times) >= 2:
        duration_min = float((times.max() - times.min()).total_seconds() / 60.0)

    gas_exceed_types = _collect_gas_exceed_types(gas_stats)
    coupling_summary = coupling_summary if isinstance(coupling_summary, dict) else {}
    geo_summary_segment = geo_summary_segment if isinstance(geo_summary_segment, dict) else {}
    forward_risk_summary = forward_risk_summary if isinstance(forward_risk_summary, dict) else {}

    current_grade = _last_value(df, ["geo_fused_grade", "fused_grade", "support_grade", "围岩等级"])
    current_hazard = _last_value(df, ["geo_hazard_summary", "hazard", "hazard_mode", "灾害表现"])
    current_sources = _last_value(df, ["active_report_source_count", "active_source_count", "source_count"])
    hazard_tags = split_tags(current_hazard or geo_summary_segment.get("main_hazards"))

    work_min = safe_float(stats.get("work_total_min"), 0.0) or 0.0
    stop_min = safe_float(stats.get("stop_total_min"), 0.0) or 0.0
    transition_min = safe_float(stats.get("transition_total_min"), 0.0) or 0.0
    abnormal_min = safe_float(stats.get("abnormal_total_min"), 0.0) or 0.0
    op_total = work_min + stop_min + transition_min + abnormal_min

    position_state = {
        "reference_type": "linear_chainage",
        "start_chainage": start_chainage,
        "end_chainage": end_chainage,
        "current_chainage": current_chainage,
        "current_chainage_dk": format_chainage_dk(current_chainage) if current_chainage is not None else None,
        "advance_length": advance_length,
    }

    operation_state = {
        "dominant_state": _dominant_operation_state(stats),
        "work_count": safe_int(stats.get("work_count")),
        "stop_count": safe_int(stats.get("stop_count")),
        "transition_count": safe_int(stats.get("transition_count")),
        "abnormal_count": safe_int(stats.get("abnormal_count")),
        "work_total_min": work_min,
        "stop_total_min": stop_min,
        "transition_total_min": transition_min,
        "abnormal_total_min": abnormal_min,
        "work_ratio": round(work_min / op_total, 6) if op_total > 0 else None,
        "stop_ratio": round(stop_min / op_total, 6) if op_total > 0 else None,
        "state_switch_count": safe_int(state_stats.get("状态切换次数", 0)) if isinstance(state_stats, dict) else 0,
    }

    geology_state = {
        "current_grade": None if pd.isna(current_grade) else current_grade,
        "current_hazard": None if pd.isna(current_hazard) else current_hazard,
        "current_hazard_tags": hazard_tags,
        "current_active_source_count": safe_float(current_sources, 0.0),
        "has_geology": bool(geo_summary_segment.get("has_geology", False)),
        "high_geo_attention_segment_count": safe_int(geo_summary_segment.get("high_geo_attention_segment_count", geo_summary_segment.get("high_risk_segment_count", 0))),
        "multi_report_source_segment_count": safe_int(geo_summary_segment.get("multi_report_source_segment_count", geo_summary_segment.get("multi_source_segment_count", 0))),
    }

    forward_state = {
        "has_forward_risk": bool(forward_risk_summary.get("has_forward_risk", False)),
        "lookahead_m": safe_float(forward_risk_summary.get("lookahead_m")),
        "forward_advice_level": forward_risk_summary.get("forward_advice_level", forward_risk_summary.get("advice_level")),
        "forward_main_hazard_tags": split_tags(forward_risk_summary.get("forward_main_hazard_tags", forward_risk_summary.get("main_hazards", []))),
        "forward_evidence_count": safe_int(forward_risk_summary.get("forward_evidence_count", forward_risk_summary.get("forward_segment_count", 0))),
        "forward_report_source_count": safe_int(forward_risk_summary.get("forward_report_source_count", forward_risk_summary.get("multi_source_count", 0))),
    }

    coupling_state = {
        "has_coupling": bool(coupling_summary.get("has_coupling", False)),
        "coupling_level_counts": coupling_summary.get("coupling_level_counts", coupling_summary.get("level_counts", {})),
        "grci_class_counts": coupling_summary.get("grci_class_counts", coupling_summary.get("class_counts", {})),
        "summary_text": coupling_summary.get("summary_text"),
        "top_grci_segments": coupling_summary.get("top_grci_segments", coupling_summary.get("high_attention_segments", [])),
        "top_rai_segments": coupling_summary.get("top_rai_segments", []),
        "top_grs_segments": coupling_summary.get("top_grs_segments", []),
    }

    return {
        "schema_version": "digital_twin_display_state_v2",
        "time_state": {
            "start_time": start_time,
            "end_time": end_time,
            "duration_min": duration_min,
            "sample_count": int(len(df)),
        },
        "position_state": position_state,
        "operation_state": operation_state,
        "geology_state": geology_state,
        "safety_state": {
            "gas_exceed_type_count": len(gas_exceed_types),
            "gas_exceed_types": gas_exceed_types,
        },
        "forward_risk_state": forward_state,
        "coupling_state": coupling_state,
        "source_semantics": {
            "operation_state": "record_window_observed",
            "geology_state": "excavated_segment_fusion_summary",
            "forward_risk_state": "forward_window_predictive_evidence",
            "coupling_state": "excavated_segment_retrospective_coupling",
        },
    }
