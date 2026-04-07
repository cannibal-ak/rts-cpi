"""Audit event ORM model — tenant-owned."""

import uuid
from sqlalchemy import Column, String, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from app.core.database import Base


class AuditEvent(Base):
    __tablename__ = "audit_event"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False, index=True)
    actor = Column(String(128), nullable=False)
    action = Column(String(64), nullable=False)
    target_type = Column(String(64), nullable=False)
    target_id = Column(String(128), nullable=False)
    outcome = Column(String(16), nullable=False, server_default="success")
    event_time = Column(DateTime(timezone=True), server_default=func.now())
