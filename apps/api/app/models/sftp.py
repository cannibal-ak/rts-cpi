"""SQLAlchemy ORM models for SFTP-driven scheduled ingestion (migration 020).

Declarative mappings only — the four tables (sftp_connection,
ingestion_schedule, ingestion_run, ingested_file) are owned by alembic
revision 020; this module binds Python classes to existing columns and
adds NO new schema. Mirrors the Phase A idiom in
``app/models/ingestion.py``: SQLAlchemy 1.x ``Column()`` style,
``postgresql.UUID(as_uuid=True)``, ``DateTime(timezone=True)``, and
``JSONB`` from ``sqlalchemy.dialects.postgresql``.

Column-type notes:
  - ``password_ciphertext`` / ``private_key_ciphertext`` are
    ``LargeBinary`` (DB ``bytea``). ``app.core.crypto.encrypt_str``
    returns ``bytes``; Phase 2's task code reads each row via
    ``bytes(row['…'])`` before passing to ``decrypt_str``.
  - ``sha256`` is ``CHAR(64)`` to match migration 020's
    ``sa.CHAR(64)`` declaration (fixed-width hex digest).
  - ``detail_log`` is ``JSONB`` and matches the per-run audit log
    emitted by Phase 2's ``sftp_pull`` task.

Relationship surface is intentionally minimal: only the
``IngestionRun <-> IngestedFile`` pair is wired, because
``IngestionRunDetail`` serialisation walks ``run.ingested_files``.
Other joins (Schedule -> Connection, Run -> Schedule) are left to
explicit ``selectinload`` / SQL joins at query time so we don't build
a wider relationship surface than Step 4 actually consumes.
"""

import uuid

from sqlalchemy import (
    BigInteger,
    Boolean,
    CHAR,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


class SftpConnection(Base):
    __tablename__ = "sftp_connection"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_code = Column(String(16), nullable=False)
    name = Column(String(64), nullable=False)
    host = Column(Text, nullable=False)
    port = Column(Integer, nullable=False, server_default="22")
    username = Column(Text, nullable=False)
    password_ciphertext = Column(LargeBinary, nullable=True)
    private_key_ciphertext = Column(LargeBinary, nullable=True)
    host_key_fingerprint = Column(Text, nullable=True)
    remote_base_path = Column(Text, nullable=False)
    is_active = Column(Boolean, nullable=False, server_default="true")
    created_by_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("app_user.id"),
        nullable=False,
    )
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint(
            "(password_ciphertext IS NOT NULL) <> "
            "(private_key_ciphertext IS NOT NULL)",
            name="sftp_connection_auth_xor",
        ),
        UniqueConstraint(
            "tenant_code", "name",
            name="uq_sftp_connection_tenant_name",
        ),
    )


class IngestionSchedule(Base):
    __tablename__ = "ingestion_schedule"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    sftp_connection_id = Column(
        UUID(as_uuid=True),
        ForeignKey("sftp_connection.id", ondelete="RESTRICT"),
        nullable=False,
    )
    tenant_code = Column(String(16), nullable=False)
    domain = Column(String(16), nullable=False)
    cron_expression = Column(String(64), nullable=False)
    timezone = Column(String(64), nullable=False, server_default="UTC")
    filename_regex = Column(Text, nullable=False)
    replace_existing = Column(
        Boolean, nullable=False, server_default="false",
    )
    is_enabled = Column(Boolean, nullable=False, server_default="true")
    last_run_at = Column(DateTime(timezone=True), nullable=True)
    next_run_at = Column(DateTime(timezone=True), nullable=True)
    created_by_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("app_user.id"),
        nullable=False,
    )
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class IngestionRun(Base):
    __tablename__ = "ingestion_run"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    schedule_id = Column(
        UUID(as_uuid=True),
        ForeignKey("ingestion_schedule.id", ondelete="SET NULL"),
        nullable=True,
    )
    triggered_by = Column(String(16), nullable=False)
    started_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    finished_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(16), nullable=False)
    files_seen = Column(Integer, nullable=False, server_default="0")
    files_pulled = Column(Integer, nullable=False, server_default="0")
    jobs_created = Column(Integer, nullable=False, server_default="0")
    jobs_committed = Column(Integer, nullable=False, server_default="0")
    error_summary = Column(Text, nullable=True)
    detail_log = Column(JSONB, nullable=True)
    # Set by the celery task wrapper to ``self.request.id``. NULL on
    # rows created by non-celery callers (tests, manual scripts) and on
    # pre-migration-028 rows. The orphan-sweeper treats NULL as "no live
    # task can claim this" — eligible for sweep once past threshold.
    celery_task_id = Column(String(155), nullable=True)

    ingested_files = relationship(
        "IngestedFile",
        back_populates="run",
        cascade="all, delete-orphan",
    )


class IngestedFile(Base):
    __tablename__ = "ingested_file"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id = Column(
        UUID(as_uuid=True),
        ForeignKey("ingestion_run.id", ondelete="CASCADE"),
        nullable=False,
    )
    schedule_id = Column(
        UUID(as_uuid=True),
        ForeignKey("ingestion_schedule.id", ondelete="SET NULL"),
        nullable=True,
    )
    remote_filename = Column(Text, nullable=False)
    remote_size_bytes = Column(BigInteger, nullable=False)
    remote_mtime_utc = Column(DateTime(timezone=True), nullable=False)
    sha256 = Column(CHAR(64), nullable=False)
    ingestion_job_id = Column(
        UUID(as_uuid=True),
        ForeignKey("ingestion_jobs.id", ondelete="SET NULL"),
        nullable=True,
    )
    outcome = Column(String(16), nullable=False)
    error_message = Column(Text, nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    run = relationship("IngestionRun", back_populates="ingested_files")

    __table_args__ = (
        UniqueConstraint(
            "sha256", "remote_filename",
            name="uq_ingested_file_sha_filename",
        ),
    )
