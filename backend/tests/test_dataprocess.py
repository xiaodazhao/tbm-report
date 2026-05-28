import pandas as pd

from analysis.dataprocess import annotate_routine_ring_building_stops


def test_annotate_routine_ring_building_stops_marks_periodic_stop_segments():
    """Mark periodic stop segments as routine ring-building candidates."""
    df = pd.DataFrame(
        [
            {"timestamp": "2023-12-30 08:00:00", "chainage": 100.0, "state": 1, "speed": 0.8},
            {"timestamp": "2023-12-30 08:20:00", "chainage": 101.5, "state": 0, "speed": 0.0},
            {"timestamp": "2023-12-30 09:00:00", "chainage": 101.5, "state": 0, "speed": 0.0},
            {"timestamp": "2023-12-30 09:10:00", "chainage": 101.6, "state": 1, "speed": 0.9},
            {"timestamp": "2023-12-30 09:30:00", "chainage": 103.0, "state": 0, "speed": 0.0},
            {"timestamp": "2023-12-30 10:10:00", "chainage": 103.0, "state": 0, "speed": 0.0},
            {"timestamp": "2023-12-30 10:20:00", "chainage": 103.1, "state": 1, "speed": 1.0},
        ]
    )

    result = annotate_routine_ring_building_stops(df)

    assert "routine_ring_building_candidate" in result.columns
    assert "routine_ring_building_score" in result.columns
    assert result.loc[1:2, "routine_ring_building_candidate"].eq(1.0).all()
    assert result.loc[4:5, "routine_ring_building_candidate"].eq(1.0).all()
    assert result.loc[1:2, "routine_ring_building_score"].gt(0.7).all()


def test_annotate_routine_ring_building_stops_leaves_irregular_long_stop_unmarked():
    """Do not mark irregular long stop segments as routine ring-building."""
    df = pd.DataFrame(
        [
            {"timestamp": "2023-12-30 08:00:00", "chainage": 100.0, "state": 1, "speed": 0.9},
            {"timestamp": "2023-12-30 08:10:00", "chainage": 101.4, "state": 0, "speed": 0.0},
            {"timestamp": "2023-12-30 10:10:00", "chainage": 101.4, "state": 0, "speed": 0.0},
            {"timestamp": "2023-12-30 10:20:00", "chainage": 101.5, "state": 1, "speed": 0.8},
        ]
    )

    result = annotate_routine_ring_building_stops(df)

    assert result["routine_ring_building_candidate"].sum() == 0.0