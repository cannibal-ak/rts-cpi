"""Initial schema — control-plane + canonical raw tables with tenant_id.

Revision ID: 001
Revises: None
Create Date: 2026-03-05
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ════════════════════════════════════════════════
    # EXTENSIONS
    # ════════════════════════════════════════════════
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')

    # ════════════════════════════════════════════════
    # 1. CONTROL-PLANE TABLES (no tenant_id — platform-level)
    # ════════════════════════════════════════════════

    # ── tenant ─────────────────────────────────────
    op.create_table(
        "tenant",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("slug", sa.String(64), nullable=False, unique=True),
        sa.Column("display_name", sa.String(256), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    # ── api_client (machine-to-machine tokens per tenant) ──
    op.create_table(
        "api_client",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False),
        sa.Column("client_name", sa.String(128), nullable=False),
        sa.Column("client_key", sa.String(64), nullable=False, unique=True),
        sa.Column("hashed_secret", sa.Text, nullable=False),
        sa.Column("scopes", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_api_client_tenant", "api_client", ["tenant_id"])

    # ════════════════════════════════════════════════
    # 2. TENANT-OWNED TABLES (all have tenant_id FK)
    # ════════════════════════════════════════════════

    # ── app_user ───────────────────────────────────
    op.create_table(
        "app_user",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False),
        sa.Column("email", sa.String(256), nullable=False),
        sa.Column("display_name", sa.String(256), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("tenant_id", "email", name="uq_app_user_tenant_email"),
    )
    op.create_index("ix_app_user_tenant", "app_user", ["tenant_id"])

    # ── role_binding ───────────────────────────────
    op.create_table(
        "role_binding",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("app_user.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(32), nullable=False),  # TENANT_ADMIN | DATA_ENGINEER | ANALYST | REVENUE_MANAGER | AUDITOR
        sa.Column("granted_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("tenant_id", "user_id", "role", name="uq_role_binding"),
    )
    op.create_index("ix_role_binding_tenant", "role_binding", ["tenant_id"])

    # ── tenant_feature ─────────────────────────────
    op.create_table(
        "tenant_feature",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("label", sa.String(128), nullable=False),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.UniqueConstraint("tenant_id", "code", name="uq_tenant_feature_code"),
    )
    op.create_index("ix_tenant_feature_tenant", "tenant_feature", ["tenant_id"])

    # ── source_system ──────────────────────────────
    op.create_table(
        "source_system",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("display_name", sa.String(256), nullable=False),
        sa.Column("domain", sa.String(16), nullable=False),  # airline | cfl
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("tenant_id", "code", name="uq_source_system_code"),
    )
    op.create_index("ix_source_system_tenant", "source_system", ["tenant_id"])

    # ── source_connection ──────────────────────────
    op.create_table(
        "source_connection",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_system_id", UUID(as_uuid=True), sa.ForeignKey("source_system.id", ondelete="CASCADE"), nullable=False),
        sa.Column("conn_type", sa.String(32), nullable=False),  # sftp | object_storage | api_push | upload
        sa.Column("config_json", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("schedule_cron", sa.String(64), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("last_poll_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_source_connection_tenant", "source_connection", ["tenant_id"])

    # ── source_file ────────────────────────────────
    op.create_table(
        "source_file",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_system_id", UUID(as_uuid=True), sa.ForeignKey("source_system.id", ondelete="CASCADE"), nullable=False),
        sa.Column("file_name", sa.String(512), nullable=False),
        sa.Column("file_size_bytes", sa.BigInteger, nullable=True),
        sa.Column("file_hash", sa.String(128), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_source_file_tenant", "source_file", ["tenant_id"])

    # ── import_job ─────────────────────────────────
    op.create_table(
        "import_job",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_system_id", UUID(as_uuid=True), sa.ForeignKey("source_system.id"), nullable=True),
        sa.Column("source_file_id", UUID(as_uuid=True), sa.ForeignKey("source_file.id"), nullable=True),
        sa.Column("domain", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default=sa.text("'queued'")),
        sa.Column("records_total", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("records_valid", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("records_rejected", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("timeline", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_import_job_tenant", "import_job", ["tenant_id"])
    op.create_index("ix_import_job_status", "import_job", ["tenant_id", "status"])

    # ── import_batch ───────────────────────────────
    op.create_table(
        "import_batch",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False),
        sa.Column("import_job_id", UUID(as_uuid=True), sa.ForeignKey("import_job.id", ondelete="CASCADE"), nullable=False),
        sa.Column("batch_seq", sa.Integer, nullable=False, server_default=sa.text("1")),
        sa.Column("record_count", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_import_batch_tenant", "import_batch", ["tenant_id"])

    # ── ingest_error ───────────────────────────────
    op.create_table(
        "ingest_error",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False),
        sa.Column("import_job_id", UUID(as_uuid=True), sa.ForeignKey("import_job.id", ondelete="CASCADE"), nullable=False),
        sa.Column("row_number", sa.Integer, nullable=False),
        sa.Column("field", sa.String(64), nullable=False),
        sa.Column("error_code", sa.String(32), nullable=False),
        sa.Column("message", sa.Text, nullable=False),
        sa.Column("severity", sa.String(16), nullable=False, server_default=sa.text("'error'")),
    )
    op.create_index("ix_ingest_error_tenant", "ingest_error", ["tenant_id"])
    op.create_index("ix_ingest_error_job", "ingest_error", ["tenant_id", "import_job_id"])

    # ── provider_contract ──────────────────────────
    op.create_table(
        "provider_contract",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("provider", sa.String(128), nullable=False),
        sa.Column("domain", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default=sa.text("'draft'")),
        sa.Column("validation_mode", sa.String(8), nullable=False, server_default=sa.text("'STRICT'")),
        sa.Column("field_mappings", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("required_fields", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("optional_fields", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_provider_contract_tenant", "provider_contract", ["tenant_id"])

    # ── alert_rule ─────────────────────────────────
    op.create_table(
        "alert_rule",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("domain", sa.String(16), nullable=False),
        sa.Column("rule_type", sa.String(16), nullable=False),
        sa.Column("condition_json", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("owner", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_alert_rule_tenant", "alert_rule", ["tenant_id"])

    # ── alert_event ────────────────────────────────
    op.create_table(
        "alert_event",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False),
        sa.Column("rule_id", UUID(as_uuid=True), sa.ForeignKey("alert_rule.id", ondelete="CASCADE"), nullable=False),
        sa.Column("rule_name", sa.String(128), nullable=False),
        sa.Column("triggered_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("severity", sa.String(16), nullable=False, server_default=sa.text("'info'")),
        sa.Column("message", sa.Text, nullable=False),
        sa.Column("delivery_status", sa.String(16), nullable=False, server_default=sa.text("'pending'")),
    )
    op.create_index("ix_alert_event_tenant", "alert_event", ["tenant_id"])

    # ── audit_event ────────────────────────────────
    op.create_table(
        "audit_event",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False),
        sa.Column("actor", sa.String(128), nullable=False),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("target_type", sa.String(64), nullable=False),
        sa.Column("target_id", sa.String(128), nullable=False),
        sa.Column("outcome", sa.String(16), nullable=False, server_default=sa.text("'success'")),
        sa.Column("event_time", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_audit_event_tenant", "audit_event", ["tenant_id"])
    op.create_index("ix_audit_event_time", "audit_event", ["tenant_id", "event_time"])

    # ── saved_view ─────────────────────────────────
    op.create_table(
        "saved_view",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("domain", sa.String(16), nullable=False),
        sa.Column("filters", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("owner", sa.String(128), nullable=False),
        sa.Column("visibility", sa.String(16), nullable=False, server_default=sa.text("'private'")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_saved_view_tenant", "saved_view", ["tenant_id"])

    # ── export_job ─────────────────────────────────
    op.create_table(
        "export_job",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False),
        sa.Column("domain", sa.String(16), nullable=False),
        sa.Column("format", sa.String(16), nullable=False, server_default=sa.text("'csv'")),
        sa.Column("filters", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("status", sa.String(16), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("row_count", sa.Integer, nullable=True),
        sa.Column("file_url", sa.Text, nullable=True),
        sa.Column("requested_by", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_export_job_tenant", "export_job", ["tenant_id"])

    # ════════════════════════════════════════════════
    # 3. CANONICAL RAW DATA TABLES
    # ════════════════════════════════════════════════

    # ── airline_cpi_snapshot ───────────────────────
    op.create_table(
        "airline_cpi_snapshot",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        # Technical / lineage columns
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False),
        sa.Column("import_batch_id", UUID(as_uuid=True), sa.ForeignKey("import_batch.id"), nullable=True),
        sa.Column("source_file_id", UUID(as_uuid=True), sa.ForeignKey("source_file.id"), nullable=True),
        sa.Column("record_hash", sa.String(64), nullable=True),
        sa.Column("ingested_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        # Capture context
        sa.Column("cap_date", sa.Date, nullable=False),
        sa.Column("cap_time", sa.Time, nullable=False),
        sa.Column("trip_type", sa.String(4), nullable=False),
        # Reference airline
        sa.Column("ref_al", sa.String(3), nullable=False),
        sa.Column("ref_flt_num", sa.String(10), nullable=False),
        sa.Column("ref_org", sa.String(4), nullable=False),
        sa.Column("ref_dst", sa.String(4), nullable=False),
        sa.Column("ref_dep_date", sa.Date, nullable=False),
        sa.Column("ref_cab_code", sa.String(4), nullable=False),
        sa.Column("ref_tot_fare", sa.Numeric(12, 2), nullable=False),
        sa.Column("ref_base_fare", sa.Numeric(12, 2), nullable=False),
        sa.Column("ref_tax", sa.Numeric(12, 2), nullable=False),
        sa.Column("ref_yq", sa.Numeric(12, 2), nullable=False),
        sa.Column("ref_seats", sa.Integer, nullable=False),
        sa.Column("ref_curr", sa.String(4), nullable=True, server_default=sa.text("'GBP'")),
        # Competitor
        sa.Column("comp_al", sa.String(3), nullable=False),
        sa.Column("comp_flt_num", sa.String(10), nullable=False),
        sa.Column("comp_org", sa.String(4), nullable=False),
        sa.Column("comp_dst", sa.String(4), nullable=False),
        sa.Column("comp_dep_date", sa.Date, nullable=False),
        sa.Column("comp_cab_code", sa.String(4), nullable=False),
        sa.Column("comp_tot_fare", sa.Numeric(12, 2), nullable=False),
        sa.Column("comp_base_fare", sa.Numeric(12, 2), nullable=False),
        sa.Column("comp_tax", sa.Numeric(12, 2), nullable=False),
        sa.Column("comp_yq", sa.Numeric(12, 2), nullable=False),
        sa.Column("comp_seats", sa.Integer, nullable=False),
        sa.Column("comp_curr", sa.String(4), nullable=True, server_default=sa.text("'GBP'")),
        # Context
        sa.Column("pos", sa.String(4), nullable=False),
        sa.Column("poa", sa.String(4), nullable=False),
    )
    op.create_index("ix_air_snap_tenant", "airline_cpi_snapshot", ["tenant_id"])
    op.create_index("ix_air_snap_cap", "airline_cpi_snapshot", ["tenant_id", "cap_date"])
    op.create_index("ix_air_snap_route", "airline_cpi_snapshot", ["tenant_id", "ref_org", "ref_dst"])
    op.create_index("ix_air_snap_ref_al", "airline_cpi_snapshot", ["tenant_id", "ref_al"])
    op.create_index("ix_air_snap_comp_al", "airline_cpi_snapshot", ["tenant_id", "comp_al"])
    op.create_index("ix_air_snap_hash", "airline_cpi_snapshot", ["tenant_id", "record_hash"])

    # ── cfl_cpi_snapshot ──────────────────────────
    op.create_table(
        "cfl_cpi_snapshot",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        # Technical / lineage columns
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False),
        sa.Column("import_batch_id", UUID(as_uuid=True), sa.ForeignKey("import_batch.id"), nullable=True),
        sa.Column("source_file_id", UUID(as_uuid=True), sa.ForeignKey("source_file.id"), nullable=True),
        sa.Column("record_hash", sa.String(64), nullable=True),
        sa.Column("ingested_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        # Capture context
        sa.Column("cap_date", sa.Date, nullable=False),
        sa.Column("cap_time", sa.Time, nullable=False),
        sa.Column("trip_type", sa.String(16), nullable=False),
        # Core fields
        sa.Column("source", sa.String(64), nullable=False),
        sa.Column("org", sa.String(32), nullable=False),
        sa.Column("dest", sa.String(32), nullable=False),
        sa.Column("out_dep_date", sa.Date, nullable=False),
        sa.Column("out_dep_time", sa.Time, nullable=True),
        sa.Column("prod_family", sa.String(64), nullable=True),
        sa.Column("out_equip_name", sa.String(64), nullable=True),
        sa.Column("out_cab_type", sa.String(32), nullable=True),
        sa.Column("total_fare", sa.Numeric(12, 2), nullable=False),
        sa.Column("out_per_pax_fare", sa.Numeric(12, 2), nullable=True),
        sa.Column("out_veh_fare", sa.Numeric(12, 2), nullable=True),
        sa.Column("out_cab_fare", sa.Numeric(12, 2), nullable=True),
        sa.Column("out_taxes", sa.Numeric(12, 2), nullable=True),
        sa.Column("out_num_pax", sa.Integer, nullable=True),
        sa.Column("veh_size", sa.String(16), nullable=True),
        sa.Column("curr_code", sa.String(4), nullable=False, server_default=sa.text("'GBP'")),
        sa.Column("out_avail", sa.String(16), nullable=True),
    )
    op.create_index("ix_cfl_snap_tenant", "cfl_cpi_snapshot", ["tenant_id"])
    op.create_index("ix_cfl_snap_cap", "cfl_cpi_snapshot", ["tenant_id", "cap_date"])
    op.create_index("ix_cfl_snap_route", "cfl_cpi_snapshot", ["tenant_id", "org", "dest"])
    op.create_index("ix_cfl_snap_source", "cfl_cpi_snapshot", ["tenant_id", "source"])
    op.create_index("ix_cfl_snap_hash", "cfl_cpi_snapshot", ["tenant_id", "record_hash"])


def downgrade() -> None:
    # Drop raw data tables
    op.drop_table("cfl_cpi_snapshot")
    op.drop_table("airline_cpi_snapshot")
    # Drop tenant-owned tables (reverse creation order)
    op.drop_table("export_job")
    op.drop_table("saved_view")
    op.drop_table("audit_event")
    op.drop_table("alert_event")
    op.drop_table("alert_rule")
    op.drop_table("provider_contract")
    op.drop_table("ingest_error")
    op.drop_table("import_batch")
    op.drop_table("import_job")
    op.drop_table("source_file")
    op.drop_table("source_connection")
    op.drop_table("source_system")
    op.drop_table("tenant_feature")
    op.drop_table("role_binding")
    op.drop_table("app_user")
    op.drop_table("api_client")
    op.drop_table("tenant")
