from __future__ import annotations

from llm.evidence_pack import build_prompt_evidence_pack
from llm.llm_provider import LLMProvider, resolve_llm_provider_config
from llm.llm_report_generator import generate_llm_report
from llm.prompts.report_generation_prompt import build_generation_prompt
from llm.prompts.report_revision_prompt import build_revision_prompt
from schemas.pipeline import ConstructionStateCell


def test_generation_prompt_is_evidence_pack_constrained():
    pack = _pack()
    prompt = build_generation_prompt(pack)

    assert "Prompt Evidence Pack" in prompt
    assert "generation_constraints" in prompt or "方法边界" in prompt
    assert "GRCI 不是灾害概率" in prompt
    assert "stop_ratio 仅作为施工响应关注信号" in prompt
    assert "当前掌子面前方关注提示" in prompt
    assert "前方风险提示" not in prompt
    assert "old-tsp-1013" not in prompt
    assert "excluded_by_distance_evidence_count" in prompt


def test_mock_llm_generation_runs_quality_and_trace():
    result = generate_llm_report(
        date="2023-12-30",
        prompt_evidence_pack=_pack(),
        twin_state={},
        generation_mode="evidence_pack_llm",
        mock_llm=True,
    )

    assert result["generation_mode"] == "evidence_pack_llm"
    assert result["provider"] == "mock"
    assert result["report_draft"]
    assert result["quality_before_revision"]["schema_version"].startswith("report_quality")
    assert result["trace_before_revision"]["schema_version"].startswith("report_trace")
    assert result["summary"]["revision_enabled"] is False


def test_mock_llm_revision_runs_second_quality_trace_pass():
    result = generate_llm_report(
        date="2023-12-30",
        prompt_evidence_pack=_pack(),
        twin_state={},
        generation_mode="evidence_pack_llm_with_revision",
        mock_llm=True,
        enable_revision=True,
    )

    assert result["revision_enabled"] is True
    assert result["revision_executed"] is True
    assert result["revision_prompt"]
    assert result["quality_after_revision"]["schema_version"].startswith("report_quality")
    assert result["trace_after_revision"]["schema_version"].startswith("report_trace")
    assert "error_type_counts" in result["revision_prompt"]


def test_disabled_provider_fails_without_crashing():
    provider = LLMProvider(resolve_llm_provider_config(provider="disabled"))
    result = provider.generate("hello")

    assert result["ok"] is False
    assert result["provider"] == "disabled"
    assert result["error_message"]
    assert "Authorization" not in str(result["request"])


def test_revision_prompt_contains_feedback_and_boundaries():
    prompt = build_revision_prompt(
        prompt_evidence_pack=_pack(),
        draft_report="GRCI 是灾害概率。",
        quality_before_revision={
            "error_type_counts": {"E3_GRCI_PROBABILITY_MISUSE": 1},
            "violations_by_error_type": {"E3_GRCI_PROBABILITY_MISUSE": []},
            "claim_results": [{"claim_text": "GRCI 是灾害概率。", "grounded": False}],
        },
        trace_before_revision={"support_type_distribution": {"none": 1}},
    )

    assert "error_type_counts" in prompt
    assert "GRCI 不是灾害概率" in prompt
    assert "前方风险提示" not in prompt


def _pack():
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
    return build_prompt_evidence_pack(
        date="2023-12-30",
        current_chainage=110,
        operation_summary={"operation_mode_summary": {"work_total_min": 10, "stop_total_min": 2}},
        cluster_summary={"has_cluster": True, "n_states": 2},
        gas_summary={"exceed_summary": {"has_exceedance": False, "exceed_gases": []}},
        construction_state_cells=[daily, forward],
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
            "current_chainage": 110,
            "daily_excavated_scope": {"start": 100, "end": 110},
            "forward_scope": {"start": 110, "end": 140},
            "local_background_scope": {"start": 0, "end": 100},
        },
        excluded_evidence_summary={
            "excluded_evidence_count": 1,
            "excluded_by_distance_evidence_count": 1,
            "examples": [{"evidence_id": "old-tsp-1013", "raw_text_excerpt": "should not enter prompt"}],
        },
    )
