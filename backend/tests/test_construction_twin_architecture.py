from __future__ import annotations

from llm.evidence_pack import build_evidence_pack_from_twin
from llm.state_interpreter import interpret_cell_state, interpret_daily_twin_summary
from llm.twin_boundary_checker import check_twin_boundary_violations
from schemas.pipeline import ConstructionStateCell
from twin.construction_twin import build_daily_construction_twin
from twin.query import get_forward_attention_cells, get_high_grci_cells, summarize_twin


def _cell(
    cell_id: str,
    role: str,
    *,
    start: float,
    end: float,
    rai: float | None = None,
    grci: float | None = None,
    grci_available: bool = False,
    is_forward: bool = False,
) -> ConstructionStateCell:
    return ConstructionStateCell(
        cell_id=cell_id,
        cell_start=start,
        cell_end=end,
        cell_center=(start + end) / 2,
        cell_role=role,
        RAI=rai,
        GRS_geo_base=0.6,
        GRS_available=True,
        GRCI=grci,
        GRCI_available=grci_available,
        GRCI_source="cell_grs_rai_formula_v1" if grci_available else "unavailable",
        GRCI_unavailable_reason=None if grci_available else "missing_plc_response",
        coupling_level="medium" if grci_available else "unavailable",
        has_plc_response=rai is not None,
        has_geology_evidence=True,
        is_excavated_today=role == "daily_review",
        is_forward_cell=is_forward,
        main_hazards=["围岩破碎"],
        supporting_evidence_ids=[f"ev-{cell_id}"],
        source_trace=[{"evidence_id": f"ev-{cell_id}", "source_type": "HSP"}],
        plc_metrics={
            "working_sample_count": 20,
            "working_ratio": 0.8,
            "working_metrics_source": "paper_based_preprocessing_steady_state_alias",
            "working_speed_cv": 0.1,
            "working_torque_cv": 0.2,
            "penetration_mean": 0.5,
            "thrust_per_penetration": 1000.0,
            "torque_per_penetration": 200.0,
            "steady_state_available": True,
            "steady_sample_count": 18,
            "steady_ratio": 0.72,
            "steady_speed_cv": 0.1,
            "steady_torque_cv": 0.2,
            "steady_thrust_per_penetration": 1000.0,
            "steady_torque_per_penetration": 200.0,
        } if role == "daily_review" else {},
        trace_completeness=1.0,
    )


def test_daily_construction_twin_separates_roles_and_strips_forward_grci():
    review = _cell("cell_0_10", "daily_review", start=0, end=10, rai=0.4, grci=0.52, grci_available=True)
    forward = _cell("cell_10_20", "forward_attention", start=10, end=20, is_forward=True)
    twin = build_daily_construction_twin(
        date="2023-12-30",
        construction_state_cells=[review, forward],
        high_grci_cells=[review.model_dump(), forward.model_dump()],
        scope_summary={"current_chainage": 10.0, "cell_length_m": 10.0},
    )

    assert len(twin.cells) == 2
    assert len(twin.daily_review_cells) == 1
    assert len(twin.forward_attention_cells) == 1
    assert get_high_grci_cells(twin)[0]["cell_id"] == "cell_0_10"
    forward_view = get_forward_attention_cells(twin)[0]
    assert forward_view.coupling_state["GRCI"] is None
    assert forward_view.coupling_state["GRCI_available"] is False
    assert summarize_twin(twin)["daily_review_cell_count"] == 1


def test_evidence_pack_from_twin_keeps_forward_out_of_grci_and_adds_governance():
    review = _cell("cell_0_10", "daily_review", start=0, end=10, rai=0.4, grci=0.52, grci_available=True)
    forward = _cell("cell_10_20", "forward_attention", start=10, end=20, is_forward=True)
    forward.speed_mean = 8.0
    forward.thrust_mean = 1200.0
    forward.torque_mean = 300.0
    forward.plc_metrics = {
        "working_sample_count": 12,
        "working_ratio": 0.6,
        "working_speed_cv": 0.2,
        "working_thrust_cv": 0.3,
        "working_torque_cv": 0.4,
        "penetration_mean": 5.0,
        "cutterhead_power_proxy": 9000.0,
        "thrust_per_penetration": 240.0,
        "torque_per_penetration": 60.0,
    }
    twin = build_daily_construction_twin(
        date="2023-12-30",
        construction_state_cells=[review, forward],
        high_grci_cells=[review.model_dump()],
        scope_summary={"current_chainage": 10.0, "cell_length_m": 10.0},
    )

    pack = build_evidence_pack_from_twin(twin=twin, high_grci_cells=[review.model_dump()])

    assert pack["evidence_pack_source"] == "daily_construction_twin"
    assert pack["geology_evidence"]["key_cells"] == pack["geology_evidence"]["selected_cells"]
    assert "GRCI" in pack["evidence_governance"]["role_rules"]["forward_attention"]["cannot_use"]
    daily_metrics = pack["daily_review_evidence"]["daily_review_cells"][0]["plc_enhanced_metrics"]
    assert daily_metrics["working_sample_count"] == 20
    assert daily_metrics["working_metrics_source"] == "paper_based_preprocessing_steady_state_alias"
    assert daily_metrics["steady_sample_count"] == 18
    assert "thrust_per_penetration" not in daily_metrics
    assert "steady_thrust_per_penetration" in daily_metrics
    forward_cell = pack["forward_attention_evidence"]["forward_attention_cells"][0]
    assert "GRCI" not in forward_cell
    assert "GRCI_available" not in forward_cell
    assert "plc_enhanced_metrics" not in forward_cell
    for field in [
        "speed_mean",
        "thrust_mean",
        "torque_mean",
        "working_sample_count",
        "working_ratio",
        "thrust_per_penetration",
        "torque_per_penetration",
    ]:
        assert field not in forward_cell


def test_state_interpreter_and_twin_boundary_checker_are_template_only():
    forward = _cell("cell_10_20", "forward_attention", start=10, end=20, is_forward=True)
    twin = build_daily_construction_twin(
        date="2023-12-30",
        construction_state_cells=[forward],
        scope_summary={"current_chainage": 10.0, "cell_length_m": 10.0},
    )
    explanation = interpret_cell_state(twin.forward_attention_cells[0])
    summary = interpret_daily_twin_summary(twin)
    assert "不使用 GRCI" in explanation["interpretation"]
    assert summary["date"] == "2023-12-30"

    violation = check_twin_boundary_violations("前方 GRCI 显示灾害概率较高。")
    assert violation["has_violation"] is True
    assert violation["violation_count"] >= 1

    ok = check_twin_boundary_violations("当前掌子面前方关注提示仅表示需要关注和现场复核。")
    assert ok["has_violation"] is False

    policy = check_twin_boundary_violations("前方关注提示不表示已发生事实，也不得把 GRCI 写成灾害概率。")
    assert policy["has_violation"] is False
