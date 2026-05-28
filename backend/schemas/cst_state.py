from __future__ import annotations

from typing import Any

from schemas.twin_contract import (
    TWIN_STATE_SCHEMA_VERSION,
    build_empty_twin_state,
    build_legacy_cst_aliases,
    deep_merge,
    normalize_twin_state,
)


CST_SCHEMA_VERSION = TWIN_STATE_SCHEMA_VERSION


def build_empty_cst_state() -> dict[str, Any]:
    """Return the canonical CST/TwinState structure.

    CST is now a compatibility name for the canonical TBM TwinState.  Canonical
    fields keep unique semantics; legacy aliases are generated only by
    ``normalize_cst_state`` for old API/prompt consumers.
    """
    return build_empty_twin_state()


def _deep_merge(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    """Compatibility wrapper around the canonical deep merge."""
    return deep_merge(base, patch)


def normalize_cst_state(payload: dict[str, Any] | None, *, include_legacy_aliases: bool = True) -> dict[str, Any]:
    """Normalize a partial CST payload into the canonical TwinState schema.

    The canonical result has stable names such as ``matched_evidence_record_count``
    and ``forward_evidence_count``.  Deprecated aliases are added only under a
    top-level ``legacy_aliases`` key, so higher layers no longer confuse record,
    segment and forward-window semantics.
    """
    state = normalize_twin_state(payload)
    if include_legacy_aliases:
        state["legacy_aliases"] = build_legacy_cst_aliases(state)
    return state
