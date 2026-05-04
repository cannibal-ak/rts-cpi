"""Postgres <-> redbeat sync service for ingestion schedules (Phase 3).

The router layer treats Postgres as the source of truth for SFTP
ingestion schedules; redbeat (a redis-backed celery beat scheduler)
caches them as cron entries the worker reads to fire scheduled pulls.
This module keeps both sides in lockstep:

* On schedule create/update/delete, the router calls ``register`` /
  ``update`` / ``unregister`` inside the same transactional path so
  the two stores never diverge (an early redbeat failure rolls back
  the SQL write; a late SQL failure has already committed redbeat,
  but the next ``reconcile_all`` corrects it).

* On API startup, the FastAPI lifespan calls ``reconcile_all`` once
  to repair any drift accumulated while the API was down (e.g. a
  redbeat key for a schedule that was deleted from the DB while beat
  was offline).

Module-load contract: NO celery / redbeat imports at module top.
Both are pulled in lazily inside the helper functions, which keeps
this module importable from contexts where celery has not been
configured (OpenAPI generation, isolated unit tests, FastAPI
type-introspection, etc.).
"""

import logging
from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.sftp import IngestionSchedule


# Our entry-name prefix (the part AFTER redbeat's configured key_prefix).
# Full redis key for a schedule is:
#   f"{_key_prefix()}{REDBEAT_KEY_PREFIX}{schedule_id}"
# e.g. "redbeat:sched-<uuid>"
REDBEAT_KEY_PREFIX = "sched-"
TASK_NAME = "app.tasks.sftp_pull.sftp_pull_for_schedule"

logger = logging.getLogger(__name__)


class RedbeatSyncError(Exception):
    """Raised when redbeat operations fail in a way the caller should
    surface as 5xx."""


# -- helpers (lazy imports) -------------------------------------------


def _entry_name(schedule_id) -> str:
    return f"{REDBEAT_KEY_PREFIX}{schedule_id}"


def _get_app():
    # Lazy import — keeps module load circular-import safe.
    from app.worker import celery_app

    return celery_app


def _key_prefix(app=None) -> str:
    """Return redbeat's runtime-configured key_prefix.

    Defaults to ``'redbeat:'`` in celery-redbeat 2.x; can be overridden
    via celery conf (``redbeat_key_prefix``). Always read live — never
    cache. ``RedBeatConfig`` is cheap to construct, and caching across
    worker / beat process restarts is the kind of thing that bites
    later.
    """
    from redbeat.schedulers import RedBeatConfig

    return RedBeatConfig(app or _get_app()).key_prefix


def _crontab_from_expr(cron_expression: str):
    from celery.schedules import crontab

    m, h, dom, mon, dow = cron_expression.split()
    return crontab(
        minute=m,
        hour=h,
        day_of_month=dom,
        month_of_year=mon,
        day_of_week=dow,
    )


# -- public API -------------------------------------------------------


def register(schedule: IngestionSchedule, *, app=None) -> None:
    """Idempotent: creates or overwrites the redbeat entry for this
    schedule. Raises ``ValueError`` if the schedule is disabled —
    callers must use :func:`unregister` or :func:`update` instead."""
    if not schedule.is_enabled:
        raise ValueError(
            "register() requires is_enabled=True; use unregister() or "
            "update() for disabled schedules"
        )
    try:
        from redbeat import RedBeatSchedulerEntry

        entry = RedBeatSchedulerEntry(
            name=_entry_name(schedule.id),
            task=TASK_NAME,
            schedule=_crontab_from_expr(schedule.cron_expression),
            args=[str(schedule.id)],
            app=app or _get_app(),
        )
        entry.save()
        logger.info(
            "redbeat register: %s cron=%r",
            _entry_name(schedule.id),
            schedule.cron_expression,
        )
    except Exception as e:
        raise RedbeatSyncError(
            f"register failed for {schedule.id}: {e}"
        ) from e


def unregister(schedule_id, *, app=None) -> None:
    """Idempotent: removes redbeat entry if present. Never raises on
    already-gone."""
    try:
        from redbeat import RedBeatSchedulerEntry
        from redbeat.schedulers import RedBeatSchedulerEntry as _E  # noqa: F401

        celery_app = app or _get_app()
        try:
            entry = RedBeatSchedulerEntry.from_key(
                f"{_key_prefix(celery_app)}{_entry_name(schedule_id)}",
                app=celery_app,
            )
            entry.delete()
            logger.info(
                "redbeat unregister: %s",
                _entry_name(schedule_id),
            )
        except KeyError:
            logger.debug(
                "redbeat unregister: %s not present (no-op)",
                _entry_name(schedule_id),
            )
    except RedbeatSyncError:
        raise
    except KeyError:
        pass  # already-gone is success
    except Exception as e:
        raise RedbeatSyncError(
            f"unregister failed for {schedule_id}: {e}"
        ) from e


def update(schedule: IngestionSchedule, *, app=None) -> None:
    """Reconciles a single schedule's redbeat state to its current DB
    state. Idempotent in either direction."""
    if schedule.is_enabled:
        unregister(schedule.id, app=app)
        register(schedule, app=app)
    else:
        unregister(schedule.id, app=app)


def is_registered(schedule_id, *, app=None) -> bool:
    """Best-effort presence check by key lookup. Returns False on any
    redis-side error so callers treating False as 'needs sync' is the
    safe default."""
    try:
        from redbeat import RedBeatSchedulerEntry

        celery_app = app or _get_app()
        RedBeatSchedulerEntry.from_key(
            f"{_key_prefix(celery_app)}{_entry_name(schedule_id)}",
            app=celery_app,
        )
        return True
    except KeyError:
        return False
    except Exception as e:
        logger.warning(
            "is_registered lookup failed for %s: %s",
            schedule_id,
            e,
        )
        return False


def reconcile_all(db: Session, *, app=None) -> dict:
    """Idempotent recovery: align redbeat with DB state.

    Returns a summary dict::

        {'added': [...], 'removed': [...], 'kept': [...]}

    where each list contains stringified schedule UUIDs. Top-level
    redis errors are wrapped as :class:`RedbeatSyncError`; per-entry
    failures are logged and skipped — partial drift is preferable to
    a hard fail at startup.
    """
    enabled = (
        db.query(IngestionSchedule)
        .filter(IngestionSchedule.is_enabled.is_(True))
        .all()
    )
    db_index = {str(s.id): s for s in enabled}

    celery_app = app or _get_app()
    # redbeat stores its keys on the broker's redis (db 1 in our setup),
    # NOT on the celery result backend (db 2). Prefer redbeat's own
    # helper; the backend.client path is a last-resort fallback for
    # redbeat versions that don't expose get_redis.
    try:
        from redbeat.schedulers import get_redis

        client = get_redis(celery_app)
    except Exception:
        try:
            client = celery_app.backend.client
        except AttributeError as e:
            raise RedbeatSyncError(
                f"reconcile_all: cannot obtain redis client ({e})"
            ) from e

    full_prefix = f"{_key_prefix(celery_app)}{REDBEAT_KEY_PREFIX}"
    redis_pattern = f"{full_prefix}*"
    try:
        raw_keys = client.keys(redis_pattern)
    except Exception as e:
        raise RedbeatSyncError(
            f"reconcile_all: redis KEYS failed ({e})"
        ) from e

    rb_ids = set()
    for raw in raw_keys:
        key = raw.decode() if isinstance(raw, bytes) else raw
        if not key.startswith(full_prefix):
            continue
        rb_ids.add(key[len(full_prefix):])

    db_ids = set(db_index.keys())
    to_add = db_ids - rb_ids
    to_remove = rb_ids - db_ids
    kept = db_ids & rb_ids

    added = []
    for sid in sorted(to_add):
        try:
            register(db_index[sid], app=celery_app)
            added.append(sid)
            logger.info("reconcile-add: %s", sid)
        except RedbeatSyncError as e:
            logger.warning("reconcile-add failed for %s: %s", sid, e)

    removed = []
    for sid in sorted(to_remove):
        try:
            unregister(sid, app=celery_app)
            removed.append(sid)
            logger.info("reconcile-remove: %s", sid)
        except RedbeatSyncError as e:
            logger.warning("reconcile-remove failed for %s: %s", sid, e)

    return {
        "added": added,
        "removed": removed,
        "kept": sorted(kept),
    }
