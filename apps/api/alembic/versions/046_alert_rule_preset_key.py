"""alert_rule.preset_key — which catalogue family a rule evaluates as.

User-created rules are now INSTANCES of a catalogue preset: is_preset stays
false (the row is not the tenant's canonical catalogue entry) but preset_key
names the family whose evaluator function and condition model it runs under.
Preset rows get preset_key = rule_key. Rows left NULL — the deprecated
free-form 'custom_*' rules and pre-040 'legacy_*' rows — remain invisible to
the evaluator, exactly as before.

040's rule applies: no app imports, pure SQL.

Revision ID: 046
Revises: 045
Create Date: 2026-09-01
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "046"
down_revision: Union[str, None] = "045"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("alert_rule", sa.Column("preset_key", sa.String(64), nullable=True))
    op.get_bind().execute(sa.text(
        "UPDATE alert_rule SET preset_key = rule_key WHERE is_preset = true"
    ))


def downgrade() -> None:
    op.drop_column("alert_rule", "preset_key")
