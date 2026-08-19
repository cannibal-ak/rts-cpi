"""DreamAir tenant — full airline build (tenant, user, RBAC, features, views).

Adds the demo airline tenant "DreamAir" (slug='da'), a functional twin of
WinAir (WM) with its own branding and palette:

  * tenant row              slug='da', display 'DreamAir'
  * app_user                da@airline.com / bcrypt('DAairline@2026'),
                            must_change_password=FALSE, TENANT_ADMIN
  * role_binding            TENANT_ADMIN for the DA user
  * tenant_feature          the full ALT set (10 rows), NOT the WM subset
  * vw_airline_cpi_da_snapshot   clone of vw_airline_cpi_jy_snapshot,
                                 predicate tenant_code='DA'
  * vw_velocity_da_snapshot      clone of vw_velocity_jy_snapshot,
                                 predicate airline_code='DA'

Both views are derived from the live JY view definitions via pg_get_viewdef +
a single predicate substitution, so they stay column-for-column identical to JY
(mirrors migrations 030 and 034).

must_change_password is FALSE, following the ALT demo tenant rather than the WM
real tenant: a demo login that forces a password change on first use stops
being reusable after the first demo.

Feature set follows ALT (10 rows), not WM (6 rows). WM is missing
`superset_embed` even though it renders an embedded dashboard — verified
against the live tenant_feature table. That is a WM inconsistency, not a
pattern worth cloning.

ALSO REPAIRS A GAP, additively: vw_velocity_wm_snapshot exists in every live
database and is referenced by app/routers/airline.py, but no migration has ever
created it — it was made by hand after 034 shipped ("NO velocity view" in that
docstring). A fresh checkout therefore builds a database where WinAir velocity
500s on a missing relation. It is created here guarded so existing databases
are untouched.

Revision ID: 038
Revises: 037
Create Date: 2026-08-19
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "038"
down_revision: Union[str, None] = "037"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Fixed UUIDs. The tenant convention was a doubled hex pair (a0, bb, cc, dd, ee,
# ff) which has no successor — 'gg' is not hex — so DreamAir takes 'ab'. The
# user convention (1111.., 2222.., .., 6666..) continues cleanly to 7777.
TENANT_DA = "ab000000-0000-0000-0000-000000000001"
USER_DA = "77777777-0000-0000-0000-000000000001"

# Precomputed bcrypt('DAairline@2026'), generated in the api container against
# the same passlib CryptContext(schemes=["bcrypt"]) the app verifies with.
DA_PWD_HASH = "$2b$12$mAEBuO8DAayi1JwgRb3lgu4xOhLvVgEblbhW2l9T4C3U.rZsVj9UG"

# Full feature set, mirroring ALT's ten rows so the admin feature list is
# complete. Three are present-but-disabled: custom_branding and
# anomaly_detection because ALT has them off, and cfl because DreamAir is an
# airline — ALT enables it only because ALT is a kitchen-sink demo.
#
# These rows do not gate anything today: tenant_feature is read only by the
# admin CRUD in routers/admin.py, and the frontend derives enabled_modules from
# TENANT_MODULE_MAP (slug -> one ModuleCode), not from here. They are set
# correctly anyway so the admin screen does not lie.
_FEATURES = [
    ("airline",           "Airline Module",       "module",     True),
    ("cfl",               "CFL Module",           "module",     False),
    ("superset_embed",    "Superset Dashboards",  "analytics",  True),
    ("anomaly_detection", "AI Anomaly Detection", "analytics",  False),
    ("custom_branding",   "Custom Branding",      "branding",   False),
    ("alerts",            "Alerting",             "capability", True),
    ("audit",             "Audit Log",            "capability", True),
    ("contracts",         "Contract Overlays",    "capability", True),
    ("exports",           "CSV / Excel Export",   "capability", True),
    ("saved_views",       "Saved Views",          "capability", True),
]


def _clone_view(conn, src: str, dst: str, marker: str, replacement: str) -> None:
    """Clone a per-tenant view by substituting its tenant predicate.

    Raises rather than silently creating an unfiltered view if the marker is
    absent — a view that returned every tenant's rows would be a data leak, not
    a cosmetic bug.
    """
    src_def = conn.execute(sa.text(f"SELECT pg_get_viewdef('{src}', true)")).scalar()
    if src_def is None:
        raise RuntimeError(f"source view {src} does not exist")
    new_def = src_def.replace(marker, replacement)
    if new_def == src_def:
        raise RuntimeError(
            f"predicate substitution failed for {dst}: marker {marker!r} not found in {src}"
        )
    conn.execute(sa.text(f"CREATE VIEW {dst} AS {new_def}"))
    conn.execute(sa.text(f"GRANT SELECT ON {dst} TO cpi_app"))


def upgrade() -> None:
    conn = op.get_bind()

    # ── tenant ──
    conn.execute(sa.text(
        "INSERT INTO tenant (id, slug, display_name, is_active) "
        "VALUES (:id, 'da', 'DreamAir', true) "
        "ON CONFLICT (id) DO NOTHING"
    ), {"id": TENANT_DA})

    # ── app_user (demo tenant: TENANT_ADMIN, no forced password change) ──
    conn.execute(sa.text("""
        INSERT INTO app_user (id, tenant_id, email, display_name, password_hash,
                              must_change_password, is_active, failed_login_count, locked_until)
        VALUES (:uid, :tid, 'da@airline.com', 'DreamAir Admin', :h,
                false, true, 0, NULL)
        ON CONFLICT (id) DO NOTHING
    """), {"uid": USER_DA, "tid": TENANT_DA, "h": DA_PWD_HASH})

    # ── role_binding ──
    conn.execute(sa.text("""
        INSERT INTO role_binding (tenant_id, user_id, role)
        VALUES (:tid, :uid, 'TENANT_ADMIN')
        ON CONFLICT DO NOTHING
    """), {"tid": TENANT_DA, "uid": USER_DA})

    # ── tenant_feature ──
    for code, label, category, enabled in _FEATURES:
        conn.execute(sa.text("""
            INSERT INTO tenant_feature (tenant_id, code, label, category, enabled)
            VALUES (:tid, :code, :label, :category, :enabled)
            ON CONFLICT (tenant_id, code) DO NOTHING
        """), {"tid": TENANT_DA, "code": code, "label": label,
               "category": category, "enabled": enabled})

    # ── DA views: clones of the JY views, predicates swapped to DA ──
    _clone_view(conn, "vw_airline_cpi_jy_snapshot", "vw_airline_cpi_da_snapshot",
                "tenant_code::text = 'JY'::text", "tenant_code::text = 'DA'::text")
    _clone_view(conn, "vw_velocity_jy_snapshot", "vw_velocity_da_snapshot",
                "airline_code::text = 'JY'::text", "airline_code::text = 'DA'::text")

    # ── Backfill the WM velocity view where it is missing (see docstring) ──
    exists = conn.execute(sa.text(
        "SELECT 1 FROM information_schema.views "
        "WHERE table_schema = 'public' AND table_name = 'vw_velocity_wm_snapshot'"
    )).scalar()
    if not exists:
        _clone_view(conn, "vw_velocity_jy_snapshot", "vw_velocity_wm_snapshot",
                    "airline_code::text = 'JY'::text", "airline_code::text = 'WM'::text")


def downgrade() -> None:
    conn = op.get_bind()
    # vw_velocity_wm_snapshot is deliberately NOT dropped: on every existing
    # database it predates this migration, so dropping it here would remove
    # something 038 did not create and break WinAir velocity.
    conn.execute(sa.text("DROP VIEW IF EXISTS vw_velocity_da_snapshot"))
    conn.execute(sa.text("DROP VIEW IF EXISTS vw_airline_cpi_da_snapshot"))
    # Explicit child deletes first; deleting the tenant also CASCADEs any
    # remaining DA rows (app_user, role_binding, tenant_feature, snapshots).
    conn.execute(sa.text("DELETE FROM role_binding WHERE tenant_id = :tid"), {"tid": TENANT_DA})
    conn.execute(sa.text("DELETE FROM tenant_feature WHERE tenant_id = :tid"), {"tid": TENANT_DA})
    conn.execute(sa.text("DELETE FROM app_user WHERE tenant_id = :tid"), {"tid": TENANT_DA})
    conn.execute(sa.text("DELETE FROM tenant WHERE id = :tid"), {"tid": TENANT_DA})
