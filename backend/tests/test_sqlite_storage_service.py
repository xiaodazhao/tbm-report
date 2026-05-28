import json
import pickle

import pandas as pd


def test_history_records_are_migrated_from_json_and_persisted(isolated_sqlite_env):
    """Test history records are migrated from json and persisted."""
    sqlite_storage_service, _, history_dir = isolated_sqlite_env

    legacy_record = {
        "date": "2026-05-20",
        "created_at": "2026-05-20 08:00:00",
        "operation": {"work_ratio": 0.5},
    }
    (history_dir / "2026-05-20.json").write_text(
        json.dumps(legacy_record, ensure_ascii=False),
        encoding="utf-8",
    )

    sqlite_storage_service.save_history_record_to_db(
        {
            "date": "2026-05-22",
            "created_at": "2026-05-22 12:00:00",
            "operation": {"work_ratio": 0.8},
        }
    )
    records = sqlite_storage_service.load_history_records_from_db(limit=10)

    assert [record["date"] for record in records] == ["2026-05-20", "2026-05-22"]


def test_evidence_dataframe_and_file_cache_round_trip(isolated_sqlite_env, tmp_path):
    """Test evidence dataframe and file cache round trip."""
    sqlite_storage_service, _, _ = isolated_sqlite_env

    evidence_df = pd.DataFrame(
        [
            {
                "evidence_id": "demo-1",
                "source_type": "tsp",
                "report_id": "R1",
                "start_num": 100.0,
                "end_num": 110.0,
                "attrs_json": "{}",
            },
            {
                "evidence_id": "demo-2",
                "source_type": "sketch",
                "report_id": "R2",
                "start_num": 120.0,
                "end_num": 120.0,
                "attrs_json": "{\"risk_level\": \"high\"}",
            },
        ]
    )

    sqlite_storage_service.sync_evidence_dataframe_to_db(evidence_df)
    loaded_df = sqlite_storage_service.load_evidence_dataframe_from_db()

    assert sorted(loaded_df["evidence_id"].tolist()) == ["demo-1", "demo-2"]

    sqlite_storage_service.save_file_cache_blob("demo", "sample.csv", 123, 456, {"value": 7})
    sqlite_storage_service.prune_stale_file_cache_entries("demo", "sample.csv", 123, 456)
    payload = sqlite_storage_service.load_file_cache_blob("demo", "sample.csv", 123, 456)

    assert pickle.loads(payload) == {"value": 7}

    fallback_csv = tmp_path / "evidence_fallback.csv"
    fallback_df = pd.DataFrame(
        [
            {
                "evidence_id": "csv-1",
                "source_type": "tsp",
                "report_id": "CSV",
                "start_num": 1.0,
                "end_num": 2.0,
                "attrs_json": "{}",
            }
        ]
    )
    fallback_df.to_csv(fallback_csv, index=False, encoding="utf-8-sig")
    sqlite_storage_service.clear_file_cache_entries()
    sqlite_storage_service._SCHEMA_READY = False
    isolated_sqlite_env[0].APP_DB_PATH.unlink(missing_ok=True)
    isolated_sqlite_env[0]._SCHEMA_READY = False

    loaded_from_csv = sqlite_storage_service.load_evidence_dataframe_from_db(fallback_csv)
    assert loaded_from_csv["evidence_id"].tolist() == ["csv-1"]


def test_agent_session_messages_round_trip(isolated_sqlite_env):
    """Test agent session messages round trip."""
    sqlite_storage_service, _, _ = isolated_sqlite_env

    sqlite_storage_service.save_agent_session(
        "session-demo",
        payload={"last_date": "2026-05-22"},
        title="测试会话",
    )
    sqlite_storage_service.append_agent_message(
        "session-demo",
        "user",
        {"query": "今天怎么样", "date": "2026-05-22"},
        session_title="测试会话",
        session_payload={"last_query": "今天怎么样"},
    )
    sqlite_storage_service.append_agent_message(
        "session-demo",
        "assistant",
        {"answer": "今天总体稳定", "routed_agents": ["DataAgent"]},
        session_title="测试会话",
        session_payload={"last_query": "今天怎么样"},
    )

    session = sqlite_storage_service.load_agent_session("session-demo")
    messages = sqlite_storage_service.load_agent_messages("session-demo", limit=10)

    assert session["title"] == "测试会话"
    assert session["payload"]["last_query"] == "今天怎么样"
    assert [item["role"] for item in messages] == ["user", "assistant"]
    assert messages[1]["payload"]["answer"] == "今天总体稳定"