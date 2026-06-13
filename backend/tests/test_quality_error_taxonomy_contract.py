from llm.report_error_taxonomy import ERROR_TYPES
from llm.report_grounding_checker import check_claim_grounding
from llm.report_quality_checker import check_report_quality


def test_quality_output_contains_error_taxonomy_fields():
    quality = check_report_quality(
        "GRCI 是灾害概率。停机直接说明异常原因。",
        prompt_evidence_pack={},
        include_claim_results=True,
    )

    assert "error_type_counts" in quality
    assert "violations_by_error_type" in quality
    assert "unsupported_by_claim_type" in quality
    for error_type in ERROR_TYPES:
        assert error_type in quality["error_type_counts"]
        assert error_type in quality["violations_by_error_type"]
    assert quality["error_type_counts"]["E3_GRCI_AS_PROBABILITY"] >= 1
    assert quality["error_type_counts"]["E13_STOP_REASON_OVERINTERPRETATION"] >= 1


def test_method_boundary_statement_gets_e12_policy_support():
    grounding = check_claim_grounding(
        [
            {
                "claim_id": "boundary",
                "claim_type": "recommendation",
                "text": "当前 PLC 字段未区分计划停机与非计划停机，stop_ratio 仅作为施工响应关注信号，不直接作为异常原因。",
            }
        ],
        prompt_evidence_pack={},
    )
    quality = check_report_quality(
        "当前 PLC 字段未区分计划停机与非计划停机，stop_ratio 仅作为施工响应关注信号，不直接作为异常原因。",
        prompt_evidence_pack={},
        include_claim_results=True,
    )

    assert grounding["claim_results"][0]["trace_support_type"] == "policy_support"
    assert any(
        item.get("error_type") == "E12_METHOD_BOUNDARY_STATEMENT"
        for item in quality.get("claim_results") or []
    )


def test_forward_evidence_boundary_statement_gets_method_boundary_policy_support():
    text = "如无当日可用掌子面素描，不把前方证据写成已揭露事实。"
    grounding = check_claim_grounding(
        [
            {
                "claim_id": "boundary-forward",
                "claim_type": "forward_segment",
                "text": text,
            }
        ],
        prompt_evidence_pack={},
    )
    quality = check_report_quality(
        text,
        prompt_evidence_pack={},
        include_claim_results=True,
    )

    claim = grounding["claim_results"][0]
    assert claim["claim_type"] == "method_boundary"
    assert claim["grounded"] is True
    assert claim["support_type"] == "recommendation_policy"
    assert claim["trace_support_type"] == "policy_support"

    quality_claims = quality.get("claim_results") or []
    assert quality["unsupported_claim_count"] == 0
    assert any(
        item.get("claim_type") == "method_boundary"
        and item.get("support_type") == "recommendation_policy"
        and item.get("trace_support_type") == "policy_support"
        and item.get("error_type") == "E12_METHOD_BOUNDARY_STATEMENT"
        for item in quality_claims
    )
    assert quality["error_type_counts"]["E11_HEADING_FALSE_POSITIVE"] == 0


def test_real_unsupported_technical_claim_does_not_get_policy_support():
    grounding = check_claim_grounding(
        [
            {
                "claim_id": "unsupported-forward",
                "claim_type": "forward_segment",
                "text": "前方 0-10m 已经发生塌方。",
                "relative_range": "0-10m",
                "hazards": ["塌方"],
            }
        ],
        prompt_evidence_pack={},
    )

    claim = grounding["claim_results"][0]
    assert claim["grounded"] is False
    assert claim["support_type"] == "none"
    assert claim["trace_support_type"] == "none"
    assert claim["claim_type"] == "forward_segment"


def test_grci_probability_and_stop_cause_still_get_strict_error_types():
    quality = check_report_quality(
        "GRCI 表示灾害概率。stop_ratio 直接作为异常原因。",
        prompt_evidence_pack={},
        include_claim_results=True,
    )

    assert quality["error_type_counts"]["E3_GRCI_AS_PROBABILITY"] >= 1
    assert quality["error_type_counts"]["E13_STOP_REASON_OVERINTERPRETATION"] >= 1
