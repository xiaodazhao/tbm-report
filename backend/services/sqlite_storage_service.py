from __future__ import annotations

import json
import pickle
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from threading import RLock
from typing import Any

import pandas as pd

from config import APP_DB_PATH, HISTORY_MEMORY_DIR
from utils.serialization import serialize_for_json


_LOCK = RLock()
_SCHEMA_READY = False


def _now_text() -> str:
    """Return the current timestamp text."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


@contextmanager
def _connect():
    """Open a SQLite connection for backend storage."""
    APP_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(APP_DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        yield conn
        conn.commit()
    finally:
        conn.close()


def ensure_storage_initialized() -> None:
    """Ensure storage initialized."""
    global _SCHEMA_READY

    with _LOCK:
        if _SCHEMA_READY:
            return

        with _connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS app_metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS history_records (
                    date TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS evidence_records (
                    evidence_id TEXT PRIMARY KEY,
                    source_type TEXT,
                    report_id TEXT,
                    start_num REAL,
                    end_num REAL,
                    payload_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_evidence_sort
                ON evidence_records (source_type, report_id, start_num, end_num);

                CREATE TABLE IF NOT EXISTS file_cache_entries (
                    namespace TEXT NOT NULL,
                    source_path TEXT NOT NULL,
                    mtime_ns INTEGER NOT NULL,
                    file_size INTEGER NOT NULL,
                    payload_blob BLOB NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (namespace, source_path, mtime_ns, file_size)
                );

                CREATE INDEX IF NOT EXISTS idx_file_cache_lookup
                ON file_cache_entries (namespace, source_path);

                CREATE TABLE IF NOT EXISTS agent_sessions (
                    session_id TEXT PRIMARY KEY,
                    title TEXT,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS agent_messages (
                    message_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(session_id) REFERENCES agent_sessions(session_id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_agent_messages_session
                ON agent_messages (session_id, message_id);

                CREATE TABLE IF NOT EXISTS cst_states (
                    cst_id TEXT PRIMARY KEY,
                    state_key TEXT NOT NULL UNIQUE,
                    date TEXT,
                    analysis_mode TEXT,
                    start_time TEXT,
                    end_time TEXT,
                    source_path TEXT,
                    previous_cst_id TEXT,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_cst_states_date
                ON cst_states (date, updated_at);

                CREATE INDEX IF NOT EXISTS idx_cst_states_previous
                ON cst_states (previous_cst_id);
                """
            )

        _SCHEMA_READY = True


def _get_metadata(conn: sqlite3.Connection, key: str) -> str | None:
    """Get metadata."""
    row = conn.execute(
        "SELECT value FROM app_metadata WHERE key = ?",
        (key,),
    ).fetchone()
    return str(row["value"]) if row else None


def _set_metadata(conn: sqlite3.Connection, key: str, value: str) -> None:
    """Internal helper for set metadata."""
    conn.execute(
        """
        INSERT INTO app_metadata (key, value, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET
            value = excluded.value,
            updated_at = excluded.updated_at
        """,
        (key, value, _now_text()),
    )


def migrate_history_json_files() -> None:
    """Migrate history json files."""
    ensure_storage_initialized()

    with _connect() as conn:
        already_done = _get_metadata(conn, "history_json_migrated")
        if already_done == "1":
            return

        history_dir = Path(HISTORY_MEMORY_DIR)
        if history_dir.exists():
            for path in sorted(history_dir.glob("*.json")):
                try:
                    payload = json.loads(path.read_text(encoding="utf-8"))
                except Exception:
                    continue

                date = str(payload.get("date", "")).strip()
                if not date:
                    continue

                created_at = str(payload.get("created_at") or _now_text())
                conn.execute(
                    """
                    INSERT INTO history_records (date, created_at, payload_json, updated_at)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(date) DO UPDATE SET
                        created_at = excluded.created_at,
                        payload_json = excluded.payload_json,
                        updated_at = excluded.updated_at
                    """,
                    (date, created_at, json.dumps(payload, ensure_ascii=False), _now_text()),
                )

        _set_metadata(conn, "history_json_migrated", "1")


def save_history_record_to_db(record: dict) -> Path:
    """Save history record to db."""
    ensure_storage_initialized()
    migrate_history_json_files()

    payload = serialize_for_json(record)
    date = str(payload.get("date", "")).strip() or "unknown"
    created_at = str(payload.get("created_at") or _now_text())

    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO history_records (date, created_at, payload_json, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(date) DO UPDATE SET
                created_at = excluded.created_at,
                payload_json = excluded.payload_json,
                updated_at = excluded.updated_at
            """,
            (date, created_at, json.dumps(payload, ensure_ascii=False), _now_text()),
        )

    return APP_DB_PATH


def load_history_records_from_db(limit: int = 10, before_date: str | None = None) -> list[dict]:
    """Load history records from db."""
    ensure_storage_initialized()
    migrate_history_json_files()

    clauses = []
    params: list[Any] = []
    if before_date:
        clauses.append("date < ?")
        params.append(str(before_date))

    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    sql = f"""
        SELECT payload_json
        FROM history_records
        {where_sql}
        ORDER BY date DESC
        LIMIT ?
    """
    params.append(int(limit))

    with _connect() as conn:
        rows = conn.execute(sql, tuple(params)).fetchall()

    records = [json.loads(row["payload_json"]) for row in rows]
    records.reverse()
    return records


def save_agent_session(session_id: str, payload: dict | None = None, title: str | None = None) -> None:
    """Save agent session."""
    ensure_storage_initialized()
    session_payload = serialize_for_json(payload or {})
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO agent_sessions (session_id, title, payload_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
                title = COALESCE(excluded.title, agent_sessions.title),
                payload_json = excluded.payload_json,
                updated_at = excluded.updated_at
            """,
            (
                str(session_id),
                title,
                json.dumps(session_payload, ensure_ascii=False),
                _now_text(),
                _now_text(),
            ),
        )


def load_agent_session(session_id: str) -> dict | None:
    """Load agent session."""
    ensure_storage_initialized()
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT session_id, title, payload_json, created_at, updated_at
            FROM agent_sessions
            WHERE session_id = ?
            """,
            (str(session_id),),
        ).fetchone()

    if not row:
        return None

    payload = json.loads(row["payload_json"]) if row["payload_json"] else {}
    return {
        "session_id": row["session_id"],
        "title": row["title"],
        "payload": payload,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def append_agent_message(
    session_id: str,
    role: str,
    payload: dict,
    *,
    session_title: str | None = None,
    session_payload: dict | None = None,
) -> int:
    """Append agent message."""
    ensure_storage_initialized()
    message_payload = serialize_for_json(payload)
    save_agent_session(
        session_id=session_id,
        payload=session_payload or {},
        title=session_title,
    )

    with _connect() as conn:
        conn.execute(
            """
            UPDATE agent_sessions
            SET updated_at = ?
            WHERE session_id = ?
            """,
            (_now_text(), str(session_id)),
        )
        cursor = conn.execute(
            """
            INSERT INTO agent_messages (session_id, role, payload_json, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (
                str(session_id),
                str(role),
                json.dumps(message_payload, ensure_ascii=False),
                _now_text(),
            ),
        )
        return int(cursor.lastrowid)


def load_agent_messages(session_id: str, limit: int = 20) -> list[dict]:
    """Load agent messages."""
    ensure_storage_initialized()
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT message_id, role, payload_json, created_at
            FROM agent_messages
            WHERE session_id = ?
            ORDER BY message_id DESC
            LIMIT ?
            """,
            (str(session_id), int(limit)),
        ).fetchall()

    messages = []
    for row in reversed(rows):
        payload = json.loads(row["payload_json"]) if row["payload_json"] else {}
        messages.append(
            {
                "message_id": int(row["message_id"]),
                "session_id": str(session_id),
                "role": row["role"],
                "created_at": row["created_at"],
                "payload": payload,
            }
        )
    return messages


def _sanitize_dataframe_records(df: pd.DataFrame) -> list[dict]:
    """Internal helper for sanitize dataframe records."""
    if df.empty:
        return []
    normalized = df.where(pd.notna(df), None)
    records = normalized.to_dict(orient="records")
    return serialize_for_json(records)


def sync_evidence_dataframe_to_db(df: pd.DataFrame) -> None:
    """Sync evidence dataframe to db."""
    ensure_storage_initialized()
    rows = _sanitize_dataframe_records(df)

    with _connect() as conn:
        conn.execute("DELETE FROM evidence_records")
        if rows:
            conn.executemany(
                """
                INSERT INTO evidence_records (
                    evidence_id,
                    source_type,
                    report_id,
                    start_num,
                    end_num,
                    payload_json,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        str(row.get("evidence_id", "")),
                        str(row.get("source_type", "")) if row.get("source_type") is not None else None,
                        str(row.get("report_id", "")) if row.get("report_id") is not None else None,
                        row.get("start_num"),
                        row.get("end_num"),
                        json.dumps(row, ensure_ascii=False),
                        _now_text(),
                    )
                    for row in rows
                ],
            )
        _set_metadata(conn, "evidence_record_count", str(len(rows)))


def load_evidence_dataframe_from_db(csv_fallback_path: Path | None = None) -> pd.DataFrame:
    """Load evidence dataframe from db."""
    ensure_storage_initialized()

    with _connect() as conn:
        row = conn.execute("SELECT COUNT(*) AS count FROM evidence_records").fetchone()
        count = int(row["count"]) if row else 0

    if count == 0 and csv_fallback_path and csv_fallback_path.exists():
        csv_df = pd.read_csv(csv_fallback_path)
        sync_evidence_dataframe_to_db(csv_df)
        return csv_df

    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT payload_json
            FROM evidence_records
            ORDER BY source_type, report_id, start_num, end_num, evidence_id
            """
        ).fetchall()

    if not rows:
        return pd.DataFrame()

    return pd.DataFrame([json.loads(row["payload_json"]) for row in rows])


def load_file_cache_blob(
    namespace: str,
    source_path: str,
    mtime_ns: int,
    file_size: int,
    *,
    cache_key: str | None = None,
) -> bytes | None:
    """Load file cache blob."""
    ensure_storage_initialized()
    lookup_path = str(cache_key or source_path)
    lookup_mtime = 0 if cache_key else int(mtime_ns)
    lookup_size = 0 if cache_key else int(file_size)
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT payload_blob
            FROM file_cache_entries
            WHERE namespace = ? AND source_path = ? AND mtime_ns = ? AND file_size = ?
            """,
            (namespace, lookup_path, lookup_mtime, lookup_size),
        ).fetchone()
    return bytes(row["payload_blob"]) if row else None


def save_file_cache_blob(
    namespace: str,
    source_path: str,
    mtime_ns: int,
    file_size: int,
    value: Any,
    *,
    cache_key: str | None = None,
) -> None:
    """Save file cache blob."""
    ensure_storage_initialized()
    lookup_path = str(cache_key or source_path)
    lookup_mtime = 0 if cache_key else int(mtime_ns)
    lookup_size = 0 if cache_key else int(file_size)
    payload = sqlite3.Binary(pickle.dumps(value, protocol=pickle.HIGHEST_PROTOCOL))
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO file_cache_entries (
                namespace, source_path, mtime_ns, file_size, payload_blob, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(namespace, source_path, mtime_ns, file_size) DO UPDATE SET
                payload_blob = excluded.payload_blob,
                updated_at = excluded.updated_at
            """,
            (namespace, lookup_path, lookup_mtime, lookup_size, payload, _now_text()),
        )


def prune_stale_file_cache_entries(
    namespace: str,
    source_path: str,
    keep_mtime_ns: int,
    keep_file_size: int,
    *,
    cache_key: str | None = None,
) -> None:
    """Prune stale file cache entries."""
    ensure_storage_initialized()
    lookup_path = str(cache_key or source_path)
    lookup_mtime = 0 if cache_key else int(keep_mtime_ns)
    lookup_size = 0 if cache_key else int(keep_file_size)
    with _connect() as conn:
        conn.execute(
            """
            DELETE FROM file_cache_entries
            WHERE namespace = ? AND source_path = ?
              AND NOT (mtime_ns = ? AND file_size = ?)
            """,
            (namespace, lookup_path, lookup_mtime, lookup_size),
        )


def clear_file_cache_entries(namespace: str | None = None) -> None:
    """Clear file cache entries."""
    ensure_storage_initialized()
    with _connect() as conn:
        if namespace is None:
            conn.execute("DELETE FROM file_cache_entries")
        else:
            conn.execute("DELETE FROM file_cache_entries WHERE namespace = ?", (namespace,))


def save_cst_state(state: dict) -> None:
    """Persist a canonical CST snapshot."""
    ensure_storage_initialized()
    payload = serialize_for_json(state or {})
    cst_id = str(payload.get("cst_id") or "")
    state_key = str(payload.get("state_key") or "")
    if not cst_id or not state_key:
        return

    time_window = payload.get("time_window", {}) if isinstance(payload.get("time_window"), dict) else {}
    provenance = payload.get("provenance_state", {}) if isinstance(payload.get("provenance_state"), dict) else {}
    sources = provenance.get("state_update_sources", []) if isinstance(provenance, dict) else []
    source_path = None
    if isinstance(sources, list):
        for item in sources:
            if isinstance(item, dict) and item.get("type") == "csv" and item.get("path"):
                source_path = str(item.get("path"))
                break

    with _connect() as conn:
        created_at = _now_text()
        existing = conn.execute(
            "SELECT created_at FROM cst_states WHERE state_key = ?",
            (state_key,),
        ).fetchone()
        if existing:
            created_at = str(existing["created_at"])
        conn.execute(
            """
            INSERT INTO cst_states (
                cst_id, state_key, date, analysis_mode, start_time, end_time,
                source_path, previous_cst_id, payload_json, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(state_key) DO UPDATE SET
                cst_id = excluded.cst_id,
                date = excluded.date,
                analysis_mode = excluded.analysis_mode,
                start_time = excluded.start_time,
                end_time = excluded.end_time,
                source_path = excluded.source_path,
                previous_cst_id = excluded.previous_cst_id,
                payload_json = excluded.payload_json,
                updated_at = excluded.updated_at
            """,
            (
                cst_id,
                state_key,
                payload.get("date"),
                payload.get("temporal_state", {}).get("analysis_mode"),
                time_window.get("start_time"),
                time_window.get("end_time"),
                source_path,
                payload.get("previous_cst_id"),
                json.dumps(payload, ensure_ascii=False),
                created_at,
                _now_text(),
            ),
        )


def load_cst_state(cst_id: str) -> dict | None:
    """Load one CST snapshot by id."""
    ensure_storage_initialized()
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT payload_json
            FROM cst_states
            WHERE cst_id = ?
            """,
            (str(cst_id),),
        ).fetchone()
    return json.loads(row["payload_json"]) if row else None


def load_cst_state_by_key(state_key: str) -> dict | None:
    """Load one CST snapshot by stable state key."""
    ensure_storage_initialized()
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT payload_json
            FROM cst_states
            WHERE state_key = ?
            """,
            (str(state_key),),
        ).fetchone()
    return json.loads(row["payload_json"]) if row else None


def load_latest_cst_state(before_date: str | None = None) -> dict | None:
    """Load the latest persisted CST before a target date."""
    ensure_storage_initialized()
    with _connect() as conn:
        if before_date:
            row = conn.execute(
                """
                SELECT payload_json
                FROM cst_states
                WHERE date < ?
                ORDER BY date DESC, updated_at DESC
                LIMIT 1
                """,
                (str(before_date),),
            ).fetchone()
        else:
            row = conn.execute(
                """
                SELECT payload_json
                FROM cst_states
                ORDER BY date DESC, updated_at DESC
                LIMIT 1
                """
            ).fetchone()
    return json.loads(row["payload_json"]) if row else None


def load_previous_cst_for_context(
    *,
    date: str | None,
    analysis_mode: str,
    end_time: str | None = None,
) -> dict | None:
    """Load the most relevant previous CST for a new daily or time-window update."""
    ensure_storage_initialized()
    with _connect() as conn:
        row = None
        if analysis_mode == "time_window" and date and end_time:
            row = conn.execute(
                """
                SELECT payload_json
                FROM cst_states
                WHERE analysis_mode = 'time_window'
                  AND (
                    (date = ? AND end_time < ?)
                    OR date < ?
                  )
                ORDER BY date DESC, end_time DESC, updated_at DESC
                LIMIT 1
                """,
                (str(date), str(end_time), str(date)),
            ).fetchone()
        elif date:
            row = conn.execute(
                """
                SELECT payload_json
                FROM cst_states
                WHERE date < ?
                ORDER BY date DESC, updated_at DESC
                LIMIT 1
                """,
                (str(date),),
            ).fetchone()
        else:
            row = conn.execute(
                """
                SELECT payload_json
                FROM cst_states
                ORDER BY date DESC, updated_at DESC
                LIMIT 1
                """
            ).fetchone()
    return json.loads(row["payload_json"]) if row else None
