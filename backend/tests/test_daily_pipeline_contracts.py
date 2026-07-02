from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pandas as pd
from fastapi import FastAPI
from fastapi.testclient import TestClient

from coupling.grs_rai_grci import build_construction_state_cells, compute_cell_grci, high_grci_cells
from plc.cell_response import project_plc_response_to_cells
from llm.evidence_pack import build_prompt_evidence_pack
from llm.report_grounding_checker import check_claim_grounding
from llm.report_trace_builder import build_report_trace
from llm.report_grounding_checker import _get_key_cells
from pipeline.evidence_scope import apply_spatial_relevance_filter, build_scope_cells, build_scope_summary
import pipeline.daily_report_pipeline as daily_pipeline
import routes.report as report_routes
from schemas.pipeline import ConstructionStateCell


def test_cell_response_reads_motion_cols_and_exports_paper_based_working_aliases():
    rows = []
    for idx in range(25):
        is_work = idx >= 5
        rows.append(
            {
                "运行时间-time": f"2023-12-30 00:{idx:02d}:00",
                "导向盾首里程": 1014601.0 + idx * 0.1,
                "掘进状态": 1 if is_work else 0,
                "推进速度": 10.0 + idx if is_work else 0.0,
                "推力": 1000.0 + idx * 10.0 if is_work else 0.0,
                "刀盘扭矩": 200.0 + idx * 2.0 if is_work else 0.0,
                "刀盘实际转速": 5.0 + idx * 0.1 if is_work else 0.0,
                "贯入度": 0.5 + idx * 0.01 if is_work else 0.0,
                "is_working": is_work,
                "is_stopped": not is_work,
                "is_abnormal": False,
            }
        )
    out = project_plc_response_to_cells(pd.DataFrame(rows), cell_length=10.0)
    assert len(out) == 1
    row = out.iloc[0]
    assert row["speed_mean"] is not None
    assert row["thrust_mean"] is not None
    assert row["torque_mean"] is not None
    assert row["rpm_mean"] is not None
    assert row["working_sample_count"] == 20
    assert row["working_ratio"] == 20 / 25
    assert bool(row["insufficient_working_samples"]) is False
    assert str(row["working_metrics_source"]).startswith("paper_based_preprocessing")
    if bool(row["steady_state_available"]):
        assert row["working_speed_cv"] == row["steady_speed_cv"]
        assert row["cutterhead_power_proxy"] == row["steady_cutterhead_power_proxy"]
    else:
        assert bool(row["steady_state_fallback_used"]) is True
        assert pd.isna(row["working_speed_cv"])
        assert pd.isna(row["cutterhead_power_proxy"])
    metrics = row["response_metrics"]
    assert metrics["working_sample_count"] == 20
    assert metrics["working_metrics_source"] == row["working_metrics_source"]


def test_cell_response_marks_insufficient_working_samples_and_safe_ratios():
    rows = []
    for idx in range(10):
        rows.append(
            {
                "运行时间-time": f"2023-12-30 00:{idx:02d}:00",
                "导向盾首里程": 1014601.0 + idx * 0.1,
                "掘进状态": 1,
                "推进速度": 10.0,
                "推力": 1000.0,
                "刀盘扭矩": 200.0,
                "刀盘实际转速": 5.0,
                "贯入度": 0.0,
                "is_working": True,
                "is_stopped": False,
                "is_abnormal": False,
            }
        )
    out = project_plc_response_to_cells(pd.DataFrame(rows), cell_length=10.0)
    row = out.iloc[0]
    assert row["working_sample_count"] == 10
    assert bool(row["insufficient_working_samples"]) is True
    assert pd.isna(row["working_speed_cv"])
    assert pd.isna(row["thrust_per_penetration"])
    assert pd.isna(row["torque_per_penetration"])


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


def test_spatial_relevance_excludes_distant_time_valid_tsp():
    scope = build_scope_summary(
        date="2023-12-30",
        current_chainage=1014616.0,
        day_start_chainage=1014601.0,
        day_end_chainage=1014616.0,
        cell_length=10.0,
        lookahead_m=30.0,
        local_background_back_m=100.0,
    )
    evidence = pd.DataFrame(
        [
            {
                "evidence_id": "old-tsp",
                "source_type_norm": "TSP",
                "evidence_role": "prediction",
                "spatial_type": "segment",
                "start_chainage": 1013080.2,
                "end_chainage": 1013096.0,
                "face_chainage": 1013080.2,
            },
            {
                "evidence_id": "local-hsp",
                "source_type_norm": "HSP",
                "evidence_role": "prediction",
                "spatial_type": "segment",
                "start_chainage": 1014608.0,
                "end_chainage": 1014641.0,
            },
        ]
    )

    spatial, excluded, counted_scope = apply_spatial_relevance_filter(evidence, scope)

    old = excluded[excluded["evidence_id"] == "old-tsp"].iloc[0]
    assert bool(old["time_valid"]) is True
    assert bool(old["spatial_relevant"]) is False
    assert old["evidence_report_role"] == "excluded_by_distance"
    assert old["spatial_invalid_reason"] == "outside_report_scope"
    assert counted_scope["spatial_relevant_evidence_count"] == 1
    assert counted_scope["excluded_by_distance_evidence_count"] == 1
    assert spatial["evidence_id"].tolist() == ["local-hsp"]


def test_report_scope_cells_are_local_not_global():
    scope = build_scope_summary(
        date="2023-12-30",
        current_chainage=1014616.0,
        day_start_chainage=1014601.0,
        day_end_chainage=1014616.0,
        cell_length=10.0,
        lookahead_m=30.0,
        local_background_back_m=100.0,
    )
    cells = build_scope_cells(scope)
    assert len(cells) == 14
    assert cells["cell_start"].min() == 1014510.0
    assert cells["cell_end"].max() == 1014650.0


def test_components_and_semantic_boundaries_are_exported():
    cells_df = pd.DataFrame(
        [
            {"cell_id": "cell_0_10", "cell_start": 0.0, "cell_end": 10.0, "cell_center": 5.0},
            {"cell_id": "cell_10_20", "cell_start": 10.0, "cell_end": 20.0, "cell_center": 15.0},
            {"cell_id": "cell_20_30", "cell_start": 20.0, "cell_end": 30.0, "cell_center": 25.0},
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
                "stop_ratio": 0.5,
                "abnormal_ratio": 0.2,
                "speed_drop_score": 0.6,
                "torque_volatility_score": 0.2,
                "speed_volatility_score": 0.2,
                "stop_component": 0.2,
                "abnormal_component": 0.05,
                "speed_drop_component": 0.12,
                "torque_component": 0.02,
                "speed_volatility_component": 0.01,
                "dominant_component": "stop_component",
                "RAI_formula_text": "RAI = 0.40 * stop_ratio + 0.25 * abnormal_ratio + 0.20 * speed_drop_score + 0.10 * torque_volatility_score + 0.05 * speed_volatility_score",
                "stop_reason_available": False,
                "planned_stop_distinguishable": False,
                "stop_interpretation_warning": "当前 PLC 字段未区分计划停机与非计划停机，stop_ratio 仅作为施工响应关注信号，不直接作为异常原因。",
                "working_sample_count": 24,
                "working_ratio": 0.8,
                "insufficient_working_samples": False,
                "working_speed_cv": 0.12,
                "working_thrust_cv": 0.08,
                "working_torque_cv": 0.18,
                "penetration_mean": 0.55,
                "cutterhead_power_proxy": 12345.0,
                "thrust_per_penetration": 1800.0,
                "torque_per_penetration": 400.0,
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
                "GRS_geo_base": 0.59,
                "grade_score_component": 0.4,
                "hazard_component": 0.8,
                "confidence_component": 0.5,
                "GRS_formula_text": "GRS = 0.45 * grade_score_component + 0.45 * hazard_component + 0.10 * confidence_component",
                "GRS_component_method": "fused",
                "supporting_evidence_ids": ["ev-1"],
            },
            {
                "cell_id": "cell_10_20",
                "cell_start": 10.0,
                "cell_end": 20.0,
                "cell_center": 15.0,
                "GRS_geo_base": 0.7,
                "grade_score_component": 0.6,
                "hazard_component": 0.8,
                "confidence_component": 0.7,
                "GRS_component_method": "fused",
                "supporting_evidence_ids": ["ev-2"],
            },
            {
                "cell_id": "cell_20_30",
                "cell_start": 20.0,
                "cell_end": 30.0,
                "cell_center": 25.0,
                "GRS_geo_base": 0.0,
                "GRS_component_method": "empty",
                "supporting_evidence_ids": [],
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
        lookahead_m=20.0,
        scope_summary={
            "daily_excavated_scope": {"start": 0.0, "end": 10.0},
            "forward_scope": {"start": 10.0, "end": 20.0},
            "local_background_scope": {"start": 20.0, "end": 30.0},
            "report_scope": {"start": 0.0, "end": 30.0},
        },
    )
    by_id = {cell.cell_id: cell for cell in result}
    daily = by_id["cell_0_10"]
    forward = by_id["cell_10_20"]
    background = by_id["cell_20_30"]

    assert round(
        daily.stop_component
        + daily.abnormal_component
        + daily.speed_drop_component
        + daily.torque_component
        + daily.speed_volatility_component,
        6,
    ) == round(daily.RAI, 6)
    assert daily.dominant_component == "stop_component"
    assert daily.stop_reason_available is False
    assert daily.planned_stop_distinguishable is False
    assert daily.stop_interpretation_warning
    assert daily.plc_metrics["working_sample_count"] == 24
    assert daily.plc_metrics["working_ratio"] == 0.8
    assert daily.plc_metrics["working_speed_cv"] == 0.12
    assert daily.plc_metrics["cutterhead_power_proxy"] == 12345.0
    assert round(0.45 * daily.grade_score_component + 0.45 * daily.hazard_component + 0.10 * daily.confidence_component, 6) == round(daily.GRS_geo_base, 6)
    assert daily.GRS_available is True
    assert round(daily.grs_term + daily.rai_term + daily.interaction_term, 4) == daily.GRCI

    assert forward.cell_role == "forward_attention"
    assert forward.RAI is None
    assert forward.GRCI_available is False
    assert forward.GRCI is None

    assert background.cell_role == "local_background"
    assert background.GRS_available is False
    assert background.GRS_unavailable_reason == "missing_spatial_relevant_geology_evidence"
    assert background.GRCI_available is False
    assert not high_grci_cells(result) or all(cell["cell_role"] == "daily_review" for cell in high_grci_cells(result))

    pack = build_prompt_evidence_pack(
        date="2023-12-30",
        current_chainage=10.0,
        operation_summary={},
        cluster_summary={},
        gas_summary={},
        construction_state_cells=result,
        forward_profile={},
        high_grci_cells=high_grci_cells(result),
    )
    daily_pack = pack["daily_review_evidence"]["daily_review_cells"][0]
    assert daily_pack["plc_enhanced_metrics"]["working_sample_count"] == 24
    assert "cutterhead_power_proxy" not in daily_pack["plc_enhanced_metrics"]
    forward_pack = pack["forward_attention_evidence"]["forward_attention_cells"][0]
    assert "plc_enhanced_metrics" not in forward_pack


def test_stop_boundary_statement_gets_policy_support():
    grounding = check_claim_grounding(
        [
            {
                "claim_id": "c1",
                "claim_type": "recommendation",
                "text": "当前 PLC 字段未区分计划停机与非计划停机，stop_ratio 仅作为施工响应关注信号，不直接作为异常原因。",
            }
        ],
        prompt_evidence_pack={},
    )
    claim = grounding["claim_results"][0]
    assert claim["grounded"] is True
    assert claim["trace_support_type"] == "policy_support"


def test_method_metrics_contains_required_keys():
    cells = [
        ConstructionStateCell(
            cell_id="cell_0_10",
            cell_role="daily_review",
            RAI=0.4,
            GRS_geo_base=0.6,
            GRS_available=True,
            GRCI=0.5,
            GRCI_available=True,
        )
    ]
    metrics = daily_pipeline._method_metrics(
        cells,
        {"date": "2023-12-30", "daily_chainage_min": 1, "daily_chainage_max": 2, "daily_advance_m": 1, "current_chainage": 2},
        {"spatial_relevant_evidence_df": pd.DataFrame(), "excluded_evidence_df": pd.DataFrame()},
        quality_summary={"claim_count": 3, "grounded_claim_count": 2, "unsupported_claim_count": 1, "grounding_rate": 0.67, "quality_score": 88},
        trace_summary={"trace_coverage": 0.5},
        warnings=["w"],
        passed=True,
        priority_cells={"review_cells": [{}], "high_priority_cells": [], "medium_priority_cells": [{}], "low_priority_cells": []},
        quality={"error_type_counts": {"E1_UNSUPPORTED_CLAIM": 1}, "violations": [{"error_type": "E9_SOURCE_ROLE_CONFUSION"}]},
        trace={"support_type_distribution": {"none": 2}},
    )
    for key in [
        "date",
        "daily_chainage_min",
        "daily_chainage_max",
        "daily_advance_m",
        "current_chainage",
        "time_valid_evidence_count",
        "spatial_relevant_evidence_count",
        "excluded_by_distance_evidence_count",
        "excluded_by_time_evidence_count",
        "construction_state_cell_count",
        "daily_review_cell_count",
        "forward_attention_cell_count",
        "local_background_cell_count",
        "RAI_available_count",
        "GRS_available_count",
        "GRCI_available_count",
        "review_cell_count",
        "high_priority_cell_count",
        "medium_priority_cell_count",
        "low_priority_cell_count",
        "claim_count",
        "grounded_claim_count",
        "unsupported_claim_count",
        "grounding_rate",
        "trace_coverage",
        "quality_score",
        "warnings",
        "passed",
        "error_type_counts",
        "support_type_distribution",
        "trace_support_none_count",
        "role_consistency_violation_count",
    ]:
        assert key in metrics
    assert metrics["trace_support_none_count"] == 2
    assert metrics["role_consistency_violation_count"] == 1


def test_report_api_returns_core_fields(monkeypatch):
    fake = _fake_result()
    monkeypatch.setattr(report_routes, "run_daily_report_pipeline", lambda date, use_llm=True, **kwargs: fake)

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
        "generation_mode",
        "llm_summary",
        "warnings",
    }


def test_report_debug_api_returns_intermediate_fields(monkeypatch):
    fake = _fake_result()
    monkeypatch.setattr(report_routes, "run_daily_report_pipeline", lambda date, use_llm=True, **kwargs: fake)

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
        "generation_mode",
        "llm_generation",
    ]:
        assert key in payload


def test_run_daily_report_pipeline_no_llm_does_not_call_llm(monkeypatch):
    _patch_minimal_pipeline(monkeypatch)

    def fail_if_called(**_kwargs):
        raise AssertionError("LLM should not be called when use_llm=False")

    monkeypatch.setattr(daily_pipeline, "generate_llm_report", fail_if_called)
    result = daily_pipeline.run_daily_report_pipeline("2023-01-01", use_llm=False)
    assert result.report_text
    assert result.generation_mode == "template"
    assert result.llm_generation == {}


def test_run_daily_report_pipeline_llm_generation_uses_optional_mode(monkeypatch):
    _patch_minimal_pipeline(monkeypatch)
    monkeypatch.setattr(
        daily_pipeline,
        "generate_llm_report",
        lambda **_kwargs: {
            "report_final": "mock llm report",
            "prompt": "mock llm prompt",
            "quality_after_revision": {
                "ok": True,
                "score": 100,
                "stats": {
                    "claim_count": 0,
                    "grounded_claim_count": 0,
                    "unsupported_claim_count": 0,
                    "grounding_rate": 0.0,
                },
                "grounding_summary": {
                    "claim_count": 0,
                    "grounded_claim_count": 0,
                    "unsupported_claim_count": 0,
                    "grounding_rate": 0.0,
                },
                "claim_results": [],
            },
            "trace_after_revision": {"trace_available": True},
            "warnings": ["mock llm warning"],
            "summary": {"passed": True},
        },
    )
    result = daily_pipeline.run_daily_report_pipeline("2023-01-01", use_llm=True)
    assert result.report_text == "mock llm report"
    assert result.prompt_text == "mock llm prompt"
    assert result.generation_mode == "evidence_pack_llm"
    assert "mock llm warning" in result.warnings


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
        generation_mode="template",
        llm_generation={},
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
