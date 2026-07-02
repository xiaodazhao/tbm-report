from llm.evidence_pack import build_prompt_evidence_pack
from llm.report_claim_extractor import extract_report_claims
from llm.report_grounding_checker import check_claim_grounding
from llm.report_quality_checker import check_report_quality
from llm.report_trace_builder import build_report_trace, summarize_report_trace
from schemas.pipeline import ConstructionStateCell


def test_evidence_pack_exports_atomic_evidence_units_without_dropping_legacy_cells():
    cell = ConstructionStateCell(
        cell_id="cell_100_110",
        cell_start=100.0,
        cell_end=110.0,
        cell_center=105.0,
        cell_role="daily_review",
        is_excavated_today=True,
        has_plc_response=True,
        has_geology_evidence=True,
        RAI=0.4,
        GRS_geo_base=0.6,
        GRS_available=True,
        GRCI=0.5,
        GRCI_available=True,
        coupling_level="medium",
        main_hazards=["broken_rock"],
        supporting_evidence_ids=["ev-1"],
        source_trace=[{"evidence_id": "ev-1", "source_type": "HSP", "evidence_role": "prediction"}],
    )

    pack = build_prompt_evidence_pack(
        date="2023-12-30",
        current_chainage=110.0,
        operation_summary={},
        cluster_summary={},
        gas_summary={},
        construction_state_cells=[cell],
        forward_profile={},
        high_grci_cells=[cell.model_dump()],
        scope_summary={"date": "2023-12-30", "daily_chainage_min": 100.0, "daily_chainage_max": 110.0},
    )

    assert pack["geology_evidence"]["key_cells"]
    assert pack["geology_evidence"]["selected_cells"]
    assert pack["evidence_units"]
    unit = pack["evidence_units"][0]
    assert unit["role"] == "daily_review"
    assert unit["entity"] == "excavated_cell"
    assert unit["spatial_scope"]["cell_id"] == "cell_100_110"
    assert unit["source_ref"]["supporting_evidence_ids"] == ["ev-1"]


def test_claim_extractor_keeps_legacy_fields_and_adds_structured_claim_fields():
    claims = extract_report_claims("2023-12-30 PLC daily advance is 15.0 m. GRCI is not a disaster probability.")

    assert claims
    claim = claims[0]
    assert claim["text"] == claim["claim_text"]
    assert claim["sentence_index"] == claim["source_sentence_index"]
    assert "entity" in claim
    assert "value" in claim
    assert "unit" in claim
    assert "time_scope" in claim
    assert "spatial_scope_detail" in claim
    assert "claim_role" in claim
    assert "certainty" in claim


def test_grounding_and_trace_include_support_status_mismatch_and_confidence():
    grounding = check_claim_grounding(
        [
            {
                "claim_id": "c1",
                "claim_type": "gas",
                "claim_text": "CH4 concentration is 123",
                "text": "CH4 concentration is 123",
                "value": 123,
                "unit": "m",
                "gases": ["CH4"],
                "claim_role": "general_report_claim",
            }
        ],
        prompt_evidence_pack={},
    )
    result = grounding["claim_results"][0]
    assert result["grounded"] is False
    assert result["support_status"] == "unsupported"
    assert result["mismatch_type"] in {"missing_evidence", "numeric_or_metric_mismatch", "overclaim"}
    assert result["confidence"] == 0.0
    assert result["aligned_evidence_ids"] == []

    trace = build_report_trace(
        "CH4 concentration is 123",
        grounding_result=grounding,
    )
    traced = trace["traced_claims"][0]
    assert traced["support_status"] == "unsupported"
    assert traced["mismatch_type"]
    assert "support_status_distribution" in trace
    assert summarize_report_trace(trace)["mismatch_type_distribution"]


def test_quality_exports_severity_and_required_fact_coverage_without_changing_score_field():
    quality = check_report_quality(
        "Report date 2023-12-30. PLC daily advance is 15.0 m.",
        prompt_evidence_pack={
            "report_scope": {
                "date": "2023-12-30",
                "daily_plc_range": {
                    "start_chainage": 1014601.0,
                    "end_chainage": 1014616.0,
                    "daily_advance_m": 15.0,
                },
            }
        },
        include_claim_results=True,
    )

    assert "quality_score" in quality
    assert "error_severity_distribution" in quality
    assert "weighted_error_penalty" in quality
    assert "engineering_significant_error_count" in quality
    assert "required_fact_coverage" in quality
    assert quality["required_fact_coverage"]["required_fact_count"] >= 2
    assert quality["stats"]["required_fact_count"] == quality["required_fact_coverage"]["required_fact_count"]
