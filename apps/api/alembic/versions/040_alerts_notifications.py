"""Alerts & Notifications engine — preset rules, event payloads, read state.

`alert_rule` and `alert_event` have existed since 001 and have carried RLS since
002, but nothing has ever written an event: there is no evaluator, and
`delivery_status` is a column no code sets. This migration turns that skeleton
into something an engine can drive, and adds the one table it was missing.

WHAT CHANGES, AND WHY EACH COLUMN EARNS ITS PLACE

alert_rule gains `rule_key` — a stable per-tenant handle ('comp_price_move')
that code and URLs reference instead of matching on `name`, which is display
text a user may edit. `id` stays the PK; rule_key is the natural key.

alert_event gains two keys, not one, because the rule families fire differently:

  scope_key   what the alert is ABOUT, stable across captures:
              'move|ZNZ-NBO|TC|00-07', 'rank|ZNZ-NBO|00-07'
  dedupe_key  THIS EXACT FIRING, unique per tenant.

A price move is inherently a transition between two captures, so its dedupe_key
carries the capture date and one event per scope per capture is correct. A rank
change is a state change that can persist: keying on the capture alone would
re-fire every day a rank stayed bad, so its dedupe_key carries the capture AND
the new state, and the evaluator only emits when the state differs from the last
one recorded for that scope. That last-state lookup needs no extra table — it is
one indexed probe into alert_event via ix_alert_event_scope_observed.

The unique index on (tenant_id, dedupe_key) plus ON CONFLICT DO NOTHING is what
makes the whole engine idempotent. A beat tick, a manual run and a backfill can
all race on the same capture pair and the result is identical.

`observed_at` / `prev_observed_at` are the capture dates the fact is about and
the baseline it was compared against — deliberately separate from triggered_at,
which is when we say it happened. A backfilled event sets triggered_at to its
own capture date (a fare that moved on the 12th moved on the 12th) and records
`evaluation_mode='backfill'` plus a real wall-clock stamp inside payload, so the
row self-describes: this fact is about the 12th, we computed it on the 20th.

alert_event_read is per-user, not a read_at column on alert_event. DA has one
user today so a column would work, but JY/PW/ALT/WM do not, an unread badge one
colleague clears for everyone is a bug users report on day one, and retrofitting
later costs a data migration AND an API break. One narrow join table now is
cheaper than that.

It needs its own RLS: 002's loop covered the tables that existed then. The
predicate here is 002's coalesce/nullif form, NOT 013's bare cast — 013 raises
when the GUC is unset where 002 returns zero rows, and returning nothing is the
safe default for a table that feeds a notification bell. FORCE and WITH CHECK
are included to match alert_rule/alert_event, both of which have them.

ALSO CLEANED UP: the two seeded rules from 004 ('Fare drop > 15%', 'New
competitor route detected'). They are not orphans — their tenant was renamed to
slug 'rts' by migration 026 — so they currently surface in the platform admin's
feed as rules owned by admin@acme-airways.com against a tenant that has no
airline data. They are deleted, and any other pre-existing rule is preserved
with a generated rule_key and is_preset=false so the evaluator ignores it.

The seeded preset rows are a frozen copy of app/services/alerts/presets.py.
Migrations must not import app code — a later edit to the catalogue would
silently rewrite history — so the two are kept in sync deliberately, with the
runtime module as the source of truth and this list as its snapshot at 040.

Revision ID: 040
Revises: 039
Create Date: 2026-08-20
"""
import json
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "040"
down_revision: Union[str, None] = "039"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# The two rules seeded by 004 against what is now the 'rts' platform tenant.
_LEGACY_RULE_IDS = (
    "fa100000-0000-0000-0000-000000000001",
    "fa200000-0000-0000-0000-000000000002",
)

# Tenants missing an `alerts` tenant_feature row. Verified against the live
# dev database: alt, da, jy, rts and wm have one; pw and fjl do not. PW is a
# real airline tenant and should have alerting available; FJL is the ferry
# tenant with no airline_cpi_snapshot rows, so its row is seeded disabled
# rather than omitted — a present-but-false row is legible in the admin screen,
# an absent one looks like an onboarding bug.
_MISSING_FEATURE_TENANTS = (("pw", True), ("fjl", False))

# Frozen snapshot of app/services/alerts/presets.py at revision 040.
# (rule_key, name, description, domain, rule_type, severity, is_active, condition)
_PRESETS = [
    (
        "comp_price_move",
        "Competitor fare moved sharply",
        "A competitor's cheapest available fare on a route and departure window "
        "moved by more than the threshold since the previous capture.",
        "airline",
        "threshold",
        "warning",
        True,
        {
            "grain": "route_competitor_window",
            "metric": "min_available_fare",
            "move_pct": 10.0,
            "direction": "both",
            "min_abs_move": 5.0,
            "windows": ["00-07", "08-14", "15-30"],
            "competitors": None,
            "routes": None,
        },
    ),
    (
        "undercut_position",
        "Lost the cheapest position",
        "Our cheapest available fare on a route and departure window fell behind "
        "the competition, or recovered.",
        "airline",
        "threshold",
        "warning",
        True,
        {
            "grain": "route_window",
            "metric": "min_available_fare",
            "max_rank": 1,
            # 1.0%, not 0. The DA demo feed drifts our own fare by +0.10 every
            # capture, so a competitor sitting cents below flips the rank on
            # noise. A floor keeps "undercut" meaning something commercial.
            "min_gap_pct": 1.0,
            "notify_on_recovery": True,
            "windows": ["00-07", "08-14", "15-30"],
            "routes": None,
        },
    ),
    (
        "comp_price_threshold",
        "Competitor fare crossed a price line",
        "A competitor's cheapest available fare crossed an absolute price you set.",
        "airline",
        "threshold",
        "info",
        # Ships OFF and unconfigured on purpose: DA fares span USD 50-353 across
        # twelve routes, so one global price line is meaningless until a user
        # picks a route. The API rejects activation while value or routes is
        # null, with a message saying why.
        False,
        {
            "grain": "route_competitor_window",
            "metric": "min_available_fare",
            "operator": "below",
            "value": None,
            "currency": "USD",
            "windows": ["00-07"],
            "competitors": None,
            "routes": None,
        },
    ),
]


def upgrade() -> None:
    conn = op.get_bind()

    # ────────────────────────────────────────────
    # alert_rule — preset identity
    # ────────────────────────────────────────────
    op.add_column("alert_rule", sa.Column("rule_key", sa.String(64), nullable=True))
    op.add_column("alert_rule", sa.Column("is_preset", sa.Boolean(),
                                          nullable=False, server_default=sa.text("true")))
    op.add_column("alert_rule", sa.Column("description", sa.Text(), nullable=True))
    op.add_column("alert_rule", sa.Column("severity_default", sa.String(16),
                                          nullable=False, server_default="warning"))
    op.add_column("alert_rule", sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("alert_rule", sa.Column(
        "updated_by_user_id", postgresql.UUID(as_uuid=True),
        sa.ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True))

    # Drop the 004 seeds, then give a rule_key to anything still lacking one.
    # Both steps run unconditionally so the migration is correct whether or not
    # someone has already cleaned these by hand.
    # The cast is required: psycopg2 sends the list as text[], and postgres has
    # no uuid = text operator.
    conn.execute(
        sa.text("DELETE FROM alert_rule WHERE id = ANY(CAST(:ids AS uuid[]))"),
        {"ids": list(_LEGACY_RULE_IDS)},
    )
    conn.execute(sa.text("""
        UPDATE alert_rule
           SET rule_key  = 'legacy_' || left(md5(id::text), 8),
               is_preset = false
         WHERE rule_key IS NULL
    """))

    op.alter_column("alert_rule", "rule_key", nullable=False)
    op.create_index("uq_alert_rule_tenant_key", "alert_rule",
                    ["tenant_id", "rule_key"], unique=True)

    # ────────────────────────────────────────────
    # alert_event — payload, dedupe, business dates
    # ────────────────────────────────────────────
    # rule_key and dedupe_key take a server_default only so the ALTER succeeds
    # on a non-empty table; the defaults are dropped immediately afterwards so
    # the evaluator cannot get away with omitting them.
    op.add_column("alert_event", sa.Column("rule_key", sa.String(64),
                                           nullable=False, server_default=""))
    op.add_column("alert_event", sa.Column("scope_key", sa.Text(),
                                           nullable=False, server_default=""))
    op.add_column("alert_event", sa.Column("dedupe_key", sa.Text(),
                                           nullable=False, server_default=""))
    op.add_column("alert_event", sa.Column(
        "payload", postgresql.JSONB(),
        nullable=False, server_default=sa.text("'{}'::jsonb")))
    op.add_column("alert_event", sa.Column("observed_at", sa.Date(), nullable=True))
    op.add_column("alert_event", sa.Column("prev_observed_at", sa.Date(), nullable=True))
    op.add_column("alert_event", sa.Column("evaluation_mode", sa.String(16),
                                           nullable=False, server_default="live"))
    # Reserved for a future "this alert has been overtaken by a newer one"
    # sweep. Nothing writes it in phase 1; it exists so adding that later is
    # not another migration against a table the bell polls.
    op.add_column("alert_event", sa.Column("superseded_at",
                                           sa.DateTime(timezone=True), nullable=True))

    op.alter_column("alert_event", "rule_key", server_default=None)
    op.alter_column("alert_event", "scope_key", server_default=None)
    op.alter_column("alert_event", "dedupe_key", server_default=None)

    # The idempotency guarantee for the entire engine.
    op.create_index("uq_alert_event_dedupe", "alert_event",
                    ["tenant_id", "dedupe_key"], unique=True)
    # The list query. The id tiebreak is not cosmetic: backfilled events share a
    # triggered_at per capture date, and ordering on the timestamp alone makes
    # keyset pagination skip and duplicate rows.
    op.execute("""
        CREATE INDEX ix_alert_event_tenant_time
            ON alert_event (tenant_id, triggered_at DESC, id DESC)
    """)
    op.execute("""
        CREATE INDEX ix_alert_event_tenant_rule_time
            ON alert_event (tenant_id, rule_key, triggered_at DESC)
    """)
    # The evaluator's last-emitted-state probe for edge-triggered rules.
    op.execute("""
        CREATE INDEX ix_alert_event_scope_observed
            ON alert_event (tenant_id, scope_key, observed_at DESC)
    """)
    # Filtering the alerts page by route / competitor, which live in payload.
    op.execute("""
        CREATE INDEX ix_alert_event_payload_gin
            ON alert_event USING gin (payload jsonb_path_ops)
    """)

    # ────────────────────────────────────────────
    # alert_event_read — per-user read state
    # ────────────────────────────────────────────
    op.execute("""
        CREATE TABLE alert_event_read (
            id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID        NOT NULL REFERENCES tenant(id)      ON DELETE CASCADE,
            event_id  UUID        NOT NULL REFERENCES alert_event(id) ON DELETE CASCADE,
            user_id   UUID        NOT NULL REFERENCES app_user(id)    ON DELETE CASCADE,
            read_at   TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    # Read == row exists, so mark-read is an idempotent upsert on this index.
    op.create_index("uq_alert_event_read", "alert_event_read",
                    ["event_id", "user_id"], unique=True)
    # Drives the unread-count anti-join.
    op.create_index("ix_alert_event_read_user", "alert_event_read",
                    ["user_id", "event_id"])
    op.create_index("ix_alert_event_read_tenant", "alert_event_read", ["tenant_id"])

    # RLS. 002's predicate, not 013's — see the module docstring.
    op.execute("ALTER TABLE alert_event_read ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE alert_event_read FORCE  ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY rls_alert_event_read_tenant_isolation ON alert_event_read
            USING (
                tenant_id::text = coalesce(
                    nullif(current_setting('app.current_tenant', true), ''),
                    '00000000-0000-0000-0000-000000000000'
                )
            )
            WITH CHECK (
                tenant_id::text = coalesce(
                    nullif(current_setting('app.current_tenant', true), ''),
                    '00000000-0000-0000-0000-000000000000'
                )
            );
    """)
    op.execute("""
        CREATE POLICY rls_alert_event_read_superuser_bypass ON alert_event_read
            TO cpi USING (true) WITH CHECK (true);
    """)
    # 002 set ALTER DEFAULT PRIVILEGES for cpi_app, so this is belt-and-braces —
    # kept so the migration is self-contained if that default is ever revoked.
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON alert_event_read TO cpi_app")

    # ────────────────────────────────────────────
    # Seed: missing capability rows, then the presets
    # ────────────────────────────────────────────
    for slug, enabled in _MISSING_FEATURE_TENANTS:
        conn.execute(sa.text("""
            INSERT INTO tenant_feature (tenant_id, code, label, category, enabled)
            SELECT id, 'alerts', 'Alerting', 'capability', :enabled
              FROM tenant WHERE slug = :slug
            ON CONFLICT (tenant_id, code) DO NOTHING
        """), {"slug": slug, "enabled": enabled})

    # One preset set per tenant that has alerting as a capability at all. Tenants
    # whose code is not in ALERT_VIEW_MAP simply never get evaluated — the rows
    # are harmless and mean a later tenant needs no backfill migration.
    tenant_ids = conn.execute(sa.text("""
        SELECT t.id FROM tenant t
          JOIN tenant_feature f ON f.tenant_id = t.id AND f.code = 'alerts'
         ORDER BY t.slug
    """)).scalars().all()

    for tid in tenant_ids:
        for (rule_key, name, description, domain, rule_type,
             severity, is_active, condition) in _PRESETS:
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
    conn = op.get_bind()

    conn.execute(sa.text(
        "DELETE FROM alert_rule WHERE is_preset = true AND owner = 'system'"))

    op.execute("DROP TABLE IF EXISTS alert_event_read")

    op.drop_index("ix_alert_event_payload_gin", table_name="alert_event")
    op.drop_index("ix_alert_event_scope_observed", table_name="alert_event")
    op.drop_index("ix_alert_event_tenant_rule_time", table_name="alert_event")
    op.drop_index("ix_alert_event_tenant_time", table_name="alert_event")
    op.drop_index("uq_alert_event_dedupe", table_name="alert_event")
    for col in ("superseded_at", "evaluation_mode", "prev_observed_at", "observed_at",
                "payload", "dedupe_key", "scope_key", "rule_key"):
        op.drop_column("alert_event", col)

    op.drop_index("uq_alert_rule_tenant_key", table_name="alert_rule")
    for col in ("updated_by_user_id", "updated_at", "severity_default",
                "description", "is_preset", "rule_key"):
        op.drop_column("alert_rule", col)

    # The 004 seed rows are deliberately NOT restored: they referenced a tenant
    # that has since been renamed and carried no working rule definition.
