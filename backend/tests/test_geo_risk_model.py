import pandas as pd

from analysis.geo_risk_model import apply_dynamic_grs_correction, compute_row_grs_base


def test_compute_row_grs_base_combines_grade_hazard_and_source_confidence():
    """Test compute row grs base combines grade hazard and source confidence."""
    df = pd.DataFrame(
        [
            {
                "fused_grade": "IV",
                "hazard": "断层 富水 掉块",
                "risk": "high",
                "active_sources": "tsp;sketch",
                "__water_flag": 1,
                "__collapse_flag": 1,
                "__deformation_flag": 0,
            },
            {
                "fused_grade": "II",
                "hazard": "完整",
                "risk": "low",
                "active_sources": "tsp",
                "__water_flag": 0,
                "__collapse_flag": 0,
                "__deformation_flag": 0,
            },
        ]
    )
    colmap = {
        "grade": "fused_grade",
        "hazard": "hazard",
        "risk": "risk",
        "active_sources": "active_sources",
    }
    warnings = []

    grs_base, source_confidence, components = compute_row_grs_base(df, colmap, warnings)

    assert warnings == []
    assert list(components.columns) == [
        "grade_score",
        "hazard_score",
        "water_score",
        "collapse_score",
        "source_confidence",
    ]
    assert grs_base.iloc[0] > grs_base.iloc[1]
    assert 0 <= source_confidence.iloc[0] <= 1
    assert grs_base.between(0, 1).all()
    assert ((components >= 0) & (components <= 1)).all().all()
    assert round(float(grs_base.iloc[0]), 3) == 1.0
    assert round(float(grs_base.iloc[1]), 3) == 0.0


def test_apply_dynamic_grs_correction_raises_high_response_segments():
    """Test apply dynamic grs correction raises high response segments."""
    segment_df = pd.DataFrame(
        {
            "GRS_base": [0.60, 0.20],
            "RAI": [0.50, 0.10],
            "stop_ratio": [0.30, 0.00],
        }
    )

    corrected_df, metadata = apply_dynamic_grs_correction(segment_df)

    assert metadata["correction_mode"] == "rai_stop_ratio"
    assert metadata["grs_weight_method"] == "equal_weight_minmax"
    assert corrected_df.loc[0, "correction"] > corrected_df.loc[1, "correction"]
    assert corrected_df.loc[0, "GRS_corrected"] > corrected_df.loc[0, "GRS_base"]
    assert corrected_df.loc[1, "GRS"] >= 0.05
    assert corrected_df["GRS"].between(0, 1).all()