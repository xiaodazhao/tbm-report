from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from config import RESULT_DIR
from schemas.twin_contract import normalize_twin_state
from utils.serialization import serialize_for_json


DEFAULT_TWIN_SNAPSHOT_DIR = RESULT_DIR / "twin_snapshots"


def _snapshot_dir(directory: str | Path | None = None) -> Path:
    path = Path(directory) if directory is not None else DEFAULT_TWIN_SNAPSHOT_DIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def _safe_file_stem(value: str | None) -> str:
    text = str(value or "unknown").strip()
    for ch in ['/', '\\', ':', '*', '?', '"', '<', '>', '|', ' ']:
        text = text.replace(ch, '_')
    return text or "unknown"


def save_twin_snapshot(twin_state: dict[str, Any], directory: str | Path | None = None) -> dict[str, Any]:
    """Persist one TwinState snapshot as JSON.

    This JSON snapshot store is intentionally independent from SQLite CST storage,
    so the twin layer remains inspectable and versionable during development.
    """
    state = normalize_twin_state(twin_state)
    out_dir = _snapshot_dir(directory)
    date = _safe_file_stem(state.get("date"))
    mode = _safe_file_stem(state.get("analysis_mode"))
    key = _safe_file_stem(state.get("state_key") or state.get("snapshot_id") or f"{mode}_{date}")
    path = out_dir / f"{date}_{key}.json"
    payload = serialize_for_json(state)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"path": str(path), "filename": path.name, "snapshot_id": state.get("snapshot_id")}


def load_twin_snapshot(date: str | None = None, state_key: str | None = None, directory: str | Path | None = None) -> dict[str, Any] | None:
    """Load one snapshot by date/state_key.  Returns the latest matching file."""
    out_dir = _snapshot_dir(directory)
    if state_key:
        pattern = f"*{_safe_file_stem(state_key)}*.json"
    elif date:
        pattern = f"{_safe_file_stem(date)}_*.json"
    else:
        pattern = "*.json"
    matches = sorted(out_dir.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    if not matches:
        return None
    try:
        return normalize_twin_state(json.loads(matches[0].read_text(encoding="utf-8")))
    except Exception:
        return None


def load_latest_twin_snapshot(directory: str | Path | None = None) -> dict[str, Any] | None:
    """Load latest snapshot from JSON store."""
    return load_twin_snapshot(directory=directory)


def list_twin_snapshots(limit: int = 50, directory: str | Path | None = None) -> list[dict[str, Any]]:
    """List known snapshots with lightweight metadata."""
    out_dir = _snapshot_dir(directory)
    matches = sorted(out_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[: max(1, int(limit))]
    items: list[dict[str, Any]] = []
    for path in matches:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            payload = {}
        items.append({
            "filename": path.name,
            "path": str(path),
            "date": payload.get("date"),
            "analysis_mode": payload.get("analysis_mode"),
            "state_key": payload.get("state_key"),
            "snapshot_id": payload.get("snapshot_id"),
            "updated_at": payload.get("updated_at"),
        })
    return items
