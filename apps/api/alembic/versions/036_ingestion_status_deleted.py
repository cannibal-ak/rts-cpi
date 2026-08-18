"""Add ``DELETED`` to ``ingestion_status_enum``.

The Ingestion Runs admin page gained a per-file "Delete data" action
(``IngestionService.delete_committed_file``): it removes a committed
file's fact rows, clears the SFTP dedup marker so the file can be
pulled again, and flips the owning ``ingestion_jobs`` row to a terminal
``DELETED`` state.

``ingestion_jobs.status`` is the Postgres enum ``ingestion_status_enum``
(migration 018), which had no value for "data was deleted". Reusing
``REPLACED`` would be misleading (it means superseded-by-another-job and
carries a ``replaced_by_job_id``), so we add an explicit ``DELETED``
value. The audit enum ``ingestion_audit_action_enum`` already contains
``DELETED`` (018), so only the status enum needs extending.

``ADD VALUE IF NOT EXISTS`` is idempotent and, on PostgreSQL 12+, is
permitted inside the migration's transaction because the new value is
not *used* within the same transaction — only declared.

Removing an enum value is not supported by PostgreSQL without recreating
the type and rewriting every dependent column, so ``downgrade`` is a
documented no-op (the extra value is harmless if unused).

Revision: 036
Revises: 035
Create Date: 2026-07-31
"""
from typing import Sequence, Union

from alembic import op


revision: str = "036"
down_revision: Union[str, None] = "035"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TYPE ingestion_status_enum ADD VALUE IF NOT EXISTS 'DELETED'"
    )


def downgrade() -> None:
    # Postgres cannot drop an enum value without recreating the type and
    # rewriting all dependent columns. Leaving the value in place is
    # harmless when unused; intentional no-op.
    pass
