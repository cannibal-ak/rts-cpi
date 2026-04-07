"""Import job, batch, and ingest error ORM models — tenant-owned."""

import uuid
from sqlalchemy import Column, String, Integer, Numeric, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
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
