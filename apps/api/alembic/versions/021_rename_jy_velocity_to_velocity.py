"""rename jy_velocity_snapshot -> velocity_snapshot, add airline_code

Phase 4 of the PW tenant parity work. Promotes the JY-implicit velocity
table to a shared multi-tenant table discriminated by airline_code.

Changes:
* Drop dependent views (vw_jy_velocity_snapshot, vw_jy_fare_vs_load).
* Drop the two RLS policies (names tied to the old table name).
* Rename jy_velocity_snapshot -> velocity_snapshot.
* Rename auto-generated PK/FK constraint and index names to match.
* Add airline_code VARCHAR(8) NOT NULL DEFAULT 'JY' so existing rows
  backfill cleanly, then drop the DEFAULT so future inserts are explicit.
* Composite index on (airline_code, report_date) — typical query path.
* Recreate RLS policies on the new table with identical predicates.
* Recreate two per-tenant views (vw_velocity_jy_snapshot,
  vw_velocity_pw_snapshot) following the airline_cpi naming convention.
* Recreate vw_jy_fare_vs_load against the renamed table for backward
  compatibility (Superset datasets may still reference it).

Downgrade reverses everything. As a hard safety check, downgrade aborts
if velocity_snapshot contains any rows where airline_code != 'JY' — those
rows would be silently lost otherwise. If you hit that abort, restore
from the pre-migration dump instead of running downgrade.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "021"
down_revision: Union[str, None] = "020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ── View bodies ─────────────────────────────────────────────

VW_VELOCITY_JY_BODY = """
CREATE OR REPLACE VIEW vw_velocity_jy_snapshot AS
SELECT id, tenant_id, dep_date, dep_time, dep_code, city_pair, origin, destination,
       eqp, legseg_type, leg_seg_order, days_left, compartment, current_booking,
       capacity, actual_seat_factor, forecasted_seat_factor,
       capacity - current_booking AS seats_available,
       CASE WHEN capacity > 0 THEN round(current_booking::numeric / capacity::numeric * 100::numeric, 1) ELSE 0::numeric END AS booking_pct,
       data_owner, tenant_code, airline_code, business_type, report_date,
       report_date AS file_date, source_file, loaded_at, ingested_at
FROM velocity_snapshot
WHERE airline_code = 'JY';
"""

VW_VELOCITY_PW_BODY = """
CREATE OR REPLACE VIEW vw_velocity_pw_snapshot AS
SELECT id, tenant_id, dep_date, dep_time, dep_code, city_pair, origin, destination,
       eqp, legseg_type, leg_seg_order, days_left, compartment, current_booking,
       capacity, actual_seat_factor, forecasted_seat_factor,
       capacity - current_booking AS seats_available,
       CASE WHEN capacity > 0 THEN round(current_booking::numeric / capacity::numeric * 100::numeric, 1) ELSE 0::numeric END AS booking_pct,
       data_owner, tenant_code, airline_code, business_type, report_date,
       report_date AS file_date, source_file, loaded_at, ingested_at
FROM velocity_snapshot
WHERE airline_code = 'PW';
"""

VW_JY_FARE_VS_LOAD_NEW = """
CREATE OR REPLACE VIEW vw_jy_fare_vs_load AS
SELECT a.id AS pricing_id, a.cap_date, a.ref_al, a.ref_flt_num, a.ref_org, a.ref_dst,
       a.ref_dep_date, a.ref_tot_fare, a.ref_base_fare, a.ref_tax, a.ref_seats,
       a.comp_al, a.comp_tot_fare, a.comp_base_fare,
       a.comp_tot_fare - a.ref_tot_fare AS fare_delta,
       CASE WHEN a.ref_tot_fare > 0::numeric
            THEN round((a.comp_tot_fare - a.ref_tot_fare) / a.ref_tot_fare * 100::numeric, 2)
            ELSE NULL::numeric END AS fare_delta_pct,
       v.dep_time, v.eqp, v.days_left, v.current_booking, v.capacity,
       v.actual_seat_factor, v.forecasted_seat_factor,
       v.capacity - v.current_booking AS seats_available,
       CASE WHEN v.capacity > 0
            THEN round(v.current_booking::numeric / v.capacity::numeric * 100::numeric, 1)
            ELSE 0::numeric END AS booking_pct,
       a.report_date AS pricing_report_date,
       v.report_date AS velocity_report_date,
       a.tenant_code, a.business_type
FROM airline_cpi_snapshot a
JOIN velocity_snapshot v
    ON v.origin::text = a.ref_org::text
    AND v.destination::text = a.ref_dst::text
    AND v.dep_date = a.ref_dep_date
    AND ('JY'::text || v.dep_code::text) = a.ref_flt_num::text
WHERE a.tenant_code::text = 'JY'::text
  AND v.airline_code::text = 'JY'::text
  AND v.legseg_type::text = 'Segment'::text
  AND v.leg_seg_order = 1;
"""

# ── Original (pre-021) view bodies — used by downgrade() to restore state ──

VW_JY_VELOCITY_OLD_BODY = """
CREATE OR REPLACE VIEW vw_jy_velocity_snapshot AS
SELECT id, tenant_id, dep_date, dep_time, dep_code, city_pair, origin, destination,
       eqp, legseg_type, leg_seg_order, days_left, compartment, current_booking,
       capacity, actual_seat_factor, forecasted_seat_factor,
       capacity - current_booking AS seats_available,
       CASE WHEN capacity > 0 THEN round(current_booking::numeric / capacity::numeric * 100::numeric, 1) ELSE 0::numeric END AS booking_pct,
       data_owner, tenant_code, business_type, report_date,
       report_date AS file_date, source_file, loaded_at, ingested_at
FROM jy_velocity_snapshot
WHERE tenant_code::text = 'JY'::text;
"""

VW_JY_FARE_VS_LOAD_OLD = """
CREATE OR REPLACE VIEW vw_jy_fare_vs_load AS
SELECT a.id AS pricing_id, a.cap_date, a.ref_al, a.ref_flt_num, a.ref_org, a.ref_dst,
       a.ref_dep_date, a.ref_tot_fare, a.ref_base_fare, a.ref_tax, a.ref_seats,
       a.comp_al, a.comp_tot_fare, a.comp_base_fare,
       a.comp_tot_fare - a.ref_tot_fare AS fare_delta,
       CASE WHEN a.ref_tot_fare > 0::numeric
            THEN round((a.comp_tot_fare - a.ref_tot_fare) / a.ref_tot_fare * 100::numeric, 2)
            ELSE NULL::numeric END AS fare_delta_pct,
       v.dep_time, v.eqp, v.days_left, v.current_booking, v.capacity,
       v.actual_seat_factor, v.forecasted_seat_factor,
       v.capacity - v.current_booking AS seats_available,
       CASE WHEN v.capacity > 0
            THEN round(v.current_booking::numeric / v.capacity::numeric * 100::numeric, 1)
            ELSE 0::numeric END AS booking_pct,
       a.report_date AS pricing_report_date,
       v.report_date AS velocity_report_date,
       a.tenant_code, a.business_type
FROM airline_cpi_snapshot a
JOIN jy_velocity_snapshot v
    ON v.origin::text = a.ref_org::text
    AND v.destination::text = a.ref_dst::text
    AND v.dep_date = a.ref_dep_date
    AND ('JY'::text || v.dep_code::text) = a.ref_flt_num::text
WHERE a.tenant_code::text = 'JY'::text
  AND v.tenant_code::text = 'JY'::text
  AND v.legseg_type::text = 'Segment'::text
  AND v.leg_seg_order = 1;
"""


def upgrade() -> None:
    # 1. Drop dependent views first
    op.execute("DROP VIEW IF EXISTS vw_jy_velocity_snapshot CASCADE;")
    op.execute("DROP VIEW IF EXISTS vw_jy_fare_vs_load CASCADE;")

    # 2. Drop RLS policies (names tied to the old table name)
    op.execute("DROP POLICY IF EXISTS rls_jy_velocity_snapshot_superuser_bypass ON jy_velocity_snapshot;")
    op.execute("DROP POLICY IF EXISTS rls_jy_velocity_snapshot_tenant_isolation ON jy_velocity_snapshot;")

    # 3. Rename the table
    op.rename_table("jy_velocity_snapshot", "velocity_snapshot")

    # 4. Rename auto-generated constraint + index names to match new table
    op.execute("ALTER TABLE velocity_snapshot RENAME CONSTRAINT jy_velocity_snapshot_pkey TO velocity_snapshot_pkey;")
    op.execute("ALTER TABLE velocity_snapshot RENAME CONSTRAINT jy_velocity_snapshot_import_batch_id_fkey TO velocity_snapshot_import_batch_id_fkey;")
    op.execute("ALTER TABLE velocity_snapshot RENAME CONSTRAINT jy_velocity_snapshot_tenant_id_fkey TO velocity_snapshot_tenant_id_fkey;")

    # 5. Add airline_code with backfill default (existing rows get JY)
    op.add_column("velocity_snapshot", sa.Column("airline_code", sa.String(8), nullable=False, server_default="JY"))

    # 6. Drop the default — future inserts must provide airline_code explicitly
    op.alter_column("velocity_snapshot", "airline_code", server_default=None)

    # 7. Composite index for (airline_code, report_date) query pattern
    op.create_index("ix_vel_airline_code_report_date", "velocity_snapshot", ["airline_code", "report_date"])

    # 8. Recreate RLS policies on the new table with verbatim predicates
    op.execute("ALTER TABLE velocity_snapshot ENABLE ROW LEVEL SECURITY;")
    op.execute("""
        CREATE POLICY rls_velocity_snapshot_tenant_isolation
        ON velocity_snapshot FOR ALL TO cpi_app
        USING (tenant_id = current_setting('app.current_tenant')::uuid);
    """)
    op.execute("""
        CREATE POLICY rls_velocity_snapshot_superuser_bypass
        ON velocity_snapshot FOR ALL TO cpi
        USING (true);
    """)

    # 9. Grant DML on the renamed table (recreates the grant from migration 013)
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON velocity_snapshot TO cpi_app;")

    # 10. Recreate per-tenant views following the airline_cpi naming convention
    op.execute(VW_VELOCITY_JY_BODY)
    op.execute("GRANT SELECT ON vw_velocity_jy_snapshot TO cpi_app;")
    op.execute(VW_VELOCITY_PW_BODY)
    op.execute("GRANT SELECT ON vw_velocity_pw_snapshot TO cpi_app;")

    # 11. Recreate vw_jy_fare_vs_load against the renamed table for backward compat
    op.execute(VW_JY_FARE_VS_LOAD_NEW)
    op.execute("GRANT SELECT ON vw_jy_fare_vs_load TO cpi_app;")


def downgrade() -> None:
    # Hard safety check: refuse to downgrade if any non-JY data exists
    conn = op.get_bind()
    non_jy_count = conn.execute(
        sa.text("SELECT COUNT(*) FROM velocity_snapshot WHERE airline_code IS DISTINCT FROM 'JY'")
    ).scalar() or 0
    if non_jy_count > 0:
        raise Exception(
            f"Downgrade aborted: velocity_snapshot has {non_jy_count} non-JY rows. "
            "Dropping airline_code would silently lose tenant data. Restore from the "
            "pre-migration dump instead."
        )

    # Drop the new views and the composite index
    op.execute("DROP VIEW IF EXISTS vw_velocity_jy_snapshot CASCADE;")
    op.execute("DROP VIEW IF EXISTS vw_velocity_pw_snapshot CASCADE;")
    op.execute("DROP VIEW IF EXISTS vw_jy_fare_vs_load CASCADE;")
    op.drop_index("ix_vel_airline_code_report_date", table_name="velocity_snapshot")

    # Drop the new RLS policies
    op.execute("DROP POLICY IF EXISTS rls_velocity_snapshot_tenant_isolation ON velocity_snapshot;")
    op.execute("DROP POLICY IF EXISTS rls_velocity_snapshot_superuser_bypass ON velocity_snapshot;")

    # Drop airline_code (safety check above already ensured no data loss)
    op.drop_column("velocity_snapshot", "airline_code")

    # Rename constraints and the index back
    op.execute("ALTER TABLE velocity_snapshot RENAME CONSTRAINT velocity_snapshot_pkey TO jy_velocity_snapshot_pkey;")
    op.execute("ALTER TABLE velocity_snapshot RENAME CONSTRAINT velocity_snapshot_import_batch_id_fkey TO jy_velocity_snapshot_import_batch_id_fkey;")
    op.execute("ALTER TABLE velocity_snapshot RENAME CONSTRAINT velocity_snapshot_tenant_id_fkey TO jy_velocity_snapshot_tenant_id_fkey;")

    # Rename the table back
    op.rename_table("velocity_snapshot", "jy_velocity_snapshot")

    # Recreate the original RLS policies on the renamed table
    op.execute("""
        CREATE POLICY rls_jy_velocity_snapshot_tenant_isolation
        ON jy_velocity_snapshot FOR ALL TO cpi_app
        USING (tenant_id = current_setting('app.current_tenant')::uuid);
    """)
    op.execute("""
        CREATE POLICY rls_jy_velocity_snapshot_superuser_bypass
        ON jy_velocity_snapshot FOR ALL TO cpi
        USING (true);
    """)

    # Recreate the original views
    op.execute(VW_JY_VELOCITY_OLD_BODY)
    op.execute("GRANT SELECT ON vw_jy_velocity_snapshot TO cpi_app;")
    op.execute(VW_JY_FARE_VS_LOAD_OLD)
    op.execute("GRANT SELECT ON vw_jy_fare_vs_load TO cpi_app;")
