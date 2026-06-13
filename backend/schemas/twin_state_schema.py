from __future__ import annotations

from typing import Any


SCHEMA_VERSION = "twin_state_schema_v1"
TWIN_STATE_PAYLOAD_VERSION = "twin_state_v1"
PROMPT_EVIDENCE_PACK_VERSION = "prompt_evidence_pack_v1"

TWIN_STATE_SECTIONS = {
    "position": "position_state",
    "operation": "operation_state",
    "cluster": "cluster_state",
    "gas": "gas_state",
    "geology": "geology_state",
    "response": "response_state",
    "coupling": "coupling_state",
    "forward": "forward_state",
    "quality": "quality_state",
    "source_refs": "source_refs",
}

PROMPT_EVIDENCE_SECTIONS = {
    "report_scope": "report_scope",
    "operation": "operation_evidence",
    "cluster": "cluster_evidence",
    "gas": "gas_evidence",
    "geology": "geology_evidence",
    "forward": "forward_evidence",
    "coupling": "coupling_evidence",
    "quality": "quality_evidence",
}

CONTEXT_PATHS = {
    "key_cells": [
        ("twin_state", TWIN_STATE_SECTIONS["geology"], "key_cells"),
        ("geology_context", "key_cells"),
        ("prompt_evidence_pack", PROMPT_EVIDENCE_SECTIONS["geology"], "key_cells"),
        ("prompt_evidence_pack", PROMPT_EVIDENCE_SECTIONS["geology"], "selected_cells"),
    ],
    "excavated_review_cells": [
        ("prompt_evidence_pack", "excavated_review_evidence", "review_cells"),
        ("prompt_evidence_pack", "excavated_review_evidence", "high_grci_cells"),
        ("prompt_evidence_pack", PROMPT_EVIDENCE_SECTIONS["geology"], "excavated_review_cells"),
        ("prompt_evidence_pack", PROMPT_EVIDENCE_SECTIONS["coupling"], "review_priority_cells"),
        ("prompt_evidence_pack", PROMPT_EVIDENCE_SECTIONS["coupling"], "high_grci_cells"),
    ],
    "forward_attention_cells": [
        ("prompt_evidence_pack", "forward_attention_evidence", "forward_attention_cells"),
        ("prompt_evidence_pack", PROMPT_EVIDENCE_SECTIONS["forward"], "forward_attention_cells"),
        ("prompt_evidence_pack", PROMPT_EVIDENCE_SECTIONS["geology"], "forward_attention_cells"),
    ],
    "background_context_cells": [
        ("prompt_evidence_pack", "background_context_evidence", "background_context_cells"),
        ("prompt_evidence_pack", PROMPT_EVIDENCE_SECTIONS["geology"], "background_context_cells"),
    ],
    "forward_segments": [
        ("twin_state", TWIN_STATE_SECTIONS["forward"], "segments"),
        ("twin_state", TWIN_STATE_SECTIONS["forward"], "forward_segments"),
        ("twin_state", TWIN_STATE_SECTIONS["forward"], "profile"),
        ("geology_context", "forward_segments"),
        ("prompt_evidence_pack", PROMPT_EVIDENCE_SECTIONS["forward"], "segments"),
        ("prompt_evidence_pack", PROMPT_EVIDENCE_SECTIONS["forward"], "forward_segments"),
        ("prompt_evidence_pack", PROMPT_EVIDENCE_SECTIONS["forward"], "profile"),
    ],
    "gas_summaries": [
        ("twin_state", TWIN_STATE_SECTIONS["gas"], "gas_summaries"),
        ("prompt_evidence_pack", PROMPT_EVIDENCE_SECTIONS["gas"], "gas_summaries"),
    ],
    "coupling_evidence": [
        ("twin_state", TWIN_STATE_SECTIONS["coupling"]),
        ("prompt_evidence_pack", PROMPT_EVIDENCE_SECTIONS["coupling"]),
    ],
    "operation_evidence": [
        ("twin_state", TWIN_STATE_SECTIONS["operation"]),
        ("prompt_evidence_pack", PROMPT_EVIDENCE_SECTIONS["operation"]),
    ],
    "cluster_evidence": [
        ("twin_state", TWIN_STATE_SECTIONS["cluster"]),
        ("prompt_evidence_pack", PROMPT_EVIDENCE_SECTIONS["cluster"]),
    ],
    "current_face": [
        ("geology_context", "current_face"),
        ("geology_context", "sections", "current_face"),
    ],
}


def _as_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return list(value)
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, set):
        return list(value)
    return []


def _get_nested(root: Any, path: tuple[str, ...], default: Any = None) -> Any:
    current = root
    for part in path:
        if not isinstance(current, dict):
            return default
        current = current.get(part)
    return current if current is not None else default


def get_context_value(
    name: str,
    *,
    twin_state: dict[str, Any] | None = None,
    geology_context: dict[str, Any] | None = None,
    prompt_evidence_pack: dict[str, Any] | None = None,
    default: Any = None,
) -> Any:
    payloads = {
        "twin_state": _as_dict(twin_state),
        "geology_context": _as_dict(geology_context),
        "prompt_evidence_pack": _as_dict(prompt_evidence_pack),
    }
    for path in CONTEXT_PATHS.get(name, []):
        root_name = path[0]
        value = _get_nested(payloads.get(root_name), path[1:], default=None)
        if value not in (None, {}, [], ""):
            return value
    return default


def get_context_list(
    name: str,
    *,
    twin_state: dict[str, Any] | None = None,
    geology_context: dict[str, Any] | None = None,
    prompt_evidence_pack: dict[str, Any] | None = None,
) -> list[Any]:
    return _as_list(
        get_context_value(
            name,
            twin_state=twin_state,
            geology_context=geology_context,
            prompt_evidence_pack=prompt_evidence_pack,
            default=[],
        )
    )


def get_context_dict(
    name: str,
    *,
    twin_state: dict[str, Any] | None = None,
    geology_context: dict[str, Any] | None = None,
    prompt_evidence_pack: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return _as_dict(
        get_context_value(
            name,
            twin_state=twin_state,
            geology_context=geology_context,
            prompt_evidence_pack=prompt_evidence_pack,
            default={},
        )
    )
