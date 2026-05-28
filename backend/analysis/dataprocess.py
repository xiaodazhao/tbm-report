# dataprocess.py
import pandas as pd


COMMON_TIME_COLUMNS = ["运行时间-time", "timestamp", "time", "datetime", "date_time"]
COMMON_CHAINAGE_COLUMNS = ["chainage", "当前里程", "导向盾首里程", "开累进尺", "里程"]
COMMON_STATE_COLUMNS = ["掘进状态", "施工状态", "state", "excavation_state"]
COMMON_SPEED_COLUMNS = ["推进速度", "advance_speed", "speed", "actual_speed"]


def _judge_condition(row):
    """Internal helper for judge condition."""
    if "掘进状态" in row.index and pd.notna(row["掘进状态"]):
        status = row["掘进状态"]
        if status == 0:
            return 0
        else:
            thrust = row["推力"] if "推力" in row.index and pd.notna(row["推力"]) else 0
            speed = row["推进速度"] if "推进速度" in row.index and pd.notna(row["推进速度"]) else 0
            torque = row["刀盘扭矩"] if "刀盘扭矩" in row.index and pd.notna(row["刀盘扭矩"]) else 0

            thrust_on = abs(thrust) > 1e-8
            speed_on = abs(speed) > 1e-8
            torque_on = abs(torque) > 1e-8

            if thrust_on and speed_on:
                return 2
            elif thrust_on and (not speed_on):
                return 1
            elif (not thrust_on) and torque_on:
                return 3
            else:
                return 1

    thrust = row["推力"] if "推力" in row.index and pd.notna(row["推力"]) else 0
    speed = row["推进速度"] if "推进速度" in row.index and pd.notna(row["推进速度"]) else 0
    torque = row["刀盘扭矩"] if "刀盘扭矩" in row.index and pd.notna(row["刀盘扭矩"]) else 0

    thrust_on = abs(thrust) > 1e-8
    speed_on = abs(speed) > 1e-8
    torque_on = abs(torque) > 1e-8

    if not thrust_on and not speed_on and not torque_on:
        return 0
    elif thrust_on and not speed_on:
        return 1
    elif thrust_on and speed_on:
        return 2
    elif (not thrust_on) and torque_on:
        return 3
    else:
        return 0


def _condition_code_to_state(code):
    """Internal helper for condition code to state."""
    mapping = {
        0: "stop",
        1: "transition",
        2: "work",
        3: "abnormal"
    }
    return mapping.get(code, "unknown")


def _condition_code_to_cn(code):
    """Internal helper for condition code to cn."""
    mapping = {
        0: "停机",
        1: "启动/过渡",
        2: "稳定掘进",
        3: "异常扭矩"
    }
    return mapping.get(code, "未知")


OPERATION_MODE_SCHEMA_VERSION = "operation_mode_v2"


def _normalize_time_sort(df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy sorted by the canonical time column when available."""
    out = df.copy()
    time_col = _find_first_existing(out, COMMON_TIME_COLUMNS)
    if time_col and time_col != "运行时间-time":
        out = out.rename(columns={time_col: "运行时间-time"})
        time_col = "运行时间-time"
    if time_col:
        out[time_col] = pd.to_datetime(out[time_col], errors="coerce")
        out = out.dropna(subset=[time_col]).sort_values(time_col).reset_index(drop=True)
    return out


def infer_sample_interval_sec(df: pd.DataFrame, time_col: str = "运行时间-time") -> float:
    """Infer median PLC sampling interval in seconds for duration correction."""
    if df is None or df.empty or time_col not in df.columns:
        return 0.0
    times = pd.to_datetime(df[time_col], errors="coerce").dropna().sort_values()
    if len(times) < 2:
        return 0.0
    diffs = times.diff().dt.total_seconds().dropna()
    diffs = diffs[(diffs > 0) & (diffs < 3600)]
    if diffs.empty:
        return 0.0
    return float(diffs.median())


def annotate_operation_mode(source) -> pd.DataFrame:
    """Annotate canonical operation_mode fields on PLC records.

    This is the single producer for basic operation-mode semantics:
    stop / transition / work / abnormal. Cluster states and response anomalies
    should not overwrite these fields.
    """
    if isinstance(source, pd.DataFrame):
        df = source.copy()
    else:
        df = pd.read_csv(source)

    df = _normalize_time_sort(df)
    if df.empty:
        return df

    df["operation_mode_schema_version"] = OPERATION_MODE_SCHEMA_VERSION
    df["operation_mode_code"] = df.apply(_judge_condition, axis=1).astype(int)
    df["operation_mode"] = df["operation_mode_code"].map(_condition_code_to_state)
    df["operation_mode_cn"] = df["operation_mode_code"].map(_condition_code_to_cn)

    reason_map = {
        0: "停机：掘进状态为0或推力/速度/扭矩均接近0",
        1: "启动/过渡：存在推力但推进速度不足或工况未稳定",
        2: "稳定掘进：推力与推进速度均为有效非零",
        3: "异常扭矩：无明显推力推进但扭矩存在响应",
    }
    df["operation_mode_reason"] = df["operation_mode_code"].map(reason_map).fillna("未知工况")
    df["is_stopped"] = df["operation_mode_code"].eq(0)
    df["is_transition"] = df["operation_mode_code"].eq(1)
    df["is_working"] = df["operation_mode_code"].eq(2)
    df["is_abnormal"] = df["operation_mode_code"].eq(3)
    return df


def annotate_routine_ring_building_stops(
    source,
    ring_lengths=(1.5, 1.8),
    tolerance_m=0.25,
    min_duration_min=25.0,
    max_duration_min=90.0,
    max_stop_drift_m=0.25,
    low_speed_threshold=1e-4,
):
    """Annotate stop rows that look like routine ring-building pauses."""
    if isinstance(source, pd.DataFrame):
        df = source.copy()
    else:
        df = pd.read_csv(source)

    df["routine_ring_building_candidate"] = 0.0
    df["routine_ring_building_score"] = 0.0

    time_col = _find_first_existing(df, COMMON_TIME_COLUMNS)
    chainage_col = _find_first_existing(df, COMMON_CHAINAGE_COLUMNS)
    state_col = _find_first_existing(df, COMMON_STATE_COLUMNS)
    speed_col = _find_first_existing(df, COMMON_SPEED_COLUMNS)

    if not time_col or not chainage_col:
        return df

    work = df.copy()
    work["__time"] = pd.to_datetime(work[time_col], errors="coerce")
    work["__chainage"] = pd.to_numeric(work[chainage_col], errors="coerce")
    if state_col:
        work["__state"] = pd.to_numeric(work[state_col], errors="coerce")
    if speed_col:
        work["__speed"] = pd.to_numeric(work[speed_col], errors="coerce")

    work = work.dropna(subset=["__time", "__chainage"]).sort_values("__time").copy()
    if work.empty:
        return df

    stop_mask = pd.Series(False, index=work.index)
    if "__state" in work.columns:
        stop_mask |= work["__state"].fillna(-1) == 0
    if "__speed" in work.columns:
        stop_mask |= work["__speed"].fillna(0).abs() <= low_speed_threshold
    if not bool(stop_mask.any()):
        return df

    work["__stop_mask"] = stop_mask.astype(bool)
    work["__group"] = (work["__stop_mask"] != work["__stop_mask"].shift()).cumsum()

    segments = []
    for _, seg in work.groupby("__group", sort=False):
        if not bool(seg["__stop_mask"].iloc[0]):
            continue
        start_time = seg["__time"].iloc[0]
        end_time = seg["__time"].iloc[-1]
        duration_min = max((end_time - start_time).total_seconds() / 60.0, 0.0)
        center_chainage = float(seg["__chainage"].median())
        drift_m = float(seg["__chainage"].max() - seg["__chainage"].min())
        prev_row = work.loc[work["__time"] < start_time].tail(1)
        next_row = work.loc[work["__time"] > end_time].head(1)
        prev_work = _is_work_like_row(prev_row, low_speed_threshold)
        next_work = _is_work_like_row(next_row, low_speed_threshold)
        segments.append(
            {
                "index": len(segments),
                "rows": seg.index.tolist(),
                "duration_min": duration_min,
                "center_chainage": center_chainage,
                "drift_m": drift_m,
                "prev_work": prev_work,
                "next_work": next_work,
            }
        )

    if not segments:
        return df

    centers = [segment["center_chainage"] for segment in segments]
    for pos, segment in enumerate(segments):
        periodic_score = _ring_periodicity_score(
            centers=centers,
            position=pos,
            ring_lengths=ring_lengths,
            tolerance_m=tolerance_m,
        )
        duration_score = 1.0 if min_duration_min <= segment["duration_min"] <= max_duration_min else 0.0
        drift_score = 1.0 if segment["drift_m"] <= max_stop_drift_m else 0.0
        neighbor_score = 1.0 if segment["prev_work"] and segment["next_work"] else 0.5 if (segment["prev_work"] or segment["next_work"]) else 0.0
        confidence = (
            0.45 * periodic_score
            + 0.25 * duration_score
            + 0.15 * drift_score
            + 0.15 * neighbor_score
        )
        if periodic_score > 0 and confidence >= 0.70:
            df.loc[segment["rows"], "routine_ring_building_candidate"] = 1.0
            df.loc[segment["rows"], "routine_ring_building_score"] = confidence

    return df


def load_and_process(source):
    """
    source: csv路径 或 DataFrame

    Returns operation-mode segments using the canonical operation_mode fields.
    Duration is corrected with the median sample interval, so one-row segments
    are not silently counted as 0 seconds when the PLC sampling interval exists.
    """
    df = annotate_operation_mode(source)

    if "运行时间-time" not in df.columns:
        raise ValueError("缺少时间列：运行时间-time")

    if df.empty:
        return []

    sample_interval_sec = infer_sample_interval_sec(df)
    df["group"] = (df["operation_mode_code"] != df["operation_mode_code"].shift()).cumsum()

    segments_df = df.groupby("group").agg(
        start_time=("运行时间-time", "first"),
        end_time=("运行时间-time", "last"),
        condition_code=("operation_mode_code", "first"),
        condition_name=("operation_mode", "first"),
        sample_count=("operation_mode_code", "count"),
    ).reset_index(drop=True)

    segments = []
    for _, row in segments_df.iterrows():
        raw_duration = (row["end_time"] - row["start_time"]).total_seconds()
        # Add one sample interval to represent the terminal sample. This keeps
        # old behavior when interval cannot be inferred.
        duration_sec = max(float(raw_duration), 0.0)
        if sample_interval_sec > 0:
            duration_sec += float(sample_interval_sec)
        seg = {
            "start": row["start_time"],
            "end": row["end_time"],
            "state": row["condition_name"],
            "state_code": int(row["condition_code"]),
            "operation_mode": row["condition_name"],
            "operation_mode_code": int(row["condition_code"]),
            "operation_mode_cn": _condition_code_to_cn(int(row["condition_code"])),
            "duration_sec": duration_sec,
            "raw_duration_sec": max(float(raw_duration), 0.0),
            "sample_count": int(row["sample_count"]),
            "sample_interval_sec": float(sample_interval_sec),
        }
        segments.append(seg)

    return segments


def segments_to_text(segments):
    """Handle segments to text."""
    if not segments:
        return "未识别到有效工况段。"

    lines = []
    for s in segments:
        start = s["start"].strftime("%Y-%m-%d %H:%M:%S")
        end = s["end"].strftime("%Y-%m-%d %H:%M:%S")

        dur = s["duration_sec"]
        dur_str = f"{int(dur)} 秒" if dur < 60 else f"{dur / 60:.1f} 分钟"

        state_cn = _condition_code_to_cn(s["state_code"])
        lines.append(f"在 {start} 到 {end} 期间，TBM 处于{state_cn}状态，持续 {dur_str}。")

    return "\n".join(lines)


def compute_stats(segments):
    """Compute stats."""
    stop = [x for x in segments if x["state"] == "stop"]
    transition = [x for x in segments if x["state"] == "transition"]
    work = [x for x in segments if x["state"] == "work"]
    abnormal = [x for x in segments if x["state"] == "abnormal"]

    def total(xs):
        """Handle total."""
        return sum(x["duration_sec"] for x in xs)

    def longest(xs):
        """Handle longest."""
        return max(xs, key=lambda x: x["duration_sec"]) if xs else None

    return {
        "stop_count": len(stop),
        "transition_count": len(transition),
        "work_count": len(work),
        "abnormal_count": len(abnormal),
        "stop_total_min": total(stop) / 60,
        "transition_total_min": total(transition) / 60,
        "work_total_min": total(work) / 60,
        "abnormal_total_min": total(abnormal) / 60,
        "longest_stop": longest(stop),
        "longest_transition": longest(transition),
        "longest_work": longest(work),
        "longest_abnormal": longest(abnormal),
        "short_stops": [x for x in stop if x["duration_sec"] < 60],
        "short_transitions": [x for x in transition if x["duration_sec"] < 60],
        "short_works": [x for x in work if x["duration_sec"] < 60],
        "short_abnormals": [x for x in abnormal if x["duration_sec"] < 60],
    }


def _find_first_existing(df: pd.DataFrame, candidates):
    """Pick the first matching column from a list of aliases."""
    lower_map = {str(col).strip().lower(): col for col in df.columns}
    for candidate in candidates:
        key = candidate.strip().lower()
        if key in lower_map:
            return lower_map[key]
    for candidate in candidates:
        key = candidate.strip().lower()
        for col in df.columns:
            if key and key in str(col).strip().lower():
                return col
    return None


def _is_work_like_row(rows: pd.DataFrame, low_speed_threshold: float) -> bool:
    """Check whether the surrounding sample looks like active excavation."""
    if rows is None or rows.empty:
        return False
    row = rows.iloc[0]
    state = row.get("__state")
    speed = row.get("__speed")
    if pd.notna(state) and float(state) != 0:
        return True
    if pd.notna(speed) and abs(float(speed)) > low_speed_threshold:
        return True
    return False


def _ring_periodicity_score(centers, position, ring_lengths, tolerance_m):
    """Score whether one stop center follows likely ring-length periodicity."""
    distances = []
    if position > 0:
        distances.append(abs(float(centers[position]) - float(centers[position - 1])))
    if position < len(centers) - 1:
        distances.append(abs(float(centers[position + 1]) - float(centers[position])))
    if not distances:
        return 0.0

    best = 0.0
    for distance in distances:
        for ring_length in ring_lengths:
            gap = abs(distance - float(ring_length))
            if gap <= tolerance_m:
                best = max(best, 1.0 - gap / max(tolerance_m, 1e-6))
    return float(best)


def stats_to_text(stats):
    """Handle stats to text."""
    def fmt_seg(s):
        """Handle fmt seg."""
        if not s:
            return "无"
        start = s["start"].strftime("%H:%M:%S")
        end = s["end"].strftime("%H:%M:%S")
        return f"{start}~{end}（约 {s['duration_sec'] / 60:.1f} 分钟）"

    return f"""
停机段数量：{stats['stop_count']}
启动/过渡段数量：{stats['transition_count']}
稳定掘进段数量：{stats['work_count']}
异常扭矩段数量：{stats['abnormal_count']}

总停机时长：{stats['stop_total_min']:.1f} 分钟
总启动/过渡时长：{stats['transition_total_min']:.1f} 分钟
总稳定掘进时长：{stats['work_total_min']:.1f} 分钟
总异常扭矩时长：{stats['abnormal_total_min']:.1f} 分钟

最长停机：{fmt_seg(stats['longest_stop'])}
最长启动/过渡：{fmt_seg(stats['longest_transition'])}
最长稳定掘进：{fmt_seg(stats['longest_work'])}
最长异常扭矩：{fmt_seg(stats['longest_abnormal'])}

短停机（<60s）：{len(stats['short_stops'])} 段
短启动/过渡（<60s）：{len(stats['short_transitions'])} 段
短稳定掘进（<60s）：{len(stats['short_works'])} 段
短异常扭矩（<60s）：{len(stats['short_abnormals'])} 段
""".strip()