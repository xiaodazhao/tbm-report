from __future__ import annotations

import re
from typing import Any

from contracts.data_dictionary import GAS_TERMS, HAZARD_TERMS, METRIC_TERMS, OPERATION_TERMS, extract_terms
from llm.report_claim_types import (
    CLAIM_TYPE_COUPLING,
    CLAIM_TYPE_CURRENT_FACE,
    CLAIM_TYPE_FORWARD_SEGMENT,
    CLAIM_TYPE_GAS,
    CLAIM_TYPE_GEOLOGY_CELL,
    CLAIM_TYPE_OPERATION,
    CLAIM_TYPE_RECOMMENDATION,
    CLAIM_TYPE_UNKNOWN,
    SPATIAL_SCOPE_CURRENT_FACE,
    SPATIAL_SCOPE_EXCAVATED,
    SPATIAL_SCOPE_FORWARD,
    SPATIAL_SCOPE_NEAR_FACE,
    SPATIAL_SCOPE_OPERATION,
    SPATIAL_SCOPE_UNKNOWN,
)
from llm.report_policy import split_sentences


SCHEMA_VERSION = "report_claim_extractor_v1"

_DK_RANGE_RE = re.compile(
    r"((?:D?y?K)\d+\+\d+(?:\.\d+)?)\s*(?:～|~|-|—|－)\s*((?:D?y?K)\d+\+\d+(?:\.\d+)?)",
    re.IGNORECASE,
)
_DK_POINT_RE = re.compile(r"((?:D?y?K)\d+\+\d+(?:\.\d+)?)", re.IGNORECASE)
_FORWARD_RANGE_RE = re.compile(
    r"(?:前方\s*)?(\d{1,3})\s*(?:-|～|~|—|－)\s*(\d{1,3})\s*m",
    re.IGNORECASE,
)
_FORWARD_WINDOW_RE = re.compile(r"前方\s*(\d{1,3})\s*m\s*范围", re.IGNORECASE)


def _safe_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _dedup_keep_order(items: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        text = _safe_text(item)
        if not text or text in seen:
            continue
        out.append(text)
        seen.add(text)
    return out


def _normalize_dk(text: str) -> str:
    value = _safe_text(text)
    if not value:
        return ""
    value = value.replace("DyK", "DK").replace("DYK", "DK").replace("dyk", "DK")
    value = value.replace("Dyk", "DK")
    return value


def _extract_range_dk(sentence: str) -> str | None:
    match = _DK_RANGE_RE.search(sentence)
    if match:
        return f"{_normalize_dk(match.group(1))}～{_normalize_dk(match.group(2))}"
    point = _DK_POINT_RE.search(sentence)
    if point:
        return _normalize_dk(point.group(1))
    return None


def _extract_relative_range(sentence: str) -> str | None:
    match = _FORWARD_RANGE_RE.search(sentence)
    if match:
        start = int(match.group(1))
        end = int(match.group(2))
        return f"{min(start, end)}-{max(start, end)}m"
    window = _FORWARD_WINDOW_RE.search(sentence)
    if window:
        end = int(window.group(1))
        return f"0-{end}m"
    return None


def _detect_spatial_scope(sentence: str) -> str:
    if "当前掌子面揭示" in sentence or "掌子面揭示" in sentence:
        return SPATIAL_SCOPE_CURRENT_FACE
    if "最近现场素描点" in sentence or "当前里程附近" in sentence:
        return SPATIAL_SCOPE_NEAR_FACE
    if "已开挖区段" in sentence or "复盘" in sentence or "回顾" in sentence:
        return SPATIAL_SCOPE_EXCAVATED
    if "前方" in sentence or "未来" in sentence or "掌子面前方" in sentence:
        return SPATIAL_SCOPE_FORWARD
    if any(term in sentence for term in OPERATION_TERMS):
        return SPATIAL_SCOPE_OPERATION
    return SPATIAL_SCOPE_UNKNOWN


def _detect_claim_type(
    sentence: str,
    *,
    spatial_scope: str,
    range_dk: str | None,
    relative_range: str | None,
    hazards: list[str],
    metrics: list[str],
    gases: list[str],
) -> str:
    if spatial_scope == SPATIAL_SCOPE_FORWARD or relative_range:
        return CLAIM_TYPE_FORWARD_SEGMENT
    if range_dk and hazards:
        return CLAIM_TYPE_GEOLOGY_CELL
    if gases:
        return CLAIM_TYPE_GAS
    if metrics:
        return CLAIM_TYPE_COUPLING
    if any(term in sentence for term in OPERATION_TERMS):
        return CLAIM_TYPE_OPERATION
    if "建议" in sentence:
        return CLAIM_TYPE_RECOMMENDATION
    if spatial_scope == SPATIAL_SCOPE_CURRENT_FACE:
        return CLAIM_TYPE_CURRENT_FACE
    return CLAIM_TYPE_UNKNOWN


def extract_report_claims(report_text: str) -> list[dict]:
    """Extract lightweight, rule-based report claims from final report text."""
    try:
        sentences = split_sentences(report_text)
        claims: list[dict[str, Any]] = []
        for index, sentence in enumerate(sentences):
            range_dk = _extract_range_dk(sentence)
            relative_range = _extract_relative_range(sentence)
            hazards = _dedup_keep_order(extract_terms(sentence, HAZARD_TERMS))
            metrics = _dedup_keep_order(extract_terms(sentence, METRIC_TERMS))
            gases = _dedup_keep_order(extract_terms(sentence, GAS_TERMS))
            spatial_scope = _detect_spatial_scope(sentence)
            claim_type = _detect_claim_type(
                sentence,
                spatial_scope=spatial_scope,
                range_dk=range_dk,
                relative_range=relative_range,
                hazards=hazards,
                metrics=metrics,
                gases=gases,
            )
            warnings: list[str] = []
            if spatial_scope == SPATIAL_SCOPE_CURRENT_FACE and relative_range:
                warnings.append("当前掌子面表述中同时出现前方范围，存在空间语义混用。")
            if "低风险" in sentence or "无风险" in sentence:
                warnings.append("句子包含低风险/无风险表述，建议做 grounded 复核。")
            claims.append(
                {
                    "claim_id": f"claim_{index + 1:04d}",
                    "text": sentence,
                    "claim_type": claim_type,
                    "range_dk": range_dk,
                    "relative_range": relative_range,
                    "hazards": hazards,
                    "metrics": metrics,
                    "gases": gases,
                    "spatial_scope": spatial_scope,
                    "sentence_index": index,
                    "warnings": warnings,
                }
            )
        return claims
    except Exception:
        return []
