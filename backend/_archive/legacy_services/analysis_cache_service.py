from collections import OrderedDict
from pathlib import Path
from threading import RLock
from typing import Any, Callable

import pickle

from services.sqlite_storage_service import (
    clear_file_cache_entries,
    load_file_cache_blob,
    prune_stale_file_cache_entries,
    save_file_cache_blob,
)


MAX_CACHE_SIZE = 8
CACHE_KEY_VERSION = "v2"

_CACHE: OrderedDict[tuple[str, str], Any] = OrderedDict()
_LOCK = RLock()


def _build_legacy_cache_identity(namespace: str, source_path: Path) -> str:
    """Build the legacy stat-based cache identity."""
    resolved = source_path.resolve()
    stat = resolved.stat()
    return ":".join(
        [
            "legacy",
            namespace,
            str(resolved),
            str(stat.st_mtime_ns),
            str(stat.st_size),
        ]
    )


def build_analysis_cache_key(
    namespace: str,
    source_path: str | None = None,
    date: str | None = None,
    run_metadata: dict | None = None,
    config_hash: str | None = None,
    prompt_policy_version: str | None = None,
    analysis_mode: str | None = None,
) -> str:
    """Build a cache key that can invalidate on data/config/evidence changes."""
    run_metadata = run_metadata if isinstance(run_metadata, dict) else {}
    source_file_hash = run_metadata.get("source_file_hash")
    evidence_db_hash = run_metadata.get("evidence_db_hash")
    config_hashes = run_metadata.get("config_hashes")
    if isinstance(config_hashes, dict):
        config_hash = config_hash or "|".join(
            f"{key}:{value}" for key, value in sorted(config_hashes.items()) if value
        )
    prompt_policy_version = prompt_policy_version or _extract_prompt_policy_version(run_metadata)
    quality_policy_version = _extract_quality_policy_version(run_metadata)
    effective_mode = analysis_mode or run_metadata.get("analysis_mode")

    if not source_file_hash or not evidence_db_hash or not config_hash or not prompt_policy_version:
        if source_path:
            try:
                return _build_legacy_cache_identity(namespace, Path(source_path))
            except Exception:
                pass
        return ":".join(
            [
                "legacy",
                namespace,
                str(date or run_metadata.get("analysis_date") or ""),
                str(source_path or run_metadata.get("source_path") or ""),
            ]
        )

    return ":".join(
        [
            namespace,
            CACHE_KEY_VERSION,
            str(date or run_metadata.get("analysis_date") or ""),
            str(source_file_hash),
            str(evidence_db_hash),
            str(config_hash),
            str(prompt_policy_version),
            str(quality_policy_version or ""),
            str(effective_mode or ""),
        ]
    )


def _extract_prompt_policy_version(run_metadata: dict[str, Any]) -> str | None:
    versions = run_metadata.get("config_versions")
    if not isinstance(versions, dict):
        return None
    return versions.get("prompt_policy.json")


def _extract_quality_policy_version(run_metadata: dict[str, Any]) -> str | None:
    versions = run_metadata.get("config_versions")
    if not isinstance(versions, dict):
        return None
    return versions.get("quality_checker_policy.json")


def _build_cache_lookup(namespace: str, source_path: Path, cache_key: str | None = None) -> tuple[tuple[str, str], str | None]:
    identity = cache_key or _build_legacy_cache_identity(namespace, source_path)
    lookup_path: str | None = cache_key if cache_key and f":{CACHE_KEY_VERSION}:" in cache_key else None
    return (namespace, identity), lookup_path


def get_or_compute_file_cache(
    namespace: str,
    source_path: Path,
    compute: Callable[[], Any],
    *,
    cache_key: str | None = None,
) -> tuple[Any, bool]:
    """Get or compute file cache."""
    key, sqlite_cache_key = _build_cache_lookup(namespace, source_path, cache_key=cache_key)
    namespace_key, identity = key
    resolved = source_path.resolve()
    stat = resolved.stat()

    with _LOCK:
        cached = _CACHE.get(key)
        if cached is not None:
            _CACHE.move_to_end(key)
            return cached, True

        stale_keys = [
            existing
            for existing in list(_CACHE.keys())
            if existing[0] == namespace_key and existing[1] == identity and existing != key
        ]
        for stale_key in stale_keys:
            _CACHE.pop(stale_key, None)

    try:
        prune_stale_file_cache_entries(
            namespace_key,
            str(resolved),
            stat.st_mtime_ns,
            stat.st_size,
            cache_key=sqlite_cache_key,
        )
        cached_blob = load_file_cache_blob(
            namespace_key,
            str(resolved),
            stat.st_mtime_ns,
            stat.st_size,
            cache_key=sqlite_cache_key,
        )
        if cached_blob is not None:
            cached_value = pickle.loads(cached_blob)
            with _LOCK:
                _CACHE[key] = cached_value
                _CACHE.move_to_end(key)
            return cached_value, True
    except Exception as exc:
        print(f"[Analysis Cache] SQLite cache read failed: {exc}")

    value = compute()

    with _LOCK:
        _CACHE[key] = value
        _CACHE.move_to_end(key)
        while len(_CACHE) > MAX_CACHE_SIZE:
            _CACHE.popitem(last=False)

    try:
        save_file_cache_blob(
            namespace_key,
            str(resolved),
            stat.st_mtime_ns,
            stat.st_size,
            value,
            cache_key=sqlite_cache_key,
        )
    except Exception as exc:
        print(f"[Analysis Cache] SQLite cache write failed: {exc}")

    return value, False


def clear_file_cache(namespace: str | None = None) -> None:
    """Clear file cache."""
    with _LOCK:
        if namespace is None:
            _CACHE.clear()
            return

        stale_keys = [key for key in list(_CACHE.keys()) if key[0] == namespace]
        for stale_key in stale_keys:
            _CACHE.pop(stale_key, None)

    clear_file_cache_entries(namespace)
