"""
geology_v2.report_context_builder

统一构造 geology_v2 报告上下文。

输入：
    geo_states_df:
        fuse_geo_states 输出。

    forward_profile:
        build_forward_profile 输出。

    coupled_df:
        couple_geo_response 输出，可为空。

    operation_context / gas_context / face_context:
        后续接入主流程时可传入已有结构化结果。
        当前阶段允许为空。

输出：
    geology_v2_report_context:
        {
            "ok": bool,
            "version": "geology_v2",
            "metadata": {...},
            "texts": {
                "geo_brief_text": "...",
                "forward_text": "...",
                "coupling_text": "...",
                "prompt_block": "..."
            },
            "sections": {
                "current_face": {...},
                "excavated_review": {...},
                "forward_profile": {...},
                "coupling": {...},
                "conclusion": {...}
            },
            "data_summary": {...},
            "warnings": [...]
        }

设计原则：
1. 分析函数仍然返回结构化数据；
2. 长文本统一交给 report_renderer.py 生成；
3. 这里只整理上下文和短文本；
4. 不把 GRCI 写成灾害概率；
5. 不把无证据写成无风险；
6. 不混写当前掌子面、已开挖区段、前方预报。
"""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

import numpy as np
import pandas as pd

from geology_v2.text_builder import (
    build_geology_v2_prompt_block,
    forward_profile_to_text,
    geo_states_to_brief_text,
)
from geology_v2.coupling_adapter import (
    coupled_df_to_text,
    summarize_coupled_df,
)
from geology_v2.fusion_engine import summarize_geo_states
from geology_v2.forward_profile import summarize_forward_profile


REPORT_CONTEXT_VERSION = "geology_v2_report_context_v1"


# ============================================================
# 1. 基础工具
# ============================================================

def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, (list, dict, tuple, set)):
        return False
    try:
        return bool(pd.isna(value))
    except Exception:
        return False


def _safe_str(value: Any, default: str = "") -> str:
    if _is_missing(value):
        return default
    text = str(value).strip()
    return text if text else default


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


def _as_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    return {}


def _as_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple) or isinstance(value, set):
        return list(value)
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


def _json_clean(value: Any) -> Any:
    if value is None:
        return None

    if isinstance(value, (str, bool, int, float)):
        if isinstance(value, float) and not math.isfinite(value):
            return None
        return value

    if isinstance(value, (np.integer,)):
        return int(value)

    if isinstance(value, (np.floating,)):
        x = float(value)
        return x if math.isfinite(x) else None

    if isinstance(value, dict):
        return {str(k): _json_clean(v) for k, v in value.items()}

    if isinstance(value, (list, tuple, set)):
        return [_json_clean(v) for v in value]

    try:
        if pd.isna(value):
            return None
    except Exception:
        pass

    return str(value)


def _df_preview_records(df: Optional[pd.DataFrame], max_rows: int = 20) -> List[Dict[str, Any]]:
    if df is None or df.empty:
        return []

    return _json_clean(df.head(max_rows).to_dict(orient="records"))


def _chainage_range_text(chainage_min: Optional[float], chainage_max: Optional[float]) -> str:
    if chainage_min is None or chainage_max is None:
        return "未指定"
    return f"{float(chainage_min):.1f}～{float(chainage_max):.1f}m"


# ============================================================
# 2. section 构造
# ============================================================

def _build_current_face_section(
    face_context: Optional[Dict[str, Any]],
    current_chainage: Optional[float],
) -> Dict[str, Any]:
    face_context = _as_dict(face_context)

    text = _safe_str(
        face_context.get("text")
        or face_context.get("face_geo_text")
        or face_context.get("description"),
        default="当前掌子面描述暂未形成有效结构化结果。",
    )

    has_face_evidence = bool(face_context.get("has_face_evidence", bool(face_context)))

    return {
        "title": "当前掌子面描述",
        "spatial_scope": "current_face",
        "current_chainage": current_chainage,
        "has_face_evidence": has_face_evidence,
        "text": text,
        "notes": [
            "当前掌子面描述只对应当前揭示位置，不替代前方预报。",
        ],
    }


def _build_excavated_review_section(
    geo_states_df: Optional[pd.DataFrame],
    geo_brief_text: str,
    chainage_min: Optional[float],
    chainage_max: Optional[float],
) -> Dict[str, Any]:
    has_geo_states = bool(geo_states_df is not None and not geo_states_df.empty)

    return {
        "title": "已开挖区段地质复核",
        "spatial_scope": "excavated_or_selected_range",
        "chainage_range": {
            "start": chainage_min,
            "end": chainage_max,
            "text": _chainage_range_text(chainage_min, chainage_max),
        },
        "has_geo_states": has_geo_states,
        "text": geo_brief_text,
        "notes": [
            "已开挖区段地质复核属于回顾性或指定范围复核，不应写成尚未开挖的前方风险。",
        ],
    }


def _build_forward_section(
    forward_profile: Optional[Dict[str, Any]],
    forward_text: str,
) -> Dict[str, Any]:
    forward_profile = _as_dict(forward_profile)
    profile = _as_list(forward_profile.get("profile"))

    return {
        "title": "前方30m分段提示",
        "spatial_scope": "forward_lookahead",
        "has_forward_evidence": bool(forward_profile.get("has_forward_evidence")),
        "current_chainage": forward_profile.get("current_chainage"),
        "lookahead_m": forward_profile.get("lookahead_m"),
        "overall_attention_level": forward_profile.get("overall_attention_level"),
        "profile_count": len(profile),
        "profile": _json_clean(profile),
        "text": forward_text,
        "notes": [
            "前方分段提示来自 forward_profile，不应与已开挖区段复核混写。",
            "缺少前方证据时只能说明证据不足，不得写成无风险。",
        ],
    }


def _build_coupling_section(
    coupled_df: Optional[pd.DataFrame],
    coupling_text: str,
    chainage_min: Optional[float],
    chainage_max: Optional[float],
) -> Dict[str, Any]:
    has_coupling = bool(coupled_df is not None and not coupled_df.empty)

    summary = summarize_coupled_df(coupled_df) if has_coupling else {
        "cell_count": 0,
        "has_response_cell_count": 0,
        "computed_grci_cell_count": 0,
        "coupling_level_counts": {},
        "coupling_type_counts": {},
        "GRCI_max": 0.0,
        "GRCI_mean": 0.0,
    }

    return {
        "title": "地质-施工响应耦合分析",
        "spatial_scope": "excavated_or_selected_range",
        "chainage_range": {
            "start": chainage_min,
            "end": chainage_max,
            "text": _chainage_range_text(chainage_min, chainage_max),
        },
        "has_coupling": has_coupling,
        "summary": _json_clean(summary),
        "text": coupling_text,
        "notes": [
            "GRCI 表示地质-施工响应耦合关注度，不表示灾害发生概率。",
            "缺少施工响应数据时，不得据此判断施工响应正常。",
        ],
    }


def _build_operation_section(operation_context: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    operation_context = _as_dict(operation_context)

    text = _safe_str(
        operation_context.get("text")
        or operation_context.get("operation_text")
        or operation_context.get("summary_text"),
        default="本阶段未接入基础工况结构化上下文。",
    )

    return {
        "title": "基础工况上下文",
        "spatial_scope": "time_window",
        "has_operation_context": bool(operation_context),
        "text": text,
        "data": _json_clean(operation_context),
    }


def _build_gas_section(gas_context: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    gas_context = _as_dict(gas_context)

    text = _safe_str(
        gas_context.get("text")
        or gas_context.get("gas_text")
        or gas_context.get("summary_text"),
        default="本阶段未接入气体监测结构化上下文。",
    )

    return {
        "title": "气体监测上下文",
        "spatial_scope": "time_window",
        "has_gas_context": bool(gas_context),
        "text": text,
        "data": _json_clean(gas_context),
    }


def _build_conclusion_section(
    forward_profile: Optional[Dict[str, Any]],
    coupled_df: Optional[pd.DataFrame],
    geo_states_df: Optional[pd.DataFrame],
) -> Dict[str, Any]:
    warnings: List[str] = []

    if geo_states_df is None or geo_states_df.empty:
        warnings.append("地质融合状态为空，不能给出地质关注降低判断。")

    fp = _as_dict(forward_profile)
    if not fp.get("has_forward_evidence"):
        warnings.append("前方窗口缺少有效地质证据，不能表述为前方无风险。")

    if coupled_df is None or coupled_df.empty:
        warnings.append("缺少地质-施工响应耦合结果，不能判断施工响应是否同步异常。")
    else:
        valid_grci = pd.to_numeric(coupled_df.get("GRCI"), errors="coerce")
        if not valid_grci.notna().any():
            warnings.append("GRCI 未形成有效值，多数情况下是施工响应数据缺失。")

    if not warnings:
        warnings.append("结论应基于结构化证据审慎表述，不得扩展到未覆盖时段或未覆盖里程。")

    return {
        "title": "结论与建议约束",
        "spatial_scope": "report_level",
        "text": "结论应综合地质融合、前方分段剖面、施工响应耦合和气体监测结果形成。",
        "constraints": warnings,
    }


# ============================================================
# 3. 主入口
# ============================================================

def build_geology_v2_report_context(
    geo_states_df: Optional[pd.DataFrame] = None,
    forward_profile: Optional[Dict[str, Any]] = None,
    coupled_df: Optional[pd.DataFrame] = None,
    operation_context: Optional[Dict[str, Any]] = None,
    gas_context: Optional[Dict[str, Any]] = None,
    face_context: Optional[Dict[str, Any]] = None,
    current_chainage: Optional[float] = None,
    chainage_min: Optional[float] = None,
    chainage_max: Optional[float] = None,
    metadata: Optional[Dict[str, Any]] = None,
    include_data_preview: bool = True,
) -> Dict[str, Any]:
    """
    构建 geology_v2_report_context。

    当前阶段主要用于测试：
        geo_brief_text + forward_text + coupling_text -> report_context

    后续接主流程时：
        operation_context / gas_context / face_context 可以从 analyze_tbm_data 的结构化结果传入。
    """
    warnings: List[str] = []
    metadata = _as_dict(metadata)

    if geo_states_df is None or geo_states_df.empty:
        warnings.append("geo_states_df 为空，当前范围未形成地质融合状态。")

    if not isinstance(forward_profile, dict):
        warnings.append("forward_profile 为空或格式不正确，前方分段提示不可用。")

    if coupled_df is None or coupled_df.empty:
        warnings.append("coupled_df 为空，地质-施工响应耦合文本不可用。")

    # 1. 生成短文本
    geo_brief_text = geo_states_to_brief_text(
        geo_states_df=geo_states_df,
        chainage_min=chainage_min,
        chainage_max=chainage_max,
        top_k=5,
    ) if geo_states_df is not None else "当前范围未形成可用地质融合状态。"

    forward_text = forward_profile_to_text(
        forward_profile or {}
    )

    coupling_text = coupled_df_to_text(
        coupled_df=coupled_df,
        chainage_min=chainage_min,
        chainage_max=chainage_max,
        top_k=5,
    ) if coupled_df is not None else (
        "当前范围未形成地质-施工响应耦合结果。"
    )

    geology_prompt_block = build_geology_v2_prompt_block(
        geo_states_df=geo_states_df,
        forward_profile=forward_profile,
        include_geo_states_brief=True,
        include_forward_profile=True,
        chainage_min=chainage_min,
        chainage_max=chainage_max,
    )

    prompt_block = "\n\n".join(
        [
            geology_prompt_block,
            "【地质-施工响应耦合分析】",
            coupling_text,
            "【写作约束】",
            "1. GRCI 只能表述为地质-施工响应耦合关注度，不得表述为灾害概率。",
            "2. weak validation 只能表述为弱标签一致性参考，不得表述为真实准确率。",
            "3. 缺少证据只能表述为证据不足，不得表述为无风险或无异常。",
            "4. 当前掌子面、已开挖区段复核、前方预报必须分开表述。",
        ]
    )

    # 2. sections
    sections = {
        "operation": _build_operation_section(operation_context),
        "current_face": _build_current_face_section(face_context, current_chainage),
        "excavated_review": _build_excavated_review_section(
            geo_states_df=geo_states_df,
            geo_brief_text=geo_brief_text,
            chainage_min=chainage_min,
            chainage_max=chainage_max,
        ),
        "forward_profile": _build_forward_section(
            forward_profile=forward_profile,
            forward_text=forward_text,
        ),
        "coupling": _build_coupling_section(
            coupled_df=coupled_df,
            coupling_text=coupling_text,
            chainage_min=chainage_min,
            chainage_max=chainage_max,
        ),
        "gas": _build_gas_section(gas_context),
        "conclusion": _build_conclusion_section(
            forward_profile=forward_profile,
            coupled_df=coupled_df,
            geo_states_df=geo_states_df,
        ),
    }

    # 3. data summary
    data_summary = {
        "geo_states_summary": summarize_geo_states(geo_states_df)
        if geo_states_df is not None else {},
        "forward_profile_summary": summarize_forward_profile(forward_profile or {}),
        "coupled_summary": summarize_coupled_df(coupled_df)
        if coupled_df is not None else {},
    }

    data_preview = {}
    if include_data_preview:
        data_preview = {
            "geo_states_preview": _df_preview_records(geo_states_df, max_rows=10),
            "coupled_preview": _df_preview_records(coupled_df, max_rows=10),
            "forward_profile": _json_clean(forward_profile or {}),
        }

    context = {
        "ok": True,
        "version": "geology_v2",
        "context_version": REPORT_CONTEXT_VERSION,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "metadata": {
            **metadata,
            "current_chainage": current_chainage,
            "chainage_min": chainage_min,
            "chainage_max": chainage_max,
            "chainage_range_text": _chainage_range_text(chainage_min, chainage_max),
        },
        "texts": {
            "geo_brief_text": geo_brief_text,
            "forward_text": forward_text,
            "coupling_text": coupling_text,
            "prompt_block": prompt_block,
        },
        "sections": sections,
        "data_summary": _json_clean(data_summary),
        "data_preview": _json_clean(data_preview),
        "warnings": _dedup_keep_order(warnings),
    }

    return _json_clean(context)


def report_context_to_prompt_text(report_context: Dict[str, Any]) -> str:
    """
    从 report_context 中取 prompt_block。

    这个函数给后续接 llm/prompt_builder.py 使用。
    """
    context = _as_dict(report_context)
    texts = _as_dict(context.get("texts"))
    return _safe_str(texts.get("prompt_block"), default="")