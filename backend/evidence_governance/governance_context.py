from __future__ import annotations

from typing import Any

from evidence_governance.boundaries import (
    FORWARD_BOUNDARIES,
    GRCI_BOUNDARIES,
    METRIC_BOUNDARIES,
    PROXY_BOUNDARIES,
)
from evidence_governance.claim_rules import ALLOWED_CLAIMS, FORBIDDEN_CLAIMS
from evidence_governance.roles import ROLE_RULES
from schemas.twin import EvidenceGovernanceContext


def build_evidence_governance_context(
    twin_or_cells: Any = None,
    *,
    warnings: list[str] | None = None,
) -> EvidenceGovernanceContext:
    """Build the shared evidence-governance contract for report cognition."""
    context = EvidenceGovernanceContext(
        role_rules=dict(ROLE_RULES),
        metric_boundaries=dict(METRIC_BOUNDARIES),
        allowed_claims=list(ALLOWED_CLAIMS),
        forbidden_claims=list(FORBIDDEN_CLAIMS),
        proxy_boundaries=dict(PROXY_BOUNDARIES),
        forward_boundaries=list(FORWARD_BOUNDARIES),
        grci_boundaries=list(GRCI_BOUNDARIES),
    )
    if warnings:
        context.forbidden_claims.extend(
            f"warning boundary: {str(item)}" for item in warnings if item
        )
    return context
