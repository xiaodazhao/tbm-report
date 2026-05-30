"""Helpers for lightweight run metadata and reproducibility records."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


RUN_METADATA_VERSION = "run_metadata_v1"


def sha256_file(path: str | Path) -> str | None:
    """Return a file SHA256 hash, or None when the file is unavailable."""
    try:
        file_path = Path(path)
        if not file_path.exists() or not file_path.is_file():
            return None
        hasher = hashlib.sha256()
        with file_path.open("rb") as file_obj:
            for chunk in iter(lambda: file_obj.read(1024 * 1024), b""):
                hasher.update(chunk)
        return hasher.hexdigest()
    except Exception:
        return None


def load_json_config(path: str | Path) -> dict[str, Any]:
    """Load a JSON config file without raising when it is missing or invalid."""
    try:
        config_path = Path(path)
        if not config_path.exists() or not config_path.is_file():
            return {}
        with config_path.open("r", encoding="utf-8") as file_obj:
            data = json.load(file_obj)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def build_config_metadata(config_paths: list[str] | None) -> dict[str, dict[str, Any]]:
    """Build schema-version and hash metadata for config files."""
    versions: dict[str, Any] = {}
    hashes: dict[str, Any] = {}

    for raw_path in config_paths or []:
        config_path = Path(raw_path)
        config_data = load_json_config(config_path)
        key = config_path.name
        versions[key] = (
            config_data.get("schema_version")
            or config_data.get("prompt_policy_version")
            or config_data.get("checker_policy_version")
            or "unknown"
        )
        hashes[key] = sha256_file(config_path)

    return {
        "config_versions": versions,
        "config_hashes": hashes,
    }


def build_run_metadata(
    context: dict | None = None,
    source_path: str | None = None,
    evidence_db_path: str | None = None,
    config_paths: list[str] | None = None,
    llm_model: str | None = None,
) -> dict[str, Any]:
    """Build lightweight reproducibility metadata for one analysis run."""
    context = context or {}
    source = Path(source_path) if source_path else None
    evidence = Path(evidence_db_path) if evidence_db_path else None
    config_meta = build_config_metadata(config_paths)

    report_config = {}
    for raw_path in config_paths or []:
        path_obj = Path(raw_path)
        if path_obj.name == "tbm_report_config.json":
            report_config = load_json_config(path_obj)
            break

    return {
        "schema_version": RUN_METADATA_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "analysis_date": context.get("date"),
        "analysis_mode": context.get("analysis_mode"),
        "source_file": source.name if source else context.get("source_name"),
        "source_path": str(source) if source else source_path,
        "source_file_hash": sha256_file(source) if source else None,
        "evidence_db_path": str(evidence) if evidence else evidence_db_path,
        "evidence_db_hash": sha256_file(evidence) if evidence else None,
        "config_versions": config_meta["config_versions"],
        "config_hashes": config_meta["config_hashes"],
        "code_version": os.getenv("GIT_COMMIT", "unknown"),
        "llm_model": llm_model,
        "availability_mode": report_config.get("evidence_filter_mode"),
        "cell_length_m": report_config.get("cell_length_m"),
        "lookahead_m": report_config.get("lookahead_m"),
    }
