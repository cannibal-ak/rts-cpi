"""ingestion overhaul: ingestion_jobs + ingestion_audit_log tables

Phase A of the ingestion overhaul. Adds two new tables to support the
authenticated, audited, two-stage (stage to commit) upload pipeline that
replaces the folder-watch path.

Notes:
- We use ``tenant_code`` (VARCHAR(16)) to stay consistent with the existing
  fact tables (``airline_cpi_snapshot``, ``cfl_cpi_snapshot``,
  ``jy_velocity_snapshot``) rather than the ``airline_code`` name suggested
  in the design doc, since FJL is a cruise/ferry tenant, not an airline.
- RLS follows the existing project pattern: a superuser-bypass policy for
  the ``cpi`` connection role plus a ``tenant_id``-based isolation policy
  for ``public``. The API connects as ``cpi`` and currently bypasses RLS,
  so application-layer auth (RequirePlatformAdmin) remains the primary gate.
- ``ingestion_jobs`` does not exist yet (alembic head is 017), so the
  conditional preservation logic is a no-op on first run; it is in place in
  case the table is ever pre-seeded by a fixture migration in a fork.

Revision ID: 018
Revises: 017
Create Date: 2026-04-30 11:30:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "018"
down_revision: Union[str, None] = "017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ── Enum definitions (used in upgrade and downgrade) ────────────────────

DOMAIN_VALUES = ("AIRLINE", "VELOCITY", "CFL")
STATUS_VALUES = (
    "STAGED",
    "VALIDATING",
    "VALIDATED",
    "COMMITTING",
    "COMMITTED",
    "REJECTED",
    "REPLACED",
    "FAILED",
)
MODE_VALUES = ("STRICT", "LENIENT")
AUDIT_ACTION_VALUES = (
    "UPLOADED",
    "VALIDATED",
    "COMMITTED",
    "REJECTED",
    "REPLACED",
    "CANCELLED",
    "DELETED",
)


def upgrade() -> None:
    bind = op.get_bind()

    # ── Enums ─────────────────────────────────────────────
    domain_enum = postgresql.ENUM(
        *DOMAIN_VALUES, name="ingestion_domain_enum", create_type=False
    )
    status_enum = postgresql.ENUM(
        *STATUS_VALUES, name="ingestion_status_enum", create_type=False
    )
    mode_enum = postgresql.ENUM(
        *MODE_VALUES, name="ingestion_mode_enum", create_type=False
    )
    audit_action_enum = postgresql.ENUM(
        *AUDIT_ACTION_VALUES, name="ingestion_audit_action_enum", create_type=False
    )

    domain_enum.create(bind, checkfirst=True)
    status_enum.create(bind, checkfirst=True)
    mode_enum.create(bind, checkfirst=True)
    audit_action_enum.create(bind, checkfirst=True)

    # ── ingestion_jobs ───────────────────────────────────
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    if "ingestion_jobs" not in existing_tables:
        op.create_table(
            "ingestion_jobs",
            sa.Column(
                "id",
                postgresql.UUID(as_uuid=True),
                primary_key=True,
                server_default=sa.text("gen_random_uuid()"),
            ),
            sa.Column(
                "tenant_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("tenant.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("tenant_code", sa.String(16), nullable=False),
            sa.Column("domain", domain_enum, nullable=False),
            sa.Column("filename", sa.Text(), nullable=False),
            sa.Column("file_hash", sa.String(64), nullable=False),
            sa.Column("file_size_bytes", sa.BigInteger(), nullable=False),
            sa.Column("file_date", sa.Date(), nullable=False),
            sa.Column(
                "status", status_enum, nullable=False, server_default="STAGED"
            ),
            sa.Column(
                "mode", mode_enum, nullable=False, server_default="STRICT"
            ),
            sa.Column("row_count_total", sa.Integer(), nullable=True),
            sa.Column("row_count_valid", sa.Integer(), nullable=True),
            sa.Column("row_count_rejected", sa.Integer(), nullable=True),
            sa.Column("validation_summary", postgresql.JSONB(), nullable=True),
            sa.Column(
                "uploaded_by_user_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("app_user.id"),
                nullable=False,
            ),
            sa.Column(
                "uploaded_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.Column("validated_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("committed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "replaced_by_job_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("ingestion_jobs.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("error_message", sa.Text(), nullable=True),
        )

    # ── ingestion_jobs indexes ─────────────────────────
    op.create_index(
        "ix_ingestion_jobs_tenant_code_file_date",
        "ingestion_jobs",
        ["tenant_id", "tenant_code", "file_date"],
    )
    op.create_index(
        "ix_ingestion_jobs_file_hash", "ingestion_jobs", ["file_hash"]
    )
    op.create_index(
        "ix_ingestion_jobs_status_uploaded_at",
        "ingestion_jobs",
        ["status", sa.text("uploaded_at DESC")],
    )

    # ── ingestion_audit_log ─────────────────────────────
    op.create_table(
        "ingestion_audit_log",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "job_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ingestion_jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "actor_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app_user.id"),
            nullable=False,
        ),
        sa.Column("action", audit_action_enum, nullable=False),
        sa.Column("actor_ip", postgresql.INET(), nullable=True),
        sa.Column(
            "timestamp",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("details", postgresql.JSONB(), nullable=True),
    )
    op.create_index(
        "ix_ingestion_audit_log_job_id_timestamp",
        "ingestion_audit_log",
        ["job_id", sa.text("timestamp DESC")],
    )

    # ── RLS on ingestion_jobs ───────────────────────────
    op.execute("ALTER TABLE ingestion_jobs ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE ingestion_jobs FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY rls_ingestion_jobs_superuser_bypass ON ingestion_jobs
            FOR ALL
            TO cpi
            USING (true)
            WITH CHECK (true)
        """
    )
    op.execute(
        """
        CREATE POLICY rls_ingestion_jobs_tenant_isolation ON ingestion_jobs
            FOR ALL
            USING (
                (tenant_id)::text = COALESCE(
                    NULLIF(current_setting('app.current_tenant', true), ''),
                    '00000000-0000-0000-0000-000000000000'
                )
            )
            WITH CHECK (
                (tenant_id)::text = COALESCE(
                    NULLIF(current_setting('app.current_tenant', true), ''),
                    '00000000-0000-0000-0000-000000000000'
                )
            )
        """
    )

    # ── RLS on ingestion_audit_log ──────────────────────
    op.execute("ALTER TABLE ingestion_audit_log ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE ingestion_audit_log FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY rls_ingestion_audit_log_superuser_bypass ON ingestion_audit_log
            FOR ALL
            TO cpi
            USING (true)
            WITH CHECK (true)
        """
    )
    op.execute(
        """
        CREATE POLICY rls_ingestion_audit_log_via_job ON ingestion_audit_log
            FOR ALL
            USING (
                EXISTS (
                    SELECT 1 FROM ingestion_jobs j
                    WHERE j.id = ingestion_audit_log.job_id
                      AND (j.tenant_id)::text = COALESCE(
                          NULLIF(current_setting('app.current_tenant', true), ''),
                          '00000000-0000-0000-0000-000000000000'
                      )
                )
            )
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP POLICY IF EXISTS rls_ingestion_audit_log_via_job ON ingestion_audit_log"
    )
    op.execute(
        "DROP POLICY IF EXISTS rls_ingestion_audit_log_superuser_bypass ON ingestion_audit_log"
    )
    op.execute("ALTER TABLE ingestion_audit_log DISABLE ROW LEVEL SECURITY")

    op.execute(
        "DROP POLICY IF EXISTS rls_ingestion_jobs_tenant_isolation ON ingestion_jobs"
    )
    op.execute(
        "DROP POLICY IF EXISTS rls_ingestion_jobs_superuser_bypass ON ingestion_jobs"
    )
    op.execute("ALTER TABLE ingestion_jobs DISABLE ROW LEVEL SECURITY")

    op.drop_index(
        "ix_ingestion_audit_log_job_id_timestamp", table_name="ingestion_audit_log"
    )
    op.drop_table("ingestion_audit_log")

    op.drop_index(
        "ix_ingestion_jobs_status_uploaded_at", table_name="ingestion_jobs"
    )
    op.drop_index("ix_ingestion_jobs_file_hash", table_name="ingestion_jobs")
    op.drop_index(
        "ix_ingestion_jobs_tenant_code_file_date", table_name="ingestion_jobs"
    )
    op.drop_table("ingestion_jobs")

    bind = op.get_bind()
    for enum_name in (
        "ingestion_audit_action_enum",
        "ingestion_mode_enum",
        "ingestion_status_enum",
        "ingestion_domain_enum",
    ):
        postgresql.ENUM(name=enum_name).drop(bind, checkfirst=True)
