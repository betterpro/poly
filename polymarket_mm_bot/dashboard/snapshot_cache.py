from __future__ import annotations

import os
import threading
import time
from typing import Any

import structlog

from polymarket_mm_bot.dashboard.status_store import load_status_snapshot

logger = structlog.get_logger()


def _refresh_seconds() -> float:
    # The poller reads the whole status snapshot from the DB on every tick, so a
    # short interval is the dominant source of DB egress. Default to 15s (the bot
    # only writes every ~10s anyway); override with DASHBOARD_POLL_SECONDS.
    try:
        value = float(os.environ.get("DASHBOARD_POLL_SECONDS", "15"))
    except ValueError:
        value = 15.0
    return max(value, 5.0)


REFRESH_SECONDS = _refresh_seconds()
_cache: dict[str, Any] = {}
_loaded_at: float = 0.0
_lock = threading.Lock()
_stop = threading.Event()
_poller: threading.Thread | None = None


def refresh_snapshot_cache() -> dict[str, Any]:
    global _cache, _loaded_at
    try:
        data = load_status_snapshot()
    except Exception as exc:
        logger.warning("snapshot_cache_refresh_failed", error=str(exc))
        with _lock:
            return dict(_cache)
    with _lock:
        _cache = data
        _loaded_at = time.time()
    return dict(_cache)


def get_cached_snapshot() -> dict[str, Any]:
    with _lock:
        if _cache:
            return dict(_cache)
    return refresh_snapshot_cache()


def cache_age_seconds() -> float | None:
    with _lock:
        if not _loaded_at:
            return None
        return max(time.time() - _loaded_at, 0.0)


def _poll_loop() -> None:
    while not _stop.is_set():
        refresh_snapshot_cache()
        _stop.wait(REFRESH_SECONDS)


def start_snapshot_poller() -> None:
    global _poller
    refresh_snapshot_cache()
    if _poller and _poller.is_alive():
        return
    _stop.clear()
    _poller = threading.Thread(target=_poll_loop, name="snapshot-poller", daemon=True)
    _poller.start()


def stop_snapshot_poller() -> None:
    _stop.set()
    if _poller and _poller.is_alive():
        _poller.join(timeout=2)
