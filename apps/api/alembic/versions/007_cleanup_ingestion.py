"""Cleanup demo ingestion data and source systems.

Revision ID: 007
Revises: 006
Create Date: 2026-03-12
"""
from typing import Sequence, Union
from alembic import op

revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    # Delete snapshots first due to FKs (no ON DELETE CASCADE for batches in snapshots)
    op.execute("DELETE FROM airline_cpi_snapshot;")
    op.execute("DELETE FROM cfl_cpi_snapshot;")
    
    # These have ON DELETE CASCADE or are level-1
    op.execute("DELETE FROM ingest_error;")
    op.execute("DELETE FROM import_batch;")
    op.execute("DELETE FROM import_job;")
    op.execute("DELETE FROM source_file;")
    
    # Remove demo source systems from migrations 004 and 006
    op.execute("DELETE FROM source_system WHERE code IN ('sftp-ba-daily', 'api-dfds-push', 'sftp-po-daily', 'api-ferry-manual');")

def downgrade() -> None:
    pass
