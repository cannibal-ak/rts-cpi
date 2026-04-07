"""Admin models — provider contracts, saved views, export jobs. All tenant-owned."""

import uuid
from sqlalchemy import Column, String, Integer, DateTime, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
from app.core.database import Base


class ProviderContract(Base):
    __tablename__ = "provider_contract"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(128), nullable=False)
    provider = Column(String(128), nullable=False)
    domain = Column(String(16), nullable=False)
    status = Column(String(16), nullable=False, server_default="draft")
    validation_mode = Column(String(8), nullable=False, server_default="STRICT")
    field_mappings = Column(JSONB, nullable=False, server_default="{}")
    required_fields = Column(JSONB, nullable=False, server_default="[]")
    optional_fields = Column(JSONB, nullable=False, server_default="[]")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now())


class SavedView(Base):
    __tablename__ = "saved_view"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(256), nullable=False)
    domain = Column(String(16), nullable=False)
    filters = Column(JSONB, nullable=False, server_default="{}")
    owner = Column(String(128), nullable=False)
    visibility = Column(String(16), nullable=False, server_default="private")
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class ExportJob(Base):
    __tablename__ = "export_job"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False, index=True)
    domain = Column(String(16), nullable=False)
    format = Column(String(16), nullable=False, server_default="csv")
    filters = Column(JSONB, nullable=False, server_default="{}")
    status = Column(String(16), nullable=False, server_default="pending")
    row_count = Column(Integer, nullable=True)
    file_url = Column(Text, nullable=True)
    requested_by = Column(String(128), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
