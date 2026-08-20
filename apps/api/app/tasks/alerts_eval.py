"""Celery tasks for the alerts evaluator — thin wrappers, no logic.

Everything of substance lives in app/services/alerts/runner.py so that the CLI,
the API's "run now" and these tasks all take exactly the same path, including
the RLS session and the per-tenant advisory lock.

DEPLOY NOTE: `celery_app.conf.include` is read at worker boot. Shipping this
module without restarting BOTH cpi-worker-1 and cpi-beat-1 means beat publishes
a task the worker answers with NotRegistered — silently, forever.
"""
from __future__ import annotations

import logging
from datetime import date

from sqlalchemy.exc import OperationalError

from app.worker import celery_app
from app.services.alerts import runner

logger = logging.getLogger("uvicorn.error")


@celery_app.task(name="app.tasks.alerts.evaluate_all_tenants", ignore_result=True)
def evaluate_all_tenants() -> dict:
    """Beat entry. Evaluates every tenant alerting is switched on for.

    For a tenant whose feed is up to date this creates events; for one whose
    newest capture pair has already been evaluated it is a ~30 ms no-op that
    inserts nothing, because the dedupe index suppresses every candidate.
    """
    summaries = runner.run_all_tenants()
    return {
        "tenants": len(summaries),
        "events_created": sum(s.events_created for s in summaries),
    }


@celery_app.task(
    name="app.tasks.alerts.evaluate_tenant",
    bind=True,
    autoretry_for=(OperationalError,),
    retry_backoff=True,
    max_retries=3,
)
def evaluate_tenant_task(self, tenant_id: str, tenant_code: str,
                         cap_date: str | None = None) -> dict:
    """Evaluate one tenant. Dispatched by the beat sweep and by ingestion.

    The ingestion hook fires for every committed AIRLINE job regardless of
    tenant, so most dispatches for a tenant that has not switched alerting on
    are expected and are NOT errors. They are returned as a skip rather than
    raised, so they do not enter the retry path or fill the log with tracebacks.
    """
    parsed = date.fromisoformat(cap_date) if cap_date else None
    try:
        summary = runner.run_latest(tenant_id, tenant_code, cap_date=parsed)
    except runner.AlertsNotEnabled as exc:
        logger.debug("ALERT_EVAL_SKIPPED tenant=%s reason=%s", tenant_code, exc)
        return {"tenant_code": tenant_code, "mode": "skipped_not_enabled",
                "events_created": 0}
    return summary.to_dict()


@celery_app.task(name="app.tasks.alerts.backfill_tenant", bind=True)
def backfill_tenant_task(self, tenant_id: str, tenant_code: str,
                         pairs: int = 60,
                         mark_read_before_pairs: int = 5,
                         force: bool = False) -> dict:
    return runner.run_backfill(
        tenant_id, tenant_code,
        pairs=pairs, mark_read_before_pairs=mark_read_before_pairs, force=force)
