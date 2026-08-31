"""Seed the stops_disadvantage and service_gap alert presets.

`_ensure_presets` in routers/alerts.py self-heals a tenant's missing preset rows
on any rules GET or PATCH, which is why adding a preset usually needs no
migration. That is not sufficient here, for two reasons.

First, only the three rules ENDPOINTS call it. `load_active_rules` reads
alert_rule directly, so the 15-minute beat sweep, the post-ingestion hook and
`python -m app.services.alerts.cli` all bypass it entirely — a tenant whose
settings page nobody has opened simply has no rows, indefinitely.

Second, and worse for these two rules specifically: they are EDGE-TRIGGERED, and
their state ledger is the alert_event table itself. A preset that materialises
six weeks late does not merely start late — it emits its whole initial-state
burst stamped with whatever capture happens to be current, asserting in
observed_at that a gap opened on a day nothing changed. For a price rule that is
a delay; for a state rule it is a wrong answer.

040's rule applies: migrations must not import app code, or a later edit to
presets.py would rewrite history. The two condition dicts below are therefore a
frozen snapshot of StopsDisadvantageCondition and ServiceGapCondition as of this
revision, and presets.py remains the source of truth for everything after it.
044 imports its list from 040 by file path; that is not reusable here, because
040's snapshot is the original three.

Revision ID: 045
Revises: 044
Create Date: 2026-08-28
"""
import json
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "045"
down_revision: Union[str, None] = "044"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_RULE_KEYS = ("stops_disadvantage", "service_gap")

# (rule_key, name, description, domain, rule_type, severity, is_active, condition)
_NEW_PRESETS = [
    (
        "stops_disadvantage",
        "A competitor flies it in fewer stops",
        "The best itinerary we have on sale for a route and departure window "
        "makes more stops than the best a competitor is selling.",
        "airline",
        "threshold",
        "warning",
        # Ships off. The steady state is quiet, but the first fire is not:
        # measured JY 0, PW 6, DA 6, 5L 8, WM 29 against the newest capture
        # pair. Size it per tenant with the preview endpoint, then switch on.
        False,
        {
            "grain": "route_trip_window",
            "metric": "min_stops_on_sale",
            "min_stop_gap": 1,
            "min_days": 3,
            "min_day_share": 50.0,
            "notify_on_recovery": True,
            "windows": ["00-07", "08-14", "15-30"],
            "trip_types": None,
            "competitors": None,
            "routes": None,
        },
    ),
    (
        "service_gap",
        "Nothing of ours on sale while they sell",
        "On several departure days in a window we have no fare on sale -- no "
        "flight at all, or a flight with no fare -- while competitors do.",
        "airline",
        "threshold",
        "warning",
        # Ships off: first fire is 14 events on JY and 37 on WM. See the preset
        # comment in presets.py for why that is a different reason from
        # comp_price_threshold's, and why POST /rules/{key}/preview is the
        # intended way to size it before switching on.
        False,
        {
            "grain": "route_trip_window",
            "metric": "days_not_on_sale",
            "min_gap_days": 3,
            "min_days_observed": 4,
            "min_competitors": 1,
            "include_sold_out": True,
            "notify_on_recovery": True,
            "windows": ["00-07"],
            "trip_types": None,
            "competitors": None,
            "routes": None,
        },
    ),
]


def upgrade() -> None:
    conn = op.get_bind()
    # 044's tenant query verbatim, including the deliberate absence of
    # `AND f.enabled`: a tenant holding the feature but not using it still gets
    # rows, so the admin screen shows the catalogue rather than a gap.
    tenant_ids = conn.execute(sa.text("""
        SELECT t.id FROM tenant t
          JOIN tenant_feature f ON f.tenant_id = t.id AND f.code = 'alerts'
         ORDER BY t.slug
    """)).scalars().all()

    for tid in tenant_ids:
        for (rule_key, name, description, domain, rule_type,
             severity, is_active, condition) in _NEW_PRESETS:
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
                "is_active": is_active, "rule_key": rule_key,
                "severity": severity,
            })


def downgrade() -> None:
    # Unlike 044, this one CAN be precise: it knows exactly which two rule_keys
    # it introduced, and nothing before this revision could have created them.
    # alert_event rows cascade on the alert_rule foreign key, which is intended
    # -- the events are only meaningful alongside the rule that defined them.
    conn = op.get_bind()
    conn.execute(
        sa.text("DELETE FROM alert_rule WHERE rule_key = ANY(:keys)"),
        {"keys": list(_RULE_KEYS)},
    )
