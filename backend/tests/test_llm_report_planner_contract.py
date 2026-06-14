from __future__ import annotations

from llm.evidence_pack import build_prompt_evidence_pack
from llm.llm_report_generator import generate_llm_report, normalize_generation_mode
from llm.llm_report_planner import (
    build_rule_based_report_plan,
    generate_report_plan,
    parse_report_plan,
    validate_report_plan,
)
from schemas.pipeline import ConstructionStateCell


def test_planner_generates_valid_report_plan():
    result = generate_report_plan(
        date="2023-12-30",
        prompt_evidence_pack=_pack(),
        mock_llm=True,
    )

    assert result["planner_enabled"] is True
    assert result["planner_provider"] == "mock"
    assert result["plan_validation_passed"] is True
    assert result["plan_fallback_used"] is False
    assert len(result["report_plan"]["sections"]) == 7


def test_report_plan_includes_required_section_boundaries():
    plan = build_rule_based_report_plan(date="2023-12-30", prompt_evidence_pack=_pack())

    section_ids = {item["section_id"] for item in plan["sections"]}
    assert section_ids == {
        "section_1",
        "section_2",
        "section_3",
        "section_4",
        "section_5",
        "section_6",
        "section_7",
    }

    forward_section = _section(plan, "section_6")
    assert "RAI" not in forward_section["allowed_metrics"]
    assert "GRCI" not in forward_section["allowed_metrics"]
    assert "RAI" in forward_section["forbidden_metrics"]
    assert "GRCI" in forward_section["forbidden_metrics"]

    review_section = _section(plan, "section_5")
    assert review_section["allowed_cell_roles"] == ["daily_review"]
    assert "GRCI" in review_section["allowed_metrics"]


def test_local_background_is_not_planned_as_daily_abnormal():
    plan = build_rule_based_report_plan(date="2023-12-30", prompt_evidence_pack=_pack())

    assert validate_report_plan(plan, prompt_evidence_pack=_pack())["passed"] is True
    plan_text = str(plan)
    assert "local_background_as_daily_abnormal" in plan_text
    assert "local_background 只作为背景上下文" in plan_text


def test_invalid_planner_json_fails_parse_and_can_fallback():
    try:
        parse_report_plan("not json")
    except ValueError as exc:
        assert "JSON" in str(exc) or "json" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("invalid planner JSON should fail")

    fallback = build_rule_based_report_plan(date="2023-12-30", prompt_evidence_pack=_pack())
    assert validate_report_plan(fallback, prompt_evidence_pack=_pack())["passed"] is True


def test_validation_fails_when_forward_section_allows_grci():
    plan = build_rule_based_report_plan(date="2023-12-30", prompt_evidence_pack=_pack())
    _section(plan, "section_6")["allowed_metrics"].append("GRCI")

    validation = validate_report_plan(plan, prompt_evidence_pack=_pack())

    assert validation["passed"] is False
    assert any(item["code"] == "forward_attention_allows_rai_or_grci" for item in validation["violations"])


def test_planner_generation_mode_builds_report_draft():
    result = generate_llm_report(
        date="2023-12-30",
        prompt_evidence_pack=_pack(),
        twin_state={},
        generation_mode="evidence_pack_planner_llm",
        mock_llm=True,
    )

    assert result["generation_mode"] == "evidence_pack_planner_llm"
    assert result["summary"]["planner_enabled"] is True
    assert result["summary"]["plan_validation_passed"] is True
    assert result["llm_report_plan"]
    assert result["report_draft"]


def test_planner_revision_generation_mode_builds_final_report():
    result = generate_llm_report(
        date="2023-12-30",
        prompt_evidence_pack=_pack(),
        twin_state={},
        generation_mode="evidence_pack_planner_llm_with_revision",
        mock_llm=True,
        enable_revision=True,
    )

    assert result["revision_enabled"] is True
    assert result["revision_executed"] is True
    assert result["summary"]["planner_enabled"] is True
    assert result["report_final"]


def test_existing_generation_modes_remain_supported():
    assert normalize_generation_mode("template") == "template"
    assert normalize_generation_mode("evidence_pack_llm") == "evidence_pack_llm"
    assert normalize_generation_mode("evidence_pack_llm_with_revision") == "evidence_pack_llm_with_revision"
    assert normalize_generation_mode("evidence_pack_planner_llm") == "evidence_pack_planner_llm"
    assert normalize_generation_mode("evidence_pack_planner_llm_with_revision") == "evidence_pack_planner_llm_with_revision"


def _section(plan: dict, section_id: str) -> dict:
    for section in plan["sections"]:
        if section["section_id"] == section_id:
            return section
    raise AssertionError(f"missing section {section_id}")


def _pack() -> dict:
    daily = ConstructionStateCell(
        cell_id="cell_100_110",
        cell_start=100,
        cell_end=110,
        cell_center=105,
        RAI=0.4,
        GRS_geo_base=0.6,
        GRCI=0.51,
        GRCI_available=True,
        GRCI_source="cell_grs_rai_formula_v1",
        coupling_level="medium",
        has_plc_response=True,
        has_geology_evidence=True,
        is_excavated_today=True,
        cell_role="daily_review",
        main_hazards=["掉块"],
        supporting_evidence_ids=["ev-hsp-1"],
        source_trace=[{"evidence_id": "ev-hsp-1", "source_type": "HSP", "evidence_role": "prediction"}],
    )
    forward = ConstructionStateCell(
        cell_id="cell_110_120",
        cell_start=110,
        cell_end=120,
        cell_center=115,
        GRS_geo_base=0.5,
        GRS_available=True,
        GRCI_available=False,
        GRCI_unavailable_reason="forward_attention_cell_no_grci",
        has_geology_evidence=True,
        is_forward_cell=True,
        cell_role="forward_attention",
        main_hazards=["裂隙发育"],
        supporting_evidence_ids=["ev-hsp-2"],
        source_trace=[{"evidence_id": "ev-hsp-2", "source_type": "HSP", "evidence_role": "prediction"}],
    )
    background = ConstructionStateCell(
        cell_id="cell_90_100",
        cell_start=90,
        cell_end=100,
        cell_center=95,
        GRS_geo_base=0.2,
        GRS_available=True,
        GRCI_available=False,
        GRCI_unavailable_reason="local_background_cell_no_grci",
        has_geology_evidence=True,
        cell_role="local_background",
        main_hazards=["围岩破碎"],
        supporting_evidence_ids=["ev-tsp-1"],
        source_trace=[{"evidence_id": "ev-tsp-1", "source_type": "TSP", "evidence_role": "prediction"}],
    )
    return build_prompt_evidence_pack(
        date="2023-12-30",
        current_chainage=110,
        operation_summary={"operation_mode_summary": {"work_total_min": 10, "stop_total_min": 2}},
        cluster_summary={"has_cluster": True, "n_states": 2},
        gas_summary={"exceed_summary": {"has_exceedance": False, "exceed_gases": []}},
        construction_state_cells=[background, daily, forward],
        forward_profile={"profile": [{"range_label": "0-10m"}]},
        high_grci_cells=[
            {
                "cell_id": daily.cell_id,
                "GRS_geo_base": daily.GRS_geo_base,
                "RAI": daily.RAI,
                "GRCI": daily.GRCI,
                "GRCI_available": True,
                "coupling_level": "medium",
                "main_hazards": daily.main_hazards,
                "supporting_evidence_ids": daily.supporting_evidence_ids,
                "is_excavated_today": True,
                "is_forward_cell": False,
            }
        ],
        scope_summary={
            "date": "2023-12-30",
            "current_chainage": 1014616.0,
            "daily_chainage_min": 1014601.0,
            "daily_chainage_max": 1014616.0,
            "daily_advance_m": 15.0,
            "daily_excavated_scope": {"start": 1014600.0, "end": 1014620.0},
            "forward_scope": {"start": 1014620.0, "end": 1014650.0},
            "local_background_scope": {"start": 1014510.0, "end": 1014600.0},
        },
        excluded_evidence_summary={
            "excluded_evidence_count": 1,
            "excluded_by_distance_evidence_count": 1,
        },
    )
