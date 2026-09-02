"""alert_rule.deleted_at — tombstone that lets built-in rules be deleted.

A hard-deleted preset row would resurrect with defaults on the next settings
visit (_ensure_presets seeds any rule_key the tenant is missing). Keeping the
row as a tombstone is what makes "delete" stick: the self-heal sees the key
exists and leaves it alone, the settings page hides the card (the rules
listing still returns the tombstoned row so the restore strip can offer it),
the evaluator skips it, and POST /rules/{key}/restore clears the stamp to
bring it back (switched off, with its last-tuned settings).

User-created instances keep hard DELETE — their minted keys are never reused,
so nothing can resurrect them. Pure SQL, no app imports (040's rule).

Revision ID: 047
Revises: 046
Create Date: 2026-09-02
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "047"
down_revision: Union[str, None] = "046"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "alert_rule",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("alert_rule", "deleted_at")
