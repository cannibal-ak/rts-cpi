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
    include=["app.tasks.sftp_pull"],
)

celery_app.conf.update(
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_reject_on_worker_lost=True,
    redbeat_redis_url=_BROKER,
    redbeat_lock_timeout=30,
)
