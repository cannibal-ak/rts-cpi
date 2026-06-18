"""Add MFA tables (user_mfa, mfa_recovery_code) + RLS, and app_user.mfa_exempt.

Phase 1 of RBAC-aware TOTP MFA. Adds two tenant-owned tables and one
column; NO application code reads them yet (Phase 2 wires enrollment,
two-step login, and verification on top).

Tables:
* user_mfa            — one row per app_user (UNIQUE user_id); TOTP secret
                        stored as Fernet ciphertext (BYTEA) via
                        app.core.crypto. Tracks enablement, the replay
                        step, and verify-throttle counters.
* mfa_recovery_code   — many rows per app_user; SHA-256 hash of each
                        one-time recovery code (plaintext never stored).

Column:
* app_user.mfa_exempt — per-user override letting an otherwise-mandatory
                        user skip MFA. The boolean server_default false is
                        RETAINED (not dropped) to match the boolean-add
                        pattern in migration 015 (must_change_password) so
                        existing rows backfill to false without a separate
                        UPDATE.

RLS pattern mirrors migration 002 (tenant isolation — NOT the operator
skywave-only variant from migration 020): both tenant_id tables get
ENABLE + FORCE row-level security, an rls_<t>_tenant_isolation policy
keyed on current_setting('app.current_tenant'), and an
rls_<t>_superuser_bypass policy for role 'cpi'.

Revision ID: 033
Revises: 032
Create Date: 2026-06-18
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "033"
down_revision: Union[str, None] = "032"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Tenant-owned MFA tables receiving the standard two-policy RLS template
# from migration 002 (tenant_isolation + superuser_bypass).
RLS_TABLES = ("user_mfa", "mfa_recovery_code")


def upgrade() -> None:
    # ── 1. user_mfa ──
    op.create_table(
        "user_mfa",
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
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app_user.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("secret_ciphertext", sa.LargeBinary(), nullable=True),
        sa.Column(
            "enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_step", sa.BigInteger(), nullable=True),
        sa.Column(
            "failed_attempts",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
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
        sa.UniqueConstraint("user_id", name="uq_user_mfa_user"),
    )
    op.create_index("ix_user_mfa_tenant", "user_mfa", ["tenant_id"])

    # ── 2. mfa_recovery_code ──
    op.create_table(
        "mfa_recovery_code",
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
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app_user.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("code_hash", sa.Text(), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_mfa_recovery_code_tenant", "mfa_recovery_code", ["tenant_id"]
    )
    op.create_index(
        "ix_mfa_recovery_code_user", "mfa_recovery_code", ["user_id"]
    )

    # ── 3. app_user.mfa_exempt ──
    # server_default RETAINED (not dropped) to match migration 015's
    # boolean-add pattern (e.g. must_change_password): existing rows
    # backfill to false and the column stays usable without app-side
    # defaults.
    op.add_column(
        "app_user",
        sa.Column(
            "mfa_exempt",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )

    # ── 4. RLS: two-policy template from migration 002 ──
    for tbl in RLS_TABLES:
        op.execute(f"ALTER TABLE {tbl} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {tbl} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY rls_{tbl}_tenant_isolation ON {tbl}
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
                )
            """
        )
        op.execute(
            f"""
            CREATE POLICY rls_{tbl}_superuser_bypass ON {tbl}
                TO cpi
                USING (true)
                WITH CHECK (true)
            """
        )


def downgrade() -> None:
    # Drop policies + RLS first (reverse of upgrade); idempotent.
    for tbl in RLS_TABLES:
        op.execute(f"DROP POLICY IF EXISTS rls_{tbl}_superuser_bypass ON {tbl}")
        op.execute(f"DROP POLICY IF EXISTS rls_{tbl}_tenant_isolation ON {tbl}")
        op.execute(f"ALTER TABLE IF EXISTS {tbl} DISABLE ROW LEVEL SECURITY")

    op.drop_column("app_user", "mfa_exempt")

    op.drop_index("ix_mfa_recovery_code_user", table_name="mfa_recovery_code")
    op.drop_index("ix_mfa_recovery_code_tenant", table_name="mfa_recovery_code")
    op.execute("DROP TABLE IF EXISTS mfa_recovery_code")

    op.drop_index("ix_user_mfa_tenant", table_name="user_mfa")
    op.execute("DROP TABLE IF EXISTS user_mfa")
