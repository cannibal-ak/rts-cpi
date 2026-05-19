"""Rename the platform tenant from 'skywave' to 'rts'.

Renames everything that still says "skywave" in the database:

* ``tenant.slug``: ``'skywave'`` → ``'rts'`` (``display_name`` was already
  set to ``Revenue Technology Services`` in a prior change; not touched here).
* ``app_user`` admin row: ``email`` ``admin@skywave.com`` → ``admin@rts.com``;
  ``display_name`` ``Alex Rivera`` → ``RTS Admin``. ``password_hash`` is left
  intact so the existing password continues to work.
* Four RLS policies created in migration 020 on the SFTP-ingestion tables
  are renamed from ``<tbl>_skywave_only`` to ``<tbl>_rts_only``. The policy
  body compares the platform tenant UUID (``a0000000-…``), which is
  unchanged, so the policy semantics are identical — only the names move.

The platform tenant UUID (``a0000000-0000-0000-0000-000000000001``) is the
stable identifier referenced by foreign keys and 29k+ fact rows; it is
deliberately not changed by this migration.
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "026"
down_revision: Union[str, None] = "025"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Platform tenant UUID (unchanged; verified against tenant table 2026-05-19).
PLATFORM_TENANT_ID = "a0000000-0000-0000-0000-000000000001"

# Tables that carry the platform-only RLS policy created in migration 020.
_RLS_TABLES = (
    "sftp_connection",
    "ingestion_schedule",
    "ingestion_run",
    "ingested_file",
)


def _create_rts_policy(tbl: str) -> str:
    return f"""
        CREATE POLICY {tbl}_rts_only ON {tbl}
            FOR ALL
            USING (
                COALESCE(
                    NULLIF(current_setting('app.current_tenant', true), ''),
                    '00000000-0000-0000-0000-000000000000'
                ) = '{PLATFORM_TENANT_ID}'
            )
            WITH CHECK (
                COALESCE(
                    NULLIF(current_setting('app.current_tenant', true), ''),
                    '00000000-0000-0000-0000-000000000000'
                ) = '{PLATFORM_TENANT_ID}'
            )
    """


def _create_skywave_policy(tbl: str) -> str:
    # Exact body from migration 020 — used by the downgrade path.
    return f"""
        CREATE POLICY {tbl}_skywave_only ON {tbl}
            FOR ALL
            USING (
                COALESCE(
                    NULLIF(current_setting('app.current_tenant', true), ''),
                    '00000000-0000-0000-0000-000000000000'
                ) = '{PLATFORM_TENANT_ID}'
            )
            WITH CHECK (
                COALESCE(
                    NULLIF(current_setting('app.current_tenant', true), ''),
                    '00000000-0000-0000-0000-000000000000'
                ) = '{PLATFORM_TENANT_ID}'
            )
    """


def upgrade() -> None:
    # ── RLS policies: drop *_skywave_only, recreate as *_rts_only ──
    for tbl in _RLS_TABLES:
        op.execute(f"DROP POLICY IF EXISTS {tbl}_skywave_only ON {tbl}")
        op.execute(_create_rts_policy(tbl))

    # ── Tenant slug ──
    op.execute("UPDATE tenant SET slug = 'rts' WHERE slug = 'skywave'")

    # ── Admin user: email + display_name. Password hash left intact. ──
    op.execute(
        "UPDATE app_user "
        "   SET email = 'admin@rts.com', display_name = 'RTS Admin' "
        " WHERE email = 'admin@skywave.com'"
    )


def downgrade() -> None:
    # Exact reverse.
    op.execute(
        "UPDATE app_user "
        "   SET email = 'admin@skywave.com', display_name = 'Alex Rivera' "
        " WHERE email = 'admin@rts.com'"
    )
    op.execute("UPDATE tenant SET slug = 'skywave' WHERE slug = 'rts'")

    for tbl in _RLS_TABLES:
        op.execute(f"DROP POLICY IF EXISTS {tbl}_rts_only ON {tbl}")
        op.execute(_create_skywave_policy(tbl))
