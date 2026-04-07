"""Source system, connection, and file ORM models."""

import uuid
from sqlalchemy import Column, String, Boolean, BigInteger, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
from app.core.database import Base


class SourceSystem(Base):
    __tablename__ = "source_system"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False, index=True)
    code = Column(String(64), nullable=False)
    display_name = Column(String(256), nullable=False)
    domain = Column(String(16), nullable=False)
    validation_mode = Column(String(16), nullable=False, server_default="STRICT")
    is_active = Column(Boolean, nullable=False, server_default="true")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_source_system_code"),
    )


class SourceConnection(Base):
    __tablename__ = "source_connection"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False, index=True)
    source_system_id = Column(UUID(as_uuid=True), ForeignKey("source_system.id", ondelete="CASCADE"), nullable=False)
    conn_type = Column(String(32), nullable=False)
    config_json = Column(JSONB, nullable=False, server_default="{}")
    schedule_cron = Column(String(64), nullable=True)
    is_active = Column(Boolean, nullable=False, server_default="true")
    last_poll_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class SourceFile(Base):
    __tablename__ = "source_file"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False, index=True)
    source_system_id = Column(UUID(as_uuid=True), ForeignKey("source_system.id", ondelete="CASCADE"), nullable=False)
    file_name = Column(String(512), nullable=False)
    file_size_bytes = Column(BigInteger, nullable=True)
    file_hash = Column(String(128), nullable=True)
    received_at = Column(DateTime(timezone=True), server_default=func.now())
