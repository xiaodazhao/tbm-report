# segment_analysis.py
import pandas as pd
import numpy as np

from utils.chainage_utils import format_chainage_dk, format_chainage_range_dk


def build_segments(df: pd.DataFrame, segment_length=10):
    """
    按固定里程长度划分区段。
    输出仍然是记录级 DataFrame，只是给每条记录增加 segment_id / segment_start / segment_end。
    """
    out = df.copy()

    if "chainage" not in out.columns:
        raise ValueError("输入数据缺少 chainage 字段")

    out = out.dropna(subset=["chainage"]).copy()
    out["chainage"] = pd.to_numeric(out["chainage"], errors="coerce")
    out = out.dropna(subset=["chainage"]).copy()

    out["segment_start"] = (np.floor(out["chainage"] / segment_length) * segment_length).astype(float)
    out["segment_end"] = out["segment_start"] + segment_length
    out["segment_id"] = out["segment_start"].map(_number_key) + "_" + out["segment_end"].map(_number_key)
    return out


def _number_key(value):
    try:
        x = float(value)
        if np.isfinite(x) and x.is_integer():
            return str(int(x))
        return f"{x:.3f}".rstrip("0").rstrip(".")
    except Exception:
        return str(value)


def _first_existing(df: pd.DataFrame, candidates):
    for col in candidates:
        if col in df.columns:
            return col
    return None


def _mode_text(series: pd.Series) -> str:
    clean = series.dropna().astype(str)
    clean = clean[clean.str.strip() != ""]
    if clean.empty:
        return ""
    mode = clean.mode()
    return str(mode.iloc[0]) if not mode.empty else str(clean.iloc[0])


def _safe_numeric(series, default=0.0):
    return pd.to_numeric(series, errors="coerce").replace([np.inf, -np.inf], np.nan).fillna(default)


def _add_numeric_aggregations(agg_dict, out: pd.DataFrame, source_col: str, prefix: str, stats=("max", "mean")):
    if source_col not in out.columns:
        return
    for stat in stats:
        agg_dict[f"{prefix}_{stat}"] = (source_col, stat)


def _add_mode_aggregation(agg_dict, out: pd.DataFrame, source_col: str, output_col: str):
    if source_col in out.columns:
        agg_dict[output_col] = (source_col, _mode_text)


def aggregate_segments(df: pd.DataFrame):
    """
    对每个已开挖区段做聚合统计。

    第二阶段约定：
    - df_geo 中的逐里程地质事实字段，聚合后进入 seg_* 字段；
    - 本函数不把 parser risk_level 直接解释成系统风险；
    - 旧字段仍保留兼容别名，便于上游/下游逐步迁移。
    """
    if "segment_id" not in df.columns:
        raise ValueError("请先调用 build_segments()")

    out = df.copy()
    agg_dict = {
        "chainage_min": ("chainage", "min"),
        "chainage_max": ("chainage", "max"),
        "chainage_mean": ("chainage", "mean"),
        "segment_sample_count": ("chainage", "count"),
        "segment_start": ("segment_start", "first"),
        "segment_end": ("segment_end", "first"),
    }

    # 施工参数聚合，保留中文字段输出，兼容原报告文本。
    operation_numeric_cols = [
        "推进速度", "推进给定速度", "推力", "刀盘扭矩", "贯入度",
        "推进伸出压力", "推进回收压力", "主皮带反转压力", "主皮带正转压力",
    ]
    for col in operation_numeric_cols:
        if col in out.columns:
            for stat in ["mean", "std", "min", "max"]:
                agg_dict[f"{col}_{stat}"] = (col, stat)

    # 逐里程地质事实字段：优先消费第二阶段标准字段，兼容旧字段。
    active_source_col = _first_existing(out, ["active_report_source_count", "active_source_count"])
    evidence_count_col = _first_existing(out, ["matched_evidence_record_count", "evidence_count"])
    support_weight_col = _first_existing(out, ["evidence_support_weight_sum", "weighted_evidence_strength"])
    water_col = _first_existing(out, ["geo_water_flag", "water_flag_fused"])
    collapse_col = _first_existing(out, ["geo_collapse_flag", "collapse_flag_fused"])
    deformation_col = _first_existing(out, ["geo_deformation_flag", "deformation_flag_fused"])
    hazard_col = _first_existing(out, ["geo_hazard_summary", "hazard"])
    grade_col = _first_existing(out, ["geo_fused_grade", "fused_grade"])
    coverage_col = _first_existing(out, ["geo_coverage_status", "coverage"])
    uncertainty_col = _first_existing(out, ["geo_fusion_uncertainty", "uncertainty"])

    _add_numeric_aggregations(agg_dict, out, active_source_col, "seg_active_report_source_count", stats=("max", "mean"))
    _add_numeric_aggregations(agg_dict, out, evidence_count_col, "seg_matched_evidence_record_count", stats=("max", "mean", "sum"))
    _add_numeric_aggregations(agg_dict, out, support_weight_col, "seg_evidence_support_weight", stats=("max", "mean", "sum"))
    _add_numeric_aggregations(agg_dict, out, water_col, "seg_geo_water_flag", stats=("max", "mean"))
    _add_numeric_aggregations(agg_dict, out, collapse_col, "seg_geo_collapse_flag", stats=("max", "mean"))
    _add_numeric_aggregations(agg_dict, out, deformation_col, "seg_geo_deformation_flag", stats=("max", "mean"))

    _add_mode_aggregation(agg_dict, out, hazard_col, "seg_geo_hazard_mode")
    _add_mode_aggregation(agg_dict, out, grade_col, "seg_geo_grade_mode")
    _add_mode_aggregation(agg_dict, out, coverage_col, "seg_geo_coverage_mode")
    _add_mode_aggregation(agg_dict, out, uncertainty_col, "seg_geo_uncertainty_mode")

    # 旧风险字段只作为兼容聚合，不作为新语义的主字段。
    if "risk_score" in out.columns:
        agg_dict["risk_score_max"] = ("risk_score", "max")
        agg_dict["risk_score_mean"] = ("risk_score", "mean")
    if "geo_prior_score" in out.columns:
        agg_dict["geo_prior_score_max"] = ("geo_prior_score", "max")
        agg_dict["geo_prior_score_mean"] = ("geo_prior_score", "mean")
    if "risk" in out.columns:
        agg_dict["risk_mode"] = ("risk", _mode_text)

    grouped = out.groupby("segment_id", sort=False).agg(**agg_dict).reset_index()

    # 兼容旧字段名，避免第一阶段外的调用链马上断裂。
    grouped["segment_start_first"] = grouped["segment_start"]
    grouped["segment_end_first"] = grouped["segment_end"]
    grouped["chainage_count"] = grouped["segment_sample_count"]
    if "seg_active_report_source_count_max" in grouped.columns:
        grouped["active_source_count_max"] = grouped["seg_active_report_source_count_max"]
        grouped["active_source_count_mean"] = grouped.get("seg_active_report_source_count_mean")
    if "seg_geo_hazard_mode" in grouped.columns:
        grouped["hazard_mode"] = grouped["seg_geo_hazard_mode"]
    if "seg_geo_grade_mode" in grouped.columns:
        grouped["fused_grade_mode"] = grouped["seg_geo_grade_mode"]
    if "seg_geo_coverage_mode" in grouped.columns:
        grouped["coverage_mode"] = grouped["seg_geo_coverage_mode"]

    grouped = _add_geo_attention_hint(grouped)
    return grouped


def _add_geo_attention_hint(df: pd.DataFrame) -> pd.DataFrame:
    """生成轻量地质证据关注提示，不等同于风险概率。"""
    out = df.copy()
    idx = out.index
    source_norm = (
        _safe_numeric(out.get("seg_active_report_source_count_max", pd.Series(0, index=idx))) / 4.0
    ).clip(0, 1)
    support = _safe_numeric(out.get("seg_evidence_support_weight_max", pd.Series(0, index=idx)))
    support_norm = _normalize_nonnegative(support)
    flag_parts = []
    for col in ["seg_geo_water_flag_max", "seg_geo_collapse_flag_max", "seg_geo_deformation_flag_max"]:
        if col in out.columns:
            flag_parts.append(_safe_numeric(out[col]).clip(0, 1))
    flag_score = pd.concat(flag_parts, axis=1).max(axis=1) if flag_parts else pd.Series(0.0, index=idx)
    out["geo_attention_hint_score"] = (0.45 * source_norm + 0.35 * flag_score + 0.20 * support_norm).clip(0, 1)
    out["geo_attention_hint_level"] = out["geo_attention_hint_score"].map(_attention_level)
    return out


def _normalize_nonnegative(series: pd.Series) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce").replace([np.inf, -np.inf], np.nan).fillna(0).clip(lower=0)
    max_value = values.max(skipna=True)
    if pd.notna(max_value) and max_value > 1e-9:
        return (values / max_value).clip(0, 1)
    return pd.Series(0.0, index=series.index)


def _attention_level(value: float) -> str:
    if pd.isna(value):
        return "none"
    if value >= 0.70:
        return "high"
    if value >= 0.40:
        return "medium"
    if value > 0:
        return "low"
    return "none"


def _format_dk(x):
    return format_chainage_dk(x)


def format_segment_label(df: pd.DataFrame):
    """增加 DK 里程区段标签。"""
    out = df.copy()
    start_col = "segment_start" if "segment_start" in out.columns else "segment_start_first"
    end_col = "segment_end" if "segment_end" in out.columns else "segment_end_first"
    out["segment_label_dk"] = out.apply(
        lambda r: format_chainage_range_dk(r[start_col], r[end_col]),
        axis=1,
    )
    # 兼容旧字段名
    out["segment"] = out["segment_label_dk"]
    return out


def add_efficiency_indicator(df: pd.DataFrame):
    """增加推进效率指标：推进速度 / 推进给定速度。"""
    out = df.copy()
    if "推进速度_mean" in out.columns and "推进给定速度_mean" in out.columns:
        denom = out["推进给定速度_mean"].replace(0, np.nan)
        out["efficiency"] = out["推进速度_mean"] / denom
    else:
        out["efficiency"] = np.nan
    return out


def analyze_segment_response(df: pd.DataFrame):
    """
    基于区段施工参数与地质证据支持程度进行保守解释。
    不再把 parser risk_score 直接写成系统“高风险区”。
    """
    out = df.copy()
    speed_col = "推进速度_mean" if "推进速度_mean" in out.columns else None
    thrust_col = "推力_mean" if "推力_mean" in out.columns else None
    torque_col = "刀盘扭矩_mean" if "刀盘扭矩_mean" in out.columns else None

    if speed_col is None:
        text = "区段级施工响应解释条件不足，缺少推进速度字段，需谨慎解释"
        out["segment_response_interpretation"] = text
        out["interpretation"] = text
        return out

    global_speed = out[speed_col].mean(skipna=True)
    global_thrust = out[thrust_col].mean(skipna=True) if thrust_col else np.nan
    global_torque = out[torque_col].mean(skipna=True) if torque_col else np.nan

    interpretations = []
    for _, row in out.iterrows():
        score = float(row.get("geo_attention_hint_score", 0) or 0)
        level = row.get("geo_attention_hint_level", "none")
        speed = row.get(speed_col, np.nan)
        thrust = row.get(thrust_col, np.nan) if thrust_col else np.nan
        torque = row.get(torque_col, np.nan) if torque_col else np.nan

        speed_low = pd.notna(speed) and pd.notna(global_speed) and speed < global_speed * 0.90
        thrust_high = pd.notna(thrust) and pd.notna(global_thrust) and thrust > global_thrust
        torque_high = pd.notna(torque) and pd.notna(global_torque) and torque > global_torque
        load_high = thrust_high or torque_high

        if level in {"high", "medium"}:
            if speed_low and load_high:
                interpretations.append("多源地质证据支持区段，且施工响应表现为推进速度下降与负载升高，建议重点复核")
            elif speed_low:
                interpretations.append("地质证据支持程度较高区段，施工响应表现为推进速度下降，建议结合现场复核")
            elif load_high:
                interpretations.append("地质证据支持程度较高区段，施工负载相对升高，建议关注后续变化")
            else:
                interpretations.append("地质证据支持程度较高区段，当前施工参数未见明显同步恶化")
        elif score > 0:
            if speed_low and load_high:
                interpretations.append("一般地质证据支持区段出现施工响应异常，建议复核地质与设备因素")
            elif speed_low:
                interpretations.append("一般地质证据支持区段推进速度相对下降，建议持续观察")
            else:
                interpretations.append("一般地质证据支持区段，施工响应总体平稳")
        else:
            if speed_low and load_high:
                interpretations.append("地质证据支持较弱区段出现施工响应异常，建议优先复核设备与操作因素")
            else:
                interpretations.append("地质证据支持较弱区段，施工响应未见明显异常")

    out["segment_response_interpretation"] = interpretations
    # 兼容旧字段名
    out["interpretation"] = out["segment_response_interpretation"]
    return out


def add_relative_change_features(df: pd.DataFrame):
    """增加相对全局均值的变化率，便于后续写报告。"""
    out = df.copy()
    for col in ["推进速度_mean", "推力_mean", "刀盘扭矩_mean", "efficiency"]:
        if col in out.columns:
            global_mean = out[col].mean(skipna=True)
            if pd.notna(global_mean) and global_mean != 0:
                out[f"{col}_rel_change"] = (out[col] - global_mean) / global_mean
            else:
                out[f"{col}_rel_change"] = np.nan
    return out


def run_segment_analysis(df: pd.DataFrame, segment_length=10):
    """一键完成已开挖区段级基础聚合。"""
    out = build_segments(df, segment_length=segment_length)
    out = aggregate_segments(out)
    out = format_segment_label(out)
    out = add_efficiency_indicator(out)
    out = add_relative_change_features(out)
    out = analyze_segment_response(out)
    if "segment_start" in out.columns:
        out = out.sort_values("segment_start").reset_index(drop=True)
    return out


def build_typical_segments_table(segment_df: pd.DataFrame, top_n=20):
    """生成典型区段表：按地质证据支持 + 施工响应变化 + 耦合指标排序。"""
    out = segment_df.copy()
    if out.empty:
        return out

    score = pd.Series(0, index=out.index, dtype=float)
    if "geo_attention_hint_score" in out.columns:
        score += _safe_numeric(out["geo_attention_hint_score"]) * 5
    if "seg_active_report_source_count_max" in out.columns:
        score += (_safe_numeric(out["seg_active_report_source_count_max"]) / 4.0).clip(0, 1) * 3
    if "seg_evidence_support_weight_max" in out.columns:
        score += _normalize_nonnegative(_safe_numeric(out["seg_evidence_support_weight_max"])) * 2

    for col in ["seg_geo_water_flag_max", "seg_geo_collapse_flag_max", "seg_geo_deformation_flag_max"]:
        if col in out.columns:
            score += _safe_numeric(out[col]).clip(0, 1) * 1.5

    if "推进速度_mean_rel_change" in out.columns:
        score += (-_safe_numeric(out["推进速度_mean_rel_change"])).clip(lower=0) * 8
    if "推力_mean_rel_change" in out.columns:
        score += _safe_numeric(out["推力_mean_rel_change"]).clip(lower=0) * 5
    if "刀盘扭矩_mean_rel_change" in out.columns:
        score += _safe_numeric(out["刀盘扭矩_mean_rel_change"]).clip(lower=0) * 5
    if "GRCI" in out.columns:
        score += _safe_numeric(out["GRCI"]).clip(0, 1) * 8
    elif "risk_response_coupling_index" in out.columns:
        score += _safe_numeric(out["risk_response_coupling_index"]).clip(0, 1) * 8

    out["typical_segment_priority_score"] = score
    # 兼容旧字段名
    out["priority_score"] = out["typical_segment_priority_score"]
    out = out.sort_values("typical_segment_priority_score", ascending=False).reset_index(drop=True)
    return out.head(top_n)