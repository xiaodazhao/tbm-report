from __future__ import annotations

import json
from types import SimpleNamespace

import pandas as pd

from coupling.grs_rai_grci import build_construction_state_cells
from geology_v2.evidence_projector import project_evidence_to_cells
from llm.evidence_pack import build_prompt_evidence_pack
from pipeline.evidence_scope import build_scope_cells, build_scope_summary
import pipeline.daily_report_pipeline as daily_pipeline
from scripts.analyze_batch_metrics import analyze_batch_metrics
from scripts.analyze_cell_size_sensitivity import analyze_cell_size_sensitivity
from scripts.analyze_generation_modes import analyze_generation_modes
from scripts.analyze_grci_weight_sensitivity import analyze_grci_weight_sensitivity
from scripts.export_allowed_claims import build_allowed_claims


def test_projection_exports_overlap_ratio_between_zero_and_one():
    cells = pd.DataFrame([{"cell_id": "cell_0_10", "cell_start": 0.0, "cell_end": 10.0, "cell_center": 5.0}])
    evidence = pd.DataFrame(
        [
            {
                "evidence_id": "ev-1",
                "source_type_norm": "HSP",
                "spatial_type": "segment",
                "start_chainage": 2.0,
                "end_chainage": 8.0,
                "source_reliability": 1.0,
                "evidence_strength": 1.0,
            }
        ]
    )
    out = project_evidence_to_cells(cells, evidence)
    assert out["evidence_overlap_length"].iloc[0] == 6.0
    assert out["evidence_overlap_ratio"].iloc[0] == 0.6
    assert out["evidence_overlap_ratio"].between(0, 1).all()


def test_construction_cells_export_forward_distance_and_trace_completeness():
    cells_df = pd.DataFrame(
        [
            {"cell_id": "cell_0_10", "cell_start": 0.0, "cell_end": 10.0, "cell_center": 5.0},
            {"cell_id": "cell_10_20", "cell_start": 10.0, "cell_end": 20.0, "cell_center": 15.0},
        ]
    )
    response_df = pd.DataFrame([{"cell_id": "cell_0_10", "RAI": 0.4, "cell_start": 0.0, "cell_end": 10.0, "cell_center": 5.0}])
    geo_df = pd.DataFrame(
        [
            {"cell_id": "cell_0_10", "GRS_geo_base": 0.5, "GRS_component_method": "fused", "supporting_evidence_ids": ["ev-1"]},
            {"cell_id": "cell_10_20", "GRS_geo_base": 0.6, "GRS_component_method": "fused", "supporting_evidence_ids": ["ev-2"]},
        ]
    )
    cell_evidence = pd.DataFrame(
        [
            {"cell_id": "cell_10_20", "evidence_id": "ev-2", "source_type_norm": "HSP", "evidence_overlap_length": 5.0, "evidence_overlap_ratio": 0.5, "source_reliability": 0.8}
        ]
    )
    normalized = pd.DataFrame(
        [
            {"evidence_id": "ev-1", "source_type_norm": "HSP", "start_chainage": 0.0, "end_chainage": 10.0, "report_id": "r1"},
            {"evidence_id": "ev-2", "source_type_norm": "HSP", "start_chainage": 12.0, "end_chainage": 18.0, "report_id": "r2"},
        ]
    )
    result = build_construction_state_cells(
        cells_df=cells_df,
        cell_response_df=response_df,
        geo_states_df=geo_df,
        cell_evidence_df=cell_evidence,
        normalized_evidence_df=normalized,
        current_chainage=10.0,
        day_start_chainage=0.0,
        day_end_chainage=10.0,
        scope_summary={
            "daily_excavated_scope": {"start": 0.0, "end": 10.0},
            "forward_scope": {"start": 10.0, "end": 20.0},
            "local_background_scope": {"start": None, "end": None},
            "report_scope": {"start": 0.0, "end": 20.0},
        },
    )
    by_id = {cell.cell_id: cell for cell in result}
    forward = by_id["cell_10_20"]
    assert forward.GRCI_available is False
    assert forward.distance_to_face_m == 5.0
    assert forward.forward_distance_band == "near_forward"
    assert forward.forward_distance_weight == 1.0
    assert forward.max_overlap_ratio == 0.5
    assert forward.trace_completeness is not None


def test_evidence_pack_adds_selection_score_without_using_forward_grci():
    forward_cell = _cell("cell_10_20", role="forward_attention", grs=0.6, rai=None, grci=None)
    forward_cell.is_forward_cell = True
    forward_cell.forward_distance_weight = 1.0
    forward_cell.trace_completeness = 1.0
    pack = build_prompt_evidence_pack(
        date="2023-12-30",
        current_chainage=10.0,
        operation_summary={},
        cluster_summary={},
        gas_summary={},
        construction_state_cells=[forward_cell],
        forward_profile={},
        high_grci_cells=[],
    )
    forward_pack = pack["forward_attention_evidence"]["forward_attention_cells"][0]
    assert forward_pack["selection_score"] is not None
    assert forward_pack["selection_method"] == "forward_attention_selection_score_v1_no_grci"
    assert forward_pack["GRCI_available"] is False if "GRCI_available" in forward_pack else True
    assert "GRCI" not in forward_pack or forward_pack["GRCI"] is None


def test_batch_analysis_scripts_tolerate_minimal_exports(tmp_path):
    date_dir = tmp_path / "batch" / "2023-12-30"
    date_dir.mkdir(parents=True)
    _write_json(date_dir / "method_metrics.json", {"date": "2023-12-30", "passed": True, "quality_score": 100, "grounding_rate": 1.0, "GRCI_available_count": 1})
    _write_json(date_dir / "quality.json", {"error_type_counts": {"E14_ALIGNED_SCOPE_AS_ACTUAL_ADVANCE": 0}, "grounding_summary": {"unsupported_claim_count": 0}})
    _write_json(date_dir / "trace.json", {"trace_coverage": 1.0})
    _write_json(date_dir / "summary.json", {"date": "2023-12-30", "passed": True})
    payload = analyze_batch_metrics(input_dir=tmp_path / "batch", out_dir=tmp_path / "analysis")
    assert payload["summary"]["passed_count"] == 1
    assert (tmp_path / "analysis" / "batch_method_metrics_summary.csv").exists()


def test_generation_mode_analysis_compares_modes(tmp_path):
    for mode in ["template", "revision"]:
        date_dir = tmp_path / mode / "2023-12-30"
        date_dir.mkdir(parents=True)
        (date_dir / "report.txt").write_text("report text", encoding="utf-8")
        _write_json(date_dir / "quality.json", {"score": 100, "grounding_summary": {"grounding_rate": 1.0, "unsupported_claim_count": 0}})
        _write_json(date_dir / "trace.json", {"trace_coverage": 1.0})
        _write_json(date_dir / "summary.json", {"passed": True})
    payload = analyze_generation_modes(mode_dirs={"template": tmp_path / "template", "revision": tmp_path / "revision"}, out_dir=tmp_path / "out")
    assert payload["summary"]["mode_count"] == 2
    assert (tmp_path / "out" / "generation_mode_comparison.csv").exists()


def test_weight_sensitivity_script_recomputes_only_review_cells(tmp_path):
    date_dir = tmp_path / "exports" / "2023-12-30"
    date_dir.mkdir(parents=True)
    pd.DataFrame(
        [
            {"cell_id": "a", "cell_role": "daily_review", "is_forward_cell": False, "GRS_geo_base": 0.6, "RAI": 0.4, "GRCI": 0.5, "GRCI_available": True},
            {"cell_id": "b", "cell_role": "forward_attention", "is_forward_cell": True, "GRS_geo_base": 0.8, "RAI": None, "GRCI": None, "GRCI_available": False},
        ]
    ).to_csv(date_dir / "construction_state_cells.csv", index=False)
    payload = analyze_grci_weight_sensitivity(input_dir=tmp_path / "exports", out_dir=tmp_path / "weights", top_k=1)
    assert payload["summary"]["eligible_cell_count"] == 1
    assert (tmp_path / "weights" / "grci_topk_stability.csv").exists()


def test_cell_size_sensitivity_records_stable_plc_range(monkeypatch, tmp_path):
    import scripts.analyze_cell_size_sensitivity as mod

    monkeypatch.setattr(mod, "run_daily_report_pipeline", lambda date, **kwargs: _fake_result(kwargs["cell_size_m"]))
    payload = analyze_cell_size_sensitivity(dates=["2023-12-30"], cell_sizes=[5.0, 10.0], out_dir=tmp_path)
    assert payload["summary"]["passed_count"] == 2
    assert all(row["daily_plc_range_stable"] for row in payload["comparison"])


def test_allowed_claims_export_is_optional_and_policy_bounded():
    pack = {
        "report_scope": {"daily_plc_range": {"start_chainage": 1.0, "end_chainage": 2.0, "daily_advance_m": 1.0}},
        "generation_constraints": ["GRCI 不是灾害概率"],
        "forward_attention_evidence": {"forward_attention_cells": [{"cell_id": "f", "supporting_evidence_ids": ["ev"], "source_trace": []}]},
    }
    claims = build_allowed_claims(pack)
    assert any(claim["claim_type"] == "actual_fact" for claim in claims)
    assert any(claim["claim_type"] == "method_boundary" for claim in claims)
    assert any("Do not describe as occurred fact" in claim["forbidden_usage"] for claim in claims)


def _cell(cell_id: str, *, role: str, grs: float | None, rai: float | None, grci: float | None):
    from schemas.pipeline import ConstructionStateCell

    return ConstructionStateCell(
        cell_id=cell_id,
        cell_role=role,
        GRS_geo_base=grs,
        GRS_available=grs is not None,
        RAI=rai,
        GRCI=grci,
        GRCI_available=grci is not None,
        has_geology_evidence=grs is not None,
        supporting_evidence_ids=["ev-1"],
        source_trace=[{"evidence_id": "ev-1", "source_type": "HSP", "start_chainage": 10.0, "report_id": "r"}],
    )


def _fake_result(cell_size: float):
    return SimpleNamespace(
        scope_summary={
            "daily_plc_range": {"start_chainage": 1.0, "end_chainage": 2.0},
            "daily_excavated_scope": {"start": 0.0, "end": cell_size},
            "daily_advance_m": 1.0,
        },
        construction_state_cells=[SimpleNamespace(GRCI_available=True)],
        high_grci_cells=[{}],
        quality_summary={"grounding_rate": 1.0, "unsupported_claim_count": 0},
        method_metrics={"GRCI_available_count": 1},
        warnings=[],
    )


def _write_json(path, payload):
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
