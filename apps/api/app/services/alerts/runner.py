"""Session, RLS and locking for evaluator runs outside a request.

WHY THIS MODULE EXISTS AT ALL, AND THE ONE THING NOT TO CHANGE

The `cpi` role is `rolsuper = t` AND `rolbypassrls = t`. A worker that opens
`SessionLocal()` therefore has NO tenant isolation whatsoever — the
`rls_*_superuser_bypass` policies are not even consulted, because RLS is skipped
outright. `app/tasks/sftp_pull.py` uses `SessionLocal()`, and is right to:
ingestion legitimately spans tenants. The alerts evaluator does not, so it must
NOT copy that pattern.

Running on `SessionLocalRLS` + `set_tenant_context` turns a tenant-id bug from a
silent cross-tenant insert into somebody else's notification bell into a loud
`new row violates row-level security policy`. That is the entire argument.

`SET LOCAL` needs an open transaction; SQLAlchemy's autobegin provides one. The
advisory lock is transaction-scoped for the same reason — it releases on commit
or rollback, so there is no path that leaks it.
"""
from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from datetime import date

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import SessionLocal, SessionLocalRLS, set_tenant_context
from app.services.alerts import evaluator
from app.services.alerts.evaluator import EvalSummary
from app.services.alerts.views import is_alertable

logger = logging.getLogger("uvicorn.error")


def alerts_tenant_codes() -> set[str]:
    """Tenant codes alerting is switched on for.

    Env `CPI_ALERTS_TENANT_CODES`, default DA. Widening to another tenant is one
    variable, and it can only ever name tenants that are also in ALERT_VIEW_MAP.

    Read straight from the environment: `Settings` has no such field, so an
    earlier `getattr(settings, ...)` branch here was permanently dead and only
    made it look as though the value was part of the app's typed config.
    """
    raw = os.environ.get("CPI_ALERTS_TENANT_CODES", "DA")
    codes = {c.strip().upper() for c in raw.split(",") if c.strip()}
    return {c for c in codes if is_alertable(c)}


def enabled_tenant_codes() -> set[str]:
    """Codes that pass BOTH gates: the env allow-list and tenant_feature.alerts.

    Kept separate from list_alert_tenants() so the per-tenant entry points can
    enforce the same rule without re-running the whole tenant sweep.
    """
    allowed = alerts_tenant_codes()
    if not allowed:
        return set()
    db = SessionLocal()
    try:
        rows = db.execute(
            text("""
                SELECT upper(t.slug) AS code
                  FROM tenant t
                  JOIN tenant_feature f
                    ON f.tenant_id = t.id AND f.code = 'alerts' AND f.enabled
                 WHERE t.is_active
                   AND upper(t.slug) = ANY(:allowed)
            """),
            {"allowed": sorted(allowed)},
        ).scalars().all()
    finally:
        db.close()
    return set(rows)


class AlertsNotEnabled(RuntimeError):
    """Raised when evaluation is attempted for a tenant that has not opted in."""


def _require_enabled(tenant_code: str) -> None:
    """The gate that used to exist only in the tenant sweep.

    Every per-tenant entry point must pass through here. Without it the two
    gates the feature deliberately has — the env allow-list and the
    `tenant_feature.alerts` flag — were enforced ONLY by `list_alert_tenants()`,
    i.e. only by the beat sweep. Everything else reached the evaluator through a
    (tenant_id, tenant_code) pair and wrote events regardless:

      * the ingestion hook fires on ANY committed AIRLINE job, and JY and PW
        both have enabled daily SFTP schedules — so the next pull would have
        written alerts for tenants nobody switched the feature on for;
      * the admin backfill/evaluate endpoints gated only on "has a snapshot
        view", so they disagreed with the /admin/alerts/tenants listing sitting
        next to them.
    """
    code = (tenant_code or "").strip().upper()
    if code not in enabled_tenant_codes():
        raise AlertsNotEnabled(
            f"alerting is not enabled for {code}; it must be in "
            f"CPI_ALERTS_TENANT_CODES and have tenant_feature 'alerts' enabled"
        )


def list_alert_tenants() -> list[tuple[str, str]]:
    """(tenant_id, tenant_code) for every tenant alerting should run for.

    Reads on the superuser session because it is a cross-tenant question by
    nature. Everything downstream of it is per-tenant and RLS-scoped.
    """
    allowed = alerts_tenant_codes()
    if not allowed:
        return []
    db = SessionLocal()
    try:
        rows = db.execute(
            text("""
                SELECT t.id, upper(t.slug) AS code
                  FROM tenant t
                  JOIN tenant_feature f
                    ON f.tenant_id = t.id AND f.code = 'alerts' AND f.enabled
                 WHERE t.is_active
                   AND upper(t.slug) = ANY(:allowed)
                 ORDER BY t.slug
            """),
            {"allowed": sorted(allowed)},
        ).all()
        return [(str(r.id), r.code) for r in rows]
    finally:
        db.close()


@contextmanager
def tenant_session(tenant_id: str):
    """An RLS-scoped, evaluator-prepared session for one tenant."""
    db: Session = SessionLocalRLS()
    try:
        set_tenant_context(db, tenant_id)
        evaluator.prepare_session(db)
        yield db
    finally:
        db.close()


def _try_lock(db: Session, tenant_id: str) -> bool:
    return bool(db.execute(
        text("SELECT pg_try_advisory_xact_lock(hashtext('alerts_eval:' || :t))"),
        {"t": tenant_id},
    ).scalar())


def run_latest(
    tenant_id: str, tenant_code: str, *,
    cap_date: date | None = None, dry_run: bool = False, mode: str = "live",
    force: bool = False,
) -> EvalSummary:
    """Evaluate the newest capture pair for one tenant, under lock.

    `force` is for a platform admin deliberately seeding a tenant that is not
    switched on yet. It is never set by the beat sweep or the ingestion hook.
    """
    if not force:
        _require_enabled(tenant_code)
    with tenant_session(tenant_id) as db:
        if not _try_lock(db, tenant_id):
            logger.info("ALERT_EVAL_LOCKED tenant=%s", tenant_code)
            return EvalSummary(tenant_code=tenant_code, mode="skipped_locked",
                               note="another evaluation is already running")
        summary = evaluator.evaluate_latest(
            db, tenant_id, tenant_code,
            cap_date=cap_date, mode=mode, dry_run=dry_run)
        if dry_run:
            db.rollback()
        else:
            db.commit()
        logger.info(
            "ALERT_EVAL_DONE tenant=%s cap=%s prev=%s groups=%s created=%s "
            "deduped=%s ms=%s mode=%s",
            tenant_code, summary.cap_date, summary.prev_cap_date,
            summary.groups_evaluated, summary.events_created,
            summary.events_suppressed_dedupe, summary.duration_ms, summary.mode,
        )
        return summary


def run_backfill(
    tenant_id: str, tenant_code: str, *,
    pairs: int = 60, mark_read_before_pairs: int = 5, force: bool = False,
) -> dict:
    """Backfill one tenant, under lock. Returns an aggregate summary."""
    if not force:
        _require_enabled(tenant_code)
    with tenant_session(tenant_id) as db:
        if not _try_lock(db, tenant_id):
            return {"tenant_code": tenant_code, "mode": "skipped_locked",
                    "events_created": 0}
        summaries = evaluator.backfill(
            db, tenant_id, tenant_code,
            pairs=pairs, mark_read_before_pairs=mark_read_before_pairs)
        db.commit()
        return {
            "tenant_code": tenant_code,
            "mode": "backfill",
            "pairs_evaluated": len(summaries),
            "events_created": sum(s.events_created for s in summaries),
            "events_suppressed_dedupe": sum(s.events_suppressed_dedupe for s in summaries),
            "groups_evaluated": sum(s.groups_evaluated for s in summaries),
            "captures_skipped_incomplete": sum(
                s.captures_skipped_incomplete for s in summaries),
            "first_cap_date": (
                summaries[0].cap_date.isoformat() if summaries and summaries[0].cap_date else None),
            "last_cap_date": (
                summaries[-1].cap_date.isoformat() if summaries and summaries[-1].cap_date else None),
        }


def run_all_tenants() -> list[EvalSummary]:
    out = []
    for tenant_id, code in list_alert_tenants():
        try:
            out.append(run_latest(tenant_id, code))
        except Exception:
            # One tenant's bad data must not stop the rest.
            logger.exception("ALERT_EVAL_FAILED tenant=%s", code)
    return out
