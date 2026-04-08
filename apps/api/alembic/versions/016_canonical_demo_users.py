"""Canonical demo user model — replace acme/baltic with skywave identity.

Replaces the Phase 1 demo tenants (acme-airways, baltic-ferries) and their
users with the canonical identity model:

  skywave  (a0000000)  — platform admin tenant (renamed from acme-airways)
  jy       (dd000000)  — new airline tenant
  pw       (bb000000)  — kept as-is
  fjl      (cc000000)  — kept as-is

Creates 4 canonical users with bcrypt-hashed temporary passwords and
must_change_password=TRUE.

NOTE: downgrade() is best-effort emergency rollback only. It cannot perfectly
restore the original demo state (original user UUIDs and passwords are lost).

Revision ID: 016
Revises: 015
Create Date: 2026-04-08
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "016"
down_revision: Union[str, None] = "015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Old tenant UUIDs
TENANT_ACME = "a0000000-0000-0000-0000-000000000001"
TENANT_BALTIC = "b0000000-0000-0000-0000-000000000002"

# New/kept tenant UUIDs
TENANT_SKYWAVE = "a0000000-0000-0000-0000-000000000001"  # same row, renamed
TENANT_JY = "dd000000-0000-0000-0000-000000000001"
TENANT_PW = "bb000000-0000-0000-0000-000000000001"
TENANT_FJL = "cc000000-0000-0000-0000-000000000001"

# New user UUIDs
USER_ADMIN = "11111111-0000-0000-0000-000000000001"
USER_JY = "22222222-0000-0000-0000-000000000001"
USER_PW = "33333333-0000-0000-0000-000000000001"
USER_FJL = "44444444-0000-0000-0000-000000000001"


def upgrade() -> None:
    from passlib.context import CryptContext
    pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")

    admin_hash = pwd_ctx.hash("admin123")
    airline_hash_jy = pwd_ctx.hash("airline123")
    airline_hash_pw = pwd_ctx.hash("airline123")
    cruise_hash = pwd_ctx.hash("cruise123")

    conn = op.get_bind()

    # ── Step a: Delete role bindings for acme & baltic ──
    conn.execute(sa.text(
        "DELETE FROM role_binding WHERE tenant_id IN (:acme, :baltic)"
    ), {"acme": TENANT_ACME, "baltic": TENANT_BALTIC})

    # ── Step b: Delete users for acme & baltic ──
    conn.execute(sa.text(
        "DELETE FROM app_user WHERE tenant_id IN (:acme, :baltic)"
    ), {"acme": TENANT_ACME, "baltic": TENANT_BALTIC})

    # ── Step c: Delete tenant_feature for baltic ──
    conn.execute(sa.text(
        "DELETE FROM tenant_feature WHERE tenant_id = :baltic"
    ), {"baltic": TENANT_BALTIC})

    # ── Step d: Delete baltic tenant ──
    conn.execute(sa.text(
        "DELETE FROM tenant WHERE id = :baltic"
    ), {"baltic": TENANT_BALTIC})

    # ── Step e: Rename acme → skywave ──
    conn.execute(sa.text(
        "UPDATE tenant SET slug = 'skywave', display_name = 'Skywave Platform Admin' "
        "WHERE id = :tid"
    ), {"tid": TENANT_SKYWAVE})

    # ── Step f: Insert jy tenant (idempotent) ──
    conn.execute(sa.text(
        "INSERT INTO tenant (id, slug, display_name, is_active) "
        "VALUES (:id, 'jy', 'Skywave - JY', true) "
        "ON CONFLICT (id) DO NOTHING"
    ), {"id": TENANT_JY})

    # ── Step g+h: Insert 4 canonical users ──
    conn.execute(sa.text("""
        INSERT INTO app_user (id, tenant_id, email, display_name, password_hash,
                              must_change_password, is_active, failed_login_count, locked_until)
        VALUES
            (:u1, :t1, 'admin@skywave.com',  'Alex Rivera',       :h1, true, true, 0, NULL),
            (:u2, :t2, 'jy@airline.com',     'JY Airline Admin',  :h2, true, true, 0, NULL),
            (:u3, :t3, 'pw@airline.com',     'PW Airline Admin',  :h3, true, true, 0, NULL),
            (:u4, :t4, 'fjl@cruise.com',     'FJL Cruise Admin',  :h4, true, true, 0, NULL)
        ON CONFLICT (id) DO NOTHING
    """), {
        "u1": USER_ADMIN, "t1": TENANT_SKYWAVE, "h1": admin_hash,
        "u2": USER_JY,    "t2": TENANT_JY,      "h2": airline_hash_jy,
        "u3": USER_PW,    "t3": TENANT_PW,      "h3": airline_hash_pw,
        "u4": USER_FJL,   "t4": TENANT_FJL,     "h4": cruise_hash,
    })

    # ── Step i: Insert TENANT_ADMIN role bindings ──
    conn.execute(sa.text("""
        INSERT INTO role_binding (tenant_id, user_id, role) VALUES
            (:t1, :u1, 'TENANT_ADMIN'),
            (:t2, :u2, 'TENANT_ADMIN'),
            (:t3, :u3, 'TENANT_ADMIN'),
            (:t4, :u4, 'TENANT_ADMIN')
        ON CONFLICT DO NOTHING
    """), {
        "t1": TENANT_SKYWAVE, "u1": USER_ADMIN,
        "t2": TENANT_JY,      "u2": USER_JY,
        "t3": TENANT_PW,      "u3": USER_PW,
        "t4": TENANT_FJL,     "u4": USER_FJL,
    })

    # ── Step j: Insert tenant_feature for jy tenant (same set as 004) ──
    features = [
        ("airline", "Airline Module", "module", "true"),
        ("cfl", "CFL Module", "module", "true"),
        ("alerts", "Alerting", "capability", "true"),
        ("exports", "CSV / Excel Export", "capability", "true"),
        ("audit", "Audit Log", "capability", "true"),
        ("saved_views", "Saved Views", "capability", "true"),
        ("contracts", "Contract Overlays", "capability", "true"),
        ("superset_embed", "Superset Dashboards", "analytics", "true"),
        ("anomaly_detection", "AI Anomaly Detection", "analytics", "false"),
        ("custom_branding", "Custom Branding", "branding", "false"),
    ]
    for code, label, cat, enabled in features:
        conn.execute(sa.text(
            "INSERT INTO tenant_feature (tenant_id, code, label, category, enabled) "
            "VALUES (:tid, :code, :label, :cat, :enabled) "
            "ON CONFLICT DO NOTHING"
        ), {"tid": TENANT_JY, "code": code, "label": label, "cat": cat, "enabled": enabled})


def downgrade() -> None:
    """Best-effort rollback — see module docstring."""
    conn = op.get_bind()

    # Delete canonical users + role bindings
    conn.execute(sa.text(
        "DELETE FROM role_binding WHERE user_id IN (:u1, :u2, :u3, :u4)"
    ), {"u1": USER_ADMIN, "u2": USER_JY, "u3": USER_PW, "u4": USER_FJL})

    conn.execute(sa.text(
        "DELETE FROM app_user WHERE id IN (:u1, :u2, :u3, :u4)"
    ), {"u1": USER_ADMIN, "u2": USER_JY, "u3": USER_PW, "u4": USER_FJL})

    # Delete jy tenant features + tenant
    conn.execute(sa.text(
        "DELETE FROM tenant_feature WHERE tenant_id = :jy"
    ), {"jy": TENANT_JY})

    conn.execute(sa.text(
        "DELETE FROM tenant WHERE id = :jy"
    ), {"jy": TENANT_JY})

    # Rename skywave back to acme-airways
    conn.execute(sa.text(
        "UPDATE tenant SET slug = 'acme-airways', display_name = 'Acme Airways' "
        "WHERE id = :tid"
    ), {"tid": TENANT_SKYWAVE})

    # Re-create baltic-ferries tenant
    conn.execute(sa.text(
        "INSERT INTO tenant (id, slug, display_name, is_active) "
        "VALUES (:id, 'baltic-ferries', 'Baltic Ferries', true) "
        "ON CONFLICT (id) DO NOTHING"
    ), {"id": TENANT_BALTIC})

    # Best-effort restore original users (no passwords)
    conn.execute(sa.text("""
        INSERT INTO app_user (id, tenant_id, email, display_name, must_change_password) VALUES
            ('aa100000-0000-0000-0000-000000000001', :acme,   'admin@acme-airways.com',      'Alice Admin',   true),
            ('aa200000-0000-0000-0000-000000000002', :acme,   'analyst@acme-airways.com',     'Bob Analyst',   true),
            ('bb100000-0000-0000-0000-000000000001', :baltic, 'admin@baltic-ferries.com',     'Carol Admin',   true),
            ('bb200000-0000-0000-0000-000000000002', :baltic, 'engineer@baltic-ferries.com',  'Dave Engineer', true)
        ON CONFLICT (id) DO NOTHING
    """), {"acme": TENANT_ACME, "baltic": TENANT_BALTIC})

    conn.execute(sa.text("""
        INSERT INTO role_binding (tenant_id, user_id, role) VALUES
            (:acme,   'aa100000-0000-0000-0000-000000000001', 'TENANT_ADMIN'),
            (:acme,   'aa200000-0000-0000-0000-000000000002', 'ANALYST'),
            (:baltic, 'bb100000-0000-0000-0000-000000000001', 'TENANT_ADMIN'),
            (:baltic, 'bb200000-0000-0000-0000-000000000002', 'DATA_ENGINEER')
        ON CONFLICT DO NOTHING
    """), {"acme": TENANT_ACME, "baltic": TENANT_BALTIC})
