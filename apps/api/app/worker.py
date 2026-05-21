"""Celery application instance for SFTP-driven scheduled ingestion (Phase 2).

Import-safe: defines the Celery app and configures it. No DB queries,
no broker connections at import. Tasks are auto-discovered from the
``include`` list when the worker boots.

Broker:  redis://redis:6379/1   (db 1, separate from app cache db 0)
Backend: redis://redis:6379/2   (db 2, task results only)
Beat:    redbeat (Redis-backed cron, schedules CRUD'd at runtime)
"""
from __future__ import annotations

from urllib.parse import urlparse, urlunparse

from celery import Celery

from app.core.config import settings


def _redis_db(url: str, db_num: int) -> str:
    """Return ``url`` with the path component replaced by ``/<db_num>``."""
    parsed = urlparse(url)
    return urlunparse(parsed._replace(path=f"/{db_num}"))


_BROKER = _redis_db(settings.redis_url, 1)
_BACKEND = _redis_db(settings.redis_url, 2)


celery_app = Celery(
    "cpi",
    broker=_BROKER,
    backend=_BACKEND,
    include=["app.tasks.sftp_pull", "app.tasks.reconcile_task"],
)

celery_app.conf.update(
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_reject_on_worker_lost=True,
    redbeat_redis_url=_BROKER,
    redbeat_lock_key=None,
)


# Fixed-cadence maintenance jobs. RedBeat seeds these into redis on
# ``setup_schedule`` and re-asserts them on every beat startup, so the
# entries survive redis flushes. Names here MUST NOT collide with the
# per-schedule entries written by ``app.services.redbeat_sync`` (which
# use the ``sched-`` prefix and are reconciled against the DB at API
# startup — see ``reconcile_all``).
celery_app.conf.beat_schedule = {
    "sftp-orphan-run-sweeper": {
        "task": "app.tasks.sftp_pull.sweep_orphan_runs",
        # Every 5 minutes. The sweeper itself enforces a 30-min minimum
        # row-age before touching anything; this cadence just controls
        # how soon an orphan is observed after that age is reached.
        "schedule": 300.0,
        "options": {"expires": 240.0},
    },
    "redbeat-reconcile-heartbeat": {
        "task": "app.tasks.reconcile_redbeat",
        # Every 15 minutes. Cheap self-heal in case sched-* entries
        # disappear between API restarts (e.g. a Beat crash storm).
        "schedule": 900.0,
    },
}
