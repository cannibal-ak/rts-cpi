"""Add ``DELETED`` to ``ingestion_status_enum`` (prod line, chains from 034).

Backs the Ingestion Runs per-file "Delete data" action
(``IngestionService.delete_committed_file``), which flips the owning
``ingestion_jobs`` row to a terminal ``DELETED`` state. That column is the
enum ``ingestion_status_enum`` (migration 018), which lacked a value for
"data was deleted". The audit enum already contains ``DELETED``; only the
status enum needs extending. ``ingestion_run.status`` and
``ingested_file.outcome`` are plain varchars, so they need no change.

``ADD VALUE IF NOT EXISTS`` is idempotent and, on PostgreSQL 12+, is
permitted inside the migration transaction because the new value is only
declared, not used, in the same transaction.

Revision: 035
Revises: 034
Create Date: 2026-07-31
"""
from typing import Sequence, Union

from alembic import op

revision: str = "035"
down_revision: Union[str, None] = "034"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TYPE ingestion_status_enum ADD VALUE IF NOT EXISTS 'DELETED'"
    )


def downgrade() -> None:
    # Postgres cannot drop an enum value without recreating the type;
    # intentional no-op (harmless when unused).
    pass
