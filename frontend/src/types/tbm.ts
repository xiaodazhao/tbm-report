export interface TbmDateOption {
  label: string;
  value: string;
}

export interface HealthResponse {
  ok: boolean;
  service?: string;
  pipeline?: string;
  [key: string]: unknown;
}

export interface QualitySummary {
  quality_score?: number;
  grounding_rate?: number;
  claim_count?: number;
  grounded_claim_count?: number;
  unsupported_claim_count?: number;
  [key: string]: unknown;
}

export interface TraceSummary {
  trace_coverage?: number;
  claim_count?: number;
  traced_claim_count?: number;
  grounded_claim_count?: number;
  unsupported_claim_count?: number;
  [key: string]: unknown;
}

export interface SourceTraceItem {
  evidence_id?: string;
  source_type?: string;
  source_type_norm?: string;
  report_id?: string;
  chainage?: number;
  center_chainage?: number;
  text?: string;
  excerpt?: string;
  raw_text?: string;
  [key: string]: unknown;
}

export interface HighGrciCell {
  cell_id: string;
  cell_start?: number | null;
  cell_end?: number | null;
  cell_center?: number | null;
  GRS_geo_base?: number | null;
  RAI?: number | null;
  GRCI?: number | null;
  GRCI_available?: boolean;
  coupling_level?: string | null;
  coupling_explanation?: string | null;
  main_hazards?: string[];
  supporting_evidence_ids?: string[];
  source_trace?: SourceTraceItem[];
  is_forward_cell?: boolean;
  is_excavated_today?: boolean;
  [key: string]: unknown;
}

export interface ForwardAttentionCell {
  cell_id?: string;
  cell_start?: number | null;
  cell_end?: number | null;
  cell_center?: number | null;
  distance_to_face?: number | null;
  GRS_geo_base?: number | null;
  main_hazards?: string[];
  source_trace?: SourceTraceItem[];
  attention_reason?: string;
  [key: string]: unknown;
}

export interface ForwardProfile {
  profile?: Array<Record<string, unknown>>;
  forward_attention_cells?: ForwardAttentionCell[];
  current_chainage?: number;
  current_chainage_dk?: string;
  lookahead_m?: number;
  [key: string]: unknown;
}

export interface ConstructionStateCell {
  cell_id: string;
  cell_start?: number | null;
  cell_end?: number | null;
  cell_center?: number | null;
  operation_state?: string | null;
  plc_metrics?: Record<string, unknown>;
  speed_mean?: number | null;
  thrust_mean?: number | null;
  torque_mean?: number | null;
  stop_duration_min?: number | null;
  abnormal_score?: number | null;
  RAI?: number | null;
  geology_evidence_ids?: string[];
  supporting_evidence_ids?: string[];
  source_trace?: SourceTraceItem[];
  fused_grade?: string | null;
  main_hazards?: string[];
  hazard_scores?: Record<string, number>;
  confidence_score?: number | null;
  uncertainty_level?: string | null;
  conflict_level?: string | null;
  GRS_geo_base?: number | null;
  GRCI?: number | null;
  GRCI_available?: boolean;
  GRCI_source?: string;
  GRCI_unavailable_reason?: string | null;
  coupling_level?: string | null;
  coupling_explanation?: string | null;
  has_plc_response?: boolean;
  has_geology_evidence?: boolean;
  is_excavated_today?: boolean;
  is_current_face_cell?: boolean;
  is_forward_cell?: boolean;
  used_in_evidence_pack?: boolean;
  trace_refs?: string[];
  [key: string]: unknown;
}

export type PromptEvidencePack = Record<string, unknown>;

export interface ReportResponse {
  date: string;
  report_text: string;
  quality_summary: QualitySummary;
  trace_summary: TraceSummary;
  forward_profile: ForwardProfile;
  high_grci_cells: HighGrciCell[];
  warnings: string[];
}

export interface DebugReportResponse extends ReportResponse {
  operation_summary: Record<string, unknown>;
  cluster_summary: Record<string, unknown>;
  gas_summary: Record<string, unknown>;
  normalized_evidence_summary: Record<string, unknown>;
  construction_state_cells: ConstructionStateCell[];
  prompt_evidence_pack: PromptEvidencePack;
  prompt_text: string;
  quality: Record<string, unknown>;
  trace: Record<string, unknown>;
}
