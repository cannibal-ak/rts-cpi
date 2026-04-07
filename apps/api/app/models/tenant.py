"""Tenant and API client ORM models (control-plane)."""

import uuid
from sqlalchemy import Column, String, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
from app.core.database import Base


class Tenant(Base):
    __tablename__ = "tenant"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    slug = Column(String(64), nullable=False, unique=True)
    display_name = Column(String(256), nullable=False)
    is_active = Column(Boolean, nullable=False, server_default="true")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now())


class ApiClient(Base):
    __tablename__ = "api_client"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False)
    client_name = Column(String(128), nullable=False)
    client_key = Column(String(64), nullable=False, unique=True)
    hashed_secret = Column(Text, nullable=False)
    scopes = Column(JSONB, nullable=False, server_default="[]")
    is_active = Column(Boolean, nullable=False, server_default="true")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
