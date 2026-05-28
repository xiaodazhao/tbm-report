from __future__ import annotations

from typing import Any

from schemas.twin_contract import (
    TWIN_DIFF_SCHEMA_VERSION,
    dedup_text,
    normalize_twin_state,
    safe_float,
    split_tags,
)


def _delta(current: Any, previous: Any) -> float | None:
    cur = safe_float(current)
    prev = safe_float(previous)
    if cur is None or prev is None:
        return None
    return round(cur - prev, 6)


def _metric_change_group(current_group: dict[str, Any], previous_group: dict[str, Any], metric_names: list[str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for name in metric_names:
        out[f"{name}_previous"] = previous_group.get(name)
        out[f"{name}_current"] = current_group.get(name)
        out[f"{name}_delta"] = _delta(current_group.get(name), previous_group.get(name))
    return out


def _event_keys(state: dict[str, Any]) -> set[str]:
    keys = set()
    for event in state.get("events", []) or []:
        if not isinstance(event, dict):
            continue
        loc = event.get("location", {}) or {}
        key = "|".join([
            str(event.get("event_type", "")),
            str(loc.get("segment_label") or loc.get("start_chainage") or loc.get("current_chainage") or ""),
            str(event.get("severity", "")),
        ])
        keys.add(key)
    return keys


def build_twin_diff(previous_state: dict[str, Any] | None, current_state: dict[str, Any] | None) -> dict[str, Any]:
    """Build a stable state-to-state diff.

    The diff is a structured object only.  Text summaries are produced by
    ``diff_to_text`` so structured twin state and natural-language output stay
    separate.
    """
    current = normalize_twin_state(current_state)
    if not isinstance(previous_state, dict) or not previous_state:
        return {
            "schema_version": TWIN_DIFF_SCHEMA_VERSION,
            "has_previous": False,
            "previous_snapshot_id": None,
            "current_snapshot_id": current.get("snapshot_id"),
            "changed_fields": ["initial_state"],
            "operation": {},
            "spatial": {},
            "geology": {},
            "response": {},
            "attention": {},
            "forward": {},
            "events": {
                "new_event_count": len(current.get("events", []) or []),
                "resolved_event_count": 0,
            },
        }

    previous = normalize_twin_state(previous_state)
    changed_fields: list[str] = []

    operation = _metric_change_group(
        current.get("operation_state", {}),
        previous.get("operation_state", {}),
        ["work_duration_min", "stop_duration_min", "transition_duration_min", "abnormal_duration_min", "work_ratio", "stop_ratio"],
    )
    if current.get("operation_state", {}).get("main_state") != previous.get("operation_state", {}).get("main_state"):
        changed_fields.append("operation_state.main_state")
    for key, value in operation.items():
        if key.endswith("_delta") and value not in (None, 0, 0.0):
            changed_fields.append("operation_state")
            break

    spatial = {
        "face_chainage_previous": previous.get("spatial_reference", {}).get("face_chainage"),
        "face_chainage_current": current.get("spatial_reference", {}).get("face_chainage"),
        "face_chainage_delta_m": _delta(current.get("spatial_reference", {}).get("face_chainage"), previous.get("spatial_reference", {}).get("face_chainage")),
        "advance_length_previous_m": previous.get("spatial_reference", {}).get("advance_length_m"),
        "advance_length_current_m": current.get("spatial_reference", {}).get("advance_length_m"),
    }
    if spatial.get("face_chainage_delta_m") not in (None, 0, 0.0):
        changed_fields.append("spatial_reference.face_chainage")

    prev_hazards = set(split_tags(previous.get("geological_state", {}).get("geo_hazard_tags")))
    cur_hazards = set(split_tags(current.get("geological_state", {}).get("geo_hazard_tags")))
    geology = {
        "new_hazard_tags": sorted(cur_hazards - prev_hazards),
        "resolved_hazard_tags": sorted(prev_hazards - cur_hazards),
        "continued_hazard_tags": sorted(prev_hazards & cur_hazards),
        "active_report_source_count_delta": _delta(current.get("geological_state", {}).get("active_report_source_count"), previous.get("geological_state", {}).get("active_report_source_count")),
        "matched_evidence_record_count_delta": _delta(current.get("geological_state", {}).get("matched_evidence_record_count"), previous.get("geological_state", {}).get("matched_evidence_record_count")),
    }
    if geology["new_hazard_tags"] or geology["resolved_hazard_tags"]:
        changed_fields.append("geological_state.geo_hazard_tags")

    response = _metric_change_group(current.get("response_state", {}), previous.get("response_state", {}), ["RAI"])
    if abs(response.get("RAI_delta") or 0) >= 0.05:
        changed_fields.append("response_state.RAI")

    attention = _metric_change_group(current.get("attention_state", {}), previous.get("attention_state", {}), ["GRS_geo_base", "GRS_adjusted", "GRCI"])
    if abs(attention.get("GRCI_delta") or 0) >= 0.05:
        changed_fields.append("attention_state.GRCI")
    if abs(attention.get("GRS_adjusted_delta") or 0) >= 0.05:
        changed_fields.append("attention_state.GRS_adjusted")

    prev_forward = previous.get("forward_state", {})
    cur_forward = current.get("forward_state", {})
    forward = {
        "advice_level_previous": prev_forward.get("forward_advice_level"),
        "advice_level_current": cur_forward.get("forward_advice_level"),
        "forward_evidence_count_delta": _delta(cur_forward.get("forward_evidence_count"), prev_forward.get("forward_evidence_count")),
        "new_forward_hazard_tags": sorted(set(split_tags(cur_forward.get("forward_main_hazard_tags"))) - set(split_tags(prev_forward.get("forward_main_hazard_tags")))),
    }
    if forward["advice_level_previous"] != forward["advice_level_current"]:
        changed_fields.append("forward_state.forward_advice_level")

    prev_events = _event_keys(previous)
    cur_events = _event_keys(current)
    events = {
        "new_event_count": len(cur_events - prev_events),
        "resolved_event_count": len(prev_events - cur_events),
        "continued_event_count": len(cur_events & prev_events),
    }
    if events["new_event_count"] or events["resolved_event_count"]:
        changed_fields.append("events")

    return {
        "schema_version": TWIN_DIFF_SCHEMA_VERSION,
        "has_previous": True,
        "previous_snapshot_id": previous.get("snapshot_id"),
        "current_snapshot_id": current.get("snapshot_id"),
        "previous_date": previous.get("date"),
        "current_date": current.get("date"),
        "changed_fields": dedup_text(changed_fields),
        "operation": operation,
        "spatial": spatial,
        "geology": geology,
        "response": response,
        "attention": attention,
        "forward": forward,
        "events": events,
    }


def diff_to_text(diff: dict[str, Any] | None) -> str:
    """Render a compact Chinese text from a TwinDiff object."""
    if not isinstance(diff, dict) or not diff:
        return "暂无上一状态可供比较。"
    if not diff.get("has_previous"):
        return "暂无上一状态可供比较，本次为初始施工状态快照。"

    lines = []
    spatial = diff.get("spatial", {})
    face_delta = spatial.get("face_chainage_delta_m")
    if face_delta is not None:
        lines.append(f"掌子面里程变化 {face_delta:+.2f} m")

    operation = diff.get("operation", {})
    work_delta = operation.get("work_duration_min_delta")
    stop_delta = operation.get("stop_duration_min_delta")
    if work_delta is not None or stop_delta is not None:
        lines.append(f"工作时长变化 {work_delta or 0:+.1f} min，停机时长变化 {stop_delta or 0:+.1f} min")

    response = diff.get("response", {})
    attention = diff.get("attention", {})
    if response.get("RAI_delta") is not None:
        lines.append(f"RAI 变化 {response.get('RAI_delta'):+.2f}")
    if attention.get("GRS_adjusted_delta") is not None:
        lines.append(f"GRS_adjusted 变化 {attention.get('GRS_adjusted_delta'):+.2f}")
    if attention.get("GRCI_delta") is not None:
        lines.append(f"GRCI 变化 {attention.get('GRCI_delta'):+.2f}")

    geology = diff.get("geology", {})
    if geology.get("new_hazard_tags"):
        lines.append(f"新增地质关注标签：{'、'.join(geology.get('new_hazard_tags'))}")
    forward = diff.get("forward", {})
    if forward.get("advice_level_previous") != forward.get("advice_level_current"):
        lines.append(f"前方提示等级由 {forward.get('advice_level_previous') or '无'} 变为 {forward.get('advice_level_current') or '无'}")
    events = diff.get("events", {})
    if events.get("new_event_count"):
        lines.append(f"新增孪生事件 {events.get('new_event_count')} 个")

    return "；".join(lines) + "。" if lines else "与上一状态相比未识别到主要状态变化。"
