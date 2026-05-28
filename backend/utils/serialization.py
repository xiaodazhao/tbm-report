from __future__ import annotations

import dataclasses
import math
from datetime import date, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

try:  # pydantic is available in the backend, but keep this optional.
    from pydantic import BaseModel
except Exception:  # pragma: no cover
    BaseModel = None  # type: ignore


def _safe_float(value: Any) -> float | None:
    """Return a JSON-safe float, converting NaN/inf to None."""
    try:
        x = float(value)
    except Exception:
        return None
    if not math.isfinite(x):
        return None
    return x


def serialize_for_json(obj: Any, _seen: set[int] | None = None) -> Any:
    """Convert pandas/numpy/dataclass/pydantic-heavy results into strict JSON-safe objects.

    Important behavior:
    - NaN / inf are converted to None, not Python float('nan').
    - DataFrame / Series are recursively serialized.
    - Path, datetime/date, dataclass, pydantic model, set are supported.
    - Recursive object references are represented as "<recursive_ref>" instead of
      causing maximum-recursion-depth failures.
    """
    if _seen is None:
        _seen = set()

    if obj is None:
        return None

    if isinstance(obj, (dict, list, tuple, set, pd.DataFrame, pd.Series, np.ndarray)):
        obj_id = id(obj)
        if obj_id in _seen:
            return "<recursive_ref>"
        _seen.add(obj_id)
    else:
        obj_id = None

    try:
        if BaseModel is not None and isinstance(obj, BaseModel):
            return serialize_for_json(obj.model_dump(), _seen)

        if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
            return serialize_for_json(dataclasses.asdict(obj), _seen)

        if isinstance(obj, dict):
            return {str(k): serialize_for_json(v, _seen) for k, v in obj.items()}

        if isinstance(obj, (list, tuple)):
            return [serialize_for_json(v, _seen) for v in obj]

        if isinstance(obj, set):
            return [serialize_for_json(v, _seen) for v in sorted(obj, key=lambda x: str(x))]

        if isinstance(obj, Path):
            return str(obj)

        if isinstance(obj, pd.Timestamp):
            if pd.isna(obj):
                return None
            return obj.strftime("%Y-%m-%d %H:%M:%S")

        if isinstance(obj, (datetime, date)):
            return obj.isoformat(sep=" ") if isinstance(obj, datetime) else obj.isoformat()

        if isinstance(obj, pd.DataFrame):
            safe = obj.replace([np.inf, -np.inf], np.nan).where(pd.notna(obj), None)
            return [serialize_for_json(row, _seen) for row in safe.to_dict(orient="records")]

        if isinstance(obj, pd.Series):
            safe = obj.replace([np.inf, -np.inf], np.nan).where(pd.notna(obj), None)
            return serialize_for_json(safe.to_dict(), _seen)

        if isinstance(obj, np.ndarray):
            return serialize_for_json(obj.tolist(), _seen)

        if isinstance(obj, np.integer):
            return int(obj)

        if isinstance(obj, np.floating):
            return _safe_float(obj)

        if isinstance(obj, float):
            return _safe_float(obj)

        if obj is pd.NA or obj is pd.NaT:
            return None

        try:
            if pd.isna(obj):
                return None
        except Exception:
            pass

        return obj
    finally:
        if obj_id is not None:
            _seen.discard(obj_id)
