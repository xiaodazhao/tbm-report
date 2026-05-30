# gas_analysis.py
import pandas as pd
import numpy as np

# =========================
# 1. 当前真实存在的气体字段
# =========================
GAS_COLUMNS = [
    "CO2检测",
    "H2S检测",
    "SO2检测",
    "NO2检测",
    "NO检测",
    "CH4检测"
]

# =========================
# 2. 阈值设置
# =========================
# 注意：
# 这些阈值是否合理，取决于你的字段单位是不是浓度值
# 如果这些字段其实是 0/1 报警量，那后面需要改成“报警事件分析”
THRESHOLDS = {
    "CO2检测": 0.5,   # %
    "H2S检测": 10,    # ppm
    "SO2检测": 2,     # ppm
    "NO2检测": 5,     # ppm（这里先给一个占位值，可后续再改）
    "NO检测": 20,     # ppm
    "CH4检测": 0.5    # %
}

GAS_UNIT_ASSUMPTIONS = {
    "CO2检测": "%",
    "H2S检测": "ppm",
    "SO2检测": "ppm",
    "NO2检测": "ppm",
    "NO检测": "ppm",
    "CH4检测": "%",
}

GAS_ANALYSIS_SCHEMA_VERSION = "gas_analysis_v2"


def _safe_float(value):
    """Return a finite float or None."""
    try:
        number = float(value)
    except Exception:
        return None
    return number if np.isfinite(number) else None


def _clean_json_value(value):
    """Recursively clean values for JSON serialization."""
    if isinstance(value, dict):
        return {str(key): _clean_json_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_clean_json_value(item) for item in value]
    if isinstance(value, tuple):
        return [_clean_json_value(item) for item in value]
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if pd.isna(value):
        return None
    if hasattr(value, "item"):
        try:
            return _clean_json_value(value.item())
        except Exception:
            pass
    return value

# =========================
# 3. 单一 DataFrame 的气体统计
# =========================
def _compute_gas_stats_single(df: pd.DataFrame):
    """
    对一个 DataFrame 计算气体统计（不关心工况）
    """
    results = {}

    for gas in GAS_COLUMNS:
        if gas not in df.columns:
            continue

        series = pd.to_numeric(df[gas], errors="coerce").dropna()
        if series.empty:
            continue

        stats = {
            "mean": float(series.mean()),
            "max": float(series.max()),
            "min": float(series.min()),
        }

        threshold = THRESHOLDS.get(gas)
        if threshold is not None:
            exceed_mask = series > threshold

            df_tmp = df.loc[series.index].copy()
            df_tmp["exceed"] = exceed_mask.astype(int)
            df_tmp["group"] = (df_tmp["exceed"] != df_tmp["exceed"].shift()).cumsum()

            segments = []
            if "运行时间-time" in df_tmp.columns:
                for _, part in df_tmp.groupby("group"):
                    if part["exceed"].iloc[0] == 1:
                        start = part["运行时间-time"].iloc[0]
                        end = part["运行时间-time"].iloc[-1]
                        segments.append({
                            "start": start,
                            "end": end,
                            "duration_sec": (end - start).total_seconds()
                        })

            stats["exceed_event_count"] = len(segments)
            stats["exceed_segments"] = segments
            stats["threshold"] = threshold
            stats["threshold_basis"] = "configured_concentration_threshold"
            stats["unit_assumption"] = GAS_UNIT_ASSUMPTIONS.get(gas)

        results[gas] = stats

    return results


# =========================
# 4. 掘进 / 停机划分
# =========================
def _split_work_stop(df: pd.DataFrame):
    """
    Split work/stop using canonical operation_mode when available.
    Fallbacks preserve the old 掘进状态 / 贯入度 behavior.
    """
    if "is_working" in df.columns or "is_stopped" in df.columns:
        work_mask = df.get("is_working", pd.Series(False, index=df.index)).fillna(False).astype(bool)
        stop_mask = df.get("is_stopped", pd.Series(False, index=df.index)).fillna(False).astype(bool)
        return df[work_mask].copy(), df[stop_mask].copy()

    if "operation_mode" in df.columns:
        mode = df["operation_mode"].astype(str)
        return df[mode.eq("work")].copy(), df[mode.eq("stop")].copy()

    try:
        from analysis.dataprocess import annotate_operation_mode
        annotated = annotate_operation_mode(df)
        if "is_working" in annotated.columns:
            return annotated[annotated["is_working"]].copy(), annotated[annotated["is_stopped"]].copy()
    except Exception:
        pass

    if "掘进状态" in df.columns:
        df_work = df[df["掘进状态"] != 0]
        df_stop = df[df["掘进状态"] == 0]
        return df_work, df_stop

    if "贯入度" in df.columns:
        df_work = df[df["贯入度"] > 0]
        df_stop = df[df["贯入度"] <= 0]
        return df_work, df_stop

    return pd.DataFrame(columns=df.columns), pd.DataFrame(columns=df.columns)


# =========================
# 5. 主入口：状态感知气体分析
# =========================
def compute_gas_stats(df: pd.DataFrame, df_state: pd.DataFrame = None):
    """
    返回：
    - 全天气体统计
    - 掘进期气体统计
    - 停机期气体统计
    - （可选）施工状态级气体统计
    """
    df = df.copy()

    if "运行时间-time" in df.columns:
        df["运行时间-time"] = pd.to_datetime(df["运行时间-time"], errors="coerce")

    results = {"schema_version": GAS_ANALYSIS_SCHEMA_VERSION}

    # ===== 5.1 全天 =====
    results["all"] = _compute_gas_stats_single(df)

    # ===== 5.2 掘进 / 停机 =====
    df_work, df_stop = _split_work_stop(df)
    results["work"] = _compute_gas_stats_single(df_work) if not df_work.empty else {}
    results["stop"] = _compute_gas_stats_single(df_stop) if not df_stop.empty else {}

    # ===== 5.3 施工状态级（可选）=====
    if df_state is not None:
        state_col = None
        if "state_id" in df_state.columns:
            state_col = "state_id"
        elif "state" in df_state.columns:
            state_col = "state"

        if state_col is not None:
            state_results = {}
            for state in sorted(df_state[state_col].dropna().unique()):
                df_s = df_state[df_state[state_col] == state]
                if not df_s.empty:
                    state_results[int(state)] = _compute_gas_stats_single(df_s)
            results["by_state"] = state_results

    return results


# =========================
# 6. 文本化（给 LLM 用）
# =========================
def gas_stats_to_text(stats: dict):
    """
    默认输出：全天 + 掘进期 + 停机期 + 可选状态级
    """
    lines = []

    def render(title, s):
        """Handle render."""
        if not s:
            return

        lines.append(f"\n【{title}】")
        for gas, g in s.items():
            line = (
                f"{gas}: 平均 {g['mean']:.3f}, "
                f"最大 {g['max']:.3f}, "
                f"最小 {g['min']:.3f}"
            )

            if "threshold" in g:
                line += f"，阈值 {g['threshold']}"

            if "exceed_event_count" in g:
                line += f"，超过当前配置阈值的记录段 {g['exceed_event_count']} 次"

            lines.append(line)

            if g.get("exceed_event_count", 0) > 0:
                for seg in g["exceed_segments"]:
                    if pd.notna(seg["start"]) and pd.notna(seg["end"]):
                        lines.append(
                            f"  - {seg['start'].strftime('%H:%M:%S')}~"
                            f"{seg['end'].strftime('%H:%M:%S')}（{seg['duration_sec']:.1f}s）"
                        )

    render("全天气体统计", stats.get("all"))
    render("掘进期气体统计", stats.get("work"))
    render("停机期气体统计", stats.get("stop"))

    by_state = stats.get("by_state", {})
    if by_state:
        for state, s in by_state.items():
            render(f"施工状态 {state} 气体统计", s)

    return "\n".join(lines)


def build_gas_context(
    gas_stats: dict,
    quality_report: dict | None = None,
) -> dict:
    """Build a structured gas context while keeping legacy gas_text/gas_stats intact."""
    warnings: list[str] = []
    quality_report = quality_report if isinstance(quality_report, dict) else {}
    diagnostics = quality_report.get("gas_field_diagnostics", {}) if isinstance(quality_report, dict) else {}
    gas_all = gas_stats.get("all", {}) if isinstance(gas_stats, dict) else {}

    gas_summaries = []
    exceed_gases: list[str] = []
    exceed_event_count_total = 0

    for gas_name in GAS_COLUMNS:
        stats_item = gas_all.get(gas_name, {}) if isinstance(gas_all, dict) else {}
        diag = diagnostics.get(gas_name, {}) if isinstance(diagnostics, dict) else {}
        field_type_guess = diag.get("value_type_guess", "unknown")
        unit_assumption = diag.get("unit_assumption") or stats_item.get("unit_assumption")
        exceed_event_count = int(stats_item.get("exceed_event_count", 0) or 0)
        threshold = _safe_float(stats_item.get("threshold"))
        exceed_segments_preview = []

        if field_type_guess == "alarm_flag":
            interpretation_caution = "该字段疑似报警量，应按报警事件解释，不宜直接作为浓度值。"
            threshold = None
            exceed_event_count = 0
            if diag.get("warning"):
                warnings.append(f"{gas_name}: {diag.get('warning')}")
        elif field_type_guess == "unknown":
            interpretation_caution = "气体字段单位或含义未确认，需谨慎解释。"
            threshold = None
            exceed_event_count = 0
            if diag.get("warning"):
                warnings.append(f"{gas_name}: {diag.get('warning')}")
        else:
            interpretation_caution = "该字段按浓度值解释，但仍需结合原始数据字典确认单位。"
            if exceed_event_count > 0:
                exceed_gases.append(gas_name)
                exceed_event_count_total += exceed_event_count
                for seg in (stats_item.get("exceed_segments") or [])[:3]:
                    exceed_segments_preview.append(
                        {
                            "start": seg.get("start").strftime("%Y-%m-%d %H:%M:%S") if hasattr(seg.get("start"), "strftime") else str(seg.get("start")) if seg.get("start") else None,
                            "end": seg.get("end").strftime("%Y-%m-%d %H:%M:%S") if hasattr(seg.get("end"), "strftime") else str(seg.get("end")) if seg.get("end") else None,
                            "duration_sec": _safe_float(seg.get("duration_sec")),
                        }
                    )

        gas_summaries.append(
            {
                "gas": gas_name,
                "canonical_gas": gas_name.replace("检测", ""),
                "field_type_guess": field_type_guess,
                "unit_assumption": unit_assumption,
                "mean": _safe_float(stats_item.get("mean")),
                "max": _safe_float(stats_item.get("max")),
                "min": _safe_float(stats_item.get("min")),
                "threshold": threshold if field_type_guess == "concentration" else None,
                "exceed_event_count": exceed_event_count if field_type_guess == "concentration" else 0,
                "exceed_segments_preview": exceed_segments_preview,
                "interpretation_caution": interpretation_caution,
            }
        )

    return _clean_json_value(
        {
            "schema_version": "gas_context_v1",
            "gas_field_diagnostics": diagnostics,
            "exceed_summary": {
                "has_exceedance": bool(exceed_gases),
                "exceed_gases": exceed_gases,
                "exceed_event_count_total": exceed_event_count_total,
            },
            "gas_summaries": gas_summaries,
            "warnings": warnings,
        }
    )
