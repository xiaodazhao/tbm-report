from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from schemas.twin_contract import (
    LEVEL_FORWARD_WINDOW,
    LEVEL_RECORD_WINDOW,
    LEVEL_SEGMENT_WINDOW,
    SEMANTIC_OBSERVED,
    SEMANTIC_PREDICTIVE_EVIDENCE,
    SEMANTIC_RETROSPECTIVE,
    STATE_FORWARD_EVIDENCE,
    STATE_GAS_SAFETY,
    STATE_GEO_RESPONSE_COUPLING,
    STATE_RESPONSE_ANOMALY,
    TWIN_EVENT_SCHEMA_VERSION,
    clamp01,
    dedup_text,
    safe_float,
    safe_int,
    safe_text,
    split_tags,
)


def _event_id(event_type: str, index: int) -> str:
    return f"evt_{datetime.now().strftime('%Y%m%d%H%M%S')}_{event_type}_{index}_{str(uuid4())[:8]}"


def _segment_name(item: dict[str, Any]) -> str:
    for key in ("segment", "segment_label_dk", "segment_name", "chainage_range_dk", "chainage_range"):
        if item.get(key):
            return str(item.get(key))
    start = item.get("segment_start_first", item.get("segment_start"))
    end = item.get("segment_end_first", item.get("segment_end"))
    if start is not None or end is not None:
        return f"{start or '?'}~{end or '?'}"
    return "未知区段"


def _segment_chainage(item: dict[str, Any]) -> dict[str, Any]:
    start = item.get("segment_start_first", item.get("segment_start"))
    end = item.get("segment_end_first", item.get("segment_end"))
    return {
        "start_chainage": safe_float(start),
        "end_chainage": safe_float(end),
        "segment_label": _segment_name(item),
    }


def _metric_dict(item: dict[str, Any]) -> dict[str, float]:
    return {
        "GRS_geo_base": clamp01(item.get("GRS_geo_base", item.get("GRS_base", 0.0))),
        "GRS_adjusted": clamp01(item.get("GRS_adjusted", item.get("GRS", 0.0))),
        "RAI": clamp01(item.get("RAI", item.get("response_anomaly_index", 0.0))),
        "GRCI": clamp01(item.get("GRCI", item.get("geo_response_coupling_index", item.get("coupling_index", 0.0)))),
    }


def _segment_reasons(item: dict[str, Any], *, focus: str) -> list[str]:
    metrics = _metric_dict(item)
    reasons: list[str] = []
    hazards = split_tags(item.get("seg_geo_hazard_mode") or item.get("geo_hazard_tags") or item.get("hazard_mode"))
    if hazards:
        reasons.append(f"地质证据提示：{'、'.join(hazards[:4])}")
    grade = item.get("seg_geo_grade_mode") or item.get("fused_grade_mode") or item.get("geo_fused_grade")
    if grade:
        reasons.append(f"融合围岩等级/建议等级为 {grade}")
    if metrics["GRS_geo_base"] >= 0.55:
        reasons.append(f"地质基础关注度 GRS_geo_base={metrics['GRS_geo_base']:.2f}")
    if metrics["RAI"] >= 0.55:
        reasons.append(f"施工响应异常度 RAI={metrics['RAI']:.2f}")
    if metrics["GRCI"] >= 0.50:
        reasons.append(f"地质-施工耦合关注度 GRCI={metrics['GRCI']:.2f}")
    anomaly_type = item.get("anomaly_type")
    if anomaly_type:
        reasons.append(f"响应异常类型为{anomaly_type}")
    weak_reasons = safe_text(item.get("weak_anomaly_reasons"), default="")
    if weak_reasons:
        reasons.append(f"弱标签响应依据：{weak_reasons}")
    interp = safe_text(item.get("coupling_interpretation"), default="")
    if interp:
        reasons.append(interp)
    if not reasons:
        reasons.append(focus)
    return dedup_text(reasons)


def _build_event(
    *,
    event_type: str,
    state_space: str,
    level: str,
    semantic: str,
    title: str,
    severity: str,
    metrics: dict[str, Any] | None = None,
    location: dict[str, Any] | None = None,
    reasons: list[str] | None = None,
    source_refs: dict[str, Any] | None = None,
    payload: dict[str, Any] | None = None,
    index: int = 0,
) -> dict[str, Any]:
    return {
        "schema_version": TWIN_EVENT_SCHEMA_VERSION,
        "event_id": _event_id(event_type, index),
        "event_type": event_type,
        "state_space": state_space,
        "level": level,
        "semantic": semantic,
        "title": title,
        "severity": severity,
        "metrics": metrics or {},
        "location": location or {},
        "reasons": reasons or [],
        "source_refs": source_refs or {},
        "payload": payload or {},
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def build_twin_events(analysis_result: dict[str, Any], twin_state: dict[str, Any] | None = None, *, top_k: int = 5) -> list[dict[str, Any]]:
    """Build typed TwinEvents from analysis outputs.

    Events are the bridge between raw metrics and an explorable digital-twin
    state.  They keep current-face / excavated-segment / forward-window semantics
    separate and provide stable reasons for Agent answers.
    """
    result = analysis_result if isinstance(analysis_result, dict) else {}
    twin = twin_state if isinstance(twin_state, dict) else {}
    events: list[dict[str, Any]] = []

    top_grci = result.get("top_grci_segments") or (result.get("coupling_summary") or {}).get("top_grci_segments") or result.get("high_attention_segments") or []
    for idx, item in enumerate(top_grci[:top_k]):
        if not isinstance(item, dict):
            continue
        metrics = _metric_dict(item)
        severity = "high" if metrics["GRCI"] >= 0.75 else "medium" if metrics["GRCI"] >= 0.50 else "low"
        events.append(_build_event(
            event_type="high_geo_response_coupling",
            state_space=STATE_GEO_RESPONSE_COUPLING,
            level=LEVEL_SEGMENT_WINDOW,
            semantic=SEMANTIC_RETROSPECTIVE,
            title=f"已开挖区段地质-施工耦合关注：{_segment_name(item)}",
            severity=severity,
            metrics=metrics,
            location=_segment_chainage(item),
            reasons=_segment_reasons(item, focus="该区段 GRCI 排名靠前，需结合地质证据和施工响应复核。"),
            source_refs={"matched_evidence_ids": item.get("matched_evidence_ids", [])},
            payload=item,
            index=idx,
        ))

    top_rai = result.get("top_rai_segments") or (result.get("coupling_summary") or {}).get("top_rai_segments") or []
    for idx, item in enumerate(top_rai[:top_k]):
        if not isinstance(item, dict):
            continue
        metrics = _metric_dict(item)
        if metrics["RAI"] < 0.50:
            continue
        severity = "high" if metrics["RAI"] >= 0.75 else "medium"
        events.append(_build_event(
            event_type="response_anomaly_segment",
            state_space=STATE_RESPONSE_ANOMALY,
            level=LEVEL_SEGMENT_WINDOW,
            semantic=SEMANTIC_RETROSPECTIVE,
            title=f"已开挖区段施工响应异常：{_segment_name(item)}",
            severity=severity,
            metrics=metrics,
            location=_segment_chainage(item),
            reasons=_segment_reasons(item, focus="该区段施工响应异常度较高。"),
            payload=item,
            index=idx,
        ))

    forward = result.get("forward_risk_summary") or twin.get("forward_state") or {}
    if isinstance(forward, dict) and forward.get("has_forward_risk"):
        evidence_count = safe_int(forward.get("forward_evidence_count", forward.get("forward_segment_count", 0)))
        level = forward.get("forward_advice_level") or forward.get("advice_level") or "none"
        if evidence_count > 0 or level not in {"none", None, ""}:
            hazards = split_tags(forward.get("forward_main_hazard_tags") or forward.get("main_hazards"))
            reasons = []
            reasons.append(f"前方窗口内 evidence 记录数为 {evidence_count} 条")
            reasons.append(f"报告-来源组合数为 {safe_int(forward.get('forward_report_source_count', forward.get('multi_source_count', 0)))}")
            if hazards:
                reasons.append(f"主要前方关注类型：{'、'.join(hazards[:4])}")
            events.append(_build_event(
                event_type="forward_evidence_attention",
                state_space=STATE_FORWARD_EVIDENCE,
                level=LEVEL_FORWARD_WINDOW,
                semantic=SEMANTIC_PREDICTIVE_EVIDENCE,
                title="掌子面前方窗口地质证据提示",
                severity="high" if level == "high" else "medium" if level == "medium" else "low",
                metrics={
                    "forward_evidence_count": evidence_count,
                    "forward_high_source_risk_evidence_count": safe_int(forward.get("forward_high_source_risk_evidence_count", forward.get("high_risk_count", 0))),
                    "forward_report_source_count": safe_int(forward.get("forward_report_source_count", forward.get("multi_source_count", 0))),
                },
                location={
                    "current_chainage": safe_float(forward.get("current_chainage")),
                    "start_chainage": safe_float(forward.get("forward_start")),
                    "end_chainage": safe_float(forward.get("forward_end")),
                    "lookahead_m": safe_float(forward.get("lookahead_m")),
                },
                reasons=dedup_text(reasons),
                payload=forward,
                index=len(events),
            ))

    gas_stats = result.get("gas_stats") or {}
    gas_all = gas_stats.get("all", {}) if isinstance(gas_stats, dict) else {}
    for gas_name, stat in gas_all.items():
        if not isinstance(stat, dict):
            continue
        count = safe_int(stat.get("exceed_event_count"))
        if count <= 0:
            continue
        events.append(_build_event(
            event_type="gas_threshold_exceedance",
            state_space=STATE_GAS_SAFETY,
            level=LEVEL_RECORD_WINDOW,
            semantic=SEMANTIC_OBSERVED,
            title=f"气体阈值超限：{gas_name}",
            severity="medium",
            metrics={"exceed_event_count": count, "threshold": stat.get("threshold"), "max": stat.get("max")},
            reasons=[f"{gas_name} 超过当前配置阈值的记录段 {count} 次"],
            payload={"gas": gas_name, "stat": stat},
            index=len(events),
        ))

    stats = result.get("stats") or {}
    abnormal_count = safe_int(stats.get("abnormal_count"))
    abnormal_min = safe_float(stats.get("abnormal_total_min"), 0.0) or 0.0
    if abnormal_count > 0 or abnormal_min > 0:
        events.append(_build_event(
            event_type="operation_abnormal_mode",
            state_space="operation_mode",
            level=LEVEL_RECORD_WINDOW,
            semantic=SEMANTIC_OBSERVED,
            title="基础工况异常扭矩记录",
            severity="medium" if abnormal_min < 30 else "high",
            metrics={"abnormal_count": abnormal_count, "abnormal_duration_min": abnormal_min},
            reasons=[f"基础工况识别到异常扭矩段 {abnormal_count} 个，累计 {abnormal_min:.1f} min"],
            payload={"stats": stats},
            index=len(events),
        ))

    # Stable deterministic-ish order: high first, then semantic level.
    severity_rank = {"high": 0, "medium": 1, "low": 2, "info": 3}
    events.sort(key=lambda event: (severity_rank.get(event.get("severity"), 9), event.get("level", ""), event.get("event_type", "")))
    return events
