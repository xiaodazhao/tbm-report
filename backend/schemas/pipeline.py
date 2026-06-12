from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ConstructionStateCell(BaseModel):
    """Unified cell-level state used by Evidence Pack, report, and trace."""

    cell_id: str
    cell_start: float | None = None
    cell_end: float | None = None
    cell_center: float | None = None

    operation_state: str | None = None
    plc_metrics: dict[str, Any] = Field(default_factory=dict)
    speed_mean: float | None = None
    thrust_mean: float | None = None
    torque_mean: float | None = None
    stop_duration_min: float | None = None
    abnormal_score: float | None = None
    RAI: float | None = None

    geology_evidence_ids: list[str] = Field(default_factory=list)
    supporting_evidence_ids: list[str] = Field(default_factory=list)
    source_trace: list[dict[str, Any]] = Field(default_factory=list)
    fused_grade: str | None = None
    main_hazards: list[str] = Field(default_factory=list)
    hazard_scores: dict[str, float] = Field(default_factory=dict)
    confidence_score: float | None = None
    uncertainty_level: str | None = None
    conflict_level: str | None = None
    GRS_geo_base: float | None = None

    GRCI: float | None = None
    GRCI_available: bool = False
    GRCI_source: str = "unavailable"
    GRCI_unavailable_reason: str | None = None
    coupling_level: str | None = None
    coupling_explanation: str | None = None

    has_plc_response: bool = False
    has_geology_evidence: bool = False
    is_excavated_today: bool = False
    is_current_face_cell: bool = False
    is_forward_cell: bool = False
    used_in_evidence_pack: bool = False
    trace_refs: list[str] = Field(default_factory=list)


class DailyReportResult(BaseModel):
    """Result returned by the only daily report pipeline."""

    date: str
    report_text: str
    operation_summary: dict[str, Any] = Field(default_factory=dict)
    cluster_summary: dict[str, Any] = Field(default_factory=dict)
    gas_summary: dict[str, Any] = Field(default_factory=dict)
    normalized_evidence_summary: dict[str, Any] = Field(default_factory=dict)
    construction_state_cells: list[ConstructionStateCell] = Field(default_factory=list)
    forward_profile: dict[str, Any] = Field(default_factory=dict)
    prompt_evidence_pack: dict[str, Any] = Field(default_factory=dict)
    prompt_text: str = ""
    quality: dict[str, Any] = Field(default_factory=dict)
    quality_summary: dict[str, Any] = Field(default_factory=dict)
    trace: dict[str, Any] = Field(default_factory=dict)
    trace_summary: dict[str, Any] = Field(default_factory=dict)
    high_grci_cells: list[dict[str, Any]] = Field(default_factory=list)
    twin_state: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
