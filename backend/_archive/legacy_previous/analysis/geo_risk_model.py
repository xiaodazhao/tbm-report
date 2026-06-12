from __future__ import annotations

import re
from typing import Any

import numpy as np
import pandas as pd


GRS_MODEL_VERSION = "equal_weight_minmax_dynamic_v2"

DEFAULT_CORRECTION_LAMBDA = 0.40
DEFAULT_MIN_GRS = 0.05

GRADE_SCORES = {
    "I": 0.05,
    "II": 0.20,
    "III": 0.40,
    "IV": 0.70,
    "V": 1.00,
    "1": 0.05,
    "2": 0.20,
    "3": 0.40,
    "4": 0.70,
    "5": 1.00,
    "\u2160": 0.05,
    "\u2161": 0.20,
    "\u2162": 0.40,
    "\u2163": 0.70,
    "\u2164": 1.00,
}

HAZARD_KEYWORDS = [
    ("\u88c2\u9699", 0.25),
    ("\u8282\u7406", 0.20),
    ("\u7834\u788e", 0.30),
    ("\u6781\u7834\u788e", 0.40),
    ("\u65ad\u5c42", 0.35),
    ("\u5f31\u98ce\u5316", 0.20),
    ("\u8f6f\u5f31", 0.30),
    ("\u5f02\u5e38\u53cd\u5c04", 0.30),
    ("\u53cd\u5c04\u5f02\u5e38", 0.30),
    ("\u5ca9\u6eb6", 0.35),
    ("fracture", 0.25),
    ("fissure", 0.25),
    ("joint", 0.20),
    ("broken", 0.30),
    ("fault", 0.35),
    ("weak", 0.25),
    ("reflection", 0.25),
    ("karst", 0.35),
]

WATER_KEYWORDS = [
    "\u51fa\u6c34",
    "\u6d8c\u6c34",
    "\u7a81\u6c34",
    "\u5bcc\u6c34",
    "\u6e17\u6c34",
    "water",
    "inrush",
]

COLLAPSE_KEYWORDS = [
    "\u6389\u5757",
    "\u584c\u65b9",
    "\u574d\u584c",
    "\u5192\u843d",
    "\u6389\u584c",
    "collapse",
    "fall",
]


def compute_row_grs_base(
    df: pd.DataFrame,
    colmap: dict[str, str | None],
    warnings: list[str] | None = None,
) -> tuple[pd.Series, pd.Series, pd.DataFrame]:
    """
    计算逐记录地质关注基础分 GRS_base。

    本函数是 GRS 的地质侧基础评分模型。
    它不使用机器学习，而是基于工程先验提取多个地质证据分量，
    将每个分量归一化到 0~1 后进行等权平均。

    输入：
        df:
            清洗后的逐记录 df_geo，包含地质融合字段。
        colmap:
            字段映射表，用于找到 hazard、risk、active_sources、
            围岩等级、出水、掉块等字段。
        warnings:
            警告列表。若关键地质字段缺失，会追加 warning。

    输出：
        grs_base:
            每条记录的基础地质关注分，范围 0~1。
        source_confidence:
            每条记录的多源证据支持度，范围 0~1。
        components:
            GRS 的各组成分量表，包括：
                grade_score
                hazard_score
                water_score
                collapse_score
                source_confidence
    """
    if warnings is None:
        warnings = []

    # 保留原始索引，保证后面生成的 Series 与 df 对齐
    idx = df.index

    # 将 hazard、risk、active_sources 等文本字段合并成一个文本证据池
    # 后续 hazard/water/collapse 等分量可以从文本中识别关键词。
    text = _combined_text(
        df,
        [colmap.get("hazard"), colmap.get("risk"), colmap.get("active_sources")]
    )

    # 1. 围岩等级分量：围岩等级越差，分数越高
    grade_score = _grade_score_series(df, colmap, warnings)

    # 2. 地质异常标签分量：根据破碎、裂隙、反射异常、软弱夹层等标签计算
    hazard_score = _hazard_score_series(df, colmap, text, warnings)

    # 3. 水害分量：根据出水标志、出水类型或文本中的水害关键词计算
    water_score = _water_score_series(df, colmap, text, warnings)

    # 4. 掉块/塌方/失稳分量：根据 collapse 标志或相关关键词计算
    collapse_score = _collapse_score_series(df, colmap, text, warnings)

    # 5. 多源证据支持分量：来源越多，证据置信度越高
    source_confidence = _source_confidence_series(df, colmap, warnings)

    # 6. 组装原始分量，并清洗异常值
    # 所有分量都限制在 0~1 范围内。
    raw_components = pd.DataFrame(
        {
            "grade_score": grade_score,
            "hazard_score": hazard_score,
            "water_score": water_score,
            "collapse_score": collapse_score,
            "source_confidence": source_confidence,
        },
        index=idx,
    ).replace([np.inf, -np.inf], np.nan).fillna(0).clip(0, 1)

    # 7. 对每一个分量再次归一化到统一 0~1 空间
    # 这样后续可以进行等权平均，避免某一分量因数值尺度不同而主导结果。
    components = pd.DataFrame(
        {
            column: _normalize_feature_series(raw_components[column])
            for column in raw_components.columns
        },
        index=idx,
    ).replace([np.inf, -np.inf], np.nan).fillna(0).clip(0, 1)

    # 8. 等权平均得到逐记录 GRS_base
    # GRS_base = 五个归一化地质分量的平均值。
    grs_base = components.mean(axis=1).fillna(0).clip(0, 1)

    # 9. 如果所有分量都为 0，说明地质字段可能缺失或不可用，记录 warning
    # 注意：这不代表真实无风险，而是模型没有可用地质证据。
    if float(components.abs().sum(axis=1).sum()) <= 1e-12:
        warnings.append("GRS base uses zero-risk fallback because geology component fields are unavailable")

    # 10. 返回 GRS_base、多源证据支持度和分量明细
    return grs_base.clip(0, 1), source_confidence.fillna(0).clip(0, 1), components
# ============================================================
# apply_dynamic_grs_correction：对区段级 GRS 做动态修正
#
# 输入：
#   segment_df：
#       区段级特征表，至少包含 GRS_base 或 GRS。
#       如果包含 RAI/response_anomaly_index 和停机比例字段，
#       则可以进行施工响应修正。
#
# 核心逻辑：
#   1. 读取基础地质关注分 GRS_base；
#   2. 如果存在 RAI 和 stop_ratio/speed_zero_ratio/stop_state_ratio，
#      则计算修正项：
#          correction = 0.5 * RAI + 0.5 * stop_ratio
#   3. 使用 correction_lambda 对 GRS_base 做乘法修正：
#          GRS_corrected = GRS_base * (1 + lambda * correction)
#   4. 对修正结果进行空间平滑；
#   5. 施加 min_grs 下限，得到最终 GRS_adjusted；
#   6. 将 GRS 作为 GRS_adjusted 的兼容别名；
#   7. 返回修正后的区段表和 GRS 修正元信息 metadata。
#
# 注意：
#   GRS_geo_base 表示纯地质基础分；
#   GRS_adjusted 表示结合施工响应修正后的最终分；
#   GRS 当前作为 GRS_adjusted 的兼容字段。
# ============================================================
def apply_dynamic_grs_correction(
    segment_df: pd.DataFrame,
    correction_lambda: float = DEFAULT_CORRECTION_LAMBDA,
    min_grs: float = DEFAULT_MIN_GRS,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Apply response-based correction, spatial smoothing, and bounds to GRS.

    ``GRS_base`` is the engineering-prior score. When both RAI and stop-ratio
    columns are available, the score is corrected by
    ``1 + lambda * (0.5 * RAI + 0.5 * stop_ratio)``. If response information is
    missing, the method falls back to the base score, then still applies spatial
    smoothing and min/max bounds for stable segment-level output.
    """
    out = segment_df.copy()
    idx = out.index

    if "GRS_base" in out.columns:
        base = pd.to_numeric(out["GRS_base"], errors="coerce").fillna(0).clip(0, 1)
    else:
        base = pd.to_numeric(out.get("GRS", _zero_series(idx)), errors="coerce").fillna(0).clip(0, 1)
        out["GRS_base"] = base

    rai_col = _first_existing(out, ["response_anomaly_index", "RAI"])
    stop_cols = [col for col in ["stop_ratio", "speed_zero_ratio", "stop_state_ratio"] if col in out.columns]

    has_rai = rai_col is not None
    has_stop_ratio = bool(stop_cols)

    if has_rai and has_stop_ratio:
        rai = pd.to_numeric(out[rai_col], errors="coerce").fillna(0).clip(0, 1)
        stop_ratio = pd.concat(
            [pd.to_numeric(out[col], errors="coerce").fillna(0).clip(0, 1) for col in stop_cols],
            axis=1,
        ).max(axis=1).fillna(0).clip(0, 1)
        correction = (0.5 * rai + 0.5 * stop_ratio).clip(0, 1)
        correction_mode = "rai_stop_ratio"
    else:
        correction = _zero_series(idx)
        correction_mode = "base_only_fallback"

    lambda_value = float(np.clip(correction_lambda, 0, 1))
    min_value = float(np.clip(min_grs, 0, 1))
    correction_factor = (1.0 + lambda_value * correction).clip(lower=1.0, upper=1.0 + lambda_value)
    corrected = (base * correction_factor).clip(0, 1)
    smooth = _spatial_smooth(corrected).clip(0, 1)
    final = smooth.clip(lower=min_value, upper=1.0)

    out["GRS_base"] = base
    out["GRS_geo_base"] = base
    out["GRS_corrected"] = corrected
    out["GRS_smooth"] = smooth
    out["GRS_final"] = final
    out["GRS_adjusted"] = final
    out["correction"] = correction
    out["correction_factor"] = correction_factor
    # GRS is kept as a compatibility alias for the adjusted/final score.
    out["GRS"] = final
    out["geo_risk_score"] = final
    out["geo_risk_norm"] = final

    metadata = {
        "grs_model_version": GRS_MODEL_VERSION,
        "grs_weight_method": "equal_weight_minmax",
        "feature_aggregation": "mean(normalized_features)",
        "equal_weight_features": [
            "grade_score",
            "hazard_score",
            "water_score",
            "collapse_score",
            "source_confidence",
        ],
        "engineering_weights": {},
        "correction_lambda": lambda_value,
        "min_grs": min_value,
        "correction_formula": "GRS_base * (1 + lambda * (0.5 * RAI + 0.5 * stop_ratio))",
        "standard_fields": {"GRS_geo_base": "pure geology evidence base score", "GRS_adjusted": "response-adjusted final score", "GRS": "compatibility alias of GRS_adjusted"},
        "correction_mode": correction_mode,
        "has_rai": has_rai,
        "has_stop_ratio": has_stop_ratio,
    }
    return out, metadata


def _grade_score_series(
    df: pd.DataFrame,
    colmap: dict[str, str | None],
    warnings: list[str],
) -> pd.Series:
    """Internal helper for grade score series."""
    col = colmap.get("grade")
    if not col or col not in df.columns:
        warnings.append("GRS base missing grade field; grade_score set to 0")
        return _zero_series(df.index)
    return df[col].map(_grade_score).fillna(0).clip(0, 1)


def _hazard_score_series(
    df: pd.DataFrame,
    colmap: dict[str, str | None],
    text: pd.Series,
    warnings: list[str],
) -> pd.Series:
    """Internal helper for hazard score series."""
    scores = text.map(_keyword_score).fillna(0).clip(0, 1)
    if "__deformation_flag" in df.columns:
        deformation = pd.to_numeric(df["__deformation_flag"], errors="coerce").fillna(0).clip(0, 1) * 0.20
        scores = pd.concat([scores, deformation], axis=1).max(axis=1).clip(0, 1)
    if not any(colmap.get(key) for key in ["hazard", "risk", "active_sources"]) and "__deformation_flag" not in df.columns:
        warnings.append("GRS base missing structural hazard fields; hazard_score set to 0")
    return scores


def _water_score_series(
    df: pd.DataFrame,
    colmap: dict[str, str | None],
    text: pd.Series,
    warnings: list[str],
) -> pd.Series:
    """Internal helper for water score series."""
    parts = []
    if "__water_flag" in df.columns:
        parts.append(pd.to_numeric(df["__water_flag"], errors="coerce").fillna(0).clip(0, 1))
    text_score = text.map(lambda value: _keyword_presence(value, WATER_KEYWORDS)).fillna(0).clip(0, 1)
    if float(text_score.sum()) > 0:
        parts.append(text_score)
    if not parts:
        warnings.append("GRS base missing water-risk fields; water_score set to 0")
        return _zero_series(df.index)
    return pd.concat(parts, axis=1).max(axis=1).fillna(0).clip(0, 1)


def _collapse_score_series(
    df: pd.DataFrame,
    colmap: dict[str, str | None],
    text: pd.Series,
    warnings: list[str],
) -> pd.Series:
    """Internal helper for collapse score series."""
    parts = []
    if "__collapse_flag" in df.columns:
        parts.append(pd.to_numeric(df["__collapse_flag"], errors="coerce").fillna(0).clip(0, 1))
    text_score = text.map(lambda value: _keyword_presence(value, COLLAPSE_KEYWORDS)).fillna(0).clip(0, 1)
    if float(text_score.sum()) > 0:
        parts.append(text_score)
    if not parts:
        warnings.append("GRS base missing collapse-risk fields; collapse_score set to 0")
        return _zero_series(df.index)
    return pd.concat(parts, axis=1).max(axis=1).fillna(0).clip(0, 1)


def _source_confidence_series(
    df: pd.DataFrame,
    colmap: dict[str, str | None],
    warnings: list[str],
) -> pd.Series:
    """Internal helper for source confidence series."""
    if "__active_source_count" in df.columns:
        return (pd.to_numeric(df["__active_source_count"], errors="coerce").fillna(0) / 4.0).clip(0, 1)

    coverage_col = colmap.get("coverage")
    if coverage_col and coverage_col in df.columns:
        return df[coverage_col].fillna("").astype(str).map(_coverage_confidence).clip(0, 1)

    active_sources_col = colmap.get("active_sources")
    if active_sources_col and active_sources_col in df.columns:
        return df[active_sources_col].fillna("").astype(str).map(_source_text_confidence).clip(0, 1)

    warnings.append("GRS base missing source confidence fields; source_confidence set to 0")
    return _zero_series(df.index)


def _spatial_smooth(series: pd.Series) -> pd.Series:
    """Smooth adjacent mileage segments with boundary weight renormalization."""
    values = pd.to_numeric(series, errors="coerce").fillna(0).clip(0, 1)
    smoothed = []
    for pos in range(len(values)):
        weighted_sum = 0.0
        weight_sum = 0.0
        for offset, weight in [(-1, 0.25), (0, 0.50), (1, 0.25)]:
            neighbor = pos + offset
            if 0 <= neighbor < len(values):
                weighted_sum += float(values.iloc[neighbor]) * weight
                weight_sum += weight
        smoothed.append(weighted_sum / weight_sum if weight_sum else 0.0)
    return pd.Series(smoothed, index=series.index).clip(0, 1)


def _normalize_feature_series(series: pd.Series) -> pd.Series:
    """Normalize one component series into a shared 0-1 feature space."""
    values = pd.to_numeric(series, errors="coerce").replace([np.inf, -np.inf], np.nan).fillna(0)
    min_value = float(values.min(skipna=True)) if not values.empty else 0.0
    max_value = float(values.max(skipna=True)) if not values.empty else 0.0
    if max_value - min_value > 1e-9:
        return ((values - min_value) / (max_value - min_value)).clip(0, 1)
    return values.clip(0, 1)


def _grade_score(value: Any) -> float:
    """Internal helper for grade score."""
    text = str(value).strip().upper()
    if not text or text == "NAN":
        return 0.0

    roman_order = ["VIII", "VII", "VI", "III", "II", "IV", "V", "I"]
    for key in roman_order:
        if key in text and key in GRADE_SCORES:
            return GRADE_SCORES[key]

    for key in ["\u2164", "\u2163", "\u2162", "\u2161", "\u2160"]:
        if key in text:
            return GRADE_SCORES[key]

    match = re.search(r"[1-5]", text)
    if match:
        return GRADE_SCORES.get(match.group(0), 0.0)
    return 0.0


def _keyword_score(text: Any) -> float:
    """Internal helper for keyword score."""
    haystack = str(text).lower()
    if not haystack or haystack == "nan":
        return 0.0
    score = 0.0
    for keyword, weight in HAZARD_KEYWORDS:
        if keyword.lower() in haystack:
            score += weight
    return float(np.clip(score, 0, 1))


def _keyword_presence(text: Any, keywords: list[str]) -> float:
    """Internal helper for keyword presence."""
    haystack = str(text).lower()
    if not haystack or haystack == "nan":
        return 0.0
    return 1.0 if any(keyword.lower() in haystack for keyword in keywords) else 0.0


def _coverage_confidence(value: Any) -> float:
    """Internal helper for coverage confidence."""
    text = str(value).strip().lower()
    if not text or text == "nan":
        return 0.0
    if "multi" in text or "\u591a\u6e90" in text:
        return 0.75
    if "single" in text or "\u5355\u6e90" in text:
        return 0.25
    return 0.35


def _source_text_confidence(value: Any) -> float:
    """Internal helper for source text confidence."""
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return 0.0
    parts = [part for part in re.split(r"[,;|/\s]+", text) if part.strip()]
    if not parts:
        return 0.25
    return float(np.clip(len(set(parts)) / 4.0, 0, 1))


def _combined_text(df: pd.DataFrame, columns: list[str | None]) -> pd.Series:
    """Internal helper for combined text."""
    existing = [col for col in columns if col and col in df.columns]
    if not existing:
        return pd.Series("", index=df.index)
    out = pd.Series("", index=df.index, dtype=object)
    for col in existing:
        out = out + " " + df[col].fillna("").astype(str)
    return out.str.strip()


def _first_existing(df: pd.DataFrame, columns: list[str]) -> str | None:
    """Internal helper for first existing."""
    for col in columns:
        if col in df.columns:
            return col
    return None


def _zero_series(index: pd.Index) -> pd.Series:
    """Build a zero-filled series for the target index."""
    return pd.Series(0.0, index=index)