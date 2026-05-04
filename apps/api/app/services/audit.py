"""Tiny audit-event writer used by the Phase 3 admin SFTP routers.

Phase A's existing ``ingestion_audit_log`` table is FK'd to
``ingestion_jobs.id`` (NOT NULL), so it cannot accept events for our
SFTP-side resources (connections, schedules, runs). The generic
``audit_event`` table — already populated by other Phase A flows and
exposed read-only at ``/api/v1/audit/events`` — fits the use case
without a migration.

The helper deliberately does NOT commit. Callers control the
surrounding transaction so the audit row is durable iff the parent
operation is. A failure inside :func:`record` is downgraded to a
WARNING log instead of bubbling out — losing one audit row is
preferable to crashing the parent action.

Tenant-id semantics: ``audit_event.tenant_id`` is set to the actor's
tenant_id — for SFTP admin actions this is always the Skywave
tenant, regardless of which data tenant the connection serves.
Phase 4 may add a separate ``target_tenant_code`` column if
per-data-tenant audit filtering is needed. Do not change this
without coordinating with the audit-event consumers (currently
``/api/v1/audit/events``).
"""

import logging
from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.audit import AuditEvent


logger = logging.getLogger("uvicorn.error")


def record(
    db: Session,
    *,
    tenant_id: UUID,
    actor: str,
    action: str,
    target_type: str,
    target_id: str,
    outcome: str = "success",
) -> None:
    """Append a row to ``audit_event``.

    The caller controls the db transaction — this helper does NOT
    commit. The router's surrounding ``commit`` / ``rollback`` governs
    whether the audit row is durable.

    Args:
        action: short verb like ``CREATE``, ``UPDATE``, ``DELETE``,
            ``TEST``, ``RUN_NOW``, ``ENABLE``, ``DISABLE``.
        target_type: ``sftp_connection`` / ``ingestion_schedule`` /
            ``ingestion_run`` (the resource being acted on).
        target_id: stringified UUID of the resource. For multi-row
            deletes pass the parent's id.
        outcome: ``success`` (default) or ``failure``. Caller logs
            failure when raising 4xx / 5xx after a partial state
            change.
    """
    try:
        evt = AuditEvent(
            tenant_id=tenant_id,
            actor=actor,
            action=action,
            target_type=target_type,
            target_id=target_id,
            outcome=outcome,
        )
        db.add(evt)
    except Exception as e:
        # Audit failure must not crash the parent operation. The next
        # reconcile / inspection surfaces the gap.
        logger.warning(
            "audit.record failed: action=%s target=%s/%s outcome=%s err=%s",
            action,
            target_type,
            target_id,
            outcome,
            e,
        )
