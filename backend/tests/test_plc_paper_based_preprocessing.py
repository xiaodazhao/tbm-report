from __future__ import annotations

import pandas as pd

from llm.evidence_pack import _strip_forward_plc_response_fields
from plc.paper_based_preprocessing import PLCPreprocessingConfig, apply_paper_based_preprocessing


def _base_frame(n: int = 60) -> pd.DataFrame:
    penetration = [3.0] * min(5, n) + [10.0] * max(n - 5, 0)
    return pd.DataFrame(
        {
            "__time": pd.date_range("2023-12-30 00:00:00", periods=n, freq="1s"),
            "chainage": [1014600.0 + i * 0.05 for i in range(n)],
            "__speed": [20.0] * n,
            "__thrust": [1000.0] * n,
            "__torque": [300.0] * n,
            "__rpm": [4.0] * n,
            "__penetration": penetration,
            "__duration_sec": [1.0] * n,
            "is_working": [True] * n,
        }
    )


def test_wang_shutdown_removal_uses_thrust_and_torque() -> None:
    frame = _base_frame(4)
    frame.loc[0, "__thrust"] = 0.0
    frame.loc[1, "__torque"] = 0.0
    frame.loc[2, ["__thrust", "__torque"]] = [0.0, 0.0]

    result = apply_paper_based_preprocessing(frame)
    samples = result["samples"]

    assert bool(samples.loc[samples["__paper_original_index"].eq(0), "is_shutdown_segment"].iloc[0]) is True
    assert bool(samples.loc[samples["__paper_original_index"].eq(1), "is_shutdown_segment"].iloc[0]) is True
    assert samples.loc[samples["__paper_original_index"].eq(2), "shutdown_reason"].iloc[0] == "both_thrust_and_torque_zero_or_near_zero"
    assert bool(samples.loc[samples["__paper_original_index"].eq(3), "is_shutdown_segment"].iloc[0]) is False


def test_three_sigma_outlier_filter_marks_obvious_noise() -> None:
    frame = _base_frame(40)
    frame.loc[39, "__torque"] = 2000.0

    result = apply_paper_based_preprocessing(frame)
    samples = result["samples"]
    outlier_row = samples.loc[samples["__paper_original_index"].eq(39)].iloc[0]

    assert bool(outlier_row["is_outlier"]) is True
    assert "torque_outside_3sigma" in str(outlier_row["outlier_reason"])


def test_working_interval_breaks_on_shutdown_and_short_interval_is_flagged() -> None:
    frame = _base_frame(35)
    frame.loc[10, "__torque"] = 0.0
    config = PLCPreprocessingConfig(min_interval_sample_count=20, min_interval_duration_seconds=20)

    result = apply_paper_based_preprocessing(frame, config=config)
    intervals = result["intervals"]

    assert len(intervals) == 2
    assert intervals.iloc[0]["interval_type"] == "short_transition_interval"
    assert intervals.iloc[1]["interval_type"] == "valid_working_interval"


def test_shan_style_steady_state_extraction_outputs_cell_metrics() -> None:
    frame = _base_frame(80)

    result = apply_paper_based_preprocessing(frame)
    cells = result["cell_metrics"]
    samples = result["samples"]

    assert samples["paper_plc_stage"].eq("steady_state").any()
    assert int(cells["steady_sample_count"].sum()) >= 20
    assert cells["steady_state_available"].any()
    assert "steady_cutterhead_power_proxy" in cells.columns
    assert "plc_preprocessing_quality_grade" in cells.columns


def test_steady_state_falls_back_when_detection_signal_missing() -> None:
    frame = _base_frame(40)
    frame["__penetration"] = pd.NA
    frame["__speed"] = pd.NA

    result = apply_paper_based_preprocessing(frame)
    cells = result["cell_metrics"]

    assert cells["steady_state_available"].fillna(False).sum() == 0
    assert cells["steady_state_fallback_used"].fillna(False).any()
    assert "no_detection_signal" in set(cells["steady_state_fallback_reason"].dropna())


def test_forward_pack_strips_steady_state_plc_fields() -> None:
    payload = {
        "RAI": 0.5,
        "plc_enhanced_metrics": {"steady_sample_count": 30},
        "steady_state_available": True,
        "steady_sample_count": 30,
        "steady_speed_mean": 12.0,
        "steady_cutterhead_power_proxy": 42.0,
        "plc_preprocessing_quality_grade": "A",
        "GRS_geo_base": 0.7,
    }

    _strip_forward_plc_response_fields(payload)

    assert "RAI" not in payload
    assert "plc_enhanced_metrics" not in payload
    assert "steady_state_available" not in payload
    assert "steady_cutterhead_power_proxy" not in payload
    assert payload["GRS_geo_base"] == 0.7
