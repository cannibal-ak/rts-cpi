"""Alert endpoints — tenant-aware DB queries with RBAC."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.core.deps import get_tenant_db, get_tenant_id
from app.models.alerts import AlertRule, AlertEvent
from app.schemas.alerts import AlertRuleOut, AlertRuleCreate, AlertEventOut

router = APIRouter(
    prefix="/api/v1/alerts",
    tags=["alerts"],
)


@router.get("/rules", response_model=list[AlertRuleOut])
def list_rules(db: Session = Depends(get_tenant_db)):
    return db.scalars(select(AlertRule)).all()


@router.post(
    "/rules",
    response_model=AlertRuleOut,
    status_code=201,
)
def create_rule(
    body: AlertRuleCreate,
    db: Session = Depends(get_tenant_db),
    tenant_id: str = Depends(get_tenant_id),
):
    rule = AlertRule(
        tenant_id=tenant_id,
        name=body.name,
        domain=body.domain,
        rule_type=body.rule_type,
        condition_json=body.condition_json if isinstance(body.condition_json, dict) else {},
        is_active=body.is_active,
        owner=body.owner or "system",
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


@router.get("/events", response_model=list[AlertEventOut])
def list_events(db: Session = Depends(get_tenant_db)):
    return db.scalars(select(AlertEvent).order_by(AlertEvent.triggered_at.desc())).all()
