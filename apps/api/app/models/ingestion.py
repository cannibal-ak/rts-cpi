"""Ingestion ORM models — tenant-owned (Phase A).

Also contains the new IngestionJob and IngestionAuditLog models added in
migration 018 for the ingestion overhaul (Phase A). IngestionJob / IngestionAuditLog are
the Phase A overhaul tables, written by the staged-then-committed
upload pipeline (used by the SFTP-driven scheduled ingestion path).
"""

import uuid
from sqlalchemy import BigInteger, Column, Date, String, Integer, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB, INET
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.database import Base


# ── New ingestion overhaul tables (migration 018) ──


class IngestionJob(Base):
    """Job record for the staged-then-committed upload pipeline."""

    __tablename__ = "ingestion_jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False)
    tenant_code = Column(String(16), nullable=False)
    domain = Column(String(16), nullable=False)
    filename = Column(Text, nullable=False)
    file_hash = Column(String(64), nullable=False)
    file_size_bytes = Column(BigInteger, nullable=False)
    file_date = Column(Date, nullable=False)
    status = Column(String(16), nullable=False, server_default="STAGED")
    mode = Column(String(16), nullable=False, server_default="STRICT")
    row_count_total = Column(Integer, nullable=True)
    row_count_valid = Column(Integer, nullable=True)
    row_count_rejected = Column(Integer, nullable=True)
    validation_summary = Column(JSONB, nullable=True)
    uploaded_by_user_id = Column(UUID(as_uuid=True), ForeignKey("app_user.id"), nullable=False)
    uploaded_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    validated_at = Column(DateTime(timezone=True), nullable=True)
    committed_at = Column(DateTime(timezone=True), nullable=True)
    replaced_by_job_id = Column(UUID(as_uuid=True), ForeignKey("ingestion_jobs.id", ondelete="SET NULL"), nullable=True)
    error_message = Column(Text, nullable=True)

    audit_entries = relationship(
        "IngestionAuditLog", back_populates="job", cascade="all, delete-orphan"
    )


class IngestionAuditLog(Base):
    """Append-only audit trail for ingestion job lifecycle events."""

    __tablename__ = "ingestion_audit_log"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id = Column(UUID(as_uuid=True), ForeignKey("ingestion_jobs.id", ondelete="CASCADE"), nullable=False)
    actor_user_id = Column(UUID(as_uuid=True), ForeignKey("app_user.id"), nullable=False)
    action = Column(String(16), nullable=False)
    actor_ip = Column(INET, nullable=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    details = Column(JSONB, nullable=True)

    job = relationship("IngestionJob", back_populates="audit_entries")
