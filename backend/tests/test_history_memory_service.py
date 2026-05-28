from services.history_memory_service import build_history_comparison, build_history_record
from utils.chainage_utils import format_chainage_dk


def test_build_history_record_extracts_core_fields():
    """Test build history record extracts core fields."""
    analysis_result = {
        "stats": {
            "stop_total_min": 30,
            "transition_total_min": 10,
            "work_total_min": 60,
            "abnormal_total_min": 5,
            "work_count": 3,
            "stop_count": 2,
            "abnormal_count": 1,
        },
        "state_stats": {"状态切换次数": 4},
        "gas_stats": {
            "all": {
                "CH4": {"exceed_event_count": 1},
                "CO2": {"exceed_event_count": 0},
            }
        },
        "geo_summary_segment": {
            "has_geology": True,
            "high_risk_segment_count": 2,
            "multi_source_segment_count": 1,
        },
        "forward_risk_summary": {
            "has_forward_risk": True,
            "lookahead_m": 30,
            "high_risk_count": 2,
            "multi_source_count": 1,
            "main_hazards": ["突水", "掉块"],
        },
        "coupling_summary": {
            "has_coupling": True,
            "max_index": 0.8,
            "mean_index": 0.5,
            "level_counts": {"强耦合区": 1},
            "top_segments": [{"segment": "DK100+000~DK110+000", "risk_response_coupling_index": 0.8}],
        },
        "digital_twin_state": {
            "position_state": {
                "current_chainage": 1234.5,
                "start_chainage_dk": "DK1+200.0",
                "end_chainage_dk": "DK1+260.0",
                "advance_length": 60,
            },
            "coupling_state": {"dominant_level": "强耦合区"},
        },
    }

    record = build_history_record("2026-05-22", analysis_result)

    assert record["date"] == "2026-05-22"
    assert record["position"]["current_chainage_dk"] == format_chainage_dk(1234.5)
    assert record["operation"]["work_ratio"] == 0.571
    assert record["forward_risk"]["main_hazards"] == ["突水", "掉块"]
    assert record["safety"]["gas_exceed_types"] == ["CH4"]


def test_build_history_comparison_describes_deltas_and_new_hazards():
    """Test build history comparison describes deltas and new hazards."""
    current_record = {
        "operation": {
            "work_ratio": 0.60,
            "stop_ratio": 0.20,
            "state_switch_count": 5,
        },
        "forward_risk": {
            "high_risk_count": 3,
            "main_hazards": ["突水", "掉块"],
        },
        "coupling": {
            "mean_index": 0.55,
        },
    }
    history_records = [
        {
            "date": "2026-05-21",
            "operation": {
                "work_ratio": 0.50,
                "stop_ratio": 0.30,
                "state_switch_count": 3,
            },
            "forward_risk": {
                "high_risk_count": 1,
                "main_hazards": ["突水"],
            },
            "coupling": {
                "mean_index": 0.40,
            },
        }
    ]

    comparison = build_history_comparison(current_record, history_records)

    assert comparison["has_history"] is True
    assert comparison["previous_date"] == "2026-05-21"
    assert "有效掘进占比较上一记录升高10.0个百分点" in comparison["comparison_text"]
    assert "本次新增主要风险类型：掉块。" in comparison["comparison_text"]