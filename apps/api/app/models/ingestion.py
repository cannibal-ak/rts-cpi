"""Import job, batch, and ingest error ORM models — tenant-owned.

Also contains the new IngestionJob and IngestionAuditLog models added in
migration 018 for the ingestion overhaul (Phase A). The legacy ImportJob /
ImportBatch / IngestError tables are kept for historical rows and the
existing read-only router; the new flow writes only to IngestionJob /
IngestionAuditLog.
"""

import uuid
from sqlalchemy import BigInteger, Column, Date, String, Integer, Numeric, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB, INET
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.database import Base


class ImportJob(Base):
    __tablename__ = "import_job"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False, index=True)
    source_system_id = Column(UUID(as_uuid=True), ForeignKey("source_system.id"), nullable=True)
    source_file_id = Column(UUID(as_uuid=True), ForeignKey("source_file.id"), nullable=True)
    domain = Column(String(16), nullable=False)
    status = Column(String(16), nullable=False, server_default="queued")
    source_name = Column(String(256), nullable=True)
    validation_mode = Column(String(16), nullable=False, server_default="STRICT")
    records_total = Column(Integer, nullable=False, server_default="0")
    records_valid = Column(Integer, nullable=False, server_default="0")
    records_rejected = Column(Integer, nullable=False, server_default="0")
    timeline = Column(JSONB, nullable=False, server_default="[]")
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
    data_owner = Column(String(32), nullable=True, index=True)

    errors = relationship("IngestError", back_populates="job", cascade="all, delete-orphan")
    batches = relationship("ImportBatch", back_populates="job", cascade="all, delete-orphan")


class ImportBatch(Base):
    __tablename__ = "import_batch"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False, index=True)
    import_job_id = Column(UUID(as_uuid=True), ForeignKey("import_job.id", ondelete="CASCADE"), nullable=False)
    batch_seq = Column(Integer, nullable=False, server_default="1")
    record_count = Column(Integer, nullable=False, server_default="0")
    completeness_score = Column(Numeric(5, 2), nullable=True)
    warning_codes = Column(JSONB, nullable=False, server_default="[]")
    validation_results = Column(JSONB, nullable=False, server_default="{}")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    job = relationship("ImportJob", back_populates="batches")


class IngestError(Base):
    __tablename__ = "ingest_error"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False, index=True)
    import_job_id = Column(UUID(as_uuid=True), ForeignKey("import_job.id", ondelete="CASCADE"), nullable=False)
    row_number = Column(Integer, nullable=False)
    field = Column(String(64), nullable=False)
    error_code = Column(String(32), nullable=False)
    message = Column(Text, nullable=False)
    severity = Column(String(16), nullable=False, server_default="error")

    job = relationship("ImportJob", back_populates="errors")


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
