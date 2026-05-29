"""
geology_v2.evidence_projector

将标准化后的地质证据投影到 chainage cells。

输入：
    cells_df
    normalized_evidence_df

输出：
    cell_evidence_df

核心思想：
1. segment 类型证据：
   - cell_center 在证据区间内，distance=0；
   - 区间外，distance 为 cell_center 到区间边界的距离。
2. point / anomaly_point 类型证据：
   - distance 为 cell_center 到证据 center_chainage 的距离。
3. overview / background：
   - 默认不参与强逐里程融合；
   - 可以保留极低权重，作为背景。
4. spatial_weight:
   spatial_weight = exp(-0.5 * (distance / sigma) ** 2)
5. effective_weight:
   effective_weight = spatial_weight * source_reliability * evidence_strength

注意：
    effective_weight 只是融合权重，不是风险概率。
"""

from __future__ import annotations

import math
from typing import Any, Optional

import pandas as pd

from geology_v2.config import get_spatial_sigma


CELL_EVIDENCE_COLUMNS = [
    "cell_id",
    "evidence_id",
    "source_type_norm",
    "spatial_type",
    "distance_m",
    "spatial_weight",
    "source_reliability",
    "evidence_strength",
    "effective_weight",
]


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


def _spatial_weight(distance_m: float, sigma_m: float) -> float:
    """
    高斯空间权重。
    """
    distance = abs(float(distance_m))
    sigma = max(float(sigma_m), 1e-6)
    value = math.exp(-0.5 * (distance / sigma) ** 2)
    return float(max(0.0, min(value, 1.0)))


def _distance_to_segment(
    cell_center: float,
    start_chainage: Optional[float],
    end_chainage: Optional[float],
) -> Optional[float]:
    """
    cell_center 到 segment 证据区间的距离。

    区间内 distance = 0。
    区间外 distance = 到最近边界的距离。
    """
    if start_chainage is None or end_chainage is None:
        return None

    start = float(min(start_chainage, end_chainage))
    end = float(max(start_chainage, end_chainage))
    center = float(cell_center)

    if start <= center <= end:
        return 0.0

    if center < start:
        return float(start - center)

    return float(center - end)


def _distance_to_point(
    cell_center: float,
    center_chainage: Optional[float],
) -> Optional[float]:
    """
    cell_center 到点状证据的距离。
    """
    if center_chainage is None:
        return None

    return float(abs(float(cell_center) - float(center_chainage)))


def _evidence_distance(cell_center: float, evidence_row: pd.Series) -> Optional[float]:
    """
    根据 spatial_type 计算证据到 cell 的距离。
    """
    spatial_type = str(evidence_row.get("spatial_type", "unknown") or "unknown")

    start_chainage = _safe_float(evidence_row.get("start_chainage"))
    end_chainage = _safe_float(evidence_row.get("end_chainage"))
    center_chainage = _safe_float(evidence_row.get("center_chainage"))

    if spatial_type in {"segment", "report_conclusion"}:
        return _distance_to_segment(
            cell_center=cell_center,
            start_chainage=start_chainage,
            end_chainage=end_chainage,
        )

    if spatial_type in {"point", "anomaly_point"}:
        return _distance_to_point(
            cell_center=cell_center,
            center_chainage=center_chainage,
        )

    if spatial_type in {"overview", "background"}:
        # overview 不强逐里程融合，给一个很大的虚拟距离。
        # 后面 effective_weight 会非常低。
        if center_chainage is not None:
            return _distance_to_point(
                cell_center=cell_center,
                center_chainage=center_chainage,
            )
        return 9999.0

    # unknown 尽量用 center_chainage。
    if center_chainage is not None:
        return _distance_to_point(
            cell_center=cell_center,
            center_chainage=center_chainage,
        )

    return None


def _projection_radius(source_type_norm: str, spatial_type: str, sigma_m: float) -> float:
    """
    控制投影范围，避免所有证据投影到所有 cell，导致速度太慢。

    默认取 3 * sigma。
    对 segment 证据，区间内总是命中；区间外最多扩散 3 * sigma。
    """
    if spatial_type in {"overview", "background"}:
        return 0.0

    return float(max(3.0 * sigma_m, 1.0))


def _should_keep_projection(
    distance_m: Optional[float],
    source_type_norm: str,
    spatial_type: str,
    sigma_m: float,
) -> bool:
    """
    判断一条 evidence-cell 投影是否保留。
    """
    if distance_m is None:
        return False

    if spatial_type in {"overview", "background"}:
        # overview 默认不进入强融合。
        # 如果后续你想让 overview 作为背景进入，可以改这里。
        return False

    radius = _projection_radius(source_type_norm, spatial_type, sigma_m)
    return abs(float(distance_m)) <= radius


def project_evidence_to_cells(
    cells_df: pd.DataFrame,
    normalized_evidence_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    将 normalized_evidence_df 投影到 cells_df。

    参数：
        cells_df:
            build_chainage_cells 的输出。
        normalized_evidence_df:
            normalize_evidence_df 的输出。

    输出字段：
        cell_id
        evidence_id
        source_type_norm
        spatial_type
        distance_m
        spatial_weight
        source_reliability
        evidence_strength
        effective_weight
    """
    if cells_df is None or cells_df.empty:
        return pd.DataFrame(columns=CELL_EVIDENCE_COLUMNS)

    if normalized_evidence_df is None or normalized_evidence_df.empty:
        return pd.DataFrame(columns=CELL_EVIDENCE_COLUMNS)

    required_cell_cols = {"cell_id", "cell_center"}
    missing_cell_cols = required_cell_cols - set(cells_df.columns)
    if missing_cell_cols:
        raise ValueError(f"cells_df missing required columns: {sorted(missing_cell_cols)}")

    required_evidence_cols = {
        "evidence_id",
        "source_type_norm",
        "spatial_type",
        "source_reliability",
        "evidence_strength",
    }
    missing_evidence_cols = required_evidence_cols - set(normalized_evidence_df.columns)
    if missing_evidence_cols:
        raise ValueError(f"normalized_evidence_df missing required columns: {sorted(missing_evidence_cols)}")

    cells = cells_df.copy()
    evidences = normalized_evidence_df.copy()

    cells["cell_center"] = pd.to_numeric(cells["cell_center"], errors="coerce")
    cells = cells.dropna(subset=["cell_center"]).copy()

    if cells.empty:
        return pd.DataFrame(columns=CELL_EVIDENCE_COLUMNS)

    records = []

    for _, evidence in evidences.iterrows():
        evidence_id = str(evidence.get("evidence_id", "") or "").strip()
        if not evidence_id:
            continue

        source_type_norm = str(evidence.get("source_type_norm", "unknown") or "unknown")
        spatial_type = str(evidence.get("spatial_type", "unknown") or "unknown")

        source_reliability = _safe_float(evidence.get("source_reliability"))
        evidence_strength = _safe_float(evidence.get("evidence_strength"))

        if source_reliability is None:
            source_reliability = 0.0
        if evidence_strength is None:
            evidence_strength = 0.0

        # v2 可靠性修正：
        # source_reliability / evidence_strength 是融合权重项，不允许单项超过 1。
        # 否则 point evidence 在 spatial_weight 接近 1 时，会把 effective_weight 推到 1 以上。
        source_reliability = float(max(0.0, min(source_reliability, 1.0)))
        evidence_strength = float(max(0.0, min(evidence_strength, 1.0)))

        sigma_m = get_spatial_sigma(
            source_type_norm=source_type_norm,
            spatial_type=spatial_type,
        )

        for _, cell in cells.iterrows():
            cell_center = _safe_float(cell.get("cell_center"))
            if cell_center is None:
                continue

            distance_m = _evidence_distance(
                cell_center=cell_center,
                evidence_row=evidence,
            )

            if not _should_keep_projection(
                distance_m=distance_m,
                source_type_norm=source_type_norm,
                spatial_type=spatial_type,
                sigma_m=sigma_m,
            ):
                continue

            spatial_weight = _spatial_weight(
                distance_m=float(distance_m),
                sigma_m=sigma_m,
            )

            effective_weight = float(spatial_weight * source_reliability * evidence_strength)
            effective_weight = float(max(0.0, min(effective_weight, 1.0)))

            if effective_weight <= 1e-12:
                continue

            records.append(
                {
                    "cell_id": str(cell.get("cell_id")),
                    "evidence_id": evidence_id,
                    "source_type_norm": source_type_norm,
                    "spatial_type": spatial_type,
                    "distance_m": float(distance_m),
                    "spatial_weight": float(spatial_weight),
                    "source_reliability": float(source_reliability),
                    "evidence_strength": float(evidence_strength),
                    "effective_weight": float(effective_weight),
                }
            )

    if not records:
        return pd.DataFrame(columns=CELL_EVIDENCE_COLUMNS)

    out = pd.DataFrame(records)

    for col in CELL_EVIDENCE_COLUMNS:
        if col not in out.columns:
            out[col] = None

    out = out[CELL_EVIDENCE_COLUMNS].copy()

    numeric_cols = [
        "distance_m",
        "spatial_weight",
        "source_reliability",
        "evidence_strength",
        "effective_weight",
    ]
    for col in numeric_cols:
        out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0.0)

    return out


def summarize_cell_evidence(cell_evidence_df: pd.DataFrame) -> dict:
    """
    便捷调试函数：统计投影结果。
    """
    if cell_evidence_df is None or cell_evidence_df.empty:
        return {
            "projection_count": 0,
            "cell_count": 0,
            "evidence_count": 0,
            "source_type_counts": {},
            "spatial_type_counts": {},
            "effective_weight_max": 0.0,
            "effective_weight_mean": 0.0,
        }

    return {
        "projection_count": int(len(cell_evidence_df)),
        "cell_count": int(cell_evidence_df["cell_id"].nunique())
        if "cell_id" in cell_evidence_df.columns else 0,
        "evidence_count": int(cell_evidence_df["evidence_id"].nunique())
        if "evidence_id" in cell_evidence_df.columns else 0,
        "source_type_counts": cell_evidence_df["source_type_norm"].value_counts(dropna=False).to_dict()
        if "source_type_norm" in cell_evidence_df.columns else {},
        "spatial_type_counts": cell_evidence_df["spatial_type"].value_counts(dropna=False).to_dict()
        if "spatial_type" in cell_evidence_df.columns else {},
        "effective_weight_max": float(cell_evidence_df["effective_weight"].max())
        if "effective_weight" in cell_evidence_df.columns else 0.0,
        "effective_weight_mean": float(cell_evidence_df["effective_weight"].mean())
        if "effective_weight" in cell_evidence_df.columns else 0.0,
    }
