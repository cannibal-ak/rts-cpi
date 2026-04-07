"""Tenant feature flag ORM model."""

import uuid
from sqlalchemy import Column, String, Boolean, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from app.core.database import Base


class TenantFeature(Base):
    __tablename__ = "tenant_feature"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False, index=True)
    code = Column(String(64), nullable=False)
    label = Column(String(128), nullable=False)
    category = Column(String(32), nullable=False)
    enabled = Column(Boolean, nullable=False, server_default="false")

    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_tenant_feature_code"),
    )
