# Backend Inventory

This document summarizes the current backend architecture after the CST upgrade. It focuses on the production path, the formal Construction State Twin layer, retained CLI tools, and the experiment-facing interfaces.

## 1. Runtime Mainline

### Web entry

- `backend/app.py`
  - Creates the FastAPI application.
- `backend/routes/tbm.py`
  - Exposes the TBM APIs, including summary, state, geology, report, history, digital twin, and `agent_v2`.

### Main analysis orchestration

- `backend/services/tbm_analysis_service.py`
  - Orchestrates the full daily or time-window analysis pipeline.
  - Produces operation summaries, geological fusion results, `GRS / RAI / GRCI`, `digital_twin_state`, `llm_summary`, and the formal `cst_state`.

### Operation analysis

- `backend/analysis/dataprocess.py`
  - Basic operation segmentation.
  - Stoppage statistics.
  - Routine ring-building stoppage candidate detection.
- `backend/analysis/excavation_state.py`
  - Construction state recognition and efficiency statistics.
- `backend/analysis/gas_analysis.py`
  - Gas monitoring analysis.

### Geological fusion and segment analysis

- `backend/geology/geology_fusion_backend.py`
  - Loads the evidence database and attaches geological evidence to TBM records.
- `backend/geology/fusion.py`
  - Point-wise multi-source geological fusion.
- `backend/geology/segment_analysis.py`
  - Fixed-length segment aggregation.
- `backend/geology/geology_summary.py`
  - Geological summaries and face-condition summaries.

### Attention and coupling analysis

- `backend/analysis/geo_risk_model.py`
  - Builds normalized equal-weight `GRS` components.
- `backend/analysis/geology_response_coupling.py`
  - Main `GRS / RAI / GRCI` implementation.
  - Gaussian mileage smoothing.
  - Isolation Forest response anomaly scoring.
  - Coupling analysis with routine-stop penalty reduction.
- `backend/analysis/forward_risk_advisor.py`
  - Forward attention and look-ahead risk prompts.

### Evidence parsing and import

- `backend/parsers/tsp_parser.py`
- `backend/parsers/hsp_parser.py`
- `backend/parsers/sketch_parser.py`
- `backend/services/evidence_import_service.py`

### LLM reporting

- `backend/llm/prompt_builder.py`
  - Daily state-aware report prompt.
- `backend/llm/prompt_builder_timewindow.py`
  - Time-window state-aware report prompt.
- `backend/llm/llm_api.py`
  - Model provider abstraction.

### Agent layer

- `backend/agent/supervisor_agent.py`
  - Supervisor-style session agent.
- `backend/agent/tbm_tools.py`
  - Tool wrappers over the analysis and CST outputs.
- `backend/agent/common.py`
- `backend/agent/registry.py`

## 2. Formal CST Layer

The project no longer treats CST as an experiment-only JSON wrapper. It is now a formal backend state layer.

### CST schema

- `backend/schemas/cst_state.py`
  - Defines the canonical CST structure.
  - Main sections:
    - `temporal_state`
    - `spatial_state`
    - `operation_state`
    - `geological_state`
    - `response_state`
    - `attention_state`
    - `provenance_state`

### CST update service

- `backend/services/cst_update_service.py`
  - Builds the current CST snapshot from the latest analysis result.
  - Reads `CST_{t-1}` when available.
  - Updates `CST_t` with:
    - deltas
    - persistent hazards
    - persistent attention segments
    - confidence
    - stability
    - trend labels
    - changed fields
    - previous-state summaries

### CST persistence

- `backend/services/sqlite_storage_service.py`
  - Persists CST into the `cst_states` table.
  - Supports:
    - save current state
    - load a state by id or key
    - load previous state for a given context

### CST in main outputs

- `backend/services/tbm_analysis_service.py`
  - Returns `cst_state` in the main analysis result.
- `backend/routes/tbm.py`
  - Includes `cst_state` in relevant API responses.
- `backend/agent/tbm_tools.py`
  - Exposes `cst_state` to the agent and tool outputs.
- `experiments/common.py`
  - Reuses the formal `cst_state` instead of building a parallel experimental twin.

## 3. Supporting Services and Utilities

- `backend/services/digital_twin_state.py`
  - Runtime twin snapshot builder used by the CST update service.
- `backend/services/history_memory_service.py`
  - History record and comparison logic, now CST-aware.
- `backend/services/analysis_cache_service.py`
  - Cached daily analysis.
- `backend/config.py`
  - Environment and path configuration.
- `backend/utils/io_utils.py`
- `backend/utils/time_window_utils.py`
- `backend/utils/serialization.py`
- `backend/utils/api_response.py`
- `backend/utils/chainage_utils.py`

### Schemas and API models

- `backend/schemas/api.py`
- `backend/schemas/responses.py`
- `backend/schemas/schemas.py`

## 4. Retained CLI Tools

These scripts are intentionally kept as manual tools, not as part of the online request path.

- `backend/scripts/build_evidence_db.py`
  - Full evidence database rebuild.
- `backend/scripts/import_evidence_reports.py`
  - Incremental evidence import.
- `backend/scripts/inspect_coupling_analysis.py`
  - Coupling analysis inspection for a selected date.
- `backend/scripts/test_agent_v2.py`
  - Agent smoke test.

## 5. Test Coverage

The current backend tests cover the mainline and the CST integration path.

- `backend/tests/test_dataprocess.py`
- `backend/tests/test_geo_risk_model.py`
- `backend/tests/test_geology_response_coupling.py`
- `backend/tests/test_history_memory_service.py`
- `backend/tests/test_sqlite_storage_service.py`
- `backend/tests/test_evidence_import_service.py`
- `backend/tests/test_parsers.py`
- `backend/tests/test_tbm_routes.py`

## 6. Current Status

The backend is now organized around:

- one main production analysis path
- one formal CST layer
- one reporting path
- one agent path
- a retained CLI tool layer
- a separate experiment layer

This is a significant change from the earlier "multiple analysis outputs plus ad hoc experimental wrapping" structure. The current project is centered on CST as the shared intermediate state object.
