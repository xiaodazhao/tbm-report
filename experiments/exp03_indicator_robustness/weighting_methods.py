from __future__ import annotations

import numpy as np
import pandas as pd


EPS = 1e-12


def equal_weights(columns: list[str]) -> dict[str, float]:
    """Return uniform weights for available columns."""
    if not columns:
        return {}
    weight = 1.0 / len(columns)
    return {column: weight for column in columns}


def entropy_weights(frame: pd.DataFrame, columns: list[str]) -> dict[str, float]:
    """Compute entropy weights on non-negative normalized indicator columns."""
    work = _clean_indicator_frame(frame, columns)
    if work.empty:
        return equal_weights(columns)

    values = work.to_numpy(dtype=float)
    col_sums = values.sum(axis=0)
    valid = col_sums > EPS
    if not valid.any():
        return equal_weights(list(work.columns))

    p = np.zeros_like(values, dtype=float)
    p[:, valid] = values[:, valid] / col_sums[valid]
    n = max(values.shape[0], 1)
    k = 1.0 / np.log(n) if n > 1 else 0.0
    entropy = -k * np.nansum(np.where(p > 0, p * np.log(p + EPS), 0.0), axis=0)
    divergence = 1.0 - entropy
    divergence = np.where(np.isfinite(divergence) & (divergence > 0), divergence, 0.0)

    if divergence.sum() <= EPS:
        return equal_weights(list(work.columns))
    weights = divergence / divergence.sum()
    return {column: float(weight) for column, weight in zip(work.columns, weights)}


def critic_weights(frame: pd.DataFrame, columns: list[str]) -> dict[str, float]:
    """Compute CRITIC weights using variability and conflict among indicators."""
    work = _clean_indicator_frame(frame, columns)
    if work.empty:
        return equal_weights(columns)
    if len(work.columns) == 1:
        return {work.columns[0]: 1.0}

    std = work.std(axis=0, ddof=0).fillna(0.0)
    corr = work.corr(method="pearson").fillna(0.0)
    conflict = (1.0 - corr).sum(axis=0)
    information = std * conflict
    information = information.where(np.isfinite(information), 0.0).clip(lower=0.0)
    total = float(information.sum())
    if total <= EPS:
        return equal_weights(list(work.columns))
    return {column: float(information[column] / total) for column in work.columns}


def weighted_mean(frame: pd.DataFrame, weights: dict[str, float]) -> pd.Series:
    """Weighted row-wise mean for indicator columns, preserving missing values."""
    if not weights:
        return pd.Series(np.nan, index=frame.index)
    available = [column for column in weights if column in frame.columns]
    if not available:
        return pd.Series(np.nan, index=frame.index)

    values = frame[available].apply(pd.to_numeric, errors="coerce")
    weight_values = pd.Series({column: weights[column] for column in available}, dtype=float)
    numerator = values.mul(weight_values, axis=1).sum(axis=1, skipna=True)
    denominator = values.notna().mul(weight_values, axis=1).sum(axis=1)
    return numerator.where(denominator > EPS) / denominator.where(denominator > EPS)


def _clean_indicator_frame(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    available = [column for column in columns if column in frame.columns]
    if not available:
        return pd.DataFrame(index=frame.index)
    work = frame[available].apply(pd.to_numeric, errors="coerce")
    work = work.dropna(axis=1, how="all")
    if work.empty:
        return work
    return work.fillna(work.median(numeric_only=True)).clip(lower=0.0, upper=1.0)
