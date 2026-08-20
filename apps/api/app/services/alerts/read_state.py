"""Per-user read state for alert events.

Read == a row exists in alert_event_read for (event, user). That makes every
write an idempotent upsert and every read an anti-join, so a double-click on
"mark read" and a racing poll cannot disagree.

Tenant scoping on every statement here comes from RLS on both tables, which is
why migration 040 gave alert_event_read a WITH CHECK as well as a USING clause:
the mark-all-read INSERT ... SELECT writes rows it never named individually.
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

# The bell polls the unread count every minute. Capping the scan means that cost
# is flat no matter how much history a tenant accumulates — a tenant with 40,000
# events pays the same as one with 40. Anything at or above the cap renders as
# "99+" anyway.
UNREAD_CAP = 500


def unread_count(db: Session, user_id: str) -> dict:
    n = db.execute(
        text(f"""
            SELECT count(*) FROM (
                SELECT 1
                  FROM alert_event e
                  LEFT JOIN alert_event_read r
                         ON r.event_id = e.id AND r.user_id = CAST(:uid AS uuid)
                 WHERE r.id IS NULL
                   AND e.delivery_status <> 'suppressed'
                 LIMIT {UNREAD_CAP + 1}
            ) x
        """),
        {"uid": user_id},
    ).scalar() or 0
    return {"unread": min(n, UNREAD_CAP), "capped": n > UNREAD_CAP}


def mark_read(db: Session, tenant_id: str, user_id: str, event_ids: list[str]) -> int:
    if not event_ids:
        return 0
    result = db.execute(
        text("""
            INSERT INTO alert_event_read (id, tenant_id, event_id, user_id)
            SELECT gen_random_uuid(), e.tenant_id, e.id, CAST(:uid AS uuid)
              FROM alert_event e
             WHERE e.id = ANY(CAST(:ids AS uuid[]))
            ON CONFLICT (event_id, user_id) DO NOTHING
        """),
        {"uid": user_id, "ids": event_ids},
    )
    return result.rowcount or 0


def mark_unread(db: Session, user_id: str, event_ids: list[str]) -> int:
    if not event_ids:
        return 0
    result = db.execute(
        text("""
            DELETE FROM alert_event_read
             WHERE user_id = CAST(:uid AS uuid)
               AND event_id = ANY(CAST(:ids AS uuid[]))
        """),
        {"uid": user_id, "ids": event_ids},
    )
    return result.rowcount or 0


def mark_all_read(db: Session, user_id: str, before: str | None = None) -> int:
    """Mark every visible event read. RLS confines this to the caller's tenant."""
    result = db.execute(
        text("""
            INSERT INTO alert_event_read (id, tenant_id, event_id, user_id)
            SELECT gen_random_uuid(), e.tenant_id, e.id, CAST(:uid AS uuid)
              FROM alert_event e
             WHERE (:before IS NULL OR e.triggered_at <= CAST(:before AS timestamptz))
               AND e.delivery_status <> 'suppressed'
            ON CONFLICT (event_id, user_id) DO NOTHING
        """),
        {"uid": user_id, "before": before},
    )
    return result.rowcount or 0
