from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class EvidenceUnit(BaseModel):
    """Atomic evidence view used for claim grounding and audit exports."""

    evidence_id: str
    source_type: str | None = None
    time_scope: dict[str, Any] = Field(default_factory=dict)
    spatial_scope: dict[str, Any] = Field(default_factory=dict)
    role: str = "unknown"
    entity: str | None = None
    state: str | None = None
    certainty: str = "unknown"
    support_value: Any = None
    allowed_expression: list[str] = Field(default_factory=list)
    source_ref: dict[str, Any] = Field(default_factory=dict)


class ReportClaim(BaseModel):
    """Structured claim extracted from a generated report sentence."""

    claim_id: str
    claim_text: str
    claim_type: str = "unknown"
    entity: str | None = None
    value: Any = None
    unit: str | None = None
    time_scope: dict[str, Any] = Field(default_factory=dict)
    spatial_scope: dict[str, Any] | str = "unknown"
    claim_role: str = "unknown"
    certainty: str = "asserted"
    source_sentence_index: int | None = None


class ClaimEvidenceTrace(BaseModel):
    """Detailed claim-to-evidence alignment result."""

    claim_id: str
    aligned_evidence_ids: list[str] = Field(default_factory=list)
    support_status: str = "unsupported"
    mismatch_type: str = "missing_evidence"
    confidence: float = 0.0
    reason: str | None = None


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
    stop_ratio: float | None = None
    abnormal_ratio: float | None = None
    speed_drop_score: float | None = None
    torque_volatility_score: float | None = None
    speed_volatility_score: float | None = None
    stop_component: float | None = None
    abnormal_component: float | None = None
    speed_drop_component: float | None = None
    torque_component: float | None = None
    speed_volatility_component: float | None = None
    dominant_component: str | None = None
    RAI_formula_text: str | None = None
    stop_reason_available: bool = False
    planned_stop_distinguishable: bool = False
    stop_interpretation_warning: str | None = None

    geology_evidence_ids: list[str] = Field(default_factory=list)
    supporting_evidence_ids: list[str] = Field(default_factory=list)
    source_trace: list[dict[str, Any]] = Field(default_factory=list)
    evidence_overlap_length: float | None = None
    evidence_overlap_ratio: float | None = None
    max_overlap_ratio: float | None = None
    mean_overlap_ratio: float | None = None
    total_overlap_length: float | None = None
    evidence_count: int = 0
    evidence_ids: list[str] = Field(default_factory=list)
    source_type_distribution: dict[str, int] = Field(default_factory=dict)
    evidence_confidence: float | None = None
    evidence_confidence_method: str = "unavailable"
    trace_completeness: float | None = None
    trace_completeness_method: str = "unavailable"
    manual_review_status: str | None = None
    source_reliability: float | None = None
    source_reliability_method: str = "unavailable"
    fused_grade: str | None = None
    main_hazards: list[str] = Field(default_factory=list)
    hazard_scores: dict[str, float] = Field(default_factory=dict)
    confidence_score: float | None = None
    uncertainty_level: str | None = None
    conflict_level: str | None = None
    GRS_geo_base: float | None = None
    grade_score_component: float | None = None
    hazard_component: float | None = None
    confidence_component: float | None = None
    GRS_formula_text: str | None = None
    GRS_component_method: str = "unavailable"
    GRS_available: bool = False
    GRS_unavailable_reason: str | None = None

    GRCI: float | None = None
    GRCI_available: bool = False
    GRCI_source: str = "unavailable"
    GRCI_unavailable_reason: str | None = None
    grs_term: float | None = None
    rai_term: float | None = None
    interaction_term: float | None = None
    GRCI_formula_text: str | None = None
    coupling_level: str | None = None
    coupling_explanation: str | None = None

    has_plc_response: bool = False
    has_geology_evidence: bool = False
    is_excavated_today: bool = False
    is_current_face_cell: bool = False
    is_forward_cell: bool = False
    distance_to_face_m: float | None = None
    forward_distance_band: str | None = None
    forward_distance_weight: float | None = None
    cell_role: str = "outside_report_scope"
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
    review_cells: list[dict[str, Any]] = Field(default_factory=list)
    high_priority_cells: list[dict[str, Any]] = Field(default_factory=list)
    medium_priority_cells: list[dict[str, Any]] = Field(default_factory=list)
    low_priority_cells: list[dict[str, Any]] = Field(default_factory=list)
    twin_state: dict[str, Any] = Field(default_factory=dict)
    daily_construction_twin: dict[str, Any] = Field(default_factory=dict)
    twin_summary: dict[str, Any] = Field(default_factory=dict)
    twin_boundary_summary: dict[str, Any] = Field(default_factory=dict)
    scope_summary: dict[str, Any] = Field(default_factory=dict)
    time_valid_evidence: list[dict[str, Any]] = Field(default_factory=list)
    spatial_relevant_evidence: list[dict[str, Any]] = Field(default_factory=list)
    excluded_evidence: list[dict[str, Any]] = Field(default_factory=list)
    cell_response_records: list[dict[str, Any]] = Field(default_factory=list)
    geo_state_records: list[dict[str, Any]] = Field(default_factory=list)
    cell_evidence_records: list[dict[str, Any]] = Field(default_factory=list)
    daily_review_cells: list[dict[str, Any]] = Field(default_factory=list)
    forward_attention_cells: list[dict[str, Any]] = Field(default_factory=list)
    local_background_cells: list[dict[str, Any]] = Field(default_factory=list)
    method_metrics: dict[str, Any] = Field(default_factory=dict)
    generation_mode: str = "template"
    llm_generation: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
