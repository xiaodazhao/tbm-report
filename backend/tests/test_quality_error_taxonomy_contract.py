from llm.report_error_taxonomy import ERROR_TYPES
from llm.report_grounding_checker import check_claim_grounding
from llm.report_quality_checker import check_report_quality
from llm.report_policy import split_sentences


def test_quality_output_contains_error_taxonomy_fields():
    quality = check_report_quality(
        "GRCI 表示灾害概率。stop_ratio 直接说明异常原因。",
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
    text = (
        "当前 PLC 字段未区分计划停机与非计划停机，stop_ratio 仅作为施工响应关注信号，"
        "不直接作为异常原因。"
    )
    grounding = check_claim_grounding(
        [{"claim_id": "boundary", "claim_type": "recommendation", "text": text}],
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
    assert claim["trace_support_type"] == "policy_support"
    assert any(
        item.get("error_type") == "E12_METHOD_BOUNDARY_STATEMENT"
        for item in quality.get("claim_results") or []
    )


def test_forward_evidence_boundary_statement_gets_method_boundary_policy_support():
    text = "如无当日可用掌子面素描，不把前方证据写成已揭露事实。"
    grounding = check_claim_grounding(
        [{"claim_id": "boundary-forward", "claim_type": "forward_segment", "text": text}],
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


def test_gas_none_fragment_is_excluded_from_grounding_denominator():
    quality = check_report_quality(
        "涉及气体为 无。",
        prompt_evidence_pack={},
        include_claim_results=True,
    )

    assert quality["claim_count"] == 0
    assert quality["unsupported_claim_count"] == 0
    assert quality.get("claim_results") == []
    assert quality["stats"]["excluded_non_technical_claim_count"] >= 1


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


def test_standard_m4_sections_are_recognized_as_complete():
    text = "\n\n".join(
        [
            "## 综合摘要\n当前 Evidence Pack 未提供足够证据，不作扩展判断。",
            "## 总体概况\n当前 Evidence Pack 未提供足够证据，不作扩展判断。",
            "## 工况统计\n当前 Evidence Pack 未提供足够证据，不作扩展判断。",
            "## 聚类状态与效率分析\n当前 Evidence Pack 未提供足够证据，不作扩展判断。",
            "## 掌子面与地质揭示\n当前 Evidence Pack 未提供足够证据，不作扩展判断。",
            "## 已掘区段地质-施工响应复核\n当前 Evidence Pack 未提供足够证据，不作扩展判断。",
            "## 气体监测\n当前 Evidence Pack 未提供足够证据，不作扩展判断。",
            "## 前方地质关注提示\n当前 Evidence Pack 未提供足够证据，不作扩展判断。",
            "## 结论与施工建议\n当前 Evidence Pack 未提供足够证据，不作扩展判断。",
        ]
    )

    quality = check_report_quality(text, prompt_evidence_pack={}, include_claim_results=True)

    assert quality["stats"]["section_count"] == 9
    assert quality["stats"]["missing_section_count"] == 0
    assert quality["error_type_counts"]["E8_MISSING_REQUIRED_SECTION"] == 0


def test_gas_negated_concentration_context_does_not_fail_or_flag_misuse():
    quality = check_report_quality(
        "气体监测字段单位或含义未确认，不宜直接按浓度解释，未见异常。",
        prompt_evidence_pack={},
        include_claim_results=True,
    )

    assert not any("_is_gas_negated_concentration_context" in item for item in quality.get("warnings", []))
    assert quality["error_type_counts"]["E6_GAS_FIELD_MISUSE"] == 0


def test_grounding_checker_gas_negated_context_no_name_error():
    grounding = check_claim_grounding(
        [
            {
                "claim_id": "gas-negated",
                "claim_type": "gas",
                "text": "CH4 字段单位或含义未确认，不宜直接按浓度解释，未超限。",
                "gases": ["CH4"],
            }
        ],
        prompt_evidence_pack={
            "gas_evidence": {
                "gas_summaries": [
                    {
                        "gas": "CH4检测",
                        "field_type_guess": "alarm_flag",
                    }
                ]
            }
        },
    )

    claim = grounding["claim_results"][0]
    assert claim["grounded"] is True
    assert claim["support_type"] == "gas_context"


def test_aligned_scope_review_context_is_not_actual_advance_e14():
    quality = check_report_quality(
        "用于已掘复核的 10m 对齐单元范围为 DK1013+940 至 DK1013+960。",
        prompt_evidence_pack={
            "report_scope": {
                "daily_plc_range": {
                    "start_chainage": 1013949.0,
                    "end_chainage": 1013953.0,
                    "daily_advance_m": 4.0,
                },
                "daily_excavated_scope": {
                    "start": 1013940.0,
                    "end": 1013960.0,
                },
            }
        },
        include_claim_results=True,
    )

    assert quality["error_type_counts"]["E14_ALIGNED_SCOPE_AS_ACTUAL_ADVANCE"] == 0


def test_aligned_scope_cell_ids_do_not_trigger_e14_when_context_is_review_scope():
    quality = check_report_quality(
        (
            "当日 PLC 实测推进范围：DK1013+949 至 DK1013+953，日推进量 4.0 m。"
            "用于已掘复核的 10m 对齐单元范围为 DK1013+940 至 DK1013+960。"
            "两个 10m 对齐复核单元（cell_1013940_1013950、cell_1013950_1013960）用于复盘。"
        ),
        prompt_evidence_pack={
            "report_scope": {
                "daily_plc_range": {
                    "start_chainage": 1013949.0,
                    "end_chainage": 1013953.0,
                    "daily_advance_m": 4.0,
                },
                "daily_excavated_scope": {
                    "start": 1013940.0,
                    "end": 1013960.0,
                },
            }
        },
        include_claim_results=True,
    )

    assert quality["error_type_counts"]["E14_ALIGNED_SCOPE_AS_ACTUAL_ADVANCE"] == 0


def test_aligned_scope_written_as_actual_advance_still_triggers_e14():
    quality = check_report_quality(
        "当日 PLC 实测推进范围为 DK1013+940 至 DK1013+960，日进尺 20.0 m。",
        prompt_evidence_pack={
            "report_scope": {
                "daily_plc_range": {
                    "start_chainage": 1013949.0,
                    "end_chainage": 1013953.0,
                    "daily_advance_m": 4.0,
                },
                "daily_excavated_scope": {
                    "start": 1013940.0,
                    "end": 1013960.0,
                },
            }
        },
        include_claim_results=True,
    )

    assert quality["error_type_counts"]["E14_ALIGNED_SCOPE_AS_ACTUAL_ADVANCE"] >= 1


def test_sentence_splitter_keeps_decimal_percent_date_and_dk_values_intact():
    text = (
        "PLC 实测日进尺：1.0m。总运行时间占比 67.5%。"
        "报告日期：2023-09-15。当前掌子面里程：DK1013+198。"
    )

    sentences = split_sentences(text)

    assert any("1.0m" in item for item in sentences)
    assert any("67.5%" in item for item in sentences)
    assert any("2023-09-15" in item for item in sentences)
    assert any("DK1013+198" in item for item in sentences)
    assert "1." not in sentences
    assert "0m" not in sentences
    assert "5%" not in sentences


def test_scope_metadata_claims_are_grounded_but_not_forward_facts():
    pack = {
        "report_scope": {
            "date": "2023-09-15",
            "daily_plc_range": {
                "start_chainage": 1013197.0,
                "end_chainage": 1013198.0,
                "daily_advance_m": 1.0,
            },
            "daily_excavated_scope": {"start": 1013190.0, "end": 1013200.0},
            "current_chainage": 1013198.0,
            "forward_scope": {"start": 1013200.0, "end": 1013230.0},
            "local_background_scope": {"start": 1013090.0, "end": 1013190.0},
        }
    }
    grounding = check_claim_grounding(
        [
            {"claim_id": "date", "text": "报告日期：2023-09-15", "claim_type": "unknown"},
            {"claim_id": "advance", "text": "PLC 实测日进尺：1.0m", "claim_type": "unknown"},
            {"claim_id": "face", "text": "当前掌子面里程：DK1013+198", "claim_type": "unknown"},
            {"claim_id": "forward", "text": "前方关注范围：DK1013+200 至 DK1013+230", "claim_type": "forward_segment"},
            {"claim_id": "background", "text": "局部背景范围：DK1013+090 至 DK1013+190", "claim_type": "unknown"},
            {"claim_id": "bad-forward", "text": "前方关注范围 DK1013+200 至 DK1013+230 已发生异常", "claim_type": "forward_segment"},
            {"claim_id": "bad-aligned", "text": "实际推进范围为 DK1013+190 至 DK1013+200", "claim_type": "unknown"},
        ],
        prompt_evidence_pack=pack,
    )

    by_id = {item["claim_id"]: item for item in grounding["claim_results"]}
    for claim_id in ["date", "advance", "face", "forward", "background"]:
        assert by_id[claim_id]["grounded"] is True
        assert by_id[claim_id]["support_type"] == "scope_metadata"
    assert by_id["bad-forward"]["grounded"] is False
    assert by_id["bad-aligned"]["grounded"] is False
