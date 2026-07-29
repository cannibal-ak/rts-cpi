"""Tiny in-process TTL cache.

Deliberately dependency-free. Redis is present but wired only as the Celery
broker/result backend (core/config.py), and adding a network hop to the hot
read path is a bigger change than this warrants. The call signature can be
re-pointed at Redis later without touching callers.

CAVEAT: this cache is per-process. Prod runs gunicorn with 4 workers, so there
are 4 independent copies and a 60s TTL means up to 4 refreshes per minute
rather than 1. That is an acceptable trade for zero new moving parts, and the
values cached here (row counts, distinct-date lists) are cheap to recompute.
"""

import threading
import time
from typing import Any, Callable

_LOCK = threading.Lock()
_STORE: dict[Any, tuple[float, Any]] = {}


def cached(key: Any, ttl: float, producer: Callable[[], Any]) -> Any:
    """Return a cached value, or run `producer` and store its result.

    `producer` runs OUTSIDE the lock. That admits a thundering herd — N
    concurrent misses on the same cold key all hit the database — which is the
    right trade here: holding the lock across a DB call would serialise every
    unrelated cache user behind one slow query. The bound is small and the
    duplicated work is idempotent.
    """
    now = time.monotonic()
    with _LOCK:
        hit = _STORE.get(key)
        if hit is not None and hit[0] > now:
            return hit[1]

    value = producer()

    with _LOCK:
        _STORE[key] = (time.monotonic() + ttl, value)
    return value


def invalidate(namespace: str | None = None) -> None:
    """Drop everything, or every key whose first tuple element matches.

    Call with a namespace after an ingest run so freshly loaded dates appear
    without waiting out the TTL.
    """
    with _LOCK:
        if namespace is None:
            _STORE.clear()
            return
        stale = [k for k in _STORE if isinstance(k, tuple) and k and k[0] == namespace]
        for k in stale:
            _STORE.pop(k, None)
