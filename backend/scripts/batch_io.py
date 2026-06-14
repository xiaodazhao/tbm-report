from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pandas as pd


DATE_RE = re.compile(r"(20\d{2})[-_]?(\d{2})[-_]?(\d{2})")


def backend_dir() -> Path:
    return Path(__file__).resolve().parents[1]


def resolve_output_dir(value: str | Path) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = backend_dir() / path
    path.mkdir(parents=True, exist_ok=True)
    return path


def parse_date_from_name(name: str) -> str | None:
    match = DATE_RE.search(str(name))
    if not match:
        return None
    return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"


def parse_dates(date: str | None = None, dates: str | None = None) -> list[str]:
    values: list[str] = []
    if dates:
        values.extend(item.strip() for item in dates.split(",") if item.strip())
    if date:
        values.append(date.strip())
    return list(dict.fromkeys(values))


def dates_from_file(path: str | Path, *, class_filter: set[str] | None = None) -> list[str]:
    frame = pd.read_csv(path)
    if "date" not in frame.columns:
        return []
    if class_filter and "class_label" in frame.columns:
        frame = frame[frame["class_label"].astype(str).isin(class_filter)].copy()
    if "usable_for_batch" in frame.columns:
        usable = frame["usable_for_batch"].map(_truthy)
        frame = frame[usable].copy()
    return [str(item) for item in frame["date"].dropna().tolist()]


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(json_safe(payload), ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([csv_safe(row) for row in rows]).to_csv(path, index=False, encoding="utf-8-sig")


def json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [json_safe(item) for item in value]
    if isinstance(value, pd.DataFrame):
        return [json_safe(item) for item in value.to_dict(orient="records")]
    if isinstance(value, pd.Series):
        return json_safe(value.to_dict())
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    if hasattr(value, "item"):
        try:
            return json_safe(value.item())
        except Exception:
            pass
    return value


def csv_safe(row: dict[str, Any]) -> dict[str, Any]:
    out = {}
    for key, value in row.items():
        if isinstance(value, (dict, list, tuple, set)):
            out[key] = json.dumps(json_safe(value), ensure_ascii=False, default=str)
        else:
            out[key] = value
    return out


def safe_float(value: Any) -> float | None:
    try:
        number = float(value)
    except Exception:
        return None
    if pd.isna(number):
        return None
    return number


def safe_int(value: Any) -> int:
    try:
        return int(value)
    except Exception:
        return 0


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    return text in {"1", "true", "yes", "y", "on"}
