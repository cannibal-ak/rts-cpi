"""Sky Airways demo tenant — structure only (tenant, user, RBAC, views).

Adds a fully self-contained DEMO tenant "Sky Airways" (slug='alt') that
mirrors the JY airline pattern. Structure only — synthetic data is loaded
separately by scripts/seed_demo_altitude.py.

Creates:
  * tenant row              slug='alt', display 'Sky Airways'
  * app_user                alt@airline.com / bcrypt('airline123'),
                            must_change_password=FALSE, TENANT_ADMIN
  * role_binding            TENANT_ADMIN for the ALT user
  * tenant_feature          10 rows mirroring JY verbatim
  * vw_airline_cpi_alt_snapshot   exact clone of vw_airline_cpi_jy_snapshot,
                                  predicate tenant_code='ALT'
  * vw_velocity_alt_snapshot      exact clone of vw_velocity_jy_snapshot,
                                  predicate airline_code='ALT'

The two ALT views are derived from the live JY view definitions via
pg_get_viewdef + a single predicate substitution, so they stay column-for-column
identical to JY (no hand-transcription of the ~88-column projection).

Revision ID: 030
Revises: 029
Create Date: 2026-06-03
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "030"
down_revision: Union[str, None] = "029"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Fixed UUIDs (follow the existing aa/bb/cc/dd + 22/33/44 conventions)
TENANT_ALT = "ee000000-0000-0000-0000-000000000001"
USER_ALT = "55555555-0000-0000-0000-000000000001"

# JY's 10 tenant_feature rows, replicated verbatim for ALT.
_FEATURES = [
    ("airline",           "Airline Module",       "module",     True),
    ("cfl",               "CFL Module",           "module",     True),
    ("superset_embed",    "Superset Dashboards",  "analytics",  True),
    ("anomaly_detection", "AI Anomaly Detection", "analytics",  False),
    ("custom_branding",   "Custom Branding",      "branding",   False),
    ("alerts",            "Alerting",             "capability", True),
    ("audit",             "Audit Log",            "capability", True),
    ("contracts",         "Contract Overlays",    "capability", True),
    ("exports",           "CSV / Excel Export",   "capability", True),
    ("saved_views",       "Saved Views",          "capability", True),
]


def upgrade() -> None:
    from passlib.context import CryptContext
    pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
    alt_hash = pwd_ctx.hash("airline123")

    conn = op.get_bind()

    # ── tenant ──
    conn.execute(sa.text(
        "INSERT INTO tenant (id, slug, display_name, is_active) "
        "VALUES (:id, 'alt', 'Sky Airways', true) "
        "ON CONFLICT (id) DO NOTHING"
    ), {"id": TENANT_ALT})

    # ── app_user (mirror JY: TENANT_ADMIN, must_change_password=FALSE) ──
    conn.execute(sa.text("""
        INSERT INTO app_user (id, tenant_id, email, display_name, password_hash,
                              must_change_password, is_active, failed_login_count, locked_until)
        VALUES (:uid, :tid, 'alt@airline.com', 'Sky Airline Admin', :h,
                false, true, 0, NULL)
        ON CONFLICT (id) DO NOTHING
    """), {"uid": USER_ALT, "tid": TENANT_ALT, "h": alt_hash})

    # ── role_binding ──
    conn.execute(sa.text("""
        INSERT INTO role_binding (tenant_id, user_id, role)
        VALUES (:tid, :uid, 'TENANT_ADMIN')
        ON CONFLICT DO NOTHING
    """), {"tid": TENANT_ALT, "uid": USER_ALT})

    # ── tenant_feature (10 rows, mirror JY) ──
    for code, label, category, enabled in _FEATURES:
        conn.execute(sa.text("""
            INSERT INTO tenant_feature (tenant_id, code, label, category, enabled)
            VALUES (:tid, :code, :label, :category, :enabled)
            ON CONFLICT (tenant_id, code) DO NOTHING
        """), {"tid": TENANT_ALT, "code": code, "label": label,
               "category": category, "enabled": enabled})

    # ── ALT views: exact clones of the JY views, predicate swapped to ALT ──
    air_def = conn.execute(sa.text(
        "SELECT pg_get_viewdef('vw_airline_cpi_jy_snapshot', true)"
    )).scalar()
    air_alt = air_def.replace("tenant_code::text = 'JY'::text",
                              "tenant_code::text = 'ALT'::text")
    if air_alt == air_def:
        raise RuntimeError("airline view predicate substitution failed (JY marker not found)")
    conn.execute(sa.text(f"CREATE VIEW vw_airline_cpi_alt_snapshot AS {air_alt}"))
    conn.execute(sa.text("GRANT SELECT ON vw_airline_cpi_alt_snapshot TO cpi_app"))

    vel_def = conn.execute(sa.text(
        "SELECT pg_get_viewdef('vw_velocity_jy_snapshot', true)"
    )).scalar()
    vel_alt = vel_def.replace("airline_code::text = 'JY'::text",
                              "airline_code::text = 'ALT'::text")
    if vel_alt == vel_def:
        raise RuntimeError("velocity view predicate substitution failed (JY marker not found)")
    conn.execute(sa.text(f"CREATE VIEW vw_velocity_alt_snapshot AS {vel_alt}"))
    conn.execute(sa.text("GRANT SELECT ON vw_velocity_alt_snapshot TO cpi_app"))


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("DROP VIEW IF EXISTS vw_velocity_alt_snapshot"))
    conn.execute(sa.text("DROP VIEW IF EXISTS vw_airline_cpi_alt_snapshot"))
    # Explicit child deletes first; deleting the tenant also CASCADEs any
    # remaining ALT rows (app_user, role_binding, tenant_feature, snapshots).
    conn.execute(sa.text("DELETE FROM role_binding WHERE tenant_id = :tid"), {"tid": TENANT_ALT})
    conn.execute(sa.text("DELETE FROM tenant_feature WHERE tenant_id = :tid"), {"tid": TENANT_ALT})
    conn.execute(sa.text("DELETE FROM app_user WHERE tenant_id = :tid"), {"tid": TENANT_ALT})
    conn.execute(sa.text("DELETE FROM tenant WHERE id = :tid"), {"tid": TENANT_ALT})
