"""Alert rule and event ORM models — tenant-owned."""

import uuid
from sqlalchemy import Column, String, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
from app.core.database import Base


class AlertRule(Base):
    __tablename__ = "alert_rule"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(128), nullable=False)
    domain = Column(String(16), nullable=False)
    rule_type = Column(String(16), nullable=False)
    condition_json = Column(JSONB, nullable=False, server_default="{}")
    is_active = Column(Boolean, nullable=False, server_default="true")
    owner = Column(String(128), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class AlertEvent(Base):
    __tablename__ = "alert_event"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False, index=True)
    rule_id = Column(UUID(as_uuid=True), ForeignKey("alert_rule.id", ondelete="CASCADE"), nullable=False)
    rule_name = Column(String(128), nullable=False)
    triggered_at = Column(DateTime(timezone=True), server_default=func.now())
    severity = Column(String(16), nullable=False, server_default="info")
    message = Column(Text, nullable=False)
    delivery_status = Column(String(16), nullable=False, server_default="pending")
