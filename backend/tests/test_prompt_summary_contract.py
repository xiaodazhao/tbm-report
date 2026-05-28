from copy import deepcopy

from llm.prompt_builder import build_prompt
from llm.prompt_builder_timewindow import build_prompt_timewindow
from llm.summary_contract import normalize_llm_summary
from routes.tbm import _build_state_payload


def _sample_summary() -> dict:
    return {
        "schema_version": "tbm_llm_summary_v2",
        "cluster_state_summary": {
            "valid_samples": 18,
            "config": {"n_states": 3, "min_duration_sec": 20},
        },
        "forward_risk_summary": {
            "advice_level": "medium",
            "high_risk_count": 1,
            "main_hazards": ["hazard"],
        },
        "forward_risk_text": "forward text",
        "response_anomaly_summary": {
            "summary_text": "response summary",
        },
        "coupling_summary": {
            "summary_text": "coupling summary",
        },
        "history_comparison": {
            "comparison_text": "history text",
        },
        "prompt_text_inputs": {
            "operation_segments_text": "seg text",
            "operation_stats_text": "stats text",
            "cluster_state_text": "cluster text",
            "cluster_efficiency_text": "eff text",
            "cluster_state_stats_text": "cluster stats",
            "gas_text": "gas text",
            "face_description_text": "face text",
            "excavated_segment_text": "excavated text",
            "forward_risk_text": "forward text",
            "response_anomaly_text": "response summary",
            "coupling_text": "coupling summary",
            "history_comparison_text": "history text",
        },
    }


def test_build_prompt_uses_text_adapter_instead_of_raw_dicts():
    """Prompt builders should consume prompt_text_inputs instead of stringifying dicts."""
    prompt = build_prompt(
        seg_text="fallback seg",
        stats_text="fallback stats",
        state_text="fallback state",
        eff_text="fallback eff",
        state_stats_text="fallback state stats",
        gas_text="fallback gas",
        geo_text="fallback geo",
        face_geo_text="fallback face",
        llm_summary=deepcopy(_sample_summary()),
        risk_prob_text="fallback risk profile",
    )

    assert "face text" in prompt
    assert "excavated text" in prompt
    assert "forward text" in prompt
    assert "response summary" in prompt
    assert "coupling summary" in prompt
    assert "history text" in prompt
    assert "{'" not in prompt


def test_build_prompt_timewindow_uses_same_contract():
    """Time-window prompts should share the same normalized llm_summary contract."""
    prompt = build_prompt_timewindow(
        start_time="2023-12-30 08:00:00",
        end_time="2023-12-30 10:00:00",
        seg_text="fallback seg",
        stats_text="fallback stats",
        state_text="fallback state",
        eff_text="fallback eff",
        state_stats_text="fallback state stats",
        gas_text="fallback gas",
        geo_text="fallback geo",
        llm_summary=deepcopy(_sample_summary()),
    )

    assert "response summary" in prompt
    assert "coupling summary" in prompt
    assert "{'" not in prompt


def test_state_payload_reads_new_cluster_state_schema():
    """State route payload should read valid_samples/config from cluster_state_summary."""
    payload = _build_state_payload(
        {
            "state_segments": {1: []},
            "state_labels": {1: "cluster label"},
            "state_stats": {},
            "eff_df": [],
            "llm_summary": deepcopy(_sample_summary()),
        }
    )

    assert payload["valid_samples"] == 18
    assert payload["state_config"]["n_states"] == 3


def test_normalize_summary_keeps_forward_risk_contract():
    """Normalization should preserve the canonical forward-risk keys."""
    normalized = normalize_llm_summary(
        {
            "forward_risk_summary": {"advice_level": "low"},
            "forward_risk_text": "legacy text",
        }
    )

    assert normalized["forward_risk_summary"]["advice_level"] == "low"
    assert normalized["forward_risk_text"] == "legacy text"