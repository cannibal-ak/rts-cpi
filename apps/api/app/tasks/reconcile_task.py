"""Periodic self-heal for SFTP-schedule Redbeat entries.

The API lifespan calls ``reconcile_all`` once at startup. If Redbeat
entries get wiped while the API is up (e.g. a Beat crash storm), the
schedules silently stop firing until the next API restart. This task
runs every 15 minutes from Beat and re-runs the same reconciler so
drift heals itself.
"""
from __future__ import annotations

import logging

from app.core.database import SessionLocal
from app.services.redbeat_sync import reconcile_all
from app.worker import celery_app


logger = logging.getLogger(__name__)


@celery_app.task(
    name="app.tasks.reconcile_redbeat",
    ignore_result=True,
)
def reconcile_redbeat() -> None:
    with SessionLocal() as db:
        summary = reconcile_all(db)
    if summary["added"]:
        logger.warning(
            "reconcile heartbeat healed: added=%s removed=%s kept=%s",
            summary["added"], summary["removed"], summary["kept"],
        )
