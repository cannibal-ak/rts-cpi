"""Liat Air tenant — full airline build (tenant, user, RBAC, features, views).

Adds the demo airline tenant "Liat Air" (slug='5l'), a functional twin of
DreamAir (DA) with its own branding and palette:

  * tenant row              slug='5l', display 'Liat Air'
  * app_user                liat@airline.com / bcrypt('5Lairline@2026'),
                            must_change_password=FALSE, TENANT_ADMIN
  * role_binding            TENANT_ADMIN for the Liat user
  * tenant_feature          the full ALT/DA set (10 rows), alerts enabled
  * vw_airline_cpi_5l_snapshot   clone of vw_airline_cpi_jy_snapshot,
                                 predicate tenant_code='5L'
  * vw_velocity_5l_snapshot      clone of vw_velocity_jy_snapshot,
                                 predicate airline_code='5L'
  * four partial indexes on airline_cpi_snapshot for the 5L partition

Both views are derived from the live JY view definitions via pg_get_viewdef +
a single predicate substitution, so they stay column-for-column identical to JY
(mirrors migrations 030, 034 and 038).

'5L' is Liat's real IATA code, and it ALREADY EXISTS in other tenants' data as
a competitor carrier (ref_al/comp_al '5L' under JY and WM — Liat is a genuine
interCaribbean competitor). That is safe: every per-tenant view filters on
tenant_code, never on the carrier columns, so vw_airline_cpi_5l_snapshot sees
only rows ingested FOR the Liat tenant and JY keeps seeing its own '5L'
competitor rows. The collision is called out here so nobody "fixes" it later.

THE INDEXES ARE NEW RELATIVE TO 038, deliberately. DreamAir's four partial
indexes (ix_air_snap_da_grid / _filtervals / _pricerec / _triptype) were
created out of band after 038 shipped, when the missing-index cost had been
measured (dashboard filters at 39s -> 3s once indexed, and the grid
date-pin work in 3034363). A fresh checkout does not reproduce them. For 5L
they are created up front in the migration: the 5L partition is empty at
migration time, so each CREATE INDEX is instant, and the tenant never goes
through the slow-then-fixed cycle. Definitions mirror the live DA indexes
column-for-column.

must_change_password is FALSE, following the ALT/DA demo tenants rather than
the WM real tenant: a demo login that forces a password change on first use
stops being reusable after the first demo.

Revision ID: 041
Revises: 040
Create Date: 2026-08-25
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "041"
down_revision: Union[str, None] = "040"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Fixed UUIDs, continuing the conventions 038 documented: tenants take doubled
# hex pairs and DreamAir took 'ab', so Liat takes 'ac'; users count up in
# repeated digits and DreamAir took 7777.., so Liat takes 8888…
TENANT_5L = "ac000000-0000-0000-0000-000000000001"
USER_5L = "88888888-0000-0000-0000-000000000001"

# Precomputed bcrypt('5Lairline@2026'), generated in the api container against
# the same passlib CryptContext(schemes=["bcrypt"]) the app verifies with.
LIAT_PWD_HASH = "$2b$12$NpMOUqKY92MkG9g94sLRrew.1rF/jqaw2b2p8k7kd0PmCaheWWLUm"

# Full feature set, mirroring ALT/DA's ten rows so the admin feature list is
# complete. Three are present-but-disabled for the same reasons as DA:
# custom_branding and anomaly_detection follow ALT, and cfl because Liat is an
# airline. As 038 notes, these rows do not gate anything today — the frontend
# derives enabled_modules from TENANT_MODULE_MAP — but they are set correctly
# so the admin screen does not lie.
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

# Partial indexes for the 5L partition, mirroring the live DA set (which was
# built out of band — see the docstring). Names and column lists match
# pg_indexes for the DA originals with only the tenant literal swapped.
_INDEX_SQL = [
    """CREATE INDEX IF NOT EXISTS ix_air_snap_5l_grid
       ON airline_cpi_snapshot (cap_date, cap_time, id)
       WHERE tenant_code::text = '5L'""",
    """CREATE INDEX IF NOT EXISTS ix_air_snap_5l_filtervals
       ON airline_cpi_snapshot (ref_org, ref_dst, ref_dep_date, cap_date,
                                ref_flt_num, ref_stops, comp_stops, comp_al)
       WHERE tenant_code::text = '5L'""",
    """CREATE INDEX IF NOT EXISTS ix_air_snap_5l_pricerec
       ON airline_cpi_snapshot (ref_org, ref_dst, ref_dep_date, trip_type,
                                cap_date, comp_tot_fare)
       INCLUDE (ref_via, ref_tot_fare, comp_al)
       WHERE tenant_code::text = '5L' AND comp_tot_fare > 0::numeric""",
    """CREATE INDEX IF NOT EXISTS ix_air_snap_5l_triptype
       ON airline_cpi_snapshot (trip_type)
       WHERE tenant_code::text = '5L'""",
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
        "VALUES (:id, '5l', 'Liat Air', true) "
        "ON CONFLICT (id) DO NOTHING"
    ), {"id": TENANT_5L})

    # ── app_user (demo tenant: TENANT_ADMIN, no forced password change) ──
    conn.execute(sa.text("""
        INSERT INTO app_user (id, tenant_id, email, display_name, password_hash,
                              must_change_password, is_active, failed_login_count, locked_until)
        VALUES (:uid, :tid, 'liat@airline.com', 'Liat Air Admin', :h,
                false, true, 0, NULL)
        ON CONFLICT (id) DO NOTHING
    """), {"uid": USER_5L, "tid": TENANT_5L, "h": LIAT_PWD_HASH})

    # ── role_binding ──
    conn.execute(sa.text("""
        INSERT INTO role_binding (tenant_id, user_id, role)
        VALUES (:tid, :uid, 'TENANT_ADMIN')
        ON CONFLICT DO NOTHING
    """), {"tid": TENANT_5L, "uid": USER_5L})

    # ── tenant_feature ──
    for code, label, category, enabled in _FEATURES:
        conn.execute(sa.text("""
            INSERT INTO tenant_feature (tenant_id, code, label, category, enabled)
            VALUES (:tid, :code, :label, :category, :enabled)
            ON CONFLICT (tenant_id, code) DO NOTHING
        """), {"tid": TENANT_5L, "code": code, "label": label,
               "category": category, "enabled": enabled})

    # ── 5L views: clones of the JY views, predicates swapped to 5L ──
    _clone_view(conn, "vw_airline_cpi_jy_snapshot", "vw_airline_cpi_5l_snapshot",
                "tenant_code::text = 'JY'::text", "tenant_code::text = '5L'::text")
    _clone_view(conn, "vw_velocity_jy_snapshot", "vw_velocity_5l_snapshot",
                "airline_code::text = 'JY'::text", "airline_code::text = '5L'::text")

    # ── partial indexes for the (currently empty) 5L partition ──
    for stmt in _INDEX_SQL:
        conn.execute(sa.text(stmt))


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("DROP INDEX IF EXISTS ix_air_snap_5l_triptype"))
    conn.execute(sa.text("DROP INDEX IF EXISTS ix_air_snap_5l_pricerec"))
    conn.execute(sa.text("DROP INDEX IF EXISTS ix_air_snap_5l_filtervals"))
    conn.execute(sa.text("DROP INDEX IF EXISTS ix_air_snap_5l_grid"))
    conn.execute(sa.text("DROP VIEW IF EXISTS vw_velocity_5l_snapshot"))
    conn.execute(sa.text("DROP VIEW IF EXISTS vw_airline_cpi_5l_snapshot"))
    # Explicit child deletes first; deleting the tenant also CASCADEs any
    # remaining 5L rows (app_user, role_binding, tenant_feature, snapshots).
    conn.execute(sa.text("DELETE FROM role_binding WHERE tenant_id = :tid"), {"tid": TENANT_5L})
    conn.execute(sa.text("DELETE FROM tenant_feature WHERE tenant_id = :tid"), {"tid": TENANT_5L})
    conn.execute(sa.text("DELETE FROM app_user WHERE tenant_id = :tid"), {"tid": TENANT_5L})
    conn.execute(sa.text("DELETE FROM tenant WHERE id = :tid"), {"tid": TENANT_5L})
