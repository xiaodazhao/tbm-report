from __future__ import annotations

import re
from typing import Any

from contracts.field_contract import FIELD_SEMANTICS


SCHEMA_VERSION = "data_dictionary_v1"

HAZARD_TERMS = [
    "线-股状出水",
    "线状出水",
    "渗滴水",
    "围岩极破碎",
    "围岩破碎",
    "裂隙密集",
    "裂隙发育",
    "明显反射异常",
    "围岩稳定性差",
    "软硬不均",
    "反射异常",
    "突涌水",
    "瓦斯突出",
    "塌方",
    "岩爆",
    "掉块",
    "出水",
    "渗水",
]

METRIC_TERMS = [
    "GRS_geo_base",
    "GRS_adjusted",
    "RAI_proxy",
    "GRCI",
    "GRS",
    "RAI",
    "work_ratio",
    "stop_ratio",
]

GAS_TERMS = [
    "CH4",
    "CO2",
    "H2S",
    "SO2",
    "NO2",
    "NO",
    "甲烷",
]

OPERATION_TERMS = [
    "operation_mode",
    "work",
    "stop",
    "停机",
    "工作",
    "工况",
    "推进",
    "扭矩",
    "推力",
    "转速",
    "速度",
    "cluster_state",
]

STRONG_HAZARD_TERMS = ["突涌水", "塌方", "岩爆", "瓦斯突出"]

REPORT_FIELD_SEMANTICS = {
    "GRS_geo_base": FIELD_SEMANTICS.get("GRS_geo_base"),
    "GRS_adjusted": FIELD_SEMANTICS.get("GRS_adjusted"),
    "RAI": FIELD_SEMANTICS.get("RAI"),
    "GRCI": FIELD_SEMANTICS.get("GRCI"),
    "forward_attention_level": FIELD_SEMANTICS.get("forward_attention_level"),
}


def _safe_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def dedup_text(items: Any) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()

    if isinstance(items, (list, tuple, set)):
        iterable = items
    elif items is None:
        iterable = []
    else:
        iterable = [items]

    for item in iterable:
        text = _safe_text(item)
        if not text or text in seen:
            continue
        out.append(text)
        seen.add(text)
    return out


def extract_terms(text: str, terms: list[str]) -> list[str]:
    return dedup_text([term for term in terms if term and term in _safe_text(text)])


def split_tag_text(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return dedup_text(value)
    text = _safe_text(value)
    if not text:
        return []
    return dedup_text([part for part in re.split(r"[、,，;；/| ]+", text) if _safe_text(part)])


def collect_text_tokens_from_obj(obj: Any) -> set[str]:
    tokens: set[str] = set()
    if isinstance(obj, dict):
        for value in obj.values():
            tokens.update(collect_text_tokens_from_obj(value))
    elif isinstance(obj, list):
        for value in obj:
            tokens.update(collect_text_tokens_from_obj(value))
    else:
        text = _safe_text(obj)
        if text:
            tokens.add(text)
            tokens.update(split_tag_text(text))
    return tokens


def collect_supported_tags_from_item(item: dict[str, Any]) -> set[str]:
    tags: set[str] = set()

    for key in (
        "main_hazards",
        "hazard_tags",
        "attribute_tags",
        "method_tags",
        "attention_tags",
        "main_geology_hazards",
        "main_response_hazards",
        "geology_attention",
        "response_attention",
        "construction_attention",
    ):
        tags.update(split_tag_text(item.get(key)))

    for trace in item.get("source_trace", []) if isinstance(item.get("source_trace"), list) else []:
        if not isinstance(trace, dict):
            continue
        for key in ("hazard_tags", "attribute_tags", "method_tags", "risk_tags"):
            tags.update(split_tag_text(trace.get(key)))

    tags.update(collect_text_tokens_from_obj(item))
    return tags


def hazards_supported_by_tags(claim_hazards: list[str], supported_tags: set[str]) -> bool:
    hazards = [_safe_text(item) for item in claim_hazards if _safe_text(item)]
    if not hazards:
        return True

    supported = [_safe_text(item) for item in supported_tags if _safe_text(item)]
    for hazard in hazards:
        ok = False
        for tag in supported:
            if hazard == tag or hazard in tag or tag in hazard:
                ok = True
                break
        if not ok:
            return False
    return True
