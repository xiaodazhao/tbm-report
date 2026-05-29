from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

from analysis.geo_risk_model import apply_dynamic_grs_correction, compute_row_grs_base
from utils.chainage_utils import format_chainage_range_dk
from utils.serialization import serialize_for_json


GEOLOGY_METHOD_VERSION = "GRS_equal_weight_RAI_iforest_GRCI_validation_v4"

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
    "Ⅰ": 0.05,
    "Ⅱ": 0.20,
    "Ⅲ": 0.40,
    "Ⅳ": 0.70,
    "Ⅴ": 1.00,
}

HAZARD_KEYWORDS = [
    (("突水", "涌水", "出水", "富水", "water", "inrush"), 0.35),
    (("坍塌", "塌方", "掉块", "collapse", "fall"), 0.35),
    (("破碎", "极破碎", "围岩破碎", "broken", "fractured"), 0.30),
    (("裂隙", "裂缝", "裂隙密集", "joint", "fissure", "crack"), 0.25),
    (("异常反射", "明显反射异常", "反射异常", "reflection"), 0.25),
    (("断层", "软弱", "岩溶", "溶洞", "fault", "karst", "weak"), 0.35),
    (("变形", "挤压", "deformation", "squeeze"), 0.20),
]

CLASS_LABELS = {
    "A": "A类：地质响应耦合型高风险",
    "B": "B类：地质预警型潜在风险",
    "C": "C类：施工异常型未知风险",
    "D": "D类：正常稳定区段",
}

COUPLING_LEVEL_LABELS = {
    "strong": "强耦合区",
    "medium": "中耦合区",
    "weak": "弱耦合区",
    "low": "低耦合区",
    "unknown": "未知耦合区",
}

FIELD_ALIASES = {
    "chainage": ["chainage", "里程", "当前里程", "桩号", "推进里程"],
    "time": ["时间", "timestamp", "datetime", "date_time", "采集时间"],
    "speed": ["推进速度", "advance_speed", "speed", "actual_speed"],
    "set_speed": ["推进给定速度", "给定速度", "target_speed", "set_speed"],
    "thrust": ["推力", "总推力", "thrust", "total_thrust"],
    "torque": ["刀盘扭矩", "扭矩", "cutter_torque", "torque"],
    "rpm": ["刀盘转速", "转速", "cutter_rpm", "rpm"],
    "penetration": ["贯入度", "penetration"],
    "state": ["掘进状态", "施工状态", "state", "excavation_state"],
    "risk_score": ["risk_score", "地质风险分数", "风险分数"],
    "geo_prior_score": ["geo_prior_score", "geo_risk_score", "GRS", "GRS_adjusted", "地质先验分数"],
    "active_source_count": ["active_report_source_count", "active_source_count", "source_count", "命中来源数", "多源命中数"],
    "water_flag": ["geo_water_flag", "water_flag_fused", "water_flag", "出水标记"],
    "collapse_flag": ["geo_collapse_flag", "collapse_flag_fused", "collapse_flag", "坍塌标记", "掉块标记"],
    "deformation_flag": ["geo_deformation_flag", "deformation_flag_fused", "deformation_flag", "变形标记"],
    "grade": ["geo_fused_grade", "fused_grade", "围岩等级", "grade", "rock_grade"],
    "risk": ["risk", "risk_mode", "source_risk_level", "风险等级"],
    "hazard": ["geo_hazard_summary", "hazard", "hazard_mode", "灾害", "灾害表现", "hazard_desc"],
    "coverage": ["geo_coverage_status", "coverage", "coverage_mode", "覆盖情况"],
    "uncertainty": ["geo_fusion_uncertainty", "uncertainty", "不确定性"],
    "active_sources": ["active_source_types", "active_sources", "sources", "证据来源"],
}

METRIC_COLUMNS = [
    "segment",
    "segment_label_dk",
    "GRS",
    "GRS_geo_base",
    "GRS_adjusted",
    "geo_risk_score",
    "GRS_base",
    "GRS_corrected",
    "GRS_smooth",
    "GRS_final",
    "correction",
    "correction_factor",
    "GRS_mean",
    "GRS_max",
    "RAI",
    "response_anomaly_index",
    "iforest_anomaly_score",
    "stop_anomaly",
    "efficiency_anomaly",
    "param_anomaly",
    "anomaly_type",
    "anomaly_type_score",
    "GRCI",
    "coupling_index",
    "coupling_class",
    "coupling_type",
    "delta_RAI",
    "delta_GRS",
    "geo_risk_norm",
    "source_evidence_norm",
    "response_consistency",
    "sync_coupling",
    "lag_coupling",
    "lag_response",
    "response_change_coupling",
    "risk_response_coupling_index",
    "coupling_level",
    "coupling_label",
    "grci_class_code",
    "grci_class_label",
    "coupling_interpretation",
    "weak_anomaly_label",
    "weak_anomaly_reasons",
    "speed_drop_score",
    "speed_volatility_score",
    "thrust_anomaly_score",
    "torque_anomaly_score",
    "rpm_anomaly_score",
    "penetration_anomaly_score",
    "efficiency_anomaly_score",
    "speed_zero_ratio",
    "stop_state_ratio",
]

# ============================================================
# run_coupling_analysis：地质-施工响应耦合分析总入口
#
# 输入：
#   df_geo：
#       带地质融合字段的逐记录 TBM 数据。
#   base_segment_df：
#       前面 run_segment_analysis 得到的基础区段表，可为空。
#
# 核心指标：
#   GRS：
#       Geology Risk Score，地质关注度。
#       根据多源证据、围岩等级、出水/掉块/变形、证据权重等计算。
#
#   RAI：
#       Response Anomaly Index，施工响应异常度。
#       根据推进速度、推力、刀盘扭矩、效率、波动等施工参数计算。
#
#   GRCI：
#       Geology Response Coupling Index，地质-施工响应耦合关注度。
#       用于识别“地质证据较强且施工响应同步异常”的区段。
#
# 主流程：
#   1. 检查输入数据与 chainage 字段
#   2. 清洗 df_geo，并按 segment_length 构造区段
#   3. 逐记录计算地质关注基础分 row_grs_base
#   4. 对 row_grs_base 沿里程方向进行高斯平滑，得到 row_grs
#   5. 逐记录计算施工响应异常分
#   6. 聚合为区段级 segment_metrics
#   7. 计算区段级 RAI
#   8. 动态修正 GRS
#   9. 计算 GRCI
#   10. 生成弱标签验证
#   11. 与 base_segment_df 合并
#   12. 提取 top_grci / top_grs / top_rai 区段
#   13. 构建 summary、validation 和输出文件路径
#
# 输出：
#   {
#       segment_df: 带 GRS/RAI/GRCI 的区段表,
#       high_attention_segments: GRCI 排名前列的高关注区段,
#       top_grci_segments: 耦合关注度最高区段,
#       top_grs_segments: 地质关注度最高区段,
#       top_rai_segments: 施工响应异常最高区段,
#       summary: 耦合分析摘要,
#       validation: 弱标签验证结果,
#       output_paths: 输出文件路径,
#       warnings: 分析警告
#   }
# ============================================================
def run_coupling_analysis(
    df_geo: pd.DataFrame,
    segment_length: float = 10.0,
    base_segment_df: pd.DataFrame | None = None,
    output_dir: str | Path | None = None,
    output_prefix: str | None = None,
    top_k: int = 10,
    risk_threshold: float = 0.55,
    response_threshold: float = 0.55,
) -> dict[str, Any]:
    """Run segment-level geology-risk and construction-response coupling analysis.

    The method builds three core values:
    - GRS: Geology Risk Score, 0-1
    - RAI: Response Anomaly Index, 0-1
    - GRCI: Geology Response Coupling Index, 0-1
    """
    warnings: list[str] = []
    if df_geo is None or df_geo.empty:
        empty = pd.DataFrame()
        return {
            "segment_df": empty,
            "high_attention_segments": [],
            "summary": _empty_summary("input dataframe is empty", warnings),
            "validation": _empty_validation(),
            "output_paths": {},
            "warnings": warnings,
        }

    df = df_geo.copy()
    colmap = _resolve_columns(df, warnings)
    if not colmap.get("chainage"):
        warnings.append("missing chainage column; coupling analysis skipped")
        empty = base_segment_df.copy() if base_segment_df is not None else pd.DataFrame()
        return {
            "segment_df": empty,
            "high_attention_segments": [],
            "summary": _empty_summary("missing chainage column", warnings),
            "validation": _empty_validation(),
            "output_paths": {},
            "warnings": warnings,
        }

    df = _prepare_raw_dataframe(df, colmap, segment_length)
    if df.empty:
        warnings.append("no valid chainage rows after cleaning")
        empty = base_segment_df.copy() if base_segment_df is not None else pd.DataFrame()
        return {
            "segment_df": empty,
            "high_attention_segments": [],
            "summary": _empty_summary("no valid chainage rows", warnings),
            "validation": _empty_validation(),
            "output_paths": {},
            "warnings": warnings,
        }

    df["row_grs_base"], df["source_evidence_norm"], _grs_components = _compute_row_geology_scores(
        df,
        colmap,
        warnings,
    )
    df["row_grs"] = _apply_gaussian_chainage_smoothing(
        df=df,
        value_col="row_grs_base",
        sigma_m=max(float(segment_length) / 2.0, 1.0),
        radius_m=max(1.5 * float(segment_length), 3.0),
    )
    df = _add_row_response_anomaly_scores(df, warnings)
    segment_metrics = _aggregate_segment_features(df, colmap, warnings)
    segment_metrics = _add_response_anomaly_index(segment_metrics, warnings)
    segment_metrics, grs_metadata = apply_dynamic_grs_correction(segment_metrics)
    segment_metrics = _add_coupling_index(
        segment_metrics,
        risk_threshold=risk_threshold,
        response_threshold=response_threshold,
    )
    segment_metrics = _add_weak_validation_labels(segment_metrics)

    segment_df = _merge_with_base_segments(base_segment_df, segment_metrics)
    if "segment_start_first" in segment_df.columns:
        segment_df = segment_df.sort_values("segment_start_first").reset_index(drop=True)
    elif "segment_start" in segment_df.columns:
        segment_df = segment_df.sort_values("segment_start").reset_index(drop=True)

    validation = _validate_coupling(segment_df, top_k=top_k)
    top_grci_segments = _build_top_segments(segment_df, top_k=top_k, sort_col="GRCI")
    top_grs_segments = _build_top_segments(segment_df, top_k=top_k, sort_col="GRS_geo_base" if "GRS_geo_base" in segment_df.columns else "GRS_base")
    top_rai_segments = _build_top_segments(segment_df, top_k=top_k, sort_col="RAI")
    high_attention_segments = top_grci_segments
    summary = _build_summary(
        segment_df=segment_df,
        validation=validation,
        high_attention_segments=high_attention_segments,
        segment_length=segment_length,
        warnings=warnings,
        grs_metadata=grs_metadata,
        top_grs_segments=top_grs_segments,
        top_rai_segments=top_rai_segments,
        top_grci_segments=top_grci_segments,
    )
    output_paths = _write_outputs(
        segment_df=segment_df,
        high_attention_segments=high_attention_segments,
        summary=summary,
        output_dir=output_dir,
        output_prefix=output_prefix or _infer_output_prefix(df, colmap),
        warnings=warnings,
    )
    summary["output_paths"] = output_paths
    summary["warnings"] = warnings

    return {
        "segment_df": segment_df,
        "high_attention_segments": high_attention_segments,  # deprecated alias: same as top_grci_segments
        "top_grci_segments": top_grci_segments,
        "top_grs_segments": top_grs_segments,
        "top_rai_segments": top_rai_segments,
        "summary": summary,
        "validation": validation,  # deprecated alias: same as weak_label_validation in summary
        "weak_label_validation": validation,
        "output_paths": output_paths,
        "warnings": warnings,
    }


def _resolve_columns(df: pd.DataFrame, warnings: list[str]) -> dict[str, str | None]:
    """Resolve columns."""
    resolved = {}
    for key, aliases in FIELD_ALIASES.items():
        resolved[key] = _find_column(df, aliases)

    required_response = ["speed", "thrust", "torque"]
    missing_response = [key for key in required_response if not resolved.get(key)]
    if missing_response:
        warnings.append(f"missing response fields: {', '.join(missing_response)}")

    geology_fields = [
        "risk_score",
        "geo_prior_score",
        "active_source_count",
        "water_flag",
        "collapse_flag",
        "deformation_flag",
        "grade",
        "hazard",
        "risk",
    ]
    if not any(resolved.get(key) for key in geology_fields):
        warnings.append("no geology risk fields found; GRS will be near zero")

    return resolved


def _find_column(df: pd.DataFrame, aliases: list[str]) -> str | None:
    """Internal helper for find column."""
    lower_map = {str(col).strip().lower(): col for col in df.columns}
    for alias in aliases:
        key = alias.strip().lower()
        if key in lower_map:
            return lower_map[key]

    for alias in aliases:
        key = alias.strip().lower()
        for col in df.columns:
            if key and key in str(col).strip().lower():
                return col
    return None


def _prepare_raw_dataframe(df: pd.DataFrame, colmap: dict[str, str | None], segment_length: float) -> pd.DataFrame:
    """Prepare raw dataframe."""
    out = df.copy()
    chainage_col = colmap["chainage"]
    out["chainage"] = pd.to_numeric(out[chainage_col], errors="coerce")
    out = out.dropna(subset=["chainage"]).copy()
    time_col = colmap.get("time")
    if time_col:
        out["__time"] = pd.to_datetime(out[time_col], errors="coerce")

    for key in ["speed", "set_speed", "thrust", "torque", "rpm", "penetration", "state"]:
        col = colmap.get(key)
        if col:
            out[f"__{key}"] = pd.to_numeric(out[col], errors="coerce")

    for key in [
        "risk_score",
        "geo_prior_score",
        "active_source_count",
        "water_flag",
        "collapse_flag",
        "deformation_flag",
    ]:
        col = colmap.get(key)
        if col:
            out[f"__{key}"] = pd.to_numeric(out[col], errors="coerce")

    for source_col, target_col in [
        ("routine_ring_building_candidate", "__routine_stop_candidate"),
        ("routine_stop_candidate", "__routine_stop_candidate"),
        ("routine_ring_building_score", "__routine_stop_score"),
        ("routine_stop_score", "__routine_stop_score"),
    ]:
        if source_col in out.columns:
            out[target_col] = pd.to_numeric(out[source_col], errors="coerce")

    out["segment_start"] = (np.floor(out["chainage"] / segment_length) * segment_length).astype(float)
    out["segment_end"] = out["segment_start"] + segment_length
    out["segment_id"] = out["segment_start"].map(_number_key) + "_" + out["segment_end"].map(_number_key)
    return out


def _compute_row_geology_scores(
    df: pd.DataFrame,
    colmap: dict[str, str | None],
    warnings: list[str],
) -> tuple[pd.Series, pd.Series, pd.DataFrame]:
    """Delegate GRS_base calculation to the engineering-prior geology model."""
    return compute_row_grs_base(df, colmap, warnings)


def _apply_gaussian_chainage_smoothing(
    df: pd.DataFrame,
    value_col: str,
    sigma_m: float,
    radius_m: float,
) -> pd.Series:
    """Smooth one row-level score along chainage with Gaussian decay."""
    if value_col not in df.columns or "chainage" not in df.columns or df.empty:
        return _zero_series(df.index)

    sigma = max(float(sigma_m), 1e-6)
    radius = max(float(radius_m), sigma)
    work = pd.DataFrame(
        {
            "chainage": pd.to_numeric(df["chainage"], errors="coerce"),
            "value": pd.to_numeric(df[value_col], errors="coerce").fillna(0).clip(0, 1),
        },
        index=df.index,
    ).dropna(subset=["chainage"]).sort_values("chainage")
    if work.empty:
        return _zero_series(df.index)

    chainage_values = work["chainage"].to_numpy(dtype=float)
    score_values = work["value"].to_numpy(dtype=float)
    smoothed = np.zeros(len(work), dtype=float)

    for pos, center in enumerate(chainage_values):
        left = np.searchsorted(chainage_values, center - radius, side="left")
        right = np.searchsorted(chainage_values, center + radius, side="right")
        local_chainage = chainage_values[left:right]
        local_scores = score_values[left:right]
        distances = local_chainage - center
        weights = np.exp(-0.5 * (distances / sigma) ** 2)
        weight_sum = float(weights.sum())
        smoothed[pos] = float(np.dot(weights, local_scores) / weight_sum) if weight_sum > 1e-12 else float(score_values[pos])

    out = pd.Series(0.0, index=df.index)
    out.loc[work.index] = smoothed
    return out.clip(0, 1)


# ============================================================
# _aggregate_segment_features：将逐记录特征聚合到区段级
#
# 输入：
#   df：
#       已经包含 row_grs、source_evidence_norm、row_rai 以及各种
#       row_* 响应异常分数的逐记录 DataFrame。
#
#   colmap：
#       字段映射表，用于找到地质风险、hazard、围岩等级、覆盖状态等字段。
#
#   warnings：
#       警告列表。若缺少速度、扭矩等关键字段，会追加提示。
#
# 主流程：
#   1. 按 segment_id 分组；
#   2. 聚合区段里程范围、样本数；
#   3. 聚合地质关注分 row_grs，生成 GRS_mean、GRS_max；
#   4. 用 GRS_mean 和 GRS_max 计算区段级 GRS_base；
#   5. 聚合施工参数 speed/thrust/torque/rpm/penetration 的
#      mean/std/min/max/median/CV；
#   6. 对地质类别字段取众数，例如 hazard_mode、fused_grade_mode；
#   7. 计算速度接近 0 比例 speed_zero_ratio；
#   8. 计算掘进状态停机比例 stop_state_ratio；
#   9. 计算区段推进效率 efficiency；
#   10. 聚合逐记录响应异常指标 row_rai、row_iforest、row_stop 等，
#       生成 mean/max 区段特征。
#
# 输出：
#   segment_metrics：
#       区段级特征表。每一行对应一个 10m 区段，
#       包含地质侧 GRS 基础指标、施工参数统计、
#       停机比例、效率指标和响应异常聚合指标。
# ============================================================
def _aggregate_segment_features(
    df: pd.DataFrame,
    colmap: dict[str, str | None],
    warnings: list[str],
) -> pd.DataFrame:
    """Internal helper for aggregate segment features."""
    grouped = df.groupby("segment_id", sort=False)

    out = grouped.agg(
        chainage_min=("chainage", "min"),
        chainage_max=("chainage", "max"),
        chainage_mean=("chainage", "mean"),
        chainage_count=("chainage", "count"),
        segment_start_first=("segment_start", "first"),
        segment_end_first=("segment_end", "first"),
        GRS_mean=("row_grs", "mean"),
        GRS_max=("row_grs", "max"),
        source_evidence_norm=("source_evidence_norm", "max"),
    ).reset_index()

    out["GRS_base"] = (0.50 * out["GRS_mean"] + 0.50 * out["GRS_max"]).clip(0, 1)
    out["GRS"] = out["GRS_base"]
    out["geo_risk_score"] = out["GRS"]
    out["geo_risk_norm"] = out["GRS"]
    out["segment"] = out.apply(
        lambda row: format_chainage_range_dk(row["segment_start_first"], row["segment_end_first"]),
        axis=1,
    )
    out["segment_label_dk"] = out["segment"]
    out["segment_sample_count"] = out["chainage_count"]

    for key in ["speed", "set_speed", "thrust", "torque", "rpm", "penetration"]:
        col = f"__{key}"
        if col not in df.columns:
            continue
        stats = grouped[col].agg(["mean", "std", "min", "max", "median"]).reset_index()
        stats = stats.rename(columns={
            "mean": f"{key}_mean",
            "std": f"{key}_std",
            "min": f"{key}_min",
            "max": f"{key}_max",
            "median": f"{key}_median",
        })
        out = out.merge(stats, on="segment_id", how="left")
        mean_col = f"{key}_mean"
        std_col = f"{key}_std"
        if mean_col in out.columns and std_col in out.columns:
            denom = out[mean_col].abs().replace(0, np.nan)
            out[f"{key}_cv"] = (out[std_col] / denom).replace([np.inf, -np.inf], np.nan).fillna(0)

    for key, source_col in [
        ("risk_mode", colmap.get("risk")),
        ("hazard_mode", colmap.get("hazard")),
        ("fused_grade_mode", colmap.get("grade")),
        ("coverage_mode", colmap.get("coverage")),
    ]:
        if source_col:
            out[key] = grouped[source_col].agg(_mode_text).values
    if "hazard_mode" in out.columns:
        out["seg_geo_hazard_mode"] = out["hazard_mode"]
    if "fused_grade_mode" in out.columns:
        out["seg_geo_grade_mode"] = out["fused_grade_mode"]
    if "coverage_mode" in out.columns:
        out["seg_geo_coverage_mode"] = out["coverage_mode"]

    if "__speed" in df.columns:
        speed_reference = _safe_positive_median(df["__speed"])
        low_threshold = speed_reference * 0.10 if speed_reference > 0 else 1e-6
        zero_ratio = grouped["__speed"].apply(
            lambda x: float((pd.to_numeric(x, errors="coerce").fillna(0).abs() <= low_threshold).mean())
        )
        out = out.merge(zero_ratio.rename("speed_zero_ratio").reset_index(), on="segment_id", how="left")
    else:
        out["speed_zero_ratio"] = 0.0

    if "__state" in df.columns:
        stop_ratio = grouped["__state"].apply(
            lambda x: float((pd.to_numeric(x, errors="coerce").fillna(-1) == 0).mean())
        )
        out = out.merge(stop_ratio.rename("stop_state_ratio").reset_index(), on="segment_id", how="left")
    else:
        out["stop_state_ratio"] = 0.0

    if "speed_mean" in out.columns and "set_speed_mean" in out.columns:
        denom = pd.to_numeric(out["set_speed_mean"], errors="coerce").replace(0, np.nan)
        out["efficiency"] = (pd.to_numeric(out["speed_mean"], errors="coerce") / denom).replace(
            [np.inf, -np.inf], np.nan
        )

    if "speed_mean" not in out.columns:
        warnings.append("speed column not found; speed decay and efficiency anomalies are limited")
    if "torque_mean" not in out.columns:
        warnings.append("torque column not found; torque anomaly validation is limited")

    row_metric_columns = [
        "row_iforest_anomaly_score",
        "row_rai",
        "row_routine_stop_relief",
        "row_stop_anomaly",
        "row_efficiency_anomaly",
        "row_speed_drop_score",
        "row_thrust_anomaly_score",
        "row_torque_anomaly_score",
        "row_rpm_anomaly_score",
        "row_penetration_anomaly_score",
        "row_efficiency_anomaly_score",
        "row_response_consistency",
        "row_load_response_norm",
        "row_speed_decay_norm",
    ]
    for column in row_metric_columns:
        if column not in df.columns:
            continue
        stats = grouped[column].agg(["mean", "max"]).reset_index()
        stats = stats.rename(columns={"mean": f"{column}_mean", "max": f"{column}_max"})
        out = out.merge(stats, on="segment_id", how="left")

    return out

    # ============================================================
# _add_row_response_anomaly_scores：逐记录施工响应异常打分
#
# 输入：
#   df：
#       已经清洗并统一字段后的逐记录 TBM 数据。
#       其中可能包含：
#           __speed：推进速度
#           __set_speed：推进给定速度
#           __thrust：推力
#           __torque：刀盘扭矩
#           __rpm：刀盘转速
#           __penetration：贯入度
#           __state：掘进状态
#           __routine_stop_score / __routine_stop_candidate：常规拼装停机识别结果
#
# 主流程：
#   1. 使用 IsolationForest 对推力、扭矩、速度、转速、贯入度等多变量组合进行异常检测；
#   2. 分别计算推进速度下降、推力偏高、扭矩偏高、转速异常、贯入度异常等单变量异常分数；
#   3. 根据实际速度/给定速度计算推进效率异常；
#   4. 根据速度接近 0 和掘进状态为 0 判断停机异常；
#   5. 对常规管片拼装停机进行降权，避免误判为施工异常；
#   6. 计算负载响应、速度衰减和多指标响应一致性；
#   7. 综合多变量异常、停机异常和效率异常，得到 row_rai。
#
# 输出新增字段：
#   row_iforest_anomaly_score：多变量施工响应异常分数
#   row_speed_drop_score：推进速度下降异常分数
#   row_thrust_anomaly_score：推力偏高异常分数
#   row_torque_anomaly_score：扭矩偏高异常分数
#   row_rpm_anomaly_score：转速异常分数
#   row_penetration_anomaly_score：贯入度异常分数
#   row_efficiency_anomaly_score：推进效率异常分数
#   row_stop_anomaly_raw：原始停机异常标志
#   row_routine_stop_relief：常规停机降权系数
#   row_stop_anomaly：降权后的停机异常分数
#   row_load_response_norm：负载响应异常程度
#   row_speed_decay_norm：速度衰减程度
#   row_response_consistency：多指标同步异常程度
#   row_rai：逐记录施工响应异常指数
# ============================================================
def _add_row_response_anomaly_scores(df: pd.DataFrame, warnings: list[str]) -> pd.DataFrame:
    """Build row-level response anomaly features before segment aggregation."""
    out = df.copy()
    idx = out.index

    feature_cols = [col for col in ["__thrust", "__torque", "__speed", "__rpm", "__penetration"] if col in out.columns]
    valid = out[feature_cols].apply(pd.to_numeric, errors="coerce") if feature_cols else pd.DataFrame(index=idx)
    if len(feature_cols) >= 2 and not valid.empty and valid.dropna(how="all").shape[0] >= 3:
        filled = valid.copy()
        for column in feature_cols:
            median = filled[column].median(skipna=True)
            filled[column] = filled[column].fillna(median if pd.notna(median) else 0.0)
        model = IsolationForest(
            n_estimators=200,
            contamination="auto",
            random_state=42,
        )
        model.fit(filled)
        raw_score = pd.Series(-model.score_samples(filled), index=filled.index)
        out["row_iforest_anomaly_score"] = _normalize_series(raw_score)
    else:
        warnings.append("IsolationForest requires at least 3 samples and 2 response features; row anomaly score set to zero")
        out["row_iforest_anomaly_score"] = _zero_series(idx)

    out["row_speed_drop_score"] = (
        _robust_score(out["__speed"], side="low")
        if "__speed" in out.columns
        else _zero_series(idx)
    )
    out["row_thrust_anomaly_score"] = (
        _robust_score(out["__thrust"], side="high")
        if "__thrust" in out.columns
        else _zero_series(idx)
    )
    out["row_torque_anomaly_score"] = (
        _robust_score(out["__torque"], side="high")
        if "__torque" in out.columns
        else _zero_series(idx)
    )
    out["row_rpm_anomaly_score"] = (
        _robust_score(out["__rpm"], side="two")
        if "__rpm" in out.columns
        else _zero_series(idx)
    )
    out["row_penetration_anomaly_score"] = (
        _robust_score(out["__penetration"], side="two")
        if "__penetration" in out.columns
        else _zero_series(idx)
    )

    if "__speed" in out.columns and "__set_speed" in out.columns:
        set_speed = pd.to_numeric(out["__set_speed"], errors="coerce").replace(0, np.nan)
        efficiency = (pd.to_numeric(out["__speed"], errors="coerce") / set_speed).replace([np.inf, -np.inf], np.nan)
        out["row_efficiency_anomaly_score"] = _robust_score(efficiency.fillna(0), side="low")
    else:
        out["row_efficiency_anomaly_score"] = out["row_speed_drop_score"].copy()

    if "__speed" in out.columns:
        speed_reference = _safe_positive_median(out["__speed"])
        low_threshold = speed_reference * 0.10 if speed_reference > 0 else 1e-6
        row_speed_stop = (
            pd.to_numeric(out["__speed"], errors="coerce").fillna(0).abs() <= low_threshold
        ).astype(float)
    else:
        row_speed_stop = _zero_series(idx)

    if "__state" in out.columns:
        row_state_stop = (
            pd.to_numeric(out["__state"], errors="coerce").fillna(-1) == 0
        ).astype(float)
    else:
        row_state_stop = _zero_series(idx)

    out["row_stop_anomaly_raw"] = pd.concat([row_speed_stop, row_state_stop], axis=1).max(axis=1).fillna(0).clip(0, 1)
    if "__routine_stop_score" in out.columns:
        routine_relief = pd.to_numeric(out["__routine_stop_score"], errors="coerce").fillna(0).clip(0, 1)
    elif "__routine_stop_candidate" in out.columns:
        routine_relief = pd.to_numeric(out["__routine_stop_candidate"], errors="coerce").fillna(0).clip(0, 1)
    else:
        routine_relief = _zero_series(idx)
    out["row_routine_stop_relief"] = routine_relief
    out["row_stop_anomaly"] = (out["row_stop_anomaly_raw"] * (1.0 - 0.80 * routine_relief)).clip(0, 1)
    out["row_efficiency_anomaly"] = out["row_efficiency_anomaly_score"].fillna(0).clip(0, 1)
    out["row_load_response_norm"] = pd.concat(
        [out["row_thrust_anomaly_score"], out["row_torque_anomaly_score"]],
        axis=1,
    ).max(axis=1).fillna(0).clip(0, 1)
    out["row_speed_decay_norm"] = out["row_speed_drop_score"].fillna(0).clip(0, 1)

    component_matrix = pd.DataFrame(
        {
            "speed": out["row_speed_drop_score"],
            "thrust": out["row_thrust_anomaly_score"],
            "torque": out["row_torque_anomaly_score"],
            "rpm": out["row_rpm_anomaly_score"],
            "penetration": out["row_penetration_anomaly_score"],
        },
        index=idx,
    ).fillna(0).clip(0, 1)
    out["row_response_consistency"] = (component_matrix >= 0.55).sum(axis=1) / max(len(component_matrix.columns), 1)
    out["row_rai"] = (
        0.70 * out["row_iforest_anomaly_score"]
        + 0.15 * out["row_stop_anomaly"]
        + 0.15 * out["row_efficiency_anomaly"]
    ).clip(0, 1)
    return out

# ============================================================
# _add_response_anomaly_index：计算区段级施工响应异常指数 RAI
#
# 输入：
#   segment_df：
#       _aggregate_segment_features 的输出。
#       每一行对应一个 10m 区段，已经包含 row_* 异常分数的
#       mean/max 聚合结果，例如：
#           row_iforest_anomaly_score_mean/max
#           row_stop_anomaly_mean/max
#           row_efficiency_anomaly_mean/max
#           row_speed_drop_score_mean/max
#           row_thrust_anomaly_score_mean/max
#           row_torque_anomaly_score_mean/max
#
# 主流程：
#   1. 使用 _mean_max_blend 将逐记录异常分数的 mean/max
#      融合成区段级异常分量；
#   2. 生成多变量异常、停机异常、效率异常、速度下降、
#      推力异常、扭矩异常、转速异常、贯入度异常等区段级指标；
#   3. 根据 speed_cv 计算速度波动异常；
#   4. 计算 param_anomaly，用于描述施工参数综合异常；
#   5. 按权重融合：
#        RAI = 0.70 * iforest_anomaly_score
#            + 0.15 * stop_anomaly
#            + 0.15 * efficiency_anomaly
#   6. 调用 _add_anomaly_pattern 生成异常模式解释字段。
#
# 输出新增字段：
#   iforest_anomaly_score：区段级多变量响应异常
#   stop_anomaly：区段级停机异常
#   efficiency_anomaly：区段级效率异常
#   speed_drop_score：区段级速度下降异常
#   thrust_anomaly_score：区段级推力异常
#   torque_anomaly_score：区段级扭矩异常
#   response_consistency：多指标同步异常程度
#   load_response_norm：负载响应异常
#   speed_decay_norm：速度衰减异常
#   speed_volatility_score：速度波动异常
#   param_anomaly：参数综合异常分数
#   RAI：区段级施工响应异常指数
#   response_anomaly_index：RAI 的兼容字段
# ============================================================
def _add_response_anomaly_index(segment_df: pd.DataFrame, warnings: list[str]) -> pd.DataFrame:
    """Aggregate row-level anomaly scores into a segment-level RAI."""
    out = segment_df.copy()
    idx = out.index

    iforest_mean = _mean_max_blend(out, "row_iforest_anomaly_score")
    if float(iforest_mean.max(skipna=True) or 0) <= 1e-12:
        warnings.append("segment RAI uses zero fallback because row-level IsolationForest scores are unavailable")

    out["iforest_anomaly_score"] = iforest_mean
    out["stop_anomaly"] = _mean_max_blend(out, "row_stop_anomaly")
    out["efficiency_anomaly"] = _mean_max_blend(out, "row_efficiency_anomaly")
    out["speed_drop_score"] = _mean_max_blend(out, "row_speed_drop_score")
    out["thrust_anomaly_score"] = _mean_max_blend(out, "row_thrust_anomaly_score")
    out["torque_anomaly_score"] = _mean_max_blend(out, "row_torque_anomaly_score")
    out["rpm_anomaly_score"] = _mean_max_blend(out, "row_rpm_anomaly_score")
    out["penetration_anomaly_score"] = _mean_max_blend(out, "row_penetration_anomaly_score")
    out["efficiency_anomaly_score"] = _mean_max_blend(out, "row_efficiency_anomaly_score")
    out["response_consistency"] = _mean_max_blend(out, "row_response_consistency")
    out["load_response_norm"] = _mean_max_blend(out, "row_load_response_norm")
    out["speed_decay_norm"] = _mean_max_blend(out, "row_speed_decay_norm")
    out["speed_volatility_score"] = (
        _robust_score(out["speed_cv"], side="high")
        if "speed_cv" in out.columns
        else _zero_series(idx)
    )

    out["param_anomaly"] = (
        0.55 * out["iforest_anomaly_score"]
        + 0.20 * out["load_response_norm"]
        + 0.15 * out["speed_decay_norm"]
        + 0.10 * out["response_consistency"]
    ).clip(0, 1)

    out["RAI"] = (
        0.70 * out["iforest_anomaly_score"]
        + 0.15 * out["stop_anomaly"]
        + 0.15 * out["efficiency_anomaly"]
    ).clip(0, 1)
    out["response_anomaly_index"] = out["RAI"]
    out = _add_anomaly_pattern(out)
    return out


def _add_anomaly_pattern(segment_df: pd.DataFrame) -> pd.DataFrame:
    """Internal helper for add anomaly pattern."""
    out = segment_df.copy()
    idx = out.index

    stop_dominant = pd.to_numeric(out.get("stop_anomaly", _zero_series(idx)), errors="coerce").fillna(0).clip(0, 1)
    efficiency_drop = pd.to_numeric(
        out.get("efficiency_anomaly", _zero_series(idx)),
        errors="coerce",
    ).fillna(0).clip(0, 1)
    speed_drop = pd.to_numeric(out.get("speed_drop_score", _zero_series(idx)), errors="coerce").fillna(0).clip(0, 1)
    high_load = pd.concat([
        pd.to_numeric(out.get("thrust_anomaly_score", _zero_series(idx)), errors="coerce").fillna(0),
        pd.to_numeric(out.get("torque_anomaly_score", _zero_series(idx)), errors="coerce").fillna(0),
        pd.to_numeric(out.get("load_response_norm", _zero_series(idx)), errors="coerce").fillna(0),
    ], axis=1).max(axis=1).clip(0, 1)
    volatility = _volatility_pattern_score(out, idx)
    pattern_scores = pd.DataFrame(
        {
            "stop_dominant": stop_dominant,
            "efficiency_drop": efficiency_drop,
            "high_load": high_load,
            "volatility": volatility,
            "speed_drop": speed_drop,
        },
        index=idx,
    ).fillna(0).clip(0, 1)
    out["anomaly_type_score"] = pattern_scores.max(axis=1).fillna(0)
    out["anomaly_type"] = [
        _classify_anomaly_pattern(row)
        for _, row in pattern_scores.iterrows()
    ]
    return out


def _compute_stop_anomaly(out: pd.DataFrame, warnings: list[str]) -> pd.Series:
    """Build a 0-1 stop anomaly score from explicit ratios or segment fallbacks."""
    idx = out.index
    explicit_cols = [
        "stop_ratio",
        "stop_duration_ratio",
        "stop_time_ratio",
        "stop_total_ratio",
        "stoppage_ratio",
    ]
    explicit_parts = [_ratio_series(out[col]) for col in explicit_cols if col in out.columns]
    if explicit_parts:
        return pd.concat(explicit_parts, axis=1).max(axis=1).fillna(0).clip(0, 1)

    working_cols = [
        "working_ratio",
        "work_ratio",
        "working_time_ratio",
        "work_time_ratio",
        "effective_working_ratio",
        "effective_digging_ratio",
        "digging_ratio",
    ]
    working_parts = [(1.0 - _ratio_series(out[col])).clip(0, 1) for col in working_cols if col in out.columns]
    if working_parts:
        warnings.append("stop_anomaly uses working_ratio fallback because stop-ratio fields are missing")
        return pd.concat(working_parts, axis=1).max(axis=1).fillna(0).clip(0, 1)

    fallback_cols = [col for col in ["stop_state_ratio", "speed_zero_ratio"] if col in out.columns]
    if fallback_cols:
        warnings.append("stop_anomaly uses segment-level stop samples / zero-speed fallback")
        return pd.concat([_ratio_series(out[col]) for col in fallback_cols], axis=1).max(axis=1).fillna(0).clip(0, 1)

    warnings.append("stop_anomaly fields are missing; stop_anomaly is set to zero")
    return _zero_series(idx)


def _compute_efficiency_anomaly(out: pd.DataFrame, warnings: list[str]) -> pd.Series:
    """Build a 0-1 efficiency anomaly score from work ratio or speed efficiency."""
    idx = out.index
    working_cols = [
        "working_ratio",
        "work_ratio",
        "working_time_ratio",
        "work_time_ratio",
        "effective_working_ratio",
        "effective_digging_ratio",
        "digging_ratio",
    ]
    working_parts = [(1.0 - _ratio_series(out[col])).clip(0, 1) for col in working_cols if col in out.columns]
    if working_parts:
        return pd.concat(working_parts, axis=1).max(axis=1).fillna(0).clip(0, 1)

    if "stop_anomaly" in out.columns:
        warnings.append("efficiency_anomaly uses inferred working-ratio fallback from stop_anomaly")
        return pd.to_numeric(out["stop_anomaly"], errors="coerce").fillna(0).clip(0, 1)

    if "efficiency" in out.columns:
        values = pd.to_numeric(out["efficiency"], errors="coerce").replace([np.inf, -np.inf], np.nan)
        if values.notna().any():
            efficiency_score = (1.0 - values.fillna(0)).clip(0, 1)
            if float(efficiency_score.max(skipna=True) or 0) > 1e-9:
                return efficiency_score

    if "speed_drop_score" in out.columns:
        warnings.append("efficiency_anomaly uses speed-drop fallback because working_ratio/efficiency fields are missing")
        return pd.to_numeric(out["speed_drop_score"], errors="coerce").fillna(0).clip(0, 1)

    if "speed_mean" in out.columns:
        speed = pd.to_numeric(out["speed_mean"], errors="coerce").replace([np.inf, -np.inf], np.nan)
        reference = speed[speed > 0].quantile(0.75)
        if pd.notna(reference) and reference > 1e-9:
            warnings.append("efficiency_anomaly uses relative speed fallback because working_ratio is missing")
            return (1.0 - (speed.fillna(0) / reference)).clip(0, 1)

    warnings.append("efficiency_anomaly fields are missing; efficiency_anomaly is set to zero")
    return _zero_series(idx)


def _ratio_series(series: pd.Series) -> pd.Series:
    """Internal helper for ratio series."""
    values = pd.to_numeric(series, errors="coerce").replace([np.inf, -np.inf], np.nan).fillna(0)
    max_value = values.max(skipna=True)
    if pd.notna(max_value) and max_value > 1.0 and max_value <= 100.0:
        values = values / 100.0
    return values.clip(0, 1)


def _mean_max_blend(df: pd.DataFrame, prefix: str) -> pd.Series:
    """Blend mean and max aggregates for one row-derived segment feature."""
    idx = df.index
    parts = []
    mean_col = f"{prefix}_mean"
    max_col = f"{prefix}_max"
    if mean_col in df.columns:
        parts.append(pd.to_numeric(df[mean_col], errors="coerce").fillna(0).clip(0, 1))
    if max_col in df.columns:
        parts.append(pd.to_numeric(df[max_col], errors="coerce").fillna(0).clip(0, 1))
    if not parts:
        return _zero_series(idx)
    if len(parts) == 1:
        return parts[0]
    return (0.50 * parts[0] + 0.50 * parts[1]).clip(0, 1)


def _normalize_series(series: pd.Series) -> pd.Series:
    """Normalize a numeric series into the 0-1 interval."""
    values = pd.to_numeric(series, errors="coerce").replace([np.inf, -np.inf], np.nan).fillna(0)
    min_value = float(values.min(skipna=True)) if not values.empty else 0.0
    max_value = float(values.max(skipna=True)) if not values.empty else 0.0
    if max_value - min_value > 1e-9:
        return ((values - min_value) / (max_value - min_value)).clip(0, 1)
    return values.clip(0, 1)


def _classify_anomaly_pattern(row: pd.Series) -> str:
    """Classify anomaly pattern."""
    stop_score = float(row.get("stop_dominant", 0) or 0)
    efficiency_score = float(row.get("efficiency_drop", 0) or 0)
    high_load_score = float(row.get("high_load", 0) or 0)
    volatility_score = float(row.get("volatility", 0) or 0)
    speed_score = float(row.get("speed_drop", 0) or 0)

    max_key = str(row.idxmax())
    max_score = float(row.max())
    if max_key == "stop_dominant" and stop_score >= 0.50:
        return "停机主导型"
    if max_key == "efficiency_drop" and efficiency_score >= 0.40:
        return "效率下降型"
    if max_key == "high_load" and high_load_score >= 0.35:
        return "高负载型"
    if max_key == "volatility" and volatility_score >= 0.35:
        return "波动型"
    if max_key == "speed_drop" and speed_score >= 0.35:
        return "速度下降型"
    if max_score >= 0.35:
        return "综合异常型"
    return "轻微异常型"


def _volatility_pattern_score(out: pd.DataFrame, idx: pd.Index) -> pd.Series:
    """Internal helper for volatility pattern score."""
    candidates = []
    for col in ["speed_volatility_score"]:
        if col in out.columns:
            candidates.append(pd.to_numeric(out[col], errors="coerce").fillna(0).clip(0, 1))
    for col in ["speed_cv", "thrust_cv", "torque_cv", "rpm_cv", "penetration_cv"]:
        if col in out.columns:
            values = pd.to_numeric(out[col], errors="coerce").replace([np.inf, -np.inf], np.nan)
            reference = values.quantile(0.75)
            if pd.notna(reference) and reference > 1e-9:
                candidates.append((values / (reference * 2.0)).fillna(0).clip(0, 1))
    return _combine_scores(candidates, idx)


def _add_coupling_index(
    segment_df: pd.DataFrame,
    risk_threshold: float,
    response_threshold: float,
) -> pd.DataFrame:
    """Internal helper for add coupling index."""
    out = segment_df.copy()
    grs = pd.to_numeric(out.get("GRS", 0), errors="coerce").fillna(0).clip(0, 1)
    rai = pd.to_numeric(out.get("RAI", 0), errors="coerce").fillna(0).clip(0, 1)

    balance = (1 - (grs - rai).abs()).clip(0, 1)
    sync = (
        0.50 * np.minimum(grs, rai)
        + 0.30 * np.sqrt((grs * rai).clip(0, 1))
        + 0.20 * balance * ((grs + rai) / 2)
    ).clip(0, 1)

    prev_grs = grs.shift(1).fillna(0)
    prev_rai = rai.shift(1).fillna(0)
    delta_grs = (grs - prev_grs).fillna(0).clip(lower=-1, upper=1)
    delta_rai = (rai - prev_rai).fillna(0).clip(lower=-1, upper=1)
    risk_entry = (grs - prev_grs).clip(lower=0, upper=1)
    response_rise = delta_rai.clip(lower=0, upper=1)
    lag = pd.concat([
        np.minimum(prev_grs, rai),
        np.minimum(grs, response_rise * 1.5),
        np.minimum(risk_entry * 1.5, rai),
    ], axis=1).max(axis=1).clip(0, 1)
    response_change = pd.concat([
        np.minimum(grs, response_rise * 1.8),
        np.sqrt((risk_entry * response_rise).clip(0, 1)),
        np.minimum((delta_grs.abs() * 1.2).clip(0, 1), rai),
    ], axis=1).max(axis=1).clip(0, 1)

    consistency = pd.to_numeric(out.get("response_consistency", 0), errors="coerce").fillna(0).clip(0, 1)
    source = pd.to_numeric(out.get("source_evidence_norm", 0), errors="coerce").fillna(0).clip(0, 1)
    multi_param = (consistency * rai).clip(0, 1)
    confidence = (0.85 + 0.15 * source).clip(0.85, 1.0)

    grci = (0.40 * sync + 0.25 * lag + 0.25 * response_change + 0.10 * multi_param) * confidence
    out["delta_RAI"] = delta_rai
    out["delta_GRS"] = delta_grs
    out["sync_coupling"] = sync.clip(0, 1)
    out["lag_coupling"] = lag.clip(0, 1)
    out["lag_response"] = lag.clip(0, 1)
    out["response_change_coupling"] = response_change.clip(0, 1)
    out["GRCI"] = grci.clip(0, 1).fillna(0)
    out["geo_response_coupling_index"] = out["GRCI"]
    out["coupling_index"] = out["GRCI"]
    out["risk_response_coupling_index"] = out["GRCI"]

    out["coupling_level"] = out["GRCI"].map(_coupling_level)
    out["coupling_label"] = out["coupling_level"].map(COUPLING_LEVEL_LABELS).fillna(COUPLING_LEVEL_LABELS["unknown"])
    out["grci_class_code"] = [
        _classify_segment(risk, response, risk_threshold, response_threshold)
        for risk, response in zip(grs, rai)
    ]
    out["grci_class_label"] = out["grci_class_code"].map(CLASS_LABELS)
    out["coupling_class"] = out["grci_class_code"]
    out["coupling_type"] = out["grci_class_label"]
    out["coupling_interpretation"] = out.apply(_build_interpretation, axis=1)
    return out


def _add_weak_validation_labels(segment_df: pd.DataFrame) -> pd.DataFrame:
    """Internal helper for add weak validation labels."""
    out = segment_df.copy()
    reasons = []
    labels = []
    for _, row in out.iterrows():
        row_reasons = []
        if float(row.get("speed_zero_ratio", 0) or 0) >= 0.45 or float(row.get("stop_state_ratio", 0) or 0) >= 0.45:
            row_reasons.append("long_stop_proxy")
        if float(row.get("speed_drop_score", 0) or 0) >= 0.65:
            row_reasons.append("speed_drop")
        if float(row.get("torque_anomaly_score", 0) or 0) >= 0.65:
            row_reasons.append("torque_fluctuation")
        if float(row.get("efficiency_anomaly_score", 0) or 0) >= 0.65:
            row_reasons.append("low_efficiency")
        if float(row.get("RAI", 0) or 0) >= 0.75 and float(row.get("response_consistency", 0) or 0) >= 0.40:
            row_reasons.append("multi_parameter_response")

        labels.append(bool(row_reasons))
        reasons.append(",".join(row_reasons))

    out["weak_anomaly_label"] = labels
    out["weak_anomaly_reasons"] = reasons
    return out

# ============================================================
# _validate_coupling：基于弱标签的 GRCI 内部一致性验证
#
# 输入：
#   segment_df：
#       带 GRCI 和 weak_anomaly_label 的区段级结果表。
#   top_k：
#       检查 GRCI 排名前 top_k 的区段命中弱标签的比例。
#
# 核心逻辑：
#   1. 读取 weak_anomaly_label 作为弱标签；
#   2. 读取 GRCI 作为排序/预测分数；
#   3. 计算 GRCI Top-K 区段中命中弱标签的数量和比例；
#   4. 使用固定阈值 GRCI >= 0.60 作为异常预测；
#   5. 计算相对于弱标签的 precision、recall、tp、fp、fn。
#
# 注意：
#   这里不是严格人工标注验证，而是弱标签验证。
#   结果只能说明 GRCI 与内部规则标签的一致性。
# ============================================================
def _validate_coupling(segment_df: pd.DataFrame, top_k: int) -> dict[str, Any]:
    """Internal helper for validate coupling."""
    if segment_df is None or segment_df.empty:
        return _empty_validation()

    labels = segment_df.get("weak_anomaly_label", pd.Series(False, index=segment_df.index)).astype(bool)
    scores = pd.to_numeric(segment_df.get("GRCI", 0), errors="coerce").fillna(0)
    top_n = int(min(max(top_k, 1), len(segment_df)))
    top_idx = scores.sort_values(ascending=False).head(top_n).index
    top_hits = int(labels.loc[top_idx].sum()) if len(top_idx) else 0

    threshold = 0.60
    pred = scores >= threshold
    tp = int((pred & labels).sum())
    fp = int((pred & ~labels).sum())
    fn = int((~pred & labels).sum())

    precision = _safe_div(tp, tp + fp)
    recall = _safe_div(tp, tp + fn)

    return {
        "has_validation": True,
        "weak_label_count": int(labels.sum()),
        "segment_count": int(len(segment_df)),
        "top_k": top_n,
        "top_k_hits": top_hits,
        "top_k_hit_rate": _safe_div(top_hits, top_n),
        "baseline_weak_label_rate": _safe_div(int(labels.sum()), len(segment_df)),
        "threshold": threshold,
        "precision": precision,
        "recall": recall,
        "tp": tp,
        "fp": fp,
        "fn": fn,
    }


def _build_high_attention(segment_df: pd.DataFrame, top_k: int) -> list[dict[str, Any]]:
    """Compatibility wrapper: high_attention_segments means top GRCI segments."""
    return _build_top_segments(segment_df, top_k=top_k, sort_col="GRCI")


def _build_top_segments(segment_df: pd.DataFrame, top_k: int, sort_col: str) -> list[dict[str, Any]]:
    """Build top-k segment records by a clearly named metric."""
    if segment_df is None or segment_df.empty:
        return []
    if sort_col not in segment_df.columns:
        fallback = "GRCI" if "GRCI" in segment_df.columns else "risk_response_coupling_index"
        sort_col = fallback if fallback in segment_df.columns else segment_df.columns[0]
    keep_cols = [
        "segment", "segment_label_dk", "segment_start_first", "segment_end_first",
        "segment_start", "segment_end", "segment_sample_count",
        "GRS", "GRS_geo_base", "GRS_adjusted", "geo_risk_score",
        "GRS_base", "GRS_corrected", "GRS_smooth", "GRS_final",
        "correction", "correction_factor", "RAI", "response_anomaly_index",
        "stop_anomaly", "efficiency_anomaly", "param_anomaly", "anomaly_type",
        "anomaly_type_score", "GRCI", "coupling_index", "geo_response_coupling_index",
        "delta_RAI", "lag_response", "response_change_coupling", "risk_response_coupling_index",
        "coupling_label", "grci_class_code", "grci_class_label", "coupling_class",
        "coupling_type", "weak_anomaly_label", "weak_anomaly_reasons",
        "coupling_interpretation", "seg_geo_hazard_mode", "seg_geo_grade_mode",
        "seg_geo_coverage_mode", "geo_attention_hint_score", "geo_attention_hint_level",
    ]
    top = segment_df.sort_values(sort_col, ascending=False).head(top_k)
    records = top[[c for c in keep_cols if c in top.columns]].to_dict(orient="records")
    return serialize_for_json(records)


def _build_summary(
    segment_df: pd.DataFrame,
    validation: dict[str, Any],
    high_attention_segments: list[dict[str, Any]],
    segment_length: float,
    warnings: list[str],
    grs_metadata: dict[str, Any] | None = None,
    top_grs_segments: list[dict[str, Any]] | None = None,
    top_rai_segments: list[dict[str, Any]] | None = None,
    top_grci_segments: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    构造地质-施工响应耦合分析的全局摘要。

    输入：
        segment_df:
            带 GRS、RAI、GRCI 等指标的区段级结果表。
        validation:
            弱标签验证结果。
        high_attention_segments:
            高关注区段列表，当前通常等同于 top_grci_segments。
        segment_length:
            区段长度，单位 m。
        warnings:
            分析过程中的警告信息。
        grs_metadata:
            GRS 动态修正相关元信息。
        top_grs_segments:
            GRS 排名前列的区段。
        top_rai_segments:
            RAI 排名前列的区段。
        top_grci_segments:
            GRCI 排名前列的区段。

    输出：
        summary:
            耦合分析全局摘要字典。
            包含指标统计、分类分布、Top 区段、弱标签验证、
            GRS 修正信息、summary_text 和 warnings。
    """
    if segment_df is None or segment_df.empty:
        return _empty_summary("no segment result", warnings)

    # 如果没有单独传入 top_grci_segments，则使用 high_attention_segments 作为兼容
    top_grci_segments = top_grci_segments if top_grci_segments is not None else high_attention_segments
    top_grs_segments = top_grs_segments or []
    top_rai_segments = top_rai_segments or []

    # 提取核心指标序列
    grci = pd.to_numeric(segment_df.get("GRCI", 0), errors="coerce").fillna(0)
    grs_adjusted = pd.to_numeric(
        segment_df.get("GRS_adjusted", segment_df.get("GRS", 0)),
        errors="coerce"
    ).fillna(0)
    grs_base = pd.to_numeric(
        segment_df.get("GRS_geo_base", segment_df.get("GRS_base", 0)),
        errors="coerce"
    ).fillna(0)
    rai = pd.to_numeric(segment_df.get("RAI", 0), errors="coerce").fillna(0)

    # 统计 GRS/RAI 四象限分类数量
    class_counts = segment_df.get("grci_class_label", pd.Series(dtype=str)).value_counts().to_dict()

    # 统计 GRCI 等级数量
    level_counts = segment_df.get("coupling_label", pd.Series(dtype=str)).value_counts().to_dict()

    # 取 GRCI 最高区段，用于 summary_text
    top = top_grci_segments[0] if top_grci_segments else {}

    # 构造报告可读的摘要文本
    summary_text = (
        f"区段级地质-施工响应耦合分析完成，共 {len(segment_df)} 个已开挖区段；"
        f"GRCI最高区段为 {top.get('segment', '--')}，"
        f"GRCI={float(top.get('GRCI', top.get('risk_response_coupling_index', 0)) or 0):.2f}，"
        f"类型为 {top.get('grci_class_label', '--')}。"
        "其中 GRS_geo_base 表示地质基础关注度，GRS_adjusted 表示结合施工响应修正后的关注值，"
        "RAI 表示施工响应异常度，GRCI 表示地质-施工响应耦合关注度。"
    )

    grs_metadata = grs_metadata or {}

    return {
        "has_coupling": True,
        "method": GEOLOGY_METHOD_VERSION,
        "grs_model_version": grs_metadata.get("grs_model_version"),
        "segment_length_m": segment_length,
        "segment_count": int(len(segment_df)),

        # 当前采用的 GRS 统计，优先使用 GRS_adjusted
        "GRS_mean": float(grs_adjusted.mean()),
        "GRS_max": float(grs_adjusted.max()),

        # 地质基础 GRS 统计
        "GRS_geo_base_mean": float(grs_base.mean()),
        "GRS_geo_base_max": float(grs_base.max()),

        # 动态修正后的 GRS 统计
        "GRS_adjusted_mean": float(grs_adjusted.mean()),
        "GRS_adjusted_max": float(grs_adjusted.max()),

        # 施工响应异常指数统计
        "RAI_mean": float(rai.mean()),
        "RAI_max": float(rai.max()),

        # 地质-施工响应耦合指数统计
        "GRCI_mean": float(grci.mean()),
        "GRCI_max": float(grci.max()),

        # 分类与等级分布
        "class_counts": serialize_for_json(class_counts),
        "level_counts": serialize_for_json(level_counts),
        "grci_class_counts": serialize_for_json(class_counts),
        "coupling_level_counts": serialize_for_json(level_counts),

        # GRS 动态修正信息
        "engineering_weights": serialize_for_json(grs_metadata.get("engineering_weights", {})),
        "grs_weight_method": grs_metadata.get("grs_weight_method", "engineering_prior_dynamic"),
        "correction_lambda": grs_metadata.get("correction_lambda"),
        "min_grs": grs_metadata.get("min_grs"),
        "correction_formula": grs_metadata.get("correction_formula"),
        "grs_correction_mode": grs_metadata.get("correction_mode"),
        "grs_has_rai": grs_metadata.get("has_rai"),
        "grs_has_stop_ratio": grs_metadata.get("has_stop_ratio"),

        # Top 区段列表
        "top_segments": top_grci_segments,
        "high_attention_segments": top_grci_segments,
        "top_grci_segments": top_grci_segments,
        "top_grs_segments": top_grs_segments,
        "top_rai_segments": top_rai_segments,

        # 弱标签验证
        "validation": validation,
        "weak_label_validation": validation,

        # 文本摘要与警告
        "summary_text": summary_text,
        "warnings": warnings,
    }

def _write_outputs(
    segment_df: pd.DataFrame,
    high_attention_segments: list[dict[str, Any]],
    summary: dict[str, Any],
    output_dir: str | Path | None,
    output_prefix: str,
    warnings: list[str],
) -> dict[str, str]:
    """Internal helper for write outputs."""
    if output_dir is None or segment_df is None or segment_df.empty:
        return {}

    paths: dict[str, str] = {}
    try:
        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        safe_prefix = re.sub(r"[^0-9A-Za-z_.-]+", "_", output_prefix).strip("_") or "tbm_coupling"

        segment_path = out_dir / f"{safe_prefix}_segments.csv"
        high_path = out_dir / f"{safe_prefix}_high_attention.json"
        summary_path = out_dir / f"{safe_prefix}_summary.json"

        segment_df.to_csv(segment_path, index=False, encoding="utf-8-sig")
        high_path.write_text(
            json.dumps(serialize_for_json(high_attention_segments), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        summary_path.write_text(
            json.dumps(serialize_for_json(summary), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        paths = {
            "segment_csv": str(segment_path),
            "high_attention_json": str(high_path),
            "summary_json": str(summary_path),
        }
    except Exception as exc:
        warnings.append(f"failed to write coupling outputs: {exc}")
    return paths


def _merge_with_base_segments(base_segment_df: pd.DataFrame | None, metric_df: pd.DataFrame) -> pd.DataFrame:
    """Internal helper for merge with base segments."""
    if base_segment_df is None or base_segment_df.empty:
        return metric_df.copy()
    if metric_df is None or metric_df.empty:
        return base_segment_df.copy()

    base = base_segment_df.copy()
    metric = metric_df.copy()
    if "segment_id" not in base.columns and not _has_segment_bounds(base):
        return metric.copy()
    if "segment_id" not in metric.columns and not _has_segment_bounds(metric):
        return metric_df.copy()

    base["__segment_key"] = _segment_merge_key(base)
    metric["__segment_key"] = _segment_merge_key(metric)

    metric_cols = [c for c in METRIC_COLUMNS if c in metric.columns]
    extra_cols = [
        c for c in metric.columns
        if c.endswith("_score") or c in {"GRCI", "GRS", "RAI", "response_consistency"}
    ]
    keep_cols = ["__segment_key"] + list(dict.fromkeys(metric_cols + extra_cols))
    keep_cols = [c for c in keep_cols if c in metric.columns]
    drop_cols = [c for c in keep_cols if c != "__segment_key" and c in base.columns]
    base = base.drop(columns=drop_cols)
    merged = base.merge(metric[keep_cols], on="__segment_key", how="left")
    return merged.drop(columns=["__segment_key"])


def _has_segment_bounds(df: pd.DataFrame) -> bool:
    """Internal helper for has segment bounds."""
    start_col = _first_existing(df, ["segment_start_first", "segment_start"])
    end_col = _first_existing(df, ["segment_end_first", "segment_end"])
    return bool(start_col and end_col)


def _segment_merge_key(df: pd.DataFrame) -> pd.Series:
    """Internal helper for segment merge key."""
    start_col = _first_existing(df, ["segment_start_first", "segment_start"])
    end_col = _first_existing(df, ["segment_end_first", "segment_end"])
    if start_col and end_col:
        return (
            pd.to_numeric(df[start_col], errors="coerce").map(_number_key)
            + "_"
            + pd.to_numeric(df[end_col], errors="coerce").map(_number_key)
        )
    return df.get("segment_id", pd.Series("", index=df.index)).map(_normalize_segment_id)


def _first_existing(df: pd.DataFrame, columns: list[str]) -> str | None:
    """Internal helper for first existing."""
    for col in columns:
        if col in df.columns:
            return col
    return None


def _normalize_segment_id(value: Any) -> str:
    """Normalize segment id."""
    parts = str(value).split("_")
    if len(parts) == 2:
        return f"{_number_key(parts[0])}_{_number_key(parts[1])}"
    return str(value)


def _empty_summary(reason: str, warnings: list[str]) -> dict[str, Any]:
    """Internal helper for empty summary."""
    return {
        "has_coupling": False,
        "method": GEOLOGY_METHOD_VERSION,
        "level_counts": {},
        "class_counts": {},
        "top_segments": [],
        "high_attention_segments": [],
        "top_grci_segments": [],
        "top_grs_segments": [],
        "top_rai_segments": [],
        "weak_label_validation": _empty_validation(),
        "summary_text": f"区段级地质-施工响应耦合分析不可用：{reason}。",
        "warnings": warnings,
    }


def _empty_validation() -> dict[str, Any]:
    """Internal helper for empty validation."""
    return {
        "has_validation": False,
        "weak_label_count": 0,
        "segment_count": 0,
        "top_k": 0,
        "top_k_hits": 0,
        "top_k_hit_rate": 0.0,
        "baseline_weak_label_rate": 0.0,
        "precision": 0.0,
        "recall": 0.0,
        "tp": 0,
        "fp": 0,
        "fn": 0,
    }


def _build_interpretation(row: pd.Series) -> str:
    """
    构造单个区段的耦合分析解释文本。

    输入：
        row:
            segment_df 中的一行，对应一个里程区段。

    使用字段：
        segment:
            区段 DK 里程标签。
        grci_class_label:
            根据 GRS/RAI 阈值划分得到的耦合类型。
        GRS:
            区段地质关注度。
        RAI:
            区段施工响应异常度。
        GRCI:
            地质-施工响应耦合关注度。

    输出：
        一句面向报告或前端展示的区段解释文本。
    """
    segment = row.get("segment", "--")
    cls = row.get("grci_class_label", "--")
    grs = float(row.get("GRS", 0) or 0)
    rai = float(row.get("RAI", 0) or 0)
    grci = float(row.get("GRCI", row.get("risk_response_coupling_index", 0)) or 0)
    return f"{segment}：{cls}，GRS={grs:.2f}，RAI={rai:.2f}，GRCI={grci:.2f}。"


def _classify_segment(risk: float, response: float, risk_threshold: float, response_threshold: float) -> str:
    """Classify segment."""
    high_risk = risk >= risk_threshold
    high_response = response >= response_threshold
    if high_risk and high_response:
        return "A"
    if high_risk and not high_response:
        return "B"
    if not high_risk and high_response:
        return "C"
    return "D"


def _coupling_level(value: float) -> str:
    """Internal helper for coupling level."""
    if value is None or pd.isna(value):
        return "unknown"
    if value >= 0.75:
        return "strong"
    if value >= 0.50:
        return "medium"
    if value >= 0.25:
        return "weak"
    return "low"


def _grade_score(value: Any) -> float:
    """Internal helper for grade score."""
    text = str(value).strip().upper()
    if not text or text == "NAN":
        return 0.0
    for key, score in GRADE_SCORES.items():
        if key in text:
            return score
    match = re.search(r"[1-5]", text)
    if match:
        return GRADE_SCORES.get(match.group(0), 0.0)
    return 0.0


def _hazard_score(text: Any) -> float:
    """Internal helper for hazard score."""
    haystack = str(text).lower()
    if not haystack or haystack == "nan":
        return 0.0
    score = 0.0
    for keywords, weight in HAZARD_KEYWORDS:
        if any(keyword.lower() in haystack for keyword in keywords):
            score += weight
    return float(np.clip(score, 0, 1))


def _combined_text(df: pd.DataFrame, columns: list[str | None]) -> pd.Series:
    """Internal helper for combined text."""
    existing = [col for col in columns if col and col in df.columns]
    if not existing:
        return pd.Series("", index=df.index)
    out = pd.Series("", index=df.index, dtype=object)
    for col in existing:
        out = out + " " + df[col].fillna("").astype(str)
    return out.str.strip()


def _mode_text(series: pd.Series) -> str:
    """Internal helper for mode text."""
    clean = series.dropna().astype(str)
    clean = clean[clean.str.strip() != ""]
    if clean.empty:
        return ""
    mode = clean.mode()
    return str(mode.iloc[0]) if not mode.empty else str(clean.iloc[0])


def _robust_score(series: pd.Series, side: str = "high") -> pd.Series:
    """Internal helper for robust score."""
    values = pd.to_numeric(series, errors="coerce").replace([np.inf, -np.inf], np.nan)
    if values.notna().sum() < 3:
        return _zero_series(series.index)

    median = values.median(skipna=True)
    mad = (values - median).abs().median(skipna=True)
    if pd.notna(mad) and mad > 1e-9:
        scale = 1.4826 * mad
    else:
        q75 = values.quantile(0.75)
        q25 = values.quantile(0.25)
        iqr = q75 - q25
        scale = iqr / 1.349 if pd.notna(iqr) and iqr > 1e-9 else values.std(skipna=True)

    if scale is None or pd.isna(scale) or scale <= 1e-9:
        return _zero_series(series.index)

    z = (values - median) / scale
    if side == "low":
        score = (-z / 3.0).clip(lower=0, upper=1)
    elif side == "two":
        score = (z.abs() / 3.0).clip(lower=0, upper=1)
    else:
        score = (z / 3.0).clip(lower=0, upper=1)
    return score.fillna(0)


def _combine_scores(scores: list[pd.Series], index: pd.Index) -> pd.Series:
    """Internal helper for combine scores."""
    if not scores:
        return _zero_series(index)
    return pd.concat(scores, axis=1).max(axis=1).fillna(0).clip(0, 1)


def _safe_positive_median(series: pd.Series) -> float:
    """Internal helper for safe positive median."""
    values = pd.to_numeric(series, errors="coerce")
    values = values[values > 0]
    if values.empty:
        return 0.0
    return float(values.median())


def _zero_series(index: pd.Index) -> pd.Series:
    """Build a zero-filled series for the target index."""
    return pd.Series(0.0, index=index)


def _safe_div(num: int | float, den: int | float) -> float:
    """Internal helper for safe div."""
    if not den:
        return 0.0
    return float(num) / float(den)


def _number_key(value: Any) -> str:
    """Internal helper for number key."""
    try:
        x = float(value)
        if math.isfinite(x) and x.is_integer():
            return str(int(x))
        return f"{x:.3f}".rstrip("0").rstrip(".")
    except Exception:
        return str(value)


def _infer_output_prefix(df: pd.DataFrame, colmap: dict[str, str | None]) -> str:
    """Infer output prefix."""
    time_col = colmap.get("time")
    if time_col and time_col in df.columns:
        times = pd.to_datetime(df[time_col], errors="coerce").dropna()
        if not times.empty:
            return f"tbm_coupling_{times.iloc[0].strftime('%Y%m%d')}"
    start = _number_key(df["chainage"].min()) if "chainage" in df.columns else "unknown"
    end = _number_key(df["chainage"].max()) if "chainage" in df.columns else "unknown"
    return f"tbm_coupling_{start}_{end}"