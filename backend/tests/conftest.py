from pathlib import Path
import sys

import pytest


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


@pytest.fixture
def isolated_sqlite_env(monkeypatch, tmp_path):
    """Provide an isolated SQLite test environment."""
    import services.sqlite_storage_service as sqlite_storage_service

    db_path = tmp_path / "test_app.sqlite3"
    history_dir = tmp_path / "history_json"
    history_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(sqlite_storage_service, "APP_DB_PATH", db_path)
    monkeypatch.setattr(sqlite_storage_service, "HISTORY_MEMORY_DIR", history_dir)
    monkeypatch.setattr(sqlite_storage_service, "_SCHEMA_READY", False)

    return sqlite_storage_service, db_path, history_dir