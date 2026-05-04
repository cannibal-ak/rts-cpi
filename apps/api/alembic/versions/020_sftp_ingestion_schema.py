"""sftp ingestion schema: sftp_connection + ingestion_schedule + ingestion_run + ingested_file

Phase 1 of the SFTP-driven scheduled ingestion overhaul. Adds 4
operator-owned tables that back automated SFTP pulls. No application
code reads these yet (Phases 2-5 will wire Celery + REST + UI on top).

Tables:
* sftp_connection      — credentials + endpoint per tenant; password OR
                         private key (XOR via CHECK), both stored as
                         Fernet ciphertext (BYTEA).
* ingestion_schedule   — cron-driven pull schedule referencing one
                         sftp_connection; tenant_code identifies the
                         DATA tenant (jy/pw/fjl) the pulled data belongs
                         to. Schedules themselves are owned by skywave.
* ingestion_run        — one row per pull attempt (manual or scheduled);
                         counts files seen vs pulled vs committed.
* ingested_file        — one row per file observed during a run; idempotency
                         via UNIQUE (sha256, remote_filename).

RLS pattern (mirrors migration 018):
* ENABLE + FORCE row-level security on all 4 tables.
* {table}_superuser_bypass policy: USING (true) for role 'cpi'
  (the connection role today; same as 018).
* {table}_skywave_only policy: app.current_tenant must equal the
  Skywave tenant UUID. Operator-only access by design — these tables
  are not accessible to data-tenant users (jy/pw/fjl).

The prompt's intent for ingestion_run/ingested_file mentioned a
"MANUAL with triggered_by_user_id" branch; the schema as specified has
no triggered_by_user_id column, so that refinement is deferred to a
future migration. The simpler skywave-only policy covers the current
"operator-only" semantic for all four tables.

Revision ID: 020
Revises: 019
Create Date: 2026-05-04
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "020"
down_revision: Union[str, None] = "019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Canonical Skywave tenant UUID (verified against the tenant table on
# 2026-04-30 — see docs/ingestion-uuid-discovery.md).
SKYWAVE_TENANT_ID = "a0000000-0000-0000-0000-000000000001"


def upgrade() -> None:
    # ── 1. sftp_connection ──
    op.create_table(
        "sftp_connection",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("tenant_code", sa.String(16), nullable=False),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("host", sa.Text(), nullable=False),
        sa.Column("port", sa.Integer(), nullable=False, server_default="22"),
        sa.Column("username", sa.Text(), nullable=False),
        sa.Column("password_ciphertext", sa.LargeBinary(), nullable=True),
        sa.Column("private_key_ciphertext", sa.LargeBinary(), nullable=True),
        sa.Column("host_key_fingerprint", sa.Text(), nullable=True),
        sa.Column("remote_base_path", sa.Text(), nullable=False),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "created_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app_user.id"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(password_ciphertext IS NOT NULL) <> "
            "(private_key_ciphertext IS NOT NULL)",
            name="sftp_connection_auth_xor",
        ),
        sa.UniqueConstraint(
            "tenant_code", "name", name="uq_sftp_connection_tenant_name"
        ),
    )
    op.create_index(
        "ix_sftp_connection_tenant",
        "sftp_connection",
        ["tenant_code", "is_active"],
    )

    # ── 2. ingestion_schedule ──
    op.create_table(
        "ingestion_schedule",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "sftp_connection_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sftp_connection.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("tenant_code", sa.String(16), nullable=False),
        sa.Column("domain", sa.String(16), nullable=False),
        sa.Column("cron_expression", sa.String(64), nullable=False),
        sa.Column(
            "timezone",
            sa.String(64),
            nullable=False,
            server_default="UTC",
        ),
        sa.Column("filename_regex", sa.Text(), nullable=False),
        sa.Column(
            "replace_existing",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "is_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app_user.id"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_ingestion_schedule_enabled",
        "ingestion_schedule",
        ["is_enabled", "next_run_at"],
    )

    # ── 3. ingestion_run ──
    op.create_table(
        "ingestion_run",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "schedule_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ingestion_schedule.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("triggered_by", sa.String(16), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column(
            "files_seen", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "files_pulled", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "jobs_created", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "jobs_committed",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("detail_log", postgresql.JSONB(), nullable=True),
    )
    op.create_index(
        "ix_ingestion_run_schedule",
        "ingestion_run",
        ["schedule_id", sa.text("started_at DESC")],
    )

    # ── 4. ingested_file ──
    op.create_table(
        "ingested_file",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ingestion_run.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "schedule_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ingestion_schedule.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("remote_filename", sa.Text(), nullable=False),
        sa.Column("remote_size_bytes", sa.BigInteger(), nullable=False),
        sa.Column(
            "remote_mtime_utc",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column("sha256", sa.CHAR(64), nullable=False),
        sa.Column(
            "ingestion_job_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ingestion_jobs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("outcome", sa.String(16), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "sha256",
            "remote_filename",
            name="uq_ingested_file_sha_filename",
        ),
    )
    op.create_index(
        "ix_ingested_file_run", "ingested_file", ["run_id"]
    )
    op.create_index(
        "ix_ingested_file_sha", "ingested_file", ["sha256"]
    )

    # ── RLS on all four tables ──
    for tbl in (
        "sftp_connection",
        "ingestion_schedule",
        "ingestion_run",
        "ingested_file",
    ):
        op.execute(f"ALTER TABLE {tbl} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {tbl} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY {tbl}_superuser_bypass ON {tbl}
                FOR ALL
                TO cpi
                USING (true)
                WITH CHECK (true)
            """
        )
        op.execute(
            f"""
            CREATE POLICY {tbl}_skywave_only ON {tbl}
                FOR ALL
                USING (
                    COALESCE(
                        NULLIF(current_setting('app.current_tenant', true), ''),
                        '00000000-0000-0000-0000-000000000000'
                    ) = '{SKYWAVE_TENANT_ID}'
                )
                WITH CHECK (
                    COALESCE(
                        NULLIF(current_setting('app.current_tenant', true), ''),
                        '00000000-0000-0000-0000-000000000000'
                    ) = '{SKYWAVE_TENANT_ID}'
                )
            """
        )


def downgrade() -> None:
    # Drop policies + RLS in reverse order; idempotent (IF EXISTS).
    for tbl in (
        "ingested_file",
        "ingestion_run",
        "ingestion_schedule",
        "sftp_connection",
    ):
        op.execute(f"DROP POLICY IF EXISTS {tbl}_skywave_only ON {tbl}")
        op.execute(f"DROP POLICY IF EXISTS {tbl}_superuser_bypass ON {tbl}")
        op.execute(f"ALTER TABLE IF EXISTS {tbl} DISABLE ROW LEVEL SECURITY")

    # Drop tables in reverse FK order. DROP TABLE cascades through indexes
    # and FK constraints inside this migration; IF EXISTS makes the whole
    # downgrade safe to re-run.
    op.execute("DROP TABLE IF EXISTS ingested_file")
    op.execute("DROP TABLE IF EXISTS ingestion_run")
    op.execute("DROP TABLE IF EXISTS ingestion_schedule")
    op.execute("DROP TABLE IF EXISTS sftp_connection")
