from pathlib import Path

import pandas as pd
from fastapi import FastAPI
from fastapi.testclient import TestClient

import agent.tbm_tools as tbm_tools
import routes.tbm as tbm_routes


def _build_client(monkeypatch, result: dict, *, cache_hit: bool = False) -> TestClient:
    """Internal helper for build client."""
    app = FastAPI()
    tbm_routes.register_tbm_routes(
        app,
        analyze_tbm_data=lambda df: result,
        build_risk_profile=lambda df: {},
        build_speed_profile=lambda df: [],
    )

    sample_path = Path("tbm_data_20231230.csv")
    monkeypatch.setattr(tbm_routes, "get_latest_csv_path", lambda: sample_path)
    monkeypatch.setattr(tbm_routes, "get_csv_path_by_date", lambda date: sample_path)
    monkeypatch.setattr(tbm_routes, "load_csv", lambda path: pd.DataFrame())
    monkeypatch.setattr(
        tbm_routes,
        "get_or_compute_file_cache",
        lambda namespace, path, compute: (result, cache_hit),
    )
    monkeypatch.setattr(tbm_tools, "load_csv_by_date", lambda date: (sample_path, pd.DataFrame()))
    monkeypatch.setattr(tbm_tools, "load_latest_csv", lambda: (sample_path, pd.DataFrame()))
    return TestClient(app)


def test_state_route_returns_defaults_when_summary_fields_missing(monkeypatch):
    """Test state route returns defaults when summary fields missing."""
    result = {
        "state_segments": {
            "0": [(pd.Timestamp("2023-12-30 08:00:00"), pd.Timestamp("2023-12-30 08:03:00"))]
        },
        "state_labels": {0: "稳定推进"},
        "eff_df": pd.DataFrame(),
        "state_stats": {"状态切换次数": 1},
        "llm_summary": {},
        "warnings": ["状态样本较少"],
    }
    client = _build_client(monkeypatch, result)

    response = client.get("/api/tbm/state?date=2023-12-30")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["warnings"] == ["状态样本较少"]
    assert payload["data"]["valid_samples"] == 0
    assert payload["data"]["state_config"] == {}
    assert payload["data"]["segments"][0]["label_text"] == "稳定推进"
    assert payload["meta"]["resolved_date"] == "2023-12-30"


def test_state_route_returns_efficiency_and_summary_meta(monkeypatch):
    """Test state route returns efficiency and summary meta."""
    result = {
        "state_segments": {
            1: [(pd.Timestamp("2023-12-30 09:10:00"), pd.Timestamp("2023-12-30 09:16:30"))]
        },
        "state_labels": {1: "高负载推进"},
        "eff_df": pd.DataFrame(
            [
                {
                    "label_text": "高负载推进",
                    "平均推进速度": 22.5,
                    "平均推力": 1034.2,
                }
            ]
        ),
        "state_stats": {1: {"segment_count": 1}},
        "llm_summary": {
            "有效状态样本数": 18,
            "状态识别配置": {"n_states": 3, "min_duration_sec": 20},
        },
        "warnings": [],
    }
    client = _build_client(monkeypatch, result, cache_hit=True)

    response = client.get("/api/tbm/state?date=2023-12-30")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["data"]["valid_samples"] == 18
    assert payload["data"]["state_config"]["n_states"] == 3
    assert payload["data"]["efficiency"][0]["label_text"] == "高负载推进"
    assert payload["data"]["segments"][0]["duration"] == 390.0
    assert payload["meta"]["cache_hit"] is True
    assert payload["meta"]["source_file"] == "tbm_data_20231230.csv"


def test_agent_v2_reuses_session_context_for_follow_up(monkeypatch, isolated_sqlite_env):
    """Test agent v2 reuses session context for follow up."""
    result = {
        "stats": {
            "work_total_min": 120.0,
            "stop_total_min": 18.0,
            "transition_total_min": 12.0,
            "abnormal_total_min": 5.0,
            "work_count": 4,
            "stop_count": 2,
            "abnormal_count": 1,
        },
        "geo_summary_segment": {
            "has_geology": True,
            "high_risk_segment_count": 2,
            "multi_source_segment_count": 1,
        },
        "coupling_summary": {
            "has_coupling": True,
            "summary_text": "重点关注 DK100+120~DK100+130。",
        },
        "forward_risk_summary": {
            "has_forward_risk": True,
            "advice_level": "中",
            "high_risk_count": 1,
            "main_hazards": ["裂隙富水"],
        },
        "digital_twin_state": {
            "position_state": {"current_chainage_dk": "DK100+120", "advance_length": 12.5},
            "operation_state": {"dominant_state": "稳定推进", "work_ratio": 0.82},
            "safety_state": {"gas_exceed_types": []},
            "forward_risk_state": {"advice_level": "中", "main_hazards": ["裂隙富水"]},
            "coupling_state": {"top_segment": "DK100+120~DK100+130"},
        },
    }
    client = _build_client(monkeypatch, result)

    first = client.post(
        "/api/tbm/agent_v2",
        json={"query": "分析地质风险", "date": "2023-12-30"},
    )
    assert first.status_code == 200
    first_payload = first.json()
    session_id = first_payload["data"]["session_id"]

    second = client.post(
        "/api/tbm/agent_v2",
        json={"query": "为什么那一段值得注意", "session_id": session_id},
    )
    assert second.status_code == 200
    second_payload = second.json()["data"]

    assert second_payload["context_summary"]["has_history"] is True
    assert second_payload["date"] == "2023-12-30"
    assert "GeologyAgent" in second_payload["routed_agents"]
    assert "OperationAgent" in second_payload["routed_agents"]

    session = client.get(f"/api/tbm/agent_v2/session?session_id={session_id}&limit=10")
    assert session.status_code == 200
    session_payload = session.json()["data"]
    assert len(session_payload["messages"]) == 4