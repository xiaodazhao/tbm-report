"""
geology_v2.text_builder

将 geology_v2 的结构化结果转换为报告可用的短文本。

输入：
    geo_states_df:
        fuse_geo_states 输出。

    forward_profile:
        build_forward_profile 输出。

输出：
    geo_state_to_text:
        单个 cell 的简短地质状态描述。

    forward_profile_to_text:
        前方 0-10m / 10-20m / 20-30m 分段描述。

    build_geology_v2_prompt_block:
        给 LLM prompt 使用的地质 v2 文本块。

设计原则：
1. 不生成长篇大论；
2. 不把 attention_level 写成“灾害概率”；
3. 不把 has_geology_evidence=False 写成“无风险/无异常”；
4. 文风保持工程报告风格；
5. 输出用于 prompt，不直接替代最终报告。
"""

from __future__ import annotations

import math
from typing import Any, Dict, Iterable, List, Optional

import pandas as pd

from utils.chainage_utils import format_chainage_dk


# ============================================================
# 1. 基础工具
# ============================================================

ATTENTION_LEVEL_CN = {
    "none": "未形成有效关注等级",
    "low": "低关注",
    "medium": "中等关注",
    "high": "高关注",
}

UNCERTAINTY_LEVEL_CN = {
    "none": "低",
    "low": "低",
    "medium": "中",
    "high": "高",
    "unknown": "未知",
}

CONFLICT_LEVEL_CN = {
    "none": "无明显冲突",
    "low": "低",
    "medium": "中",
    "high": "高",
    "unknown": "未知",
}


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, (list, dict, tuple, set)):
        return False
    try:
        return bool(pd.isna(value))
    except Exception:
        return False


def _safe_float(value: Any, default: float = 0.0) -> float:
    if _is_missing(value):
        return float(default)
    try:
        x = float(value)
        if math.isfinite(x):
            return float(x)
    except Exception:
        pass
    return float(default)


def _safe_str(value: Any, default: str = "") -> str:
    if _is_missing(value):
        return default
    text = str(value).strip()
    return text if text else default


def _as_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple) or isinstance(value, set):
        return list(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        # 注意：这里不强行 json.loads，避免把中文列表字符串拆坏。
        return [text]
    return [value]


def _dedup_keep_order(items: Iterable[Any]) -> List[str]:
    out: List[str] = []
    seen = set()

    for item in items:
        if _is_missing(item):
            continue

        text = str(item).strip()
        if not text:
            continue

        if text not in seen:
            out.append(text)
            seen.add(text)

    return out


def _join_cn(items: Iterable[Any], max_items: int = 5, empty: str = "未形成明确主控项") -> str:
    values = _dedup_keep_order(items)
    values = values[:max_items]

    if not values:
        return empty

    return "、".join(values)


def _fmt_score(value: Any, digits: int = 2) -> str:
    x = _safe_float(value, default=0.0)
    return f"{x:.{digits}f}"


def _level_cn(level: Any, mapping: Dict[str, str], default: str = "未知") -> str:
    key = _safe_str(level, default="unknown")
    return mapping.get(key, default)


def _normalize_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if _is_missing(value):
        return False
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "y", "是", "有"}:
        return True
    if text in {"false", "0", "no", "n", "否", "无"}:
        return False
    try:
        return bool(value)
    except Exception:
        return False


# ============================================================
# 2. 单个 cell 文本
# ============================================================

def geo_state_to_text(row: Any) -> str:
    """
    将 geo_states_df 的单行转成一句短文本。

    参数：
        row:
            pandas.Series 或 dict。

    返回：
        工程报告风格短句。
    """
    if row is None:
        return "该里程单元未形成可用地质状态。"

    if isinstance(row, dict):
        data = row
    else:
        try:
            data = row.to_dict()
        except Exception:
            data = {}

    cell_start = _safe_float(data.get("cell_start"))
    cell_end = _safe_float(data.get("cell_end"))
    has_evidence = _normalize_bool(data.get("has_geology_evidence"))

    if not has_evidence:
        return (
            f"{_dk_range(cell_start, cell_end)} 区段未形成有效地质证据覆盖，"
            "不宜据此判断为低风险。"
        )

    fused_grade = _safe_str(data.get("fused_grade"), default="未明确")
    main_hazards = _join_cn(
        _as_list(data.get("main_hazards")),
        max_items=5,
        empty="未形成明确主控地质问题",
    )

    confidence = _fmt_score(data.get("confidence_score"), digits=2)
    uncertainty = _level_cn(
        data.get("uncertainty_level"),
        UNCERTAINTY_LEVEL_CN,
        default="未知",
    )
    conflict = _level_cn(
        data.get("conflict_level"),
        CONFLICT_LEVEL_CN,
        default="未知",
    )
    grs = _fmt_score(data.get("GRS_geo_base"), digits=2)

    return (
        f"{_dk_range(cell_start, cell_end)} 区段融合围岩等级以 {fused_grade} 级为主，"
        f"主要关注 {main_hazards}。"
        f"地质基础关注度 GRS_geo_base={grs}，"
        f"融合置信度为 {confidence}，不确定性为{uncertainty}，"
        f"证据冲突程度为{conflict}。"
    )


def geo_states_to_brief_text(
    geo_states_df: pd.DataFrame,
    chainage_min: Optional[float] = None,
    chainage_max: Optional[float] = None,
    top_k: int = 5,
) -> str:
    """
    将一段 geo_states_df 摘要成简短文本。

    用途：
        给 prompt 提供“当前施工范围地质状态概览”。

    注意：
        top_k 控制输出最多列举几个重点 cell，避免 prompt 过长。
    """
    if geo_states_df is None or geo_states_df.empty:
        return "当前范围未形成可用地质融合状态。"

    df = geo_states_df.copy()

    if chainage_min is not None:
        df = df[df["cell_center"] >= float(chainage_min)].copy()

    if chainage_max is not None:
        df = df[df["cell_center"] <= float(chainage_max)].copy()

    if df.empty:
        return "当前指定范围未形成可用地质融合状态。"

    has_evidence = df.get("has_geology_evidence", pd.Series(False, index=df.index)).astype(bool)
    evidence_df = df[has_evidence].copy()

    if evidence_df.empty:
        return "当前指定范围缺少有效地质证据覆盖，不宜据此判断为低风险。"

    grade_counts = {}
    if "fused_grade" in evidence_df.columns:
        grade_counts = evidence_df["fused_grade"].dropna().value_counts().to_dict()

    hazard_counter: Dict[str, int] = {}
    if "main_hazards" in evidence_df.columns:
        for hazards in evidence_df["main_hazards"].tolist():
            for item in _as_list(hazards):
                text = str(item).strip()
                if not text:
                    continue
                hazard_counter[text] = hazard_counter.get(text, 0) + 1

    top_hazards = [
        name for name, _ in sorted(hazard_counter.items(), key=lambda kv: kv[1], reverse=True)[:5]
    ]

    grs = pd.to_numeric(evidence_df.get("GRS_geo_base", 0.0), errors="coerce").fillna(0.0)
    high_count = int((grs >= 0.75).sum())
    medium_count = int(((grs >= 0.50) & (grs < 0.75)).sum())
    low_count = int(((grs > 0.0) & (grs < 0.50)).sum())

    grade_text = "、".join([f"{k}级{v}个cell" for k, v in grade_counts.items()]) if grade_counts else "未形成明确等级分布"
    hazard_text = _join_cn(top_hazards, max_items=5)

    # 选 GRS 高的几个 cell 展示。
    show = evidence_df.sort_values("GRS_geo_base", ascending=False).head(top_k)

    lines = [
        (
            f"地质融合概览：当前范围共有 {len(df)} 个 cell，其中 {len(evidence_df)} 个 cell "
            f"具有地质证据覆盖；围岩等级分布为 {grade_text}；"
            f"主要关注 {hazard_text}。"
        ),
        (
            f"按 GRS_geo_base 统计，高关注 cell 数 {high_count}，"
            f"中等关注 cell 数 {medium_count}，低关注 cell 数 {low_count}。"
            "该关注等级为地质证据融合结果，不表示灾害发生概率。"
        ),
        "重点 cell 摘要：",
    ]

    for _, row in show.iterrows():
        lines.append(f"- {geo_state_to_text(row)}")

    return "\n".join(lines)


# ============================================================
# 3. forward_profile 文本
# ============================================================


def _dk(value: Any) -> str:
    return format_chainage_dk(value, unknown="未知里程", prefix="DK")


def _dk_range(start: Any, end: Any) -> str:
    return f"{_dk(start)}～{_dk(end)}"


GEO_FEATURE_TERMS = {
    "围岩破碎",
    "围岩极破碎",
    "裂隙发育",
    "裂隙密集",
    "软硬不均",
    "泥质填充",
    "稳定性较差",
    "反射异常",
    "明显反射异常",
    "较明显反射异常",
    "软弱夹层",
    "出水增强",
}

HAZARD_EVENT_TERMS = {
    "掉块",
    "坍塌",
    "塌方",
    "出水",
    "线状出水",
    "股状出水",
    "线-股状出水",
    "渗滴水",
    "变形",
}


def _split_concerns(main_hazards: List[str]) -> tuple[List[str], List[str], List[str]]:
    geo_features: List[str] = []
    hazard_events: List[str] = []
    others: List[str] = []

    for item in main_hazards or []:
        text = str(item).strip()
        if not text:
            continue

        if text in GEO_FEATURE_TERMS:
            geo_features.append(text)
        elif text in HAZARD_EVENT_TERMS:
            hazard_events.append(text)
        else:
            others.append(text)

    return (
        _dedup_keep_order(geo_features),
        _dedup_keep_order(hazard_events),
        _dedup_keep_order(others),
    )


def _source_trace_to_text(source_trace: List[Dict[str, Any]], max_items: int = 4) -> str:
    if not source_trace:
        return "未附带明确证据溯源。"

    parts: List[str] = []

    for item in source_trace[:max_items]:
        source_type = str(item.get("source_type") or "未知来源")
        report_id = str(item.get("report_id") or item.get("evidence_id") or "未知报告")
        spatial_type = str(item.get("spatial_type") or "")

        r = item.get("range") or {}
        start = r.get("start_chainage")
        end = r.get("end_chainage")
        center = r.get("center_chainage")
        face = r.get("face_chainage")

        if start is not None and end is not None:
            loc = _dk_range(start, end)
        elif center is not None:
            loc = _dk(center)
        else:
            loc = "未知里程"

        face_text = f"，预报掌子面{_dk(face)}" if face is not None else ""

        snippet = str(item.get("raw_text_snippet") or "").strip()
        if snippet:
            snippet = f"，原文片段：{snippet}"

        parts.append(
            f"{source_type}/{spatial_type}，{loc}{face_text}，来源：{report_id}{snippet}"
        )

    return "；".join(parts)



def _short_evidence_id(evidence_id: Any, max_chars: int = 90) -> str:
    text = str(evidence_id or "").strip()
    if not text:
        return ""
    if len(text) > max_chars:
        return text[: max_chars - 3].rstrip() + "..."
    return text


def _evidence_ids_to_text(evidence_ids: List[Any], max_items: int = 5) -> str:
    ids = []
    seen = set()
    for item in evidence_ids or []:
        text = _short_evidence_id(item)
        if not text or text in seen:
            continue
        ids.append(text)
        seen.add(text)
        if len(ids) >= max_items:
            break

    if not ids:
        return "未附带明确证据溯源"

    return "；".join([f"证据{i + 1}：{x}" for i, x in enumerate(ids)])


def _profile_item_to_text(item: Dict[str, Any]) -> str:
    range_label = item.get("range_label", "--")
    start_chainage = item.get("start_chainage")
    end_chainage = item.get("end_chainage")

    attention = _level_cn(
        item.get("attention_level"),
        ATTENTION_LEVEL_CN,
        default="未知关注等级",
    )

    fused_grade = item.get("fused_grade") or "未形成明确等级"
    confidence = _safe_float(item.get("confidence_score"), default=0.0)
    uncertainty = _level_cn(
        item.get("uncertainty_level"),
        UNCERTAINTY_LEVEL_CN,
        default=str(item.get("uncertainty_level") or "未知"),
    )

    main_hazards = [str(x) for x in item.get("main_hazards", []) if str(x).strip()]
    geo_features, hazard_events, other_terms = _split_concerns(main_hazards)

    monitoring_focus = "、".join(item.get("monitoring_focus", []) or []) or "未形成明确监测重点"
    support_actions = "、".join(item.get("support_actions", []) or []) or "未形成明确处置建议"

    supporting_cell_ids = item.get("supporting_cell_ids", []) or []
    supporting_evidence_ids = item.get("supporting_evidence_ids", []) or []
    source_trace = item.get("source_trace", []) or []

    concern_parts = []
    if geo_features:
        concern_parts.append("主要不良地质特征：" + "、".join(geo_features))
    if hazard_events:
        concern_parts.append("主要施工关注问题：" + "、".join(hazard_events))
    if other_terms:
        concern_parts.append("其他结构化关注标签：" + "、".join(other_terms))

    concern_text = "；".join(concern_parts) if concern_parts else "未形成明确主控地质关注项"

    source_text = _source_trace_to_text(source_trace) if source_trace else _evidence_ids_to_text(supporting_evidence_ids)

    return (
        f"{range_label}（{_dk_range(start_chainage, end_chainage)}）："
        f"地质关注等级为{attention}，融合围岩等级以 {fused_grade} 级为主；"
        f"{concern_text}；"
        f"融合置信度为 {confidence:.2f}，不确定性为{uncertainty}。"
        f"监测重点：{monitoring_focus}。"
        f"建议措施：{support_actions}。"
        f"支撑 cell 数 {len(supporting_cell_ids)}，支撑证据数 {len(supporting_evidence_ids)}。"
        f"主要依据：{source_text}。"
    )


def forward_profile_to_text(forward_profile: Dict[str, Any]) -> str:
    """
    将 forward_profile 转成报告可用短文本。

    注意：
        不把 attention_level 说成概率。
    """
    if not isinstance(forward_profile, dict):
        return "前方地质剖面未形成有效结构化结果。"

    has_forward_evidence = bool(forward_profile.get("has_forward_evidence"))
    current_chainage = _safe_float(forward_profile.get("current_chainage"))
    lookahead_m = _safe_float(forward_profile.get("lookahead_m"), default=30.0)
    overall_level = _level_cn(
        forward_profile.get("overall_attention_level"),
        ATTENTION_LEVEL_CN,
        default="未知关注等级",
    )

    profile = forward_profile.get("profile") or []

    if not has_forward_evidence or not profile:
        return (
            f"以前方 {lookahead_m:.0f}m 为窗口，当前里程 {_dk(current_chainage)} "
            "未形成有效前方地质证据覆盖。该结果不应解释为低风险，建议结合后续超前预报、掌子面揭示及施工响应继续核查。"
        )

    lines = [
        (
            f"以前方 {lookahead_m:.0f}m 为窗口，当前里程 {_dk(current_chainage)} "
            f"的综合地质关注等级为{overall_level}。"
            "该关注等级基于多源地质证据融合得到，不表示灾害发生概率。"
        )
    ]

    for item in profile:
        if isinstance(item, dict):
            lines.append(f"- {_profile_item_to_text(item)}")

    return "\n".join(lines)


# ============================================================
# 4. prompt block
# ============================================================

def build_geology_v2_prompt_block(
    geo_states_df: Optional[pd.DataFrame] = None,
    forward_profile: Optional[Dict[str, Any]] = None,
    include_geo_states_brief: bool = True,
    include_forward_profile: bool = True,
    chainage_min: Optional[float] = None,
    chainage_max: Optional[float] = None,
) -> str:
    """
    构建给 LLM 使用的 geology_v2 prompt block。

    用法：
        prompt_block = build_geology_v2_prompt_block(
            geo_states_df=geo_states_df,
            forward_profile=forward_profile,
        )

    后续接入旧 prompt 时，只需要把 prompt_block 放到地质分析部分。

    注意：
        这里不要求 LLM 自己推断风险概率；
        这里只给结构化融合结果的文字说明。
    """
    blocks: List[str] = []

    blocks.append("【地质融合 v2 结果说明】")
    blocks.append(
        "以下内容为多源地质证据融合后的结构化结果转写，"
        "其中“关注等级”表示地质证据融合关注程度，不表示灾害发生概率；"
        "缺少证据覆盖时，不得表述为“无风险”或“无异常”。"
    )

    if include_geo_states_brief and geo_states_df is not None:
        blocks.append("")
        blocks.append("【当前范围地质状态概览】")
        blocks.append(
            geo_states_to_brief_text(
                geo_states_df=geo_states_df,
                chainage_min=chainage_min,
                chainage_max=chainage_max,
                top_k=5,
            )
        )

    if include_forward_profile and forward_profile is not None:
        blocks.append("")
        blocks.append("【前方分段地质关注剖面】")
        blocks.append(forward_profile_to_text(forward_profile))

    return "\n".join(blocks)