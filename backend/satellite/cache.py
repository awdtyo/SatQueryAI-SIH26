"""Lightweight in-memory TTL cache for STAC search results."""

from __future__ import annotations

import hashlib
import json
import os
import time
from typing import Any

_TTL_SECONDS = int(os.getenv("SATQUERY_STAC_CACHE_TTL", "300"))  # 5 min default
_MAX_ENTRIES = int(os.getenv("SATQUERY_STAC_CACHE_MAX", "128"))

_cache: dict[str, tuple[float, Any]] = {}


def _hash_key(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def get_cached(key_payload: dict[str, Any]) -> Any | None:
    if _TTL_SECONDS <= 0:
        return None
    k = _hash_key(key_payload)
    entry = _cache.get(k)
    if not entry:
        return None
    ts, val = entry
    if time.time() - ts > _TTL_SECONDS:
        _cache.pop(k, None)
        return None
    return val


def set_cached(key_payload: dict[str, Any], value: Any) -> None:
    if _TTL_SECONDS <= 0:
        return
    k = _hash_key(key_payload)
    if len(_cache) >= _MAX_ENTRIES:
        # evict oldest
        oldest = min(_cache.items(), key=lambda x: x[1][0])[0]
        _cache.pop(oldest, None)
    _cache[k] = (time.time(), value)


def clear_cache() -> None:
    _cache.clear()
