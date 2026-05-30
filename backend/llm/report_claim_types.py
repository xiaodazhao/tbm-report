from __future__ import annotations

from typing import Any


SCHEMA_VERSION = "report_claim_types_v1"

CLAIM_TYPE_FORWARD_SEGMENT = "forward_segment"
CLAIM_TYPE_GEOLOGY_CELL = "geology_cell"
CLAIM_TYPE_GAS = "gas"
CLAIM_TYPE_COUPLING = "coupling"
CLAIM_TYPE_OPERATION = "operation"
CLAIM_TYPE_RECOMMENDATION = "recommendation"
CLAIM_TYPE_CURRENT_FACE = "current_face"
CLAIM_TYPE_UNKNOWN = "unknown"

ALL_CLAIM_TYPES = {
    CLAIM_TYPE_FORWARD_SEGMENT,
    CLAIM_TYPE_GEOLOGY_CELL,
    CLAIM_TYPE_GAS,
    CLAIM_TYPE_COUPLING,
    CLAIM_TYPE_OPERATION,
    CLAIM_TYPE_RECOMMENDATION,
    CLAIM_TYPE_CURRENT_FACE,
    CLAIM_TYPE_UNKNOWN,
}

SPATIAL_SCOPE_CURRENT_FACE = "current_face"
SPATIAL_SCOPE_NEAR_FACE = "near_face"
SPATIAL_SCOPE_EXCAVATED = "excavated"
SPATIAL_SCOPE_FORWARD = "forward"
SPATIAL_SCOPE_OPERATION = "operation"
SPATIAL_SCOPE_UNKNOWN = "unknown"

ALL_SPATIAL_SCOPES = {
    SPATIAL_SCOPE_CURRENT_FACE,
    SPATIAL_SCOPE_NEAR_FACE,
    SPATIAL_SCOPE_EXCAVATED,
    SPATIAL_SCOPE_FORWARD,
    SPATIAL_SCOPE_OPERATION,
    SPATIAL_SCOPE_UNKNOWN,
}


def _safe_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def normalize_claim_type(value: Any, default: str = CLAIM_TYPE_UNKNOWN) -> str:
    text = _safe_text(value)
    if text in ALL_CLAIM_TYPES:
        return text
    return default


def normalize_spatial_scope(value: Any, default: str = SPATIAL_SCOPE_UNKNOWN) -> str:
    text = _safe_text(value)
    if text in ALL_SPATIAL_SCOPES:
        return text
    return default


def is_known_claim_type(value: Any) -> bool:
    return normalize_claim_type(value, default="") in ALL_CLAIM_TYPES


def is_known_spatial_scope(value: Any) -> bool:
    return normalize_spatial_scope(value, default="") in ALL_SPATIAL_SCOPES
