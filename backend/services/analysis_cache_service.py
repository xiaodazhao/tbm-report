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

_CACHE: OrderedDict[tuple[str, str, int, int], Any] = OrderedDict()
_LOCK = RLock()


def _build_cache_key(namespace: str, source_path: Path) -> tuple[str, str, int, int]:
    """Build cache key."""
    resolved = source_path.resolve()
    stat = resolved.stat()
    return (
        namespace,
        str(resolved),
        stat.st_mtime_ns,
        stat.st_size,
    )


def get_or_compute_file_cache(
    namespace: str,
    source_path: Path,
    compute: Callable[[], Any],
) -> tuple[Any, bool]:
    """Get or compute file cache."""
    key = _build_cache_key(namespace, source_path)
    namespace_key, resolved_path, mtime_ns, file_size = key

    with _LOCK:
        cached = _CACHE.get(key)
        if cached is not None:
            _CACHE.move_to_end(key)
            return cached, True

        stale_keys = [
            existing
            for existing in list(_CACHE.keys())
            if existing[:2] == key[:2] and existing != key
        ]
        for stale_key in stale_keys:
            _CACHE.pop(stale_key, None)

    try:
        prune_stale_file_cache_entries(namespace_key, resolved_path, mtime_ns, file_size)
        cached_blob = load_file_cache_blob(namespace_key, resolved_path, mtime_ns, file_size)
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
        save_file_cache_blob(namespace_key, resolved_path, mtime_ns, file_size, value)
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