"""
geology_v2.cell_builder

构建沿里程方向的 cell。

本模块只负责根据 PLC 数据或给定 extra_min / extra_max 构建里程 cell，
不做证据投影、不做地质融合。
"""

from __future__ import annotations

import math
from typing import Any, Optional

import pandas as pd

from geology_v2.config import DEFAULT_CELL_LENGTH_M


CHAINAGE_COLUMN_CANDIDATES = [
    "chainage",
    "里程",
    "当前里程",
    "桩号",
    "推进里程",
    "mile",
    "mileage",
]


def _find_chainage_col(df: pd.DataFrame) -> Optional[str]:
    """
    自动寻找 PLC 数据中的里程列。
    """
    if df is None or df.empty:
        return None

    lower_map = {str(col).strip().lower(): col for col in df.columns}

    for name in CHAINAGE_COLUMN_CANDIDATES:
        key = name.lower()
        if key in lower_map:
            return lower_map[key]

    for col in df.columns:
        col_text = str(col).strip().lower()
        if "chainage" in col_text or "里程" in col_text or "桩号" in col_text:
            return col

    return None


def _safe_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        x = float(value)
        if math.isfinite(x):
            return x
    except Exception:
        return None
    return None


def _number_key(value: Any) -> str:
    """
    生成稳定的 cell_id 数字片段。
    """
    try:
        x = float(value)
        if math.isfinite(x) and x.is_integer():
            return str(int(x))
        return f"{x:.3f}".rstrip("0").rstrip(".")
    except Exception:
        return str(value)


def _build_cell_id(cell_start: float, cell_end: float) -> str:
    return f"cell_{_number_key(cell_start)}_{_number_key(cell_end)}"


def build_chainage_cells(
    df_plc: pd.DataFrame,
    cell_length: float = DEFAULT_CELL_LENGTH_M,
    extra_min: Optional[float] = None,
    extra_max: Optional[float] = None,
) -> pd.DataFrame:
    """
    根据 PLC 数据构建沿里程方向的 cell。

    参数：
        df_plc:
            PLC 原始数据或已处理数据，需要包含里程列。
        cell_length:
            cell 长度，默认 10m。
        extra_min:
            可选的额外最小里程。
            用于把前方预报范围也纳入 cell。
        extra_max:
            可选的额外最大里程。
            用于把前方预报范围也纳入 cell。

    输出字段：
        cell_id
        cell_start
        cell_end
        cell_center
        cell_length

    注意：
        如果 df_plc 没有里程列，但 extra_min / extra_max 都给了，
        仍然可以构建 cell。
    """
    if cell_length is None or float(cell_length) <= 0:
        cell_length = DEFAULT_CELL_LENGTH_M

    cell_length = float(cell_length)

    values = []

    if df_plc is not None and not df_plc.empty:
        chainage_col = _find_chainage_col(df_plc)
        if chainage_col is not None:
            series = pd.to_numeric(df_plc[chainage_col], errors="coerce").dropna()
            values.extend(series.astype(float).tolist())

    extra_min_value = _safe_float(extra_min)
    extra_max_value = _safe_float(extra_max)

    if extra_min_value is not None:
        values.append(extra_min_value)
    if extra_max_value is not None:
        values.append(extra_max_value)

    if not values:
        return pd.DataFrame(
            columns=[
                "cell_id",
                "cell_start",
                "cell_end",
                "cell_center",
                "cell_length",
            ]
        )

    min_chainage = min(values)
    max_chainage = max(values)

    # 向 cell_length 对齐，避免从奇怪的小数点开始切 cell。
    start_aligned = math.floor(min_chainage / cell_length) * cell_length
    end_aligned = math.ceil(max_chainage / cell_length) * cell_length

    # 如果刚好落在边界，也至少生成一个 cell。
    if end_aligned <= start_aligned:
        end_aligned = start_aligned + cell_length

    records = []
    current = start_aligned

    # 加一个很小的容差，避免浮点误差导致最后一个 cell 丢失。
    eps = 1e-9
    while current < end_aligned - eps:
        cell_start = float(current)
        cell_end = float(current + cell_length)
        cell_center = float((cell_start + cell_end) / 2.0)

        records.append(
            {
                "cell_id": _build_cell_id(cell_start, cell_end),
                "cell_start": cell_start,
                "cell_end": cell_end,
                "cell_center": cell_center,
                "cell_length": cell_length,
            }
        )

        current += cell_length

    return pd.DataFrame(records)