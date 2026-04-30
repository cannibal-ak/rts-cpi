"""Audit event endpoints — tenant-aware DB queries with RBAC."""

from fastapi import APIRouter, Query, Depends
from sqlalchemy.orm import Session
from sqlalchemy import select, func

from app.core.deps import get_tenant_db, sanitize_filter
from app.models.audit import AuditEvent
from app.schemas.common import PaginatedResponse, PageInfo
from app.schemas.audit import AuditEventOut

router = APIRouter(
    prefix="/api/v1/audit",
    tags=["audit"],
)


@router.get("/events", response_model=PaginatedResponse[AuditEventOut])
def list_events(
    db: Session = Depends(get_tenant_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    actor: str | None = None,
    action: str | None = None,
):
    actor = sanitize_filter(actor, "actor")
    action = sanitize_filter(action, "action")

    q = select(AuditEvent)
    if actor:
        q = q.where(AuditEvent.actor.ilike(f"%{actor}%"))
    if action:
        q = q.where(AuditEvent.action == action)
    q = q.order_by(AuditEvent.event_time.desc())

    total = db.scalar(select(func.count()).select_from(q.subquery()))
    rows = db.scalars(q.offset((page - 1) * page_size).limit(page_size)).all()

    return PaginatedResponse(
        items=rows,
        page_info=PageInfo(total=total, page=page, page_size=page_size,
                           has_next=((page - 1) * page_size + page_size) < total),
    )
