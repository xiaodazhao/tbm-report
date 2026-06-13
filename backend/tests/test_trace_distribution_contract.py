from llm.report_trace_builder import build_report_trace, summarize_report_trace


def test_trace_output_contains_support_and_source_distributions():
    trace = build_report_trace(
        (
            "cell_0_10 has GRCI review level medium. "
            "Forward window 0-10m has attention level medium. "
            "GRCI is not a disaster probability. "
            "DK1014+600 has an ungrounded numeric claim."
        ),
        grounding_result={
            "claim_results": [
                {
                    "claim_id": "c1",
                    "claim_text": "cell_0_10 has GRCI review level medium.",
                    "claim_type": "coupling",
                    "grounded": True,
                    "support_type": "coupling_context",
                    "trace_support_type": "daily_review_support",
                    "source_trace": [
                        {
                            "evidence_id": "ev-1",
                            "source_type": "HSP",
                            "evidence_role": "prediction",
                            "evidence_report_role": "daily_review_evidence",
                        }
                    ],
                },
                {
                    "claim_id": "c2",
                    "claim_text": "Forward window 0-10m has attention level medium.",
                    "claim_type": "forward_segment",
                    "grounded": True,
                    "support_type": "forward_segment",
                    "trace_support_type": "forward_attention_support",
                    "source_trace": [
                        {
                            "evidence_id": "ev-2",
                            "source_type": "TSP",
                            "evidence_role": "prediction",
                            "evidence_report_role": "forward_attention_evidence",
                        }
                    ],
                },
                {
                    "claim_id": "c3",
                    "claim_text": "GRCI is not a disaster probability.",
                    "claim_type": "recommendation",
                    "grounded": True,
                    "support_type": "recommendation_policy",
                    "trace_support_type": "policy_support",
                    "source_trace": [],
                },
                {
                    "claim_id": "c4",
                    "claim_text": "DK1014+600 has an ungrounded numeric claim.",
                    "claim_type": "unknown",
                    "grounded": False,
                    "support_type": "none",
                    "trace_support_type": "none",
                    "source_trace": [],
                },
            ],
            "warnings": [],
        },
    )
    summary = summarize_report_trace(trace)

    assert trace["support_type_distribution"]["daily_review_support"] == 1
    assert trace["support_type_distribution"]["forward_attention_support"] == 1
    assert trace["support_type_distribution"]["policy_support"] == 1
    assert trace["support_type_distribution"]["none"] == 1
    assert trace["source_role_distribution"]["daily_review_evidence"] == 1
    assert trace["source_role_distribution"]["forward_attention_evidence"] == 1
    assert trace["claim_type_distribution"]["unknown"] == 1
    assert trace["unsupported_by_claim_type"]["unknown"] == 1
    assert summary["support_type_distribution"]["none"] == 1
