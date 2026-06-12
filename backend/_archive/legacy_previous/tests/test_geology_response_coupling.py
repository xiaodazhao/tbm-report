import pandas as pd

from analysis.geology_response_coupling import run_coupling_analysis


def _sample_coupling_df():
    """Internal helper for sample coupling df."""
    return pd.DataFrame(
        [
            {
                "chainage": 100.0,
                "fused_grade": "IV",
                "hazard": "断层 富水 掉块",
                "risk": "high",
                "active_sources": "tsp;sketch",
                "active_source_count": 3,
                "__water_flag": 1,
                "__collapse_flag": 1,
                "__deformation_flag": 0,
                "推进速度": 0.20,
                "推力": 1200,
                "刀盘扭矩": 900,
                "刀盘转速": 1.4,
                "掘进状态": 1,
            },
            {
                "chainage": 105.0,
                "fused_grade": "V",
                "hazard": "极破碎 突水",
                "risk": "high",
                "active_sources": "tsp;hsp;sketch",
                "active_source_count": 4,
                "__water_flag": 1,
                "__collapse_flag": 0,
                "__deformation_flag": 1,
                "推进速度": 0.05,
                "推力": 1600,
                "刀盘扭矩": 1300,
                "刀盘转速": 0.8,
                "掘进状态": 0,
            },
            {
                "chainage": 120.0,
                "fused_grade": "II",
                "hazard": "完整",
                "risk": "low",
                "active_sources": "tsp",
                "active_source_count": 1,
                "__water_flag": 0,
                "__collapse_flag": 0,
                "__deformation_flag": 0,
                "推进速度": 1.20,
                "推力": 600,
                "刀盘扭矩": 500,
                "刀盘转速": 2.0,
                "掘进状态": 1,
            },
        ]
    )


def test_run_coupling_analysis_returns_segment_metrics_and_summary():
    """Test run coupling analysis returns segment metrics and summary."""
    result = run_coupling_analysis(_sample_coupling_df(), segment_length=10, output_dir=None, top_k=5)

    assert result["summary"]["has_coupling"] is True
    assert result["summary"]["method"] == "GRS_equal_weight_RAI_iforest_GRCI_validation_v4"
    assert result["summary"]["grs_weight_method"] == "equal_weight_minmax"
    assert len(result["segment_df"]) == 2
    assert {"GRS", "RAI", "GRCI", "coupling_class", "anomaly_type", "iforest_anomaly_score"}.issubset(
        set(result["segment_df"].columns)
    )
    assert result["segment_df"]["GRS"].between(0, 1).all()
    assert result["segment_df"]["RAI"].between(0, 1).all()
    assert result["segment_df"]["GRCI"].between(0, 1).all()
    assert isinstance(result["high_attention_segments"], list)


def test_run_coupling_analysis_warns_when_chainage_missing():
    """Test run coupling analysis warns when chainage missing."""
    df = pd.DataFrame([{"推进速度": 1.0, "推力": 10, "刀盘扭矩": 10}])

    result = run_coupling_analysis(df, output_dir=None)

    assert result["segment_df"].empty
    assert result["summary"]["has_coupling"] is False
    assert any("missing chainage column" in warning for warning in result["warnings"])


def test_run_coupling_analysis_spreads_geology_attention_across_segment_boundary():
    """Gaussian smoothing should preserve attention across hard segment boundaries."""
    df = pd.DataFrame(
        [
            {
                "chainage": 109.90,
                "fused_grade": "V",
                "hazard": "断层 富水 掉块",
                "risk": "high",
                "active_sources": "tsp;sketch",
                "active_source_count": 3,
                "__water_flag": 1,
                "__collapse_flag": 1,
                "__deformation_flag": 0,
                "推进速度": 0.20,
                "推力": 1200,
                "刀盘扭矩": 900,
                "刀盘转速": 1.4,
                "掘进状态": 1,
            },
            {
                "chainage": 109.95,
                "fused_grade": "V",
                "hazard": "断层 富水 掉块",
                "risk": "high",
                "active_sources": "tsp;sketch",
                "active_source_count": 3,
                "__water_flag": 1,
                "__collapse_flag": 1,
                "__deformation_flag": 0,
                "推进速度": 0.22,
                "推力": 1180,
                "刀盘扭矩": 880,
                "刀盘转速": 1.5,
                "掘进状态": 1,
            },
            {
                "chainage": 110.05,
                "fused_grade": "",
                "hazard": "",
                "risk": "low",
                "active_sources": "",
                "active_source_count": 0,
                "__water_flag": 0,
                "__collapse_flag": 0,
                "__deformation_flag": 0,
                "推进速度": 1.00,
                "推力": 600,
                "刀盘扭矩": 500,
                "刀盘转速": 2.0,
                "掘进状态": 1,
            },
            {
                "chainage": 110.10,
                "fused_grade": "",
                "hazard": "",
                "risk": "low",
                "active_sources": "",
                "active_source_count": 0,
                "__water_flag": 0,
                "__collapse_flag": 0,
                "__deformation_flag": 0,
                "推进速度": 1.05,
                "推力": 580,
                "刀盘扭矩": 480,
                "刀盘转速": 2.1,
                "掘进状态": 1,
            },
        ]
    )

    result = run_coupling_analysis(df, segment_length=10, output_dir=None, top_k=5)
    segment_df = result["segment_df"].sort_values("segment_start_first").reset_index(drop=True)

    assert len(segment_df) == 2
    assert segment_df.loc[0, "GRS"] > segment_df.loc[1, "GRS"] > 0


def test_run_coupling_analysis_reduces_stop_penalty_for_routine_ring_building_candidate():
    """Routine stop candidates should reduce stop-related RAI penalties."""
    base = pd.DataFrame(
        [
            {
                "chainage": 100.0,
                "fused_grade": "IV",
                "hazard": "断层 富水 掉块",
                "risk": "high",
                "active_sources": "tsp;sketch",
                "active_source_count": 3,
                "__water_flag": 1,
                "__collapse_flag": 1,
                "__deformation_flag": 0,
                "推进速度": 0.20,
                "推力": 1200,
                "刀盘扭矩": 900,
                "刀盘转速": 1.4,
                "掘进状态": 1,
            },
            {
                "chainage": 105.0,
                "fused_grade": "V",
                "hazard": "极破碎 突水",
                "risk": "high",
                "active_sources": "tsp;hsp;sketch",
                "active_source_count": 4,
                "__water_flag": 1,
                "__collapse_flag": 0,
                "__deformation_flag": 1,
                "推进速度": 0.05,
                "推力": 1600,
                "刀盘扭矩": 1300,
                "刀盘转速": 0.8,
                "掘进状态": 0,
            },
            {
                "chainage": 120.0,
                "fused_grade": "II",
                "hazard": "完整",
                "risk": "low",
                "active_sources": "tsp",
                "active_source_count": 1,
                "__water_flag": 0,
                "__collapse_flag": 0,
                "__deformation_flag": 0,
                "推进速度": 1.20,
                "推力": 600,
                "刀盘扭矩": 500,
                "刀盘转速": 2.0,
                "掘进状态": 1,
            },
        ]
    )
    routine = base.copy()
    routine["routine_ring_building_score"] = [0.0, 1.0, 0.0]

    result_plain = run_coupling_analysis(base, segment_length=10, output_dir=None, top_k=5)
    result_routine = run_coupling_analysis(routine, segment_length=10, output_dir=None, top_k=5)

    plain_df = result_plain["segment_df"].sort_values("segment_start_first").reset_index(drop=True)
    routine_df = result_routine["segment_df"].sort_values("segment_start_first").reset_index(drop=True)

    assert routine_df.loc[0, "stop_anomaly"] < plain_df.loc[0, "stop_anomaly"]
    assert routine_df.loc[0, "RAI"] < plain_df.loc[0, "RAI"]