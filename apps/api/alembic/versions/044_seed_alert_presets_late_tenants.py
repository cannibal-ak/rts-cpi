"""Seed alert preset rules for tenants created after migration 040.

040 seeds one preset set per tenant that holds the `alerts` feature — but it
can only see tenants that exist when it runs. Liat Air (5L) is created by
041, one step LATER in the chain, so on every database 5L ends up with the
alerts feature enabled and zero rules: the evaluator reports "no active
preset rules" and silently produces nothing. 040's comment that "a later
tenant needs no backfill migration" was only true for tenants added before
040 ran.

This re-runs 040's exact seeding loop, idempotently (ON CONFLICT DO
NOTHING), for every alerts-capable tenant — healing 5L everywhere and any
future tenant that lands in the same ordering trap, provided it is created
before this migration's successor. Tenants created after THIS migration
still need the loop re-run; the real fix for the pattern is seeding presets
in the tenant-creation migration itself, which future tenant builds should
copy.

The preset definitions are imported from 040 rather than duplicated, so the
two migrations can never drift apart.

Revision ID: 044
Revises: 043
Create Date: 2026-08-26
"""
import importlib.util
import json
from pathlib import Path
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "044"
down_revision: Union[str, None] = "043"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _presets():
    """Load _PRESETS from 040 by file path (its module name starts with a digit)."""
    path = Path(__file__).parent / "040_alerts_notifications.py"
    spec = importlib.util.spec_from_file_location("_alembic_040", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod._PRESETS


def upgrade() -> None:
    conn = op.get_bind()
    tenant_ids = conn.execute(sa.text("""
        SELECT t.id FROM tenant t
          JOIN tenant_feature f ON f.tenant_id = t.id AND f.code = 'alerts'
         ORDER BY t.slug
    """)).scalars().all()

    for tid in tenant_ids:
        for (rule_key, name, description, domain, rule_type,
             severity, is_active, condition) in _presets():
            conn.execute(sa.text("""
                INSERT INTO alert_rule (
                    tenant_id, name, description, domain, rule_type,
                    condition_json, is_active, owner,
                    rule_key, is_preset, severity_default
                ) VALUES (
                    :tid, :name, :description, :domain, :rule_type,
                    CAST(:condition AS jsonb), :is_active, 'system',
                    :rule_key, true, :severity
                )
                ON CONFLICT (tenant_id, rule_key) DO NOTHING
            """), {
                "tid": tid, "name": name, "description": description,
                "domain": domain, "rule_type": rule_type,
                "condition": json.dumps(condition),
                "is_active": is_active, "rule_key": rule_key, "severity": severity,
            })


def downgrade() -> None:
    # Removing only the rows this migration added would need a record of which
    # tenants lacked presets beforehand; there is none. Preset rows are
    # harmless for un-evaluated tenants (040's own rationale), so downgrade is
    # a deliberate no-op.
    pass
