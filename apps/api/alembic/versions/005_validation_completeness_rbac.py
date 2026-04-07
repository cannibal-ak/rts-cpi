"""Add validation mode, completeness scoring, and source_name denormalization.

Revision ID: 005
Revises: 004
Create Date: 2026-03-05
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── source_system: validation_mode ──
    op.add_column("source_system", sa.Column("validation_mode", sa.String(16), server_default="STRICT", nullable=False))

    # ── import_job: source_name (denormalized), validation_mode ──
    op.add_column("import_job", sa.Column("source_name", sa.String(256), nullable=True))
    op.add_column("import_job", sa.Column("validation_mode", sa.String(16), server_default="STRICT", nullable=False))

    # ── import_batch: completeness scoring for COMPAT mode ──
    op.add_column("import_batch", sa.Column("completeness_score", sa.Numeric(5, 2), nullable=True))
    op.add_column("import_batch", sa.Column("warning_codes", JSONB, server_default="[]", nullable=False))
    op.add_column("import_batch", sa.Column("validation_results", JSONB, server_default="{}", nullable=False))

    # ── Backfill source_name on existing import_jobs from source_system ──
    op.execute("""
        UPDATE import_job j
        SET source_name = ss.display_name
        FROM source_system ss
        WHERE j.source_system_id = ss.id
          AND j.source_name IS NULL;
    """)

    # ── Backfill validation_mode on existing import_jobs from source_system ──
    op.execute("""
        UPDATE import_job j
        SET validation_mode = ss.validation_mode
        FROM source_system ss
        WHERE j.source_system_id = ss.id;
    """)

    # ── Update seed import_batches with sample completeness data ──
    # For CFL batches (tenant B), set COMPAT completeness scores
    op.execute("""
        UPDATE import_batch ib
        SET completeness_score = 87.50,
            warning_codes = '["MISSING_VEH_FARE", "APPROX_TAX"]'::jsonb,
            validation_results = '{"total_fields": 16, "present_fields": 14, "optional_missing": ["out_cab_fare", "out_veh_fare"], "warnings": [{"code": "MISSING_VEH_FARE", "message": "Vehicle fare not provided, defaulted to 0"}, {"code": "APPROX_TAX", "message": "Tax breakdown approximated from total"}]}'::jsonb
        FROM import_job ij
        WHERE ib.import_job_id = ij.id
          AND ij.domain = 'cfl';
    """)

    # Mark CFL source systems as COMPAT
    op.execute("""
        UPDATE source_system
        SET validation_mode = 'COMPAT'
        WHERE domain = 'cfl';
    """)

    # Mark CFL import jobs as COMPAT
    op.execute("""
        UPDATE import_job
        SET validation_mode = 'COMPAT'
        WHERE domain = 'cfl';
    """)


def downgrade() -> None:
    op.drop_column("import_batch", "validation_results")
    op.drop_column("import_batch", "warning_codes")
    op.drop_column("import_batch", "completeness_score")
    op.drop_column("import_job", "validation_mode")
    op.drop_column("import_job", "source_name")
    op.drop_column("source_system", "validation_mode")
