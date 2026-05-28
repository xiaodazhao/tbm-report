import json
import pandas as pd


def _first_existing(df: pd.DataFrame, candidates):
    for col in candidates:
        if col in df.columns:
            return col
    return None


def _value_counts(df: pd.DataFrame, col: str | None, top_n: int | None = None):
    if not col or col not in df.columns:
        return {}
    counts = df[col].value_counts(dropna=False)
    if top_n:
        counts = counts.head(top_n)
    return counts.to_dict()


def summarize_geology_record_level(df: pd.DataFrame):
    """Generate record-level geology summary for auxiliary interpretation."""
    source_col = _first_existing(df, ["active_report_source_count", "active_source_count"])
    if source_col is None:
        return {"has_geology": False, "summary_text": "未进行地质融合分析。"}

    coverage_col = _first_existing(df, ["geo_coverage_status", "coverage"])
    hazard_col = _first_existing(df, ["geo_hazard_summary", "hazard"])
    evidence_col = _first_existing(df, ["matched_evidence_record_count", "evidence_count"])
    support_col = _first_existing(df, ["evidence_support_weight_sum", "weighted_evidence_strength"])
    uncertainty_col = _first_existing(df, ["geo_fusion_uncertainty", "uncertainty"])

    result = {
        "has_geology": True,
        "sample_count": int(len(df)),
        "coverage_counts": _value_counts(df, coverage_col),
        "hazard_counts": _value_counts(df, hazard_col, top_n=5),
        "fusion_uncertainty_counts": _value_counts(df, uncertainty_col),
        "max_active_report_source_count": int(pd.to_numeric(df[source_col], errors="coerce").max()) if source_col else None,
        "mean_active_report_source_count": float(pd.to_numeric(df[source_col], errors="coerce").mean()) if source_col else None,
    }
    if evidence_col:
        result["max_matched_evidence_record_count"] = int(pd.to_numeric(df[evidence_col], errors="coerce").max())
        result["mean_matched_evidence_record_count"] = float(pd.to_numeric(df[evidence_col], errors="coerce").mean())
    if support_col:
        result["max_evidence_support_weight_sum"] = float(pd.to_numeric(df[support_col], errors="coerce").max())
        result["mean_evidence_support_weight_sum"] = float(pd.to_numeric(df[support_col], errors="coerce").mean())

    high_source_df = df[pd.to_numeric(df[source_col], errors="coerce").fillna(0) >= 4]
    result["high_source_support_record_count"] = int(len(high_source_df))

    # deprecated aliases for compatibility
    result["max_attention"] = result["max_active_report_source_count"]
    result["mean_attention"] = result["mean_active_report_source_count"]
    result["high_attention_count"] = result["high_source_support_record_count"]
    result["risk_counts"] = _value_counts(df, _first_existing(df, ["risk", "source_risk_level"]))

    lines = [f"本时段共匹配到 {len(df)} 条带地质融合字段的 PLC 记录。"]
    if result["coverage_counts"]:
        lines.append("地质证据覆盖情况：" + ", ".join([f"{k}={v}" for k, v in result["coverage_counts"].items()]) + "。")
    if result["max_active_report_source_count"] is not None:
        lines.append(
            f"报告-来源组合最大命中数为 {result['max_active_report_source_count']}，"
            f"平均命中数为 {result['mean_active_report_source_count']:.2f}。"
        )
    if result["high_source_support_record_count"] > 0:
        lines.append(f"报告-来源组合数≥4 的高证据支持记录共 {result['high_source_support_record_count']} 条。")
    if result["hazard_counts"]:
        top_hazard_text = "、".join([f"{k}({v})" for k, v in result["hazard_counts"].items()])
        lines.append(f"主要地质关注标签为：{top_hazard_text}。")
    if result["fusion_uncertainty_counts"]:
        lines.append("融合不确定性分布：" + ", ".join([f"{k}={v}" for k, v in result["fusion_uncertainty_counts"].items()]) + "。")

    result["summary_text"] = "\n".join(lines)
    return result


def summarize_geology_segment_level(segment_df: pd.DataFrame):
    """Generate segment-level geology summary for report generation."""
    if segment_df is None or len(segment_df) == 0:
        return {"has_geology": False, "summary_text": "未形成区段级地质融合分析结果。"}

    source_col = _first_existing(segment_df, ["seg_active_report_source_count_max", "active_source_count_max"])
    evidence_col = _first_existing(segment_df, ["seg_matched_evidence_record_count_max", "evidence_count_max"])
    hazard_col = _first_existing(segment_df, ["seg_geo_hazard_mode", "hazard_mode"])
    grade_col = _first_existing(segment_df, ["seg_geo_grade_mode", "fused_grade_mode"])
    interp_col = _first_existing(segment_df, ["segment_response_interpretation", "interpretation"])
    attention_col = _first_existing(segment_df, ["geo_attention_hint_level"])

    result = {
        "has_geology": True,
        "segment_count": int(len(segment_df)),
        "geo_hazard_dist": _value_counts(segment_df, hazard_col),
        "geo_grade_dist": _value_counts(segment_df, grade_col),
        "geo_attention_hint_dist": _value_counts(segment_df, attention_col),
        "segment_response_interpretation_dist": _value_counts(segment_df, interp_col),
    }

    multi_source_df = segment_df[pd.to_numeric(segment_df[source_col], errors="coerce").fillna(0) >= 3] if source_col else pd.DataFrame()
    result["multi_report_source_segment_count"] = int(len(multi_source_df))

    if "geo_attention_hint_score" in segment_df.columns:
        high_geo_df = segment_df[pd.to_numeric(segment_df["geo_attention_hint_score"], errors="coerce").fillna(0) >= 0.70]
    elif source_col:
        high_geo_df = segment_df[pd.to_numeric(segment_df[source_col], errors="coerce").fillna(0) >= 4]
    else:
        high_geo_df = pd.DataFrame()
    result["high_geo_attention_segment_count"] = int(len(high_geo_df))

    if "GRCI" in segment_df.columns:
        high_coupling_df = segment_df[pd.to_numeric(segment_df["GRCI"], errors="coerce").fillna(0) >= 0.55]
        result["high_coupling_segment_count"] = int(len(high_coupling_df))
    else:
        result["high_coupling_segment_count"] = 0

    # deprecated aliases for compatibility
    result["multi_source_segment_count"] = result["multi_report_source_segment_count"]
    result["high_risk_segment_count"] = result["high_geo_attention_segment_count"]
    result["risk_dist"] = _value_counts(segment_df, _first_existing(segment_df, ["risk_mode", "seg_source_risk_level_mode"]))
    result["interpretation_dist"] = result["segment_response_interpretation_dist"]

    lines = [f"本次区段级分析共识别 {len(segment_df)} 个已开挖施工区段。"]
    if result["geo_hazard_dist"]:
        lines.append("区段地质关注标签分布为：" + ", ".join([f"{k}={v}" for k, v in result["geo_hazard_dist"].items()]) + "。")
    if result["multi_report_source_segment_count"] > 0:
        lines.append(f"报告-来源组合数≥3 的多源证据支持区段共 {result['multi_report_source_segment_count']} 个。")
    if result["high_geo_attention_segment_count"] > 0:
        lines.append(f"高地质证据关注提示区段共 {result['high_geo_attention_segment_count']} 个。")
    if result["high_coupling_segment_count"] > 0:
        lines.append(f"GRCI≥0.55 的地质-施工响应耦合高关注区段共 {result['high_coupling_segment_count']} 个。")
    if result["segment_response_interpretation_dist"]:
        lines.append("施工响应解释分布：" + ", ".join([f"{k}={v}" for k, v in result["segment_response_interpretation_dist"].items()]) + "。")

    label_col = _first_existing(segment_df, ["segment_label_dk", "segment"])
    if label_col and interp_col:
        typical = segment_df.head(3)
        typical_lines = []
        for _, row in typical.iterrows():
            seg = row.get(label_col, "")
            interp = row.get(interp_col, "")
            geo = row.get(hazard_col, "") if hazard_col else ""
            typical_lines.append(f"{seg}（{geo}，{interp}）")
        if typical_lines:
            lines.append("典型区段包括：" + "；".join(typical_lines) + "。")

    result["summary_text"] = "\n".join(lines)
    return result


def geology_summary_to_text(geo_summary: dict):
    """Convert geology summary dict to text."""
    if not geo_summary or not geo_summary.get("has_geology", False):
        return "本时段未进行地质融合分析。"
    return geo_summary.get("summary_text", "本时段已完成地质融合分析。")


def _safe_load_attrs(x):
    """Safely load serialized evidence attributes."""
    try:
        obj = json.loads(x)
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


def _mid_chainage(row: pd.Series) -> float | None:
    """Return the midpoint chainage for one evidence row."""
    start = pd.to_numeric(row.get("start_num"), errors="coerce")
    end = pd.to_numeric(row.get("end_num"), errors="coerce")
    if pd.notna(start) and pd.notna(end):
        return float((start + end) / 2.0)
    if pd.notna(start):
        return float(start)
    if pd.notna(end):
        return float(end)
    return None


def build_face_geo_text(
    evidence_df: pd.DataFrame,
    current_chainage: float | None = None,
    tolerance_m: float = 20.0,
) -> str:
    """
    Build the current face geology text from on-site sketch evidence only.

    Rules:
    - Only use `sketch` + `point` evidence as current face reveal.
    - If a current chainage is provided, prefer the nearest sketch point.
    - If the nearest sketch point is too far away, do not replace the current face
      with forecast information. Explicitly state that direct current-face reveal is unavailable.
    """
    if evidence_df is None or len(evidence_df) == 0:
        return "当前掌子面缺少可用的现场素描或揭示资料，不能直接依据超前预报替代当前掌子面情况。"

    if "source_type" not in evidence_df.columns or "source_level" not in evidence_df.columns:
        return "当前掌子面缺少可用的现场素描或揭示资料，不能直接依据超前预报替代当前掌子面情况。"

    sketch_df = evidence_df[
        (evidence_df["source_type"] == "sketch") &
        (evidence_df["source_level"] == "point")
    ].copy()

    if sketch_df.empty:
        return "当前掌子面缺少现场素描点位揭示，当前掌子面地质情况不能直接由超前预报替代。"

    if current_chainage is not None:
        sketch_df["__mid_chainage"] = sketch_df.apply(_mid_chainage, axis=1)
        sketch_df["__distance_to_face"] = (
            pd.to_numeric(sketch_df["__mid_chainage"], errors="coerce") - float(current_chainage)
        ).abs()
        sketch_df = sketch_df.sort_values("__distance_to_face")
        row = sketch_df.iloc[0]
        distance = pd.to_numeric(row.get("__distance_to_face"), errors="coerce")
        if pd.notna(distance) and float(distance) > float(tolerance_m):
            return (
                f"当前掌子面里程附近未找到与掌子面位置相匹配的现场素描揭示"
                f"（最近素描点距当前掌子面约 {float(distance):.1f} m），"
                "因此当前掌子面地质情况不能直接依据超前预报或远距离历史素描替代。"
            )
    else:
        row = sketch_df.iloc[-1]

    attrs = _safe_load_attrs(row.get("attrs_json", ""))
    parts = []

    grade = attrs.get("support_grade") or attrs.get("rock_grade")
    if grade:
        parts.append(f"围岩等级为{grade}级")

    lithology = attrs.get("lithology")
    if lithology:
        parts.append(f"岩性为{lithology}")

    weathering = attrs.get("weathering")
    if weathering:
        parts.append(f"{weathering}")

    rock_uniformity = attrs.get("rock_uniformity")
    if rock_uniformity:
        parts.append(f"岩质{rock_uniformity}")

    joint_degree = attrs.get("joint_degree")
    if joint_degree:
        parts.append(f"节理裂隙{joint_degree}")

    rock_mass_state = attrs.get("rock_mass_state")
    if rock_mass_state:
        parts.append(f"岩体{rock_mass_state}")

    stability = attrs.get("stability")
    if stability:
        parts.append(f"整体稳定性{stability}")

    water_type = attrs.get("water_type")
    water_flag = attrs.get("water_flag", 0)
    if water_type:
        parts.append(f"掌子面存在{water_type}")
    elif water_flag:
        parts.append("掌子面存在出水现象")

    collapse_flag = attrs.get("collapse_flag", 0)
    if collapse_flag:
        parts.append("局部存在掉块现象")

    if not parts:
        return "当前掌子面已有现场素描记录，但未提取到明确的掌子面地质特征。"

    distance = None
    if current_chainage is not None and "__distance_to_face" in row and pd.notna(row["__distance_to_face"]):
        distance = float(row["__distance_to_face"])

    if distance is None:
        prefix = "现场素描揭示"
    elif distance <= 0.5:
        prefix = f"与当前掌子面里程基本一致的现场素描揭示（距当前掌子面约 {distance:.1f} m）"
    else:
        prefix = f"距当前掌子面最近的现场素描点揭示（距当前掌子面约 {distance:.1f} m）"

    return (
        prefix
        + "： "
        + "，".join(parts)
        + "。该描述来源于现场素描点位记录，不能简单等同为当前掌子面实时直接观察结论。"
    )