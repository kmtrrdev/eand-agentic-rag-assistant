"""
Minimal in-process per-IP rate limiter for /chat.

The previous version of this API had no rate limiting at all on an endpoint
that makes a paid LLM call per request — a single dependency-free fixed-window
counter is enough to stop trivial cost-abuse without pulling in a new package.
Per-process only: fine for a single-worker deployment; a multi-worker/replica
deployment should front this with a shared limiter (e.g. Redis) instead.
"""
import threading
import time
from typing import Dict, Tuple

from app.config import settings

_lock = threading.Lock()
_windows: Dict[str, Tuple[float, int]] = {}
_WINDOW_SECONDS = 60.0


def is_rate_limited(client_key: str) -> bool:
    limit = settings.RATE_LIMIT_PER_MINUTE
    if limit <= 0:
        return False

    now = time.monotonic()
    with _lock:
        window_start, count = _windows.get(client_key, (now, 0))
        if now - window_start >= _WINDOW_SECONDS:
            window_start, count = now, 0
        count += 1
        _windows[client_key] = (window_start, count)
        return count > limit
