"""data correction: re-tag mis-attributed rows to correct tenant_id

The Phase A ingestion overhaul (alembic 018, commits 5ff2861..515a321)
made the JY-as-Skywave UUID hardcode bug structurally impossible going
forward. This migration is the one-time data correction for rows that
were written under the wrong tenant_id by the now-deleted
``scripts/ingest_daily.py`` before that fix landed.

Rows being re-tagged (per docs/ingestion-uuid-discovery.md):

* ``airline_cpi_snapshot`` — JY rows: ~7,022 rows move from
  ``a0000000-...`` (Skywave) to ``dd000000-...`` (JY).
* ``jy_velocity_snapshot`` — ~6,155 rows: Skywave → JY.
* ``import_job`` — 4 stale rows (one each for JY, PW, FJL, plus one
  duplicate path) all currently under Skywave's UUID, re-tagged to
  the canonical UUID for their ``data_owner``.
* ``import_batch`` — batches owned by the above import_job rows are
  re-tagged in the same direction.

WHERE clauses are idempotent: only rows currently mis-attributed are
updated, so re-running the migration is a no-op. Foreign-key constraints
are satisfied because all four canonical tenant rows exist
(`tenant.slug` in ('skywave','jy','pw','fjl')).

The downgrade reverts to the previous (mis-attributed) state. This is
provided for completeness; it is not the recommended way to back out —
restoring from the pre-Phase-A DB dump is safer if a roll-back is ever
needed.

Revision ID: 019
Revises: 018
Create Date: 2026-05-01 09:00:00.000000
"""
from typing import Sequence, Union

from alembic import op


revision: str = "019"
down_revision: Union[str, None] = "018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Canonical UUIDs from the tenant table (verified on 2026-04-30).
SKYWAVE = "a0000000-0000-0000-0000-000000000001"
JY = "dd000000-0000-0000-0000-000000000001"
PW = "bb000000-0000-0000-0000-000000000001"
FJL = "cc000000-0000-0000-0000-000000000001"


def upgrade() -> None:
    # ── Fact tables: only JY rows were mis-attributed ──
    op.execute(
        f"""
        UPDATE airline_cpi_snapshot
           SET tenant_id = '{JY}'
         WHERE tenant_code = 'JY'
           AND tenant_id = '{SKYWAVE}';
        """
    )
    op.execute(
        f"""
        UPDATE jy_velocity_snapshot
           SET tenant_id = '{JY}'
         WHERE tenant_code = 'JY'
           AND tenant_id = '{SKYWAVE}';
        """
    )

    # ── import_job: JY/PW/FJL all mis-attributed to Skywave; fix per data_owner ──
    op.execute(
        f"""
        UPDATE import_job
           SET tenant_id = '{JY}'
         WHERE data_owner = 'JY'
           AND tenant_id = '{SKYWAVE}';
        """
    )
    op.execute(
        f"""
        UPDATE import_job
           SET tenant_id = '{PW}'
         WHERE data_owner = 'PW'
           AND tenant_id = '{SKYWAVE}';
        """
    )
    op.execute(
        f"""
        UPDATE import_job
           SET tenant_id = '{FJL}'
         WHERE data_owner = 'FJL'
           AND tenant_id = '{SKYWAVE}';
        """
    )

    # ── import_batch: re-tag to match its parent job ──
    op.execute(
        f"""
        UPDATE import_batch b
           SET tenant_id = j.tenant_id
          FROM import_job j
         WHERE b.import_job_id = j.id
           AND b.tenant_id = '{SKYWAVE}'
           AND j.tenant_id <> '{SKYWAVE}';
        """
    )


def downgrade() -> None:
    # Revert each fact table and audit table to the pre-fix attribution.
    # Provided for completeness — see module docstring.
    op.execute(
        f"""
        UPDATE airline_cpi_snapshot
           SET tenant_id = '{SKYWAVE}'
         WHERE tenant_code = 'JY'
           AND tenant_id = '{JY}';
        """
    )
    op.execute(
        f"""
        UPDATE jy_velocity_snapshot
           SET tenant_id = '{SKYWAVE}'
         WHERE tenant_code = 'JY'
           AND tenant_id = '{JY}';
        """
    )
    op.execute(
        f"""
        UPDATE import_batch
           SET tenant_id = '{SKYWAVE}'
         WHERE import_job_id IN (
             SELECT id FROM import_job
              WHERE data_owner IN ('JY','PW','FJL')
         );
        """
    )
    op.execute(
        f"""
        UPDATE import_job
           SET tenant_id = '{SKYWAVE}'
         WHERE data_owner IN ('JY','PW','FJL')
           AND tenant_id IN ('{JY}','{PW}','{FJL}');
        """
    )
