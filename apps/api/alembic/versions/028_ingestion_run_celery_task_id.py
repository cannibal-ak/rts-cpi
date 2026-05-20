"""Add ``celery_task_id`` to ``ingestion_run`` for orphan-sweeper matching.

The periodic orphan-sweeper task (``app.tasks.sftp_pull.sweep_orphan_runs``)
needs a 1:1 mapping from each row to the Celery task that owns it, so
``inspect.active/reserved/scheduled`` can be used to decide whether a
RUNNING / CANCELLING row is genuinely abandoned. Matching by
``schedule_id`` alone is ambiguous when a fresh run for the same
schedule co-exists with an orphan from a prior crashed run.

Column is nullable: pre-existing rows have no recorded task id, and
non-celery callers (test harnesses, scripted backfills) may legitimately
leave it empty. The sweeper treats NULL as "no live task can claim
this" — i.e. eligible for sweep once past the age threshold.

VARCHAR(155) follows the upstream celery message-id width (UUIDs in
practice, but the message-id type is not formally constrained — leave
headroom).

Revision: 028
Revises: 027
Create Date: 2026-05-20
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "028"
down_revision: Union[str, None] = "027"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "ingestion_run",
        sa.Column("celery_task_id", sa.String(length=155), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("ingestion_run", "celery_task_id")
