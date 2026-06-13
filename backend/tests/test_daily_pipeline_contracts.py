from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pandas as pd
from fastapi import FastAPI
from fastapi.testclient import TestClient

from coupling.grs_rai_grci import build_construction_state_cells, compute_cell_grci, high_grci_cells
from llm.evidence_pack import build_prompt_evidence_pack
from llm.report_trace_builder import build_report_trace
from llm.report_grounding_checker import _get_key_cells
import pipeline.daily_report_pipeline as daily_pipeline
import routes.report as report_routes
from schemas.pipeline import ConstructionStateCell


def test_evidence_pack_exposes_key_cells_for_grounding_checker():
    cell = ConstructionStateCell(
        cell_id="cell_0_10",
        cell_start=0,
        cell_end=10,
        cell_center=5,
        RAI=0.4,
        GRS_geo_base=0.6,
        GRCI=0.5,
        GRCI_available=True,
        GRCI_source="cell_grs_rai_formula_v1",
        coupling_level="medium",
        has_plc_response=True,
        has_geology_evidence=True,
        is_excavated_today=True,
        supporting_evidence_ids=["ev-1"],
        source_trace=[{"evidence_id": "ev-1", "source_type": "HSP"}],
    )

    pack = build_prompt_evidence_pack(
        date="2023-12-30",
        current_chainage=5,
        operation_summary={},
        cluster_summary={},
        gas_summary={},
        construction_state_cells=[cell],
        forward_profile={},
        high_grci_cells=high_grci_cells([cell]),
    )

    geology_evidence = pack["geology_evidence"]
    assert len(geology_evidence["key_cells"]) > 0
    assert geology_evidence["key_cells"] == geology_evidence["selected_cells"]
    assert geology_evidence["excavated_review_cells"]
    assert "forward_attention_cells" in geology_evidence
    assert "background_context_cells" in geology_evidence
    assert pack["excavated_review_evidence"]["review_cells"]
    assert "forward_attention_cells" in pack["forward_attention_evidence"]
    assert "background_context_cells" in pack["background_context_evidence"]
    assert len(_get_key_cells({}, {}, pack)) > 0


def test_report_trace_preserves_semantic_support_type():
    trace = build_report_trace(
        "cell_0_10：GRCI复核优先级为 medium。",
        grounding_result={
            "claim_results": [
                {
                    "claim_id": "claim_1",
                    "claim_text": "cell_0_10：GRCI复核优先级为 medium。",
                    "claim_type": "coupling",
                    "grounded": True,
                    "support_type": "coupling_context",
                    "trace_support_type": "coupling_review_support",
                    "messages": ["找到可支撑的结构化证据。"],
                }
            ],
            "warnings": [],
        },
    )

    assert trace["traced_claims"]
    claim = trace["traced_claims"][0]
    assert claim["support_type"] == "coupling_context"
    assert claim["trace_support_type"] == "coupling_review_support"


def test_compute_cell_grci_requires_plc_response_and_rai():
    assert compute_cell_grci(0.6, None, has_plc_response=True) == (
        None,
        "unavailable",
        "missing_plc_response",
    )
    assert compute_cell_grci(0.6, 0.4, has_plc_response=False) == (
        None,
        "unavailable",
        "missing_plc_response",
    )
    grci, source, reason = compute_cell_grci(0.6, 0.4, has_plc_response=True)
    assert grci is not None
    assert source == "cell_grs_rai_formula_v1"
    assert reason is None


def test_build_construction_state_cells_marks_grci_unavailable_without_response():
    cells_df = pd.DataFrame(
        [
            {"cell_id": "cell_0_10", "cell_start": 0.0, "cell_end": 10.0, "cell_center": 5.0},
            {"cell_id": "cell_10_20", "cell_start": 10.0, "cell_end": 20.0, "cell_center": 15.0},
        ]
    )
    response_df = pd.DataFrame(
        [
            {
                "cell_id": "cell_0_10",
                "cell_start": 0.0,
                "cell_end": 10.0,
                "cell_center": 5.0,
                "RAI": 0.4,
                "abnormal_score": 0.4,
                "response_support_count": 3,
            }
        ]
    )
    geo_df = pd.DataFrame(
        [
            {
                "cell_id": "cell_0_10",
                "cell_start": 0.0,
                "cell_end": 10.0,
                "cell_center": 5.0,
                "GRS_geo_base": 0.6,
                "supporting_evidence_ids": ["ev-1"],
            },
            {
                "cell_id": "cell_10_20",
                "cell_start": 10.0,
                "cell_end": 20.0,
                "cell_center": 15.0,
                "GRS_geo_base": 0.7,
                "supporting_evidence_ids": ["ev-2"],
            },
        ]
    )
    normalized = pd.DataFrame(
        [
            {"evidence_id": "ev-1", "source_type_norm": "HSP"},
            {"evidence_id": "ev-2", "source_type_norm": "TSP"},
        ]
    )

    result = build_construction_state_cells(
        cells_df=cells_df,
        cell_response_df=response_df,
        geo_states_df=geo_df,
        cell_evidence_df=pd.DataFrame(),
        normalized_evidence_df=normalized,
        current_chainage=10.0,
        day_start_chainage=0.0,
        day_end_chainage=10.0,
        lookahead_m=30.0,
    )

    by_id = {cell.cell_id: cell for cell in result}
    assert by_id["cell_0_10"].GRCI_available is True
    assert by_id["cell_0_10"].GRCI is not None
    assert by_id["cell_10_20"].GRCI_available is False
    assert by_id["cell_10_20"].GRCI is None
    assert by_id["cell_10_20"].GRCI_source == "unavailable"
    assert by_id["cell_10_20"].GRCI_unavailable_reason == "missing_plc_response"
    assert by_id["cell_10_20"].coupling_level == "unavailable"
    assert all(cell["GRCI_available"] for cell in high_grci_cells(result))
    assert all(not cell["is_forward_cell"] for cell in high_grci_cells(result))


def test_report_api_returns_core_fields(monkeypatch):
    fake = _fake_result()
    monkeypatch.setattr(report_routes, "run_daily_report_pipeline", lambda date, use_llm=True: fake)

    app = FastAPI()
    report_routes.register_report_routes(app)
    client = TestClient(app)

    response = client.post("/api/tbm/report", json={"date": "2023-12-30", "use_llm": False})
    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == {
        "date",
        "report_text",
        "quality_summary",
        "trace_summary",
        "forward_profile",
        "high_grci_cells",
        "warnings",
    }


def test_report_debug_api_returns_intermediate_fields(monkeypatch):
    fake = _fake_result()
    monkeypatch.setattr(report_routes, "run_daily_report_pipeline", lambda date, use_llm=True: fake)

    app = FastAPI()
    report_routes.register_report_routes(app)
    client = TestClient(app)

    response = client.post("/api/tbm/report/debug", json={"date": "2023-12-30", "use_llm": False})
    assert response.status_code == 200
    payload = response.json()
    for key in [
        "operation_summary",
        "gas_summary",
        "normalized_evidence_summary",
        "construction_state_cells",
        "prompt_evidence_pack",
        "prompt_text",
        "quality",
        "trace",
    ]:
        assert key in payload


def test_run_daily_report_pipeline_no_llm_does_not_call_llm(monkeypatch):
    _patch_minimal_pipeline(monkeypatch)

    def fail_if_called(_prompt):
        raise AssertionError("LLM should not be called when use_llm=False")

    monkeypatch.setattr(daily_pipeline, "call_llm_result", fail_if_called)
    result = daily_pipeline.run_daily_report_pipeline("2023-01-01", use_llm=False)
    assert result.report_text
    assert "LLM disabled" in result.warnings


def test_run_daily_report_pipeline_llm_failure_falls_back_with_warning(monkeypatch):
    _patch_minimal_pipeline(monkeypatch)
    monkeypatch.setattr(
        daily_pipeline,
        "call_llm_result",
        lambda _prompt: {"ok": False, "text": "", "warnings": ["mock llm failure"]},
    )
    result = daily_pipeline.run_daily_report_pipeline("2023-01-01", use_llm=True)
    assert result.report_text
    assert "mock llm failure" in result.warnings


def test_smoke_config_snapshot_exposes_config_warning(monkeypatch):
    import scripts.smoke_test_daily_pipeline as smoke

    monkeypatch.setattr(smoke, "CONFIG_WARNINGS", ["DATA_ROOT is not set; using fallback DATA_ROOT=backend/data."])
    snapshot = smoke._config_snapshot()
    assert snapshot["warnings"]
    assert "DATA_ROOT is not set" in snapshot["warnings"][0]


def _fake_result():
    return SimpleNamespace(
        date="2023-12-30",
        report_text="report",
        quality_summary={"quality_score": 100},
        trace_summary={"trace_coverage": 1.0},
        forward_profile={"profile": []},
        high_grci_cells=[],
        warnings=[],
        operation_summary={},
        cluster_summary={},
        gas_summary={},
        normalized_evidence_summary={},
        construction_state_cells=[ConstructionStateCell(cell_id="cell_0_10")],
        prompt_evidence_pack={},
        prompt_text="prompt",
        quality={},
        trace={},
    )


def _patch_minimal_pipeline(monkeypatch):
    inputs = SimpleNamespace(
        date="2023-01-01",
        plc_path=Path("tbm_data_20230101.csv"),
        df_plc=pd.DataFrame(),
        evidence_path=Path("evidence_db.csv"),
        evidence_df=pd.DataFrame({"evidence_id": ["ev-1"]}),
        warnings=[],
    )
    cell_response_df = pd.DataFrame(
        [
            {
                "cell_id": "cell_0_10",
                "cell_start": 0.0,
                "cell_end": 10.0,
                "cell_center": 5.0,
                "RAI": 0.4,
                "abnormal_score": 0.4,
            }
        ]
    )
    cells_df = pd.DataFrame(
        [{"cell_id": "cell_0_10", "cell_start": 0.0, "cell_end": 10.0, "cell_center": 5.0}]
    )
    geo_states_df = pd.DataFrame(
        [
            {
                "cell_id": "cell_0_10",
                "cell_start": 0.0,
                "cell_end": 10.0,
                "cell_center": 5.0,
                "GRS_geo_base": 0.6,
                "main_hazards": ["掉块"],
                "supporting_evidence_ids": ["ev-1"],
            }
        ]
    )
    normalized_df = pd.DataFrame(
        [{"evidence_id": "ev-1", "source_type_norm": "HSP", "raw_text": "掉块"}]
    )

    monkeypatch.setattr(daily_pipeline, "load_daily_inputs", lambda date: inputs)
    monkeypatch.setattr(
        daily_pipeline,
        "analyze_plc_response",
        lambda *args, **kwargs: {
            "df_plc_annotated": pd.DataFrame(),
            "operation_summary": {
                "position": {
                    "start_chainage": 0.0,
                    "end_chainage": 10.0,
                    "advance_length_m": 10.0,
                },
                "operation_mode_summary": {},
            },
            "cluster_summary": {},
            "gas_summary": {},
            "cell_response_df": cell_response_df,
            "current_chainage": 10.0,
            "day_start_chainage": 0.0,
            "day_end_chainage": 10.0,
            "quality_report": {},
            "warnings": [],
        },
    )
    monkeypatch.setattr(
        daily_pipeline,
        "_run_geology_branch",
        lambda **kwargs: {
            "warnings": [],
            "cells_df": cells_df,
            "normalized_df": normalized_df,
            "cell_evidence_df": pd.DataFrame(),
            "geo_states_df": geo_states_df,
            "forward_profile": {"profile": []},
        },
    )
    monkeypatch.setattr(
        daily_pipeline,
        "check_report_quality",
        lambda *args, **kwargs: {
            "ok": True,
            "score": 100,
            "stats": {
                "claim_count": 1,
                "grounded_claim_count": 1,
                "unsupported_claim_count": 0,
                "grounding_rate": 1.0,
            },
            "grounding_summary": {
                "claim_count": 1,
                "grounded_claim_count": 1,
                "unsupported_claim_count": 0,
                "grounding_rate": 1.0,
            },
            "claim_results": [],
        },
    )
    monkeypatch.setattr(daily_pipeline, "build_report_trace", lambda *args, **kwargs: {"trace_available": True})
    monkeypatch.setattr(
        daily_pipeline,
        "summarize_report_trace",
        lambda trace: {
            "trace_available": True,
            "trace_coverage": 1.0,
            "unsupported_claim_count": 0,
        },
    )
