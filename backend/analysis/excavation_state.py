# ============================================================
# excavation_state.py
# 基于现有 TBM 字段的施工状态语义建模（不依赖贯入度）
# ============================================================

import pandas as pd
import numpy as np
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans


def _ensure_state_df(df):
    """Accept either a dataframe or the legacy (df, states) tuple."""
    if isinstance(df, tuple) and df:
        candidate = df[0]
        return candidate if isinstance(candidate, pd.DataFrame) else pd.DataFrame()
    return df if isinstance(df, pd.DataFrame) else pd.DataFrame()


def _safe_float(value):
    """Return a finite float or None."""
    try:
        number = float(value)
    except Exception:
        return None
    return number if np.isfinite(number) else None


# ============================================================
# 1. 施工状态识别（无监督）
# ============================================================
def detect_excavation_state(
    df,
    features=("推力", "刀盘扭矩", "刀盘实际转速", "推进速度"),
    n_states=3
):
    """
    基于 TBM 运行参数的施工状态识别
    输出：
      - df["state_id"]：施工状态编码
    """

    df = df.copy()

    # 仅保留真实存在的字段
    valid_features = [f for f in features if f in df.columns]
    if len(valid_features) < 2:
        df["state_id"] = np.nan
        return df, None

    df_feat = df[valid_features].copy()

    # 只在“工作中”样本上做聚类。
    # 优先消费 dataprocess.annotate_operation_mode 生成的规范字段，
    # 避免 cluster_state 与 operation_mode 的工作样本口径漂移。
    if "is_working" in df.columns:
        mask = df["is_working"].fillna(False).astype(bool)
        df_feat = df_feat[mask]
    elif "operation_mode" in df.columns:
        df_feat = df_feat[df["operation_mode"].astype(str) == "work"]
    elif "掘进状态" in df.columns:
        df_feat = df_feat[df["掘进状态"] != 0]
    else:
        # 兜底逻辑：推力或推进速度有一个明显非零，就认为是工作中
        mask = pd.Series(False, index=df.index)
        if "推力" in df.columns:
            mask |= (pd.to_numeric(df["推力"], errors="coerce").fillna(0).abs() > 1e-8)
        if "推进速度" in df.columns:
            mask |= (pd.to_numeric(df["推进速度"], errors="coerce").fillna(0).abs() > 1e-8)
        df_feat = df_feat[mask]

    df_feat = df_feat.apply(pd.to_numeric, errors="coerce").dropna()

    if len(df_feat) < n_states:
        df["state_id"] = np.nan
        return df, None

    scaler = StandardScaler()
    X = scaler.fit_transform(df_feat)

    kmeans = KMeans(n_clusters=n_states, random_state=0, n_init="auto")
    states = kmeans.fit_predict(X)

    df["state_id"] = np.nan
    df.loc[df_feat.index, "state_id"] = states

    return df, states


# ============================================================
# 2. 施工状态分段（时间连续性约束）
# ============================================================
def excavation_state_segments(df, min_duration_sec=30):
    """
    基于施工状态编码的时间连续分段
    - 小于 min_duration_sec 的段视为噪声
    """
    df = _ensure_state_df(df)
    segments = {}

    if "state_id" not in df.columns or "运行时间-time" not in df.columns:
        return segments

    df = df.copy()
    df["运行时间-time"] = pd.to_datetime(df["运行时间-time"], errors="coerce")
    df = df.dropna(subset=["运行时间-time"]).sort_values("运行时间-time").reset_index(drop=True)

    for state in sorted(df["state_id"].dropna().unique()):
        state = int(state)
        segs = []

        in_seg = False
        start = None

        for i in range(len(df)):
            cur_state = df["state_id"].iloc[i]
            cur_time = df["运行时间-time"].iloc[i]

            if cur_state == state and not in_seg:
                in_seg = True
                start = cur_time

            if in_seg and cur_state != state:
                end = df["运行时间-time"].iloc[i - 1]
                dur = (end - start).total_seconds()
                if dur >= min_duration_sec:
                    segs.append((start, end))
                in_seg = False

        if in_seg:
            end = df["运行时间-time"].iloc[-1]
            dur = (end - start).total_seconds()
            if dur >= min_duration_sec:
                segs.append((start, end))

        segments[state] = segs

    return segments


# ============================================================
# 3. 自动给施工状态做语义标签
# ============================================================
def explain_excavation_states(df):
    """
    根据每个 state 的统计特征，自动生成语义解释
    返回：
    {
        0: "高推力低速状态",
        1: "稳定推进状态",
        2: "低负载调整状态"
    }
    """

    df = _ensure_state_df(df)
    if "state_id" not in df.columns:
        return {}

    use_cols = [c for c in ["推力", "刀盘扭矩", "刀盘实际转速", "推进速度"] if c in df.columns]
    if len(use_cols) < 2:
        return {}

    stat_df = df.groupby("state_id")[use_cols].mean().dropna(how="all")
    if stat_df.empty:
        return {}

    labels = {}

    # 各指标的中位数，作为高低判断基准
    medians = stat_df.median()

    for state, row in stat_df.iterrows():
        thrust = row["推力"] if "推力" in row else np.nan
        torque = row["刀盘扭矩"] if "刀盘扭矩" in row else np.nan
        speed = row["推进速度"] if "推进速度" in row else np.nan
        rpm = row["刀盘实际转速"] if "刀盘实际转速" in row else np.nan

        if pd.notna(thrust) and pd.notna(speed):
            if thrust >= medians.get("推力", thrust) and speed >= medians.get("推进速度", speed):
                label = "高负载稳定推进状态"
            elif thrust >= medians.get("推力", thrust) and speed < medians.get("推进速度", speed):
                label = "高推力低速受阻状态"
            elif thrust < medians.get("推力", thrust) and speed >= medians.get("推进速度", speed):
                label = "低负载快速推进状态"
            else:
                label = "低负载调整状态"
        else:
            label = "一般施工状态"

        # 如果扭矩特别高，再强化语义
        if pd.notna(torque) and torque >= medians.get("刀盘扭矩", torque) * 1.1:
            if "受阻" not in label and "高负载" not in label:
                label += "（扭矩偏高）"

        labels[int(state)] = label

    return labels


# ============================================================
# 4. 施工状态段 → 文本（LLM 语义层）
# ============================================================
def excavation_state_to_text(segments, state_labels=None):
    """Handle excavation state to text."""
    lines = []

    for state, segs in segments.items():
        if not segs:
            continue

        if state_labels and state in state_labels:
            lines.append(f"\n施工状态 {state}（{state_labels[state]}）：")
        else:
            lines.append(f"\n施工状态 {state}：")

        for s, e in segs:
            dur_min = (e - s).total_seconds() / 60
            lines.append(
                f"- {s.strftime('%H:%M:%S')} ~ {e.strftime('%H:%M:%S')}（{dur_min:.1f} 分钟）"
            )

    return "\n".join(lines)


# ============================================================
# 5. 施工状态推进效率统计（不依赖贯入度）
# ============================================================
def excavation_state_efficiency(df):
    """
    每个施工状态的效率表征指标
    """

    df = _ensure_state_df(df)
    if "state_id" not in df.columns:
        return pd.DataFrame()

    agg_items = {}
    if "推进速度" in df.columns:
        agg_items["平均推进速度"] = ("推进速度", "mean")
    if "推力" in df.columns:
        agg_items["平均推力"] = ("推力", "mean")
    if "刀盘扭矩" in df.columns:
        agg_items["平均刀盘扭矩"] = ("刀盘扭矩", "mean")
    if "刀盘实际转速" in df.columns:
        agg_items["平均刀盘实际转速"] = ("刀盘实际转速", "mean")
    if "推进给定速度" in df.columns:
        agg_items["平均推进给定速度"] = ("推进给定速度", "mean")

    if not agg_items:
        return pd.DataFrame()

    eff = df.groupby("state_id").agg(**agg_items).dropna(how="all")

    # 派生指标：推力/推进速度、扭矩/推进速度、速度跟随率
    if "平均推力" in eff.columns and "平均推进速度" in eff.columns:
        eff["单位推进阻力_推力除速度"] = eff["平均推力"] / (eff["平均推进速度"] + 1e-6)

    if "平均刀盘扭矩" in eff.columns and "平均推进速度" in eff.columns:
        eff["单位推进扭矩_扭矩除速度"] = eff["平均刀盘扭矩"] / (eff["平均推进速度"] + 1e-6)

    if "平均推进给定速度" in eff.columns and "平均推进速度" in eff.columns:
        eff["速度跟随率"] = eff["平均推进速度"] / (eff["平均推进给定速度"] + 1e-6)

    return eff


# ============================================================
# 6. 施工状态统计（状态表征）
# ============================================================
def excavation_state_stats(df, segments=None):
    """
    状态表征指标：
    - 累计持续时间
    - 占比
    - 最大连续段
    - 状态切换次数（施工稳定性）
    """

    df = _ensure_state_df(df)
    stats = {}

    if "state_id" not in df.columns or df.empty or "运行时间-time" not in df.columns:
        return stats

    df = df.copy()
    df["运行时间-time"] = pd.to_datetime(df["运行时间-time"], errors="coerce")
    df = df.dropna(subset=["运行时间-time"]).sort_values("运行时间-time").reset_index(drop=True)

    total_time = (
        df["运行时间-time"].iloc[-1] - df["运行时间-time"].iloc[0]
    ).total_seconds()

    if segments is None:
        segments = excavation_state_segments(df)

    seq = list(df["state_id"].dropna())
    switches = sum(1 for i in range(1, len(seq)) if seq[i] != seq[i - 1])

    for state, segs in segments.items():
        total_dur = sum((e - s).total_seconds() for s, e in segs)
        max_seg = max(segs, key=lambda x: (x[1] - x[0]).total_seconds()) if segs else None

        stats[state] = {
            "累计时长_min": total_dur / 60,
            "占比": total_dur / total_time if total_time > 0 else 0,
            "最大连续段": max_seg,
        }

    stats["状态切换次数"] = switches
    return stats


# ============================================================
# 7. 施工状态效率 → 文本
# ============================================================
def efficiency_to_text(eff_df, state_labels=None):
    """Handle efficiency to text."""
    if eff_df.empty:
        return "数据量不足，无法计算施工状态效率统计。"

    lines = ["不同施工状态的效率统计如下：\n"]

    for state, row in eff_df.iterrows():
        title = f"施工状态 {int(state)}"
        if state_labels and int(state) in state_labels:
            title += f"（{state_labels[int(state)]}）"

        parts = [title]

        for col in eff_df.columns:
            parts.append(f"{col} {row[col]:.2f}")

        lines.append("，".join(parts) + "。")

    return "\n".join(lines)


# ============================================================
# 8. 施工状态总体统计 → 文本
# ============================================================
def excavation_state_stats_to_text(stats, state_labels=None):
    """Handle excavation state stats to text."""
    if not stats:
        return "无施工状态统计结果。"

    lines = ["\n施工状态总体统计："]

    for state in sorted(k for k in stats.keys() if isinstance(k, int)):
        d = stats[state]
        percent = d["占比"] * 100

        if d["最大连续段"]:
            s, e = d["最大连续段"]
            longest = f"{s.strftime('%H:%M:%S')}~{e.strftime('%H:%M:%S')}"
        else:
            longest = "无"

        title = f"施工状态 {state}"
        if state_labels and state in state_labels:
            title += f"（{state_labels[state]}）"

        lines.append(
            f"\n{title}：\n"
            f"- 累计持续时间：{d['累计时长_min']:.1f} 分钟（占比 {percent:.1f}%）\n"
            f"- 最大连续状态段：{longest}"
        )

    lines.append(f"\n施工状态切换次数：{stats.get('状态切换次数', 0)} 次。")
    return "\n".join(lines)


def build_cluster_context(
    df_state: pd.DataFrame,
    segments: dict | list | pd.DataFrame | None = None,
    state_labels: dict | None = None,
    eff_df: pd.DataFrame | None = None,
    state_stats: dict | None = None,
) -> dict:
    """Build a structured cluster-state context without changing legacy outputs."""
    warnings: list[str] = []
    frame = _ensure_state_df(df_state)
    state_labels = state_labels if isinstance(state_labels, dict) else {}
    state_stats = state_stats if isinstance(state_stats, dict) else {}
    feature_columns = [column for column in ["推力", "刀盘扭矩", "刀盘实际转速", "推进速度"] if column in frame.columns]

    if frame.empty or "state_id" not in frame.columns:
        return {
            "schema_version": "cluster_context_v1",
            "has_cluster": False,
            "n_states": 0,
            "feature_columns": feature_columns,
            "cluster_quality": {
                "valid_sample_count": 0,
                "cluster_count": 0,
                "min_cluster_ratio": None,
                "is_stable_enough": False,
                "warnings": ["缺少 state_id，未形成聚类施工状态。"],
                "note": "state_id only valid within the current day",
            },
            "state_summaries": [],
            "switch_count": None,
            "warnings": ["缺少 state_id，未形成聚类施工状态。"],
        }

    if segments is None:
        segments = excavation_state_segments(frame)
    elif isinstance(segments, list):
        # Backward tolerance: convert list-style segments into an empty dict if structure is unclear.
        segments = {}
    elif isinstance(segments, pd.DataFrame):
        segments = {}

    if "is_working" in frame.columns:
        valid_mask = frame["is_working"].fillna(False).astype(bool)
        valid_sample_count = int(valid_mask.sum())
    else:
        valid_mask = frame["state_id"].notna()
        valid_sample_count = int(valid_mask.sum())

    valid_state_series = frame.loc[valid_mask, "state_id"].dropna()
    unique_states = sorted(int(value) for value in valid_state_series.unique().tolist())
    cluster_count = len(unique_states)
    ratio_map = valid_state_series.value_counts(normalize=True).to_dict() if not valid_state_series.empty else {}
    min_cluster_ratio = float(min(ratio_map.values())) if ratio_map else None
    is_stable_enough = bool(
        valid_sample_count >= 30
        and cluster_count >= 2
        and min_cluster_ratio is not None
        and min_cluster_ratio >= 0.03
    )
    if valid_sample_count < 30:
        warnings.append("有效聚类样本数不足 30，聚类稳定性有限。")
    if cluster_count < 2:
        warnings.append("有效聚类状态数不足 2，聚类区分度有限。")
    if min_cluster_ratio is None or min_cluster_ratio < 0.03:
        warnings.append("最小簇占比过低，可能存在小样本簇。")

    if eff_df is None:
        eff_df = excavation_state_efficiency(frame)
    eff_lookup = {}
    if isinstance(eff_df, pd.DataFrame) and not eff_df.empty:
        try:
            eff_lookup = eff_df.to_dict(orient="index")
        except Exception:
            eff_lookup = {}

    seq = [int(value) for value in frame["state_id"].dropna().tolist()]
    switch_count = sum(1 for idx in range(1, len(seq)) if seq[idx] != seq[idx - 1]) if seq else None

    state_summaries = []
    for state_id in unique_states:
        state_frame = frame[frame["state_id"] == state_id].copy()
        segs = segments.get(state_id, []) if isinstance(segments, dict) else []
        duration_info = state_stats.get(state_id, {}) if isinstance(state_stats, dict) else {}
        eff_info = eff_lookup.get(state_id, {})
        efficiency_features = {
            key: _safe_float(value)
            for key, value in eff_info.items()
            if key not in {"平均推进速度", "平均推力", "平均刀盘扭矩", "平均刀盘实际转速"}
        }
        max_continuous_duration_min = None
        if segs:
            max_continuous_duration_min = _safe_float(
                max((end - start).total_seconds() / 60.0 for start, end in segs)
            )
        state_summaries.append(
            {
                "state_id": state_id,
                "semantic_label": state_labels.get(state_id, f"状态{state_id}"),
                "duration_min": _safe_float(duration_info.get("累计时长_min")),
                "ratio": _safe_float(duration_info.get("占比")),
                "sample_count": int(len(state_frame)),
                "max_continuous_duration_min": max_continuous_duration_min,
                "mean_advance_speed": _safe_float(eff_info.get("平均推进速度")),
                "mean_thrust": _safe_float(eff_info.get("平均推力")),
                "mean_torque": _safe_float(eff_info.get("平均刀盘扭矩")),
                "mean_rpm": _safe_float(eff_info.get("平均刀盘实际转速")),
                "efficiency_features": efficiency_features,
            }
        )

    return {
        "schema_version": "cluster_context_v1",
        "has_cluster": bool(cluster_count > 0),
        "n_states": cluster_count,
        "feature_columns": feature_columns,
        "cluster_quality": {
            "valid_sample_count": valid_sample_count,
            "cluster_count": cluster_count,
            "min_cluster_ratio": _safe_float(min_cluster_ratio),
            "is_stable_enough": is_stable_enough,
            "warnings": warnings,
            "note": "state_id only valid within the current day",
        },
        "state_summaries": state_summaries,
        "switch_count": switch_count,
        "warnings": warnings,
    }
