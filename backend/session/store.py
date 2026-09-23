"""In-memory conversational session store — per-session SatelliteAsset persistence."""

from __future__ import annotations

import time
import uuid
from typing import Any

from backend.core.assets import SatelliteAsset

# Simple in-memory store; keyed by session_id (provided by client or generated)
_store: dict[str, dict[str, Any]] = {}
_MAX_SESSIONS = 1000
_TTL_S = 3600 * 4  # 4 hours


def get_session(session_id: str | None) -> dict[str, Any]:
    if not session_id:
        session_id = str(uuid.uuid4())
    now = time.time()
    # Cleanup expired
    expired = [k for k, v in _store.items() if now - v.get("_ts", 0) > _TTL_S]
    for k in expired:
        _store.pop(k, None)
    if len(_store) > _MAX_SESSIONS:
        # evict oldest
        oldest = sorted(_store.items(), key=lambda x: x[1].get("_ts", 0))[:100]
        for k, _ in oldest:
            _store.pop(k, None)
    if session_id not in _store:
        _store[session_id] = {"_ts": now, "assets": [], "history": [], "session_id": session_id}
    _store[session_id]["_ts"] = now
    return _store[session_id]


def set_assets(session_id: str, assets: list[SatelliteAsset]) -> None:
    sess = get_session(session_id)
    sess["assets"] = assets
    sess["_ts"] = time.time()


def get_assets(session_id: str) -> list[SatelliteAsset]:
    sess = get_session(session_id)
    return sess.get("assets", [])


def append_history(session_id: str, query: str, answer: str) -> None:
    sess = get_session(session_id)
    sess.setdefault("history", []).append({"query": query, "answer": answer, "ts": time.time()})
    # keep last 20
    if len(sess["history"]) > 20:
        sess["history"] = sess["history"][-20:]


def clear_session(session_id: str) -> None:
    _store.pop(session_id, None)
