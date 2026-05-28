from __future__ import annotations

from typing import Any

from schemas.twin_contract import normalize_twin_state, safe_float
from services.twin_diff_service import build_twin_diff, diff_to_text
from services.twin_store_service import load_twin_snapshot
from utils.serialization import serialize_for_json


def get_current_twin_state(date: str | None = None) -> dict[str, Any]:
    """Load the current/latest TwinState from the snapshot store."""
    state = load_twin_snapshot(date=date)
    return normalize_twin_state(state) if state else {}


def get_twin_events(date: str | None = None, event_type: str | None = None, level: str | None = None) -> list[dict[str, Any]]:
    """Return typed TwinEvents from one snapshot."""
    state = get_current_twin_state(date)
    events = state.get("events", []) if state else []
    if event_type:
        events = [event for event in events if isinstance(event, dict) and event.get("event_type") == event_type]
    if level:
        events = [event for event in events if isinstance(event, dict) and event.get("level") == level]
    return serialize_for_json(events)


def query_twin_by_chainage(date: str | None, chainage: float) -> dict[str, Any]:
    """Query the snapshot events and windows that cover one chainage."""
    state = get_current_twin_state(date)
    if not state:
        return {"has_state": False, "message": "未找到孪生状态快照。"}
    x = safe_float(chainage)
    matched_events = []
    if x is not None:
        for event in state.get("events", []) or []:
            if not isinstance(event, dict):
                continue
            loc = event.get("location", {}) or {}
            start = safe_float(loc.get("start_chainage"))
            end = safe_float(loc.get("end_chainage"))
            if start is not None and end is not None:
                if min(start, end) <= x <= max(start, end):
                    matched_events.append(event)
    return serialize_for_json({
        "has_state": True,
        "date": state.get("date"),
        "query_chainage": x,
        "matched_event_count": len(matched_events),
        "matched_events": matched_events,
        "spatial_reference": state.get("spatial_reference", {}),
        "forward_state": state.get("forward_state", {}),
    })


def explain_twin_event(date: str | None, event_id: str) -> dict[str, Any]:
    """Return a compact explanation payload for one event."""
    for event in get_twin_events(date):
        if isinstance(event, dict) and event.get("event_id") == event_id:
            return serialize_for_json({
                "found": True,
                "event": event,
                "explanation": "；".join(event.get("reasons", []) or []) or event.get("title"),
            })
    return {"found": False, "message": "未找到对应孪生事件。"}


def compare_twin_snapshots(date1: str, date2: str) -> dict[str, Any]:
    """Compare two stored twin snapshots."""
    prev = load_twin_snapshot(date=date1)
    curr = load_twin_snapshot(date=date2)
    diff = build_twin_diff(prev, curr)
    return serialize_for_json({
        "date1": date1,
        "date2": date2,
        "has_previous": diff.get("has_previous", False),
        "diff": diff,
        "diff_text": diff_to_text(diff),
    })
