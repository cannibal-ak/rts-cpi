"""Row Level Security policies using session variable approach.

Every tenant-owned table gets:
  1. RLS enabled
  2. A policy checking current_setting('app.current_tenant')

Usage in app:
  SET app.current_tenant = '<tenant_id>';
  -- all subsequent queries are automatically filtered

Revision ID: 002
Revises: 001
Create Date: 2026-03-05
"""
from typing import Sequence, Union
from alembic import op

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# All tenant-owned tables that need RLS
RLS_TABLES = [
    "app_user",
    "role_binding",
    "tenant_feature",
    "source_system",
    "source_connection",
    "source_file",
    "import_job",
    "import_batch",
    "ingest_error",
    "provider_contract",
    "alert_rule",
    "alert_event",
    "audit_event",
    "saved_view",
    "export_job",
    "airline_cpi_snapshot",
    "cfl_cpi_snapshot",
]


def upgrade() -> None:
    # ────────────────────────────────────────────
    # Create a dedicated application role for row-level access.
    # The main 'cpi' superuser bypasses RLS, so we need a
    # non-superuser role for the FastAPI app connection.
    # ────────────────────────────────────────────
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'cpi_app') THEN
                CREATE ROLE cpi_app LOGIN PASSWORD 'cpi_app_secret';
            END IF;
        END
        $$;
    """)

    # Grant usage on public schema and all tables to cpi_app
    op.execute("GRANT USAGE ON SCHEMA public TO cpi_app;")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO cpi_app;")
    op.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO cpi_app;")
    # Grant sequence usage for UUID generation
    op.execute("GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO cpi_app;")
    op.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE ON SEQUENCES TO cpi_app;")

    # ────────────────────────────────────────────
    # Enable RLS and create policies for each table
    # ────────────────────────────────────────────
    for table in RLS_TABLES:
        policy_name = f"rls_{table}_tenant_isolation"

        # Enable RLS
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")

        # Force RLS even for table owner (important for testing)
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;")

        # Create policy: rows visible only when tenant_id matches session var
        # Using coalesce + nullif so an empty/unset variable returns no rows (safe default)
        op.execute(f"""
            CREATE POLICY {policy_name} ON {table}
                USING (
                    tenant_id::text = coalesce(
                        nullif(current_setting('app.current_tenant', true), ''),
                        '00000000-0000-0000-0000-000000000000'
                    )
                )
                WITH CHECK (
                    tenant_id::text = coalesce(
                        nullif(current_setting('app.current_tenant', true), ''),
                        '00000000-0000-0000-0000-000000000000'
                    )
                );
        """)

    # ────────────────────────────────────────────
    # Also create a bypass policy for the superuser role 'cpi'
    # so migrations and admin scripts still work without SET
    # ────────────────────────────────────────────
    for table in RLS_TABLES:
        op.execute(f"""
            CREATE POLICY rls_{table}_superuser_bypass ON {table}
                TO cpi
                USING (true)
                WITH CHECK (true);
        """)


def downgrade() -> None:
    for table in RLS_TABLES:
        op.execute(f"DROP POLICY IF EXISTS rls_{table}_tenant_isolation ON {table};")
        op.execute(f"DROP POLICY IF EXISTS rls_{table}_superuser_bypass ON {table};")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")

    op.execute("REVOKE ALL ON ALL TABLES IN SCHEMA public FROM cpi_app;")
    op.execute("DROP ROLE IF EXISTS cpi_app;")
