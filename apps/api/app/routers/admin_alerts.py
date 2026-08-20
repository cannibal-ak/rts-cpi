"""Platform-admin operations for the alerts engine.

    POST   /api/v1/admin/alerts/backfill        evaluate the last N capture pairs
    POST   /api/v1/admin/alerts/evaluate        run one tenant synchronously
    DELETE /api/v1/admin/alerts/events          purge by tenant + evaluation mode
    GET    /api/v1/admin/alerts/tenants         who alerting runs for

Backfill runs inline rather than through Celery: measured at 3.6 s for 60 pairs
against 4.3M rows, which is comfortably inside an HTTP request and avoids a
task-state polling endpoint that would exist only for this. If a tenant ever
gets slow enough to need dispatching, `runner.run_backfill` is already the unit
a task would wrap.

The purge earns its place: the dedupe index means re-running a backfill after
changing a threshold is a no-op, so without a way to clear the previous run the
only recovery is manual SQL against production.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.database import SessionLocal
from app.core.deps import RequirePlatformAdmin
from app.services.alerts import runner
from app.services.alerts.views import is_alertable

from sqlalchemy import text

logger = logging.getLogger("uvicorn.error")

router = APIRouter(
    prefix="/api/v1/admin/alerts",
    tags=["Admin - Alerts"],
    dependencies=[Depends(RequirePlatformAdmin())],
)


def _resolve(tenant_code: str) -> tuple[str, str]:
    """Map a tenant code to its id, checking only that it COULD be alerted on.

    Whether alerting is actually enabled for it is a separate question, enforced
    by runner._require_enabled at the point of evaluation — so that the same gate
    applies to the beat sweep and the ingestion hook, not just to this router.
    """
    code = tenant_code.strip().upper()
    if not is_alertable(code):
        raise HTTPException(400, f"tenant {code} has no snapshot view for alerting")
    db = SessionLocal()
    try:
        row = db.execute(
            text("SELECT id FROM tenant WHERE upper(slug) = :c"), {"c": code}
        ).first()
    finally:
        db.close()
    if row is None:
        raise HTTPException(404, f"no tenant with code {code}")
    return str(row.id), code


@router.get("/tenants")
def list_tenants():
    return [{"tenant_id": t, "tenant_code": c} for t, c in runner.list_alert_tenants()]


@router.post("/backfill")
def backfill(
    tenant_code: str = Query(..., description="e.g. DA"),
    pairs: int = Query(60, ge=1, le=400),
    mark_read_before_pairs: int = Query(5, ge=0, le=100),
    force: bool = Query(
        False,
        description="evaluate a tenant that has not switched alerting on yet"),
):
    tenant_id, code = _resolve(tenant_code)
    try:
        result = runner.run_backfill(
            tenant_id, code, pairs=pairs,
            mark_read_before_pairs=mark_read_before_pairs, force=force)
    except runner.AlertsNotEnabled as exc:
        # Refuse rather than quietly seeding a tenant that never opted in.
        # `force=true` is the deliberate way to seed one ahead of enabling it.
        raise HTTPException(409, str(exc))
    logger.info("ALERT_BACKFILL_REQUESTED tenant=%s pairs=%s created=%s",
                code, pairs, result.get("events_created"))
    return result


@router.post("/evaluate")
def evaluate(
    tenant_code: str = Query(...),
    dry_run: bool = Query(False),
    force: bool = Query(False),
):
    tenant_id, code = _resolve(tenant_code)
    try:
        summary = runner.run_latest(
            tenant_id, code, dry_run=dry_run, force=force)
    except runner.AlertsNotEnabled as exc:
        raise HTTPException(409, str(exc))
    return summary.to_dict()


@router.delete("/events")
def purge_events(
    tenant_code: str = Query(...),
    evaluation_mode: str | None = Query(
        None, pattern="^(live|backfill|manual|preview)$",
        description="omit to purge every mode for the tenant"),
):
    tenant_id, code = _resolve(tenant_code)
    db = SessionLocal()          # superuser: this is a cross-tenant admin op
    try:
        params = {"t": tenant_id}
        clause = "tenant_id = CAST(:t AS uuid)"
        if evaluation_mode:
            clause += " AND evaluation_mode = :mode"
            params["mode"] = evaluation_mode
        # Receipts cascade on the event FK, so deleting events is enough.
        deleted = db.execute(
            text(f"DELETE FROM alert_event WHERE {clause}"), params).rowcount
        db.commit()
    finally:
        db.close()
    logger.info("ALERT_EVENTS_PURGED tenant=%s mode=%s deleted=%s",
                code, evaluation_mode or "*", deleted)
    return {"tenant_code": code, "evaluation_mode": evaluation_mode, "deleted": deleted}
