"""Canonical field contract helpers for TBM report analysis."""

from __future__ import annotations

from typing import Any

try:  # pragma: no cover - optional dependency guard
    import pandas as pd
except Exception:  # pragma: no cover - keep module import-safe without pandas
    pd = None


FIELD_CONTRACT_VERSION = "field_contract_v1"

CANONICAL_FIELDS = {
    "geo_attention_base": "GRS_geo_base",
    "geo_attention_adjusted": "GRS_adjusted",
    "response_anomaly_index": "RAI",
    "geo_response_coupling_index": "GRCI",
    "source_risk_level": "source_risk_level",
    "forward_evidence_count": "forward_evidence_count",
    "unique_evidence_count": "unique_evidence_count",
    "matched_evidence_hit_count": "matched_evidence_hit_count",
    "active_report_source_count": "active_report_source_count",
}

DEPRECATED_FIELDS = {
    "risk_prob_text": "geo_attention_profile_text",
    "risk_level": "source_risk_level",
    "active_source_count": "active_report_source_count",
    "high_risk_count": "high_attention_or_high_source_risk_count",
    "forward_risk": "forward_attention",
    "advice_level": "forward_attention_level",
}

FIELD_SEMANTICS = {
    "GRS_geo_base": "纯地质证据基础关注度，不等同于灾害概率。",
    "GRS_adjusted": "结合施工响应修正后的地质关注指标，仍不等同于灾害概率。",
    "RAI": "施工响应异常度，可能受设备、组织、工序等非地质因素影响。",
    "GRCI": "地质-施工响应耦合关注度，是复盘解释指标，不是预测概率。",
    "source_risk_level": "来源报告内部风险等级，不等同于系统最终风险判断。",
    "forward_attention_level": "前方窗口证据融合关注等级，不是灾害发生概率。",
}

FIELD_LAYER = {
    "GRS_geo_base": "geology_cell_level",
    "GRS_adjusted": "segment_level",
    "RAI": "segment_level",
    "GRCI": "segment_level",
    "source_risk_level": "evidence_level",
    "forward_attention_level": "forward_level",
    "operation_mode": "row_level",
    "cluster_state": "cluster_level",
    "twin_state": "twin_state_level",
}

_CANONICAL_NAMES = set(CANONICAL_FIELDS.values()) | set(FIELD_SEMANTICS) | set(FIELD_LAYER)


def get_canonical_field(name: str) -> str:
    """Return the preferred canonical field name for a field-like identifier."""
    if not name:
        return name
    if name in CANONICAL_FIELDS:
        return CANONICAL_FIELDS[name]
    if name in DEPRECATED_FIELDS:
        return DEPRECATED_FIELDS[name]
    if name in _CANONICAL_NAMES:
        return name
    return name


def is_deprecated_field(name: str) -> bool:
    """Return True when the given field is a deprecated legacy alias."""
    return bool(name in DEPRECATED_FIELDS)


def explain_field(name: str) -> dict[str, Any]:
    """Explain a field's canonical mapping, semantic meaning, and data layer."""
    canonical_name = get_canonical_field(name)
    return {
        "requested_name": name,
        "canonical_name": canonical_name,
        "is_deprecated": is_deprecated_field(name),
        "deprecated_replacement": DEPRECATED_FIELDS.get(name),
        "semantic": FIELD_SEMANTICS.get(canonical_name),
        "layer": FIELD_LAYER.get(canonical_name),
        "field_contract_version": FIELD_CONTRACT_VERSION,
    }


def _iter_deprecated_entries(obj: Any, path: str = "root"):
    """Yield deprecated field hits from nested dict/list/DataFrame-like objects."""
    if isinstance(obj, dict):
        for key, value in obj.items():
            key_text = str(key)
            next_path = f"{path}.{key_text}"
            if is_deprecated_field(key_text):
                yield f"{next_path}: deprecated field '{key_text}' -> '{get_canonical_field(key_text)}'"
            yield from _iter_deprecated_entries(value, next_path)
        return

    if isinstance(obj, (list, tuple, set)):
        for index, value in enumerate(obj):
            yield from _iter_deprecated_entries(value, f"{path}[{index}]")
        return

    if pd is not None and isinstance(obj, pd.DataFrame):
        for column in obj.columns:
            column_text = str(column)
            if is_deprecated_field(column_text):
                yield (
                    f"{path}.columns['{column_text}']: deprecated field "
                    f"'{column_text}' -> '{get_canonical_field(column_text)}'"
                )


def validate_no_deprecated_fields(obj: Any, allowed_legacy: bool = False) -> list[str]:
    """Recursively validate that nested objects do not rely on deprecated field aliases."""
    if allowed_legacy:
        return []
    return list(_iter_deprecated_entries(obj))
