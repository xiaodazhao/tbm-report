import json
import pandas as pd

from utils.chainage_utils import format_chainage_dk
try:
    from geology.fusion import normalize_report_id
except Exception:  # pragma: no cover
    def normalize_report_id(report_id):
        return "" if pd.isna(report_id) else str(report_id).strip()


RISK_SCORE_MAP = {
    "low": 1,
    "medium": 2,
    "high": 3,
}


def _safe_load_attrs(x):
    """Safely load serialized evidence attributes."""
    try:
        if pd.isna(x):
            return {}
        obj = json.loads(x)
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


def _format_dk(chainage):
    if pd.isna(chainage):
        return "未知里程"
    return format_chainage_dk(chainage)


def _dedup_preserve_order(items):
    out = []
    seen = set()
    for item in items:
        if item in [None, ""]:
            continue
        text = str(item)
        if text not in seen:
            out.append(text)
            seen.add(text)
    return out


def _normalize_hazard(attrs):
    """Normalize hazards from evidence attributes."""
    hazards = []
    water_type = attrs.get("water_type")
    if water_type:
        hazards.append(str(water_type))
    elif attrs.get("water_flag"):
        hazards.append("出水")
    if attrs.get("collapse_flag"):
        hazards.append("掉块")
    if attrs.get("deformation_flag"):
        hazards.append("变形")
    tags = attrs.get("risk_tags", [])
    if isinstance(tags, list):
        hazards.extend(str(tag) for tag in tags if tag)
    return _dedup_preserve_order(hazards)


def _source_key(row) -> tuple[str, str]:
    source_type = str(row.get("source_type", "")).strip()
    report_id = normalize_report_id(row.get("report_id", ""))
    return source_type, report_id


def _summarize_forward_evidence(forward_df):
    """Summarize forward evidence records inside the look-ahead window."""
    if forward_df is None or forward_df.empty:
        return {
            "forward_evidence_count": 0,
            "forward_high_source_risk_evidence_count": 0,
            "forward_report_source_count": 0,
            "forward_source_type_count": 0,
            "forward_source_risk_level_dist": {},
            "forward_main_hazard_tags": [],
            "forward_source_types": [],
            "covered_start": None,
            "covered_end": None,
            # deprecated aliases
            "forward_segment_count": 0,
            "high_risk_count": 0,
            "multi_source_count": 0,
            "risk_level_dist": {},
            "main_hazards": [],
            "source_types": [],
        }

    temp = forward_df.copy()
    temp["attrs_obj"] = temp["attrs_json"].apply(_safe_load_attrs) if "attrs_json" in temp.columns else [{}] * len(temp)
    temp["source_risk_level"] = temp["attrs_obj"].apply(lambda x: x.get("source_risk_level") or x.get("risk_level", "low"))
    temp["source_risk_score"] = temp["source_risk_level"].map(RISK_SCORE_MAP).fillna(1)
    temp["forward_hazard_tags"] = temp["attrs_obj"].apply(_normalize_hazard)

    forward_evidence_count = int(len(temp))
    high_count = int((temp["source_risk_score"] >= 3).sum())
    source_types = sorted(set(temp.get("source_type", pd.Series(dtype=str)).astype(str).dropna().tolist()))
    source_keys = {_source_key(row) for _, row in temp.iterrows()}
    source_keys = {key for key in source_keys if key[0] or key[1]}

    hazard_counter = {}
    for hazards in temp["forward_hazard_tags"]:
        for hazard in hazards:
            hazard_counter[hazard] = hazard_counter.get(hazard, 0) + 1
    main_hazards = [key for key, _ in sorted(hazard_counter.items(), key=lambda x: x[1], reverse=True)]
    risk_dist = temp["source_risk_level"].value_counts(dropna=False).to_dict()

    stat = {
        "forward_evidence_count": forward_evidence_count,
        "forward_high_source_risk_evidence_count": high_count,
        "forward_report_source_count": int(len(source_keys)),
        "forward_source_type_count": int(len(source_types)),
        "forward_source_risk_level_dist": risk_dist,
        "forward_main_hazard_tags": main_hazards,
        "forward_source_types": source_types,
        "covered_start": float(temp["start_num"].min()) if "start_num" in temp.columns and temp["start_num"].notna().any() else None,
        "covered_end": float(temp["end_num"].max()) if "end_num" in temp.columns and temp["end_num"].notna().any() else None,
    }
    # deprecated aliases for compatibility
    stat.update({
        "forward_segment_count": stat["forward_evidence_count"],
        "high_risk_count": stat["forward_high_source_risk_evidence_count"],
        "multi_source_count": stat["forward_report_source_count"],
        "risk_level_dist": stat["forward_source_risk_level_dist"],
        "main_hazards": stat["forward_main_hazard_tags"],
        "source_types": stat["forward_source_types"],
    })
    return stat


def _ensure_chainage(df: pd.DataFrame) -> pd.DataFrame | None:
    out = df.copy()
    if "chainage" in out.columns:
        out["chainage"] = pd.to_numeric(out["chainage"], errors="coerce")
    elif "导向盾首里程" in out.columns:
        out["chainage"] = pd.to_numeric(out["导向盾首里程"], errors="coerce")
    elif "开累进尺" in out.columns:
        out["chainage"] = pd.to_numeric(out["开累进尺"], errors="coerce")
    else:
        return None
    out = out.dropna(subset=["chainage"]).copy()
    if out.empty:
        return None
    for time_col in ["运行时间-time", "time", "timestamp", "datetime"]:
        if time_col in out.columns:
            out["__time_sort"] = pd.to_datetime(out[time_col], errors="coerce")
            out = out.sort_values("__time_sort").drop(columns=["__time_sort"])
            break
    return out


def generate_forward_risk_summary(df_plc: pd.DataFrame, evidence_df: pd.DataFrame, lookahead_m=30, advance_direction: int = 1):
    """Generate structured forward-attention summary from evidence in the look-ahead window."""
    if df_plc is None or len(df_plc) == 0:
        return {"has_forward_risk": False, "message": "PLC 数据为空，无法生成前方风险提示。"}

    df = _ensure_chainage(df_plc)
    if df is None or df.empty:
        return {"has_forward_risk": False, "message": "PLC 数据中缺少可用里程字段，无法生成前方风险提示。"}

    if evidence_df is None or len(evidence_df) == 0:
        current_chainage = float(df["chainage"].iloc[-1])
        return {
            "has_forward_risk": False,
            "current_chainage": current_chainage,
            "current_chainage_dk": _format_dk(current_chainage),
            "message": "证据库为空，无法生成前方风险提示。",
        }

    current_chainage = float(df["chainage"].iloc[-1])
    direction = 1 if float(advance_direction or 1) >= 0 else -1
    raw_start = current_chainage
    raw_end = current_chainage + direction * float(lookahead_m)
    window_min = min(raw_start, raw_end)
    window_max = max(raw_start, raw_end)

    ev = evidence_df.copy()
    ev["start_num"] = pd.to_numeric(ev["start_num"], errors="coerce")
    ev["end_num"] = pd.to_numeric(ev["end_num"], errors="coerce")
    ev = ev.dropna(subset=["start_num", "end_num"]).copy()
    ev["__ev_min"] = ev[["start_num", "end_num"]].min(axis=1)
    ev["__ev_max"] = ev[["start_num", "end_num"]].max(axis=1)

    forward_df = ev[(ev["__ev_max"] >= window_min) & (ev["__ev_min"] <= window_max)].copy()
    stat = _summarize_forward_evidence(forward_df)

    evidence_count = stat["forward_evidence_count"]
    high_count = stat["forward_high_source_risk_evidence_count"]
    source_count = stat["forward_report_source_count"]

    if high_count > 0 and source_count >= 3:
        advice_level = "high"
    elif high_count > 0 or source_count >= 2:
        advice_level = "medium"
    elif evidence_count > 0:
        advice_level = "low"
    else:
        advice_level = "none"

    monitoring_focus = ["推进速度", "推力", "刀盘扭矩"]
    hazards = stat["forward_main_hazard_tags"]
    if any("水" in h for h in hazards):
        monitoring_focus.extend(["涌水量", "排水状态"])
    if any("掉块" in h or "塌" in h for h in hazards):
        monitoring_focus.extend(["掌子面稳定性", "掉块征兆"])

    support_actions = []
    if any("水" in h for h in hazards):
        support_actions.append("提前检查排水与止水准备")
    if any("掉块" in h or "塌" in h for h in hazards):
        support_actions.append("提前准备加强支护与围岩稳定控制措施")
    if not support_actions:
        support_actions.append("保持常规支护与监测准备")

    if evidence_count == 0:
        advice_text = (
            f"截至当前掘进位置 {_format_dk(current_chainage)}，前方 {lookahead_m} m 范围内未识别到明确的前方地质证据记录，"
            "建议保持常规施工监测，并继续跟踪后续地质资料更新。"
        )
    else:
        hazard_text = "、".join(hazards[:3]) if hazards else "未见明确风险类型"
        monitoring_text = "、".join(dict.fromkeys(monitoring_focus))
        support_text = "；".join(dict.fromkeys(support_actions))
        qualifier = "较高" if advice_level == "high" else ("一定" if advice_level == "medium" else "一般")
        advice_text = (
            f"截至当前掘进位置 {_format_dk(current_chainage)}，前方 {lookahead_m} m 范围内识别到 {evidence_count} 条相关地质证据记录，"
            f"其中来源内高关注证据 {high_count} 条，报告-来源组合数为 {source_count}，前方提示等级为{advice_level}。"
            f"主要关注类型为{hazard_text}，证据支持程度{qualifier}。建议重点加强 {monitoring_text} 的联动监测，并{support_text}。"
        )

    result = {
        "has_forward_risk": True,
        "current_chainage": current_chainage,
        "current_chainage_dk": _format_dk(current_chainage),
        "lookahead_m": float(lookahead_m),
        "advance_direction": direction,
        "forward_start": raw_start,
        "forward_end": raw_end,
        "forward_window_min": window_min,
        "forward_window_max": window_max,
        "forward_start_dk": _format_dk(raw_start),
        "forward_end_dk": _format_dk(raw_end),
        **stat,
        "forward_advice_level": advice_level,
        "forward_advice_text": advice_text,
        "monitoring_focus": list(dict.fromkeys(monitoring_focus)),
        "support_actions": list(dict.fromkeys(support_actions)),
        # deprecated aliases
        "advice_level": advice_level,
        "advice_text": advice_text,
    }
    return result


def forward_risk_to_text(summary: dict):
    """Convert structured forward-risk summary into report text."""
    if not summary or not summary.get("has_forward_risk", False):
        return "未形成可用的前方风险提示。"

    evidence_count = summary.get("forward_evidence_count", summary.get("forward_segment_count", 0))
    if evidence_count == 0:
        return summary.get("forward_advice_text") or summary.get("advice_text", "当前前方窗口未识别到明确的前方地质证据记录。")

    hazards = summary.get("forward_main_hazard_tags", summary.get("main_hazards", []))
    hazard_text = "、".join(hazards[:3]) if hazards else "未见明确风险类型"
    monitoring_text = "、".join(summary.get("monitoring_focus", [])) or "推进参数与现场状态"
    support_text = "；".join(summary.get("support_actions", [])) or "保持常规支护与准备"

    lines = [
        (
            f"截至当前掘进位置 {summary.get('current_chainage_dk', '未知里程')}，前方 "
            f"{int(summary.get('lookahead_m', 0))} m 范围（{summary.get('forward_start_dk', '')} ~ "
            f"{summary.get('forward_end_dk', '')}）内共识别到 {evidence_count} 条相关地质证据记录。"
        ),
        (
            f"其中来源内高关注证据 {summary.get('forward_high_source_risk_evidence_count', summary.get('high_risk_count', 0))} 条，"
            f"报告-来源组合数为 {summary.get('forward_report_source_count', summary.get('multi_source_count', 0))}，"
            f"主要关注类型表现为{hazard_text}。"
        ),
        f"建议重点加强 {monitoring_text} 的联合监测，并{support_text}。",
        summary.get("forward_advice_text", summary.get("advice_text", "建议后续施工过程中保持持续关注。")),
    ]
    return "\n".join(lines)