from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class TwinScope(BaseModel):
    """Scope and chainage semantics for one daily construction twin."""

    date: str | None = None
    daily_plc_range: dict[str, Any] = Field(default_factory=dict)
    daily_excavated_scope: dict[str, Any] = Field(default_factory=dict)
    current_chainage: float | None = None
    face_chainage: float | None = None
    forward_scope: dict[str, Any] = Field(default_factory=dict)
    local_background_scope: dict[str, Any] = Field(default_factory=dict)
    cell_length_m: float | None = None
    warnings: list[str] = Field(default_factory=list)


class TwinCellView(BaseModel):
    """Role-aware, queryable state view for one ConstructionStateCell."""

    cell_id: str
    mileage_start: float | None = None
    mileage_end: float | None = None
    cell_role: str = "outside_report_scope"
    distance_to_face_m: float | None = None
    position_state: dict[str, Any] = Field(default_factory=dict)
    operation_state: dict[str, Any] = Field(default_factory=dict)
    response_state: dict[str, Any] = Field(default_factory=dict)
    geology_state: dict[str, Any] = Field(default_factory=dict)
    forward_state: dict[str, Any] = Field(default_factory=dict)
    gas_state: dict[str, Any] = Field(default_factory=dict)
    coupling_state: dict[str, Any] = Field(default_factory=dict)
    quality_state: dict[str, Any] = Field(default_factory=dict)
    trace_state: dict[str, Any] = Field(default_factory=dict)


class TwinStateSummary(BaseModel):
    """Aggregated summaries exposed by the construction twin."""

    operation_summary: dict[str, Any] = Field(default_factory=dict)
    response_summary: dict[str, Any] = Field(default_factory=dict)
    plc_response_summary: dict[str, Any] = Field(default_factory=dict)
    geology_summary: dict[str, Any] = Field(default_factory=dict)
    forward_summary: dict[str, Any] = Field(default_factory=dict)
    gas_summary: dict[str, Any] = Field(default_factory=dict)
    coupling_summary: dict[str, Any] = Field(default_factory=dict)
    quality_summary: dict[str, Any] = Field(default_factory=dict)


class TwinTraceIndex(BaseModel):
    """Indexes for cell, evidence, PLC, geology, and source trace lookup."""

    cell_trace_index: dict[str, Any] = Field(default_factory=dict)
    evidence_trace_index: dict[str, Any] = Field(default_factory=dict)
    plc_trace_index: dict[str, Any] = Field(default_factory=dict)
    geology_trace_index: dict[str, Any] = Field(default_factory=dict)
    source_trace_index: dict[str, Any] = Field(default_factory=dict)
    warning_index: dict[str, Any] = Field(default_factory=dict)


class EvidenceGovernanceContext(BaseModel):
    """Claim and metric boundaries used by Evidence Pack, LLM, and checkers."""

    role_rules: dict[str, Any] = Field(default_factory=dict)
    metric_boundaries: dict[str, Any] = Field(default_factory=dict)
    allowed_claims: list[str] = Field(default_factory=list)
    forbidden_claims: list[str] = Field(default_factory=list)
    proxy_boundaries: dict[str, Any] = Field(default_factory=dict)
    forward_boundaries: list[str] = Field(default_factory=list)
    grci_boundaries: list[str] = Field(default_factory=list)


class DailyConstructionTwin(BaseModel):
    """Cell-level evidence twin for one TBM construction date."""

    date: str
    scope: TwinScope
    cells: list[TwinCellView] = Field(default_factory=list)
    daily_review_cells: list[TwinCellView] = Field(default_factory=list)
    forward_attention_cells: list[TwinCellView] = Field(default_factory=list)
    local_background_cells: list[TwinCellView] = Field(default_factory=list)
    high_grci_cells: list[dict[str, Any]] = Field(default_factory=list)
    summaries: TwinStateSummary = Field(default_factory=TwinStateSummary)
    trace_index: TwinTraceIndex = Field(default_factory=TwinTraceIndex)
    governance: EvidenceGovernanceContext = Field(default_factory=EvidenceGovernanceContext)
    debug: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
