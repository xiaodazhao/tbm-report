from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field


PayloadT = TypeVar("PayloadT")


class ApiMeta(BaseModel):
    model_config = ConfigDict(extra="allow")

    cache_hit: bool | None = None
    resolved_date: str | None = None
    source_file: str | None = None
    source_path: str | None = None


class ApiEnvelope(BaseModel, Generic[PayloadT]):
    ok: bool
    message: str
    data: PayloadT | None = None
    warnings: list[str] = Field(default_factory=list)
    meta: ApiMeta = Field(default_factory=ApiMeta)


class DatesPayload(BaseModel):
    dates: list[str] = Field(default_factory=list)


class SummaryPayload(BaseModel):
    stop_count: int = 0
    transition_count: int = 0
    work_count: int = 0
    abnormal_count: int = 0
    stop_total_min: float = 0.0
    transition_total_min: float = 0.0
    work_total_min: float = 0.0
    abnormal_total_min: float = 0.0
    geology_has: bool = False

    # New phase-2 field names.
    geology_high_geo_attention_segment_count: int = 0
    geology_multi_report_source_segment_count: int = 0
    geology_top_grci_segment_count: int = 0
    forward_evidence_count: int = 0
    forward_advice_level: str | None = None

    # Backward-compatible aliases. Prefer the new names above.
    geology_high_risk_segment_count: int = 0
    geology_multi_source_segment_count: int = 0


class StateSegmentPayload(BaseModel):
    label: int
    label_text: str
    start: str
    end: str
    duration: float


class StatePayload(BaseModel):
    segments: list[StateSegmentPayload] = Field(default_factory=list)
    efficiency: list[dict[str, Any]] = Field(default_factory=list)
    state_labels: dict[str, Any] = Field(default_factory=dict)
    state_stats: dict[str, Any] = Field(default_factory=dict)
    valid_samples: int = 0
    state_config: dict[str, Any] = Field(default_factory=dict)


class ReportPayload(BaseModel):
    report: str = ""


class EvidenceImportPayload(BaseModel):
    ok: bool = False
    dry_run: bool = False
    written: bool = False
    evidence_db_path: str | None = None
    backup_path: str | None = None
    pdf_count: int = 0
    parsed_record_count: int = 0
    clean_record_count: int = 0
    inserted_count: int = 0
    replaced_count: int = 0
    skipped_existing_count: int = 0
    skipped_existing_ids: list[str] = Field(default_factory=list)
    total_before: int = 0
    total_after: int = 0
    file_results: list[dict[str, Any]] = Field(default_factory=list)
    errors: list[dict[str, Any]] = Field(default_factory=list)


class GeologyPayload(BaseModel):
    record_summary: dict[str, Any] = Field(default_factory=dict)
    segment_summary: dict[str, Any] = Field(default_factory=dict)
    segment_table: list[dict[str, Any]] = Field(default_factory=list)
    typical_segments: list[dict[str, Any]] = Field(default_factory=list)

    coupling_summary: dict[str, Any] = Field(default_factory=dict)
    coupling_validation: dict[str, Any] = Field(default_factory=dict)  # deprecated alias
    weak_label_validation: dict[str, Any] = Field(default_factory=dict)
    coupling_output_paths: dict[str, Any] = Field(default_factory=dict)

    high_attention_segments: list[dict[str, Any]] = Field(default_factory=list)  # deprecated alias
    top_grci_segments: list[dict[str, Any]] = Field(default_factory=list)
    top_grs_segments: list[dict[str, Any]] = Field(default_factory=list)
    top_rai_segments: list[dict[str, Any]] = Field(default_factory=list)

    forward_risk_summary: dict[str, Any] = Field(default_factory=dict)
    face_description: dict[str, Any] = Field(default_factory=dict)
    digital_twin_state: dict[str, Any] = Field(default_factory=dict)
    cst_state: dict[str, Any] = Field(default_factory=dict)


class DigitalTwinPayload(BaseModel):
    date: str | None = None
    digital_twin_state: dict[str, Any] = Field(default_factory=dict)
    cst_state: dict[str, Any] = Field(default_factory=dict)
    twin_state: dict[str, Any] = Field(default_factory=dict)
    twin_events: list[dict[str, Any]] = Field(default_factory=list)
    twin_diff: dict[str, Any] = Field(default_factory=dict)
    coupling_summary: dict[str, Any] = Field(default_factory=dict)
    forward_risk_summary: dict[str, Any] = Field(default_factory=dict)


class HistoryMemoryPayload(BaseModel):
    date: str | None = None
    current_record: dict[str, Any] = Field(default_factory=dict)
    history_comparison: dict[str, Any] = Field(default_factory=dict)


class RiskProfilePayload(BaseModel):
    date: str | None = None
    risk_profile: dict[str, Any] = Field(default_factory=dict)
    speed_profile: list[dict[str, Any]] = Field(default_factory=list)


class AgentMessagePayload(BaseModel):
    message_id: int | None = None
    session_id: str | None = None
    role: str
    created_at: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class AgentSessionPayload(BaseModel):
    session_id: str
    title: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    messages: list[AgentMessagePayload] = Field(default_factory=list)