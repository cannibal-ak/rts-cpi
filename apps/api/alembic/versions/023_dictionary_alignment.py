"""Dictionary alignment to Airline DataDictionary v2026-05-09.

Aligns airline_cpi_snapshot table and its tenant views to the canonical
77-column data dictionary.

UPGRADE actions:
  1. Drop vw_jy_fare_vs_load entirely (no Superset slices reference it).
  2. Drop both tenant snapshot views (CREATE OR REPLACE cannot remove
     columns or relax NOT NULL semantics, so DROP + CREATE).
  3. Add 4 new dictionary columns to airline_cpi_snapshot:
       ref_pos, ref_channel, comp_pos, comp_channel.
  4. Drop 4 legacy columns no longer in the dictionary:
       pos (was standalone POS), poa (legacy point-of-arrival),
       pod, poc (PW point-of-departure / -consumption).
     Data in these columns will be lost on upgrade.
  5. Recreate vw_airline_cpi_jy_snapshot and vw_airline_cpi_pw_snapshot
     with exactly the 77 dictionary columns plus infra metadata.
     fare_delta and fare_delta_pct are not present in either view.

DOWNGRADE reverses table changes (re-adds dropped columns with empty
defaults to satisfy any existing NOT NULL semantics) and restores the
post-022 view definitions including fare_delta / fare_delta_pct and
vw_jy_fare_vs_load.

Revision: 023
Revises: 022
Create Date: 2026-05-09
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "023"
down_revision: Union[str, None] = "022"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ───────────────────────────────────────────────────────────────
# Post-023 view bodies — 77 dict columns + infra metadata.
# Column order matches Airline DataDictionary v2026-05-09 Sr. No. 1–77,
# with infra columns (tenant_id, ingested_at, …) appended at the end.
# ───────────────────────────────────────────────────────────────

def _new_snapshot_view_sql(tenant_code: str, view_name: str) -> str:
    return f"""\
CREATE VIEW {view_name} AS
 SELECT id,
    cap_date,
    cap_time,
    ref_al,
    ref_flt_num,
    ref_ret_flt_num,
    ref_org,
    ref_dst,
    ref_dep_date,
    ref_ret_dep_date,
    ref_dep_time,
    ref_ret_dep_time,
    ref_arr_time,
    ref_ret_arr_time,
    ref_stops,
    ref_via,
    ref_ret_via,
    ref_ret_stops,
    ref_ff_code,
    ref_curr,
    ref_base_fare,
    ref_tax,
    ref_yq,
    ref_yr,
    ref_anc_price,
    ref_anc_type,
    ref_tot_fare,
    ref_cab_name,
    ref_ret_cab_name,
    ref_cab_code,
    ref_ret_cab_code,
    ref_bkg_class,
    ref_ret_bkg_class,
    ref_seats,
    ref_ret_seats,
    ref_equip_code,
    ref_ret_equip_code,
    ref_pos,
    ref_channel,
    trip_type,
    comp_al,
    comp_flt_num,
    comp_ret_flt_num,
    comp_org,
    comp_dst,
    comp_dep_date,
    comp_ret_dep_date,
    comp_dep_time,
    comp_ret_dep_time,
    comp_arr_time,
    comp_ret_arr_time,
    comp_stops,
    comp_via,
    comp_ret_via,
    comp_ret_stops,
    comp_ff_code,
    comp_curr,
    comp_base_fare,
    comp_tax,
    comp_yq,
    comp_yr,
    comp_anc_price,
    comp_anc_type,
    comp_tot_fare,
    comp_cab_name,
    comp_ret_cab_name,
    comp_cab_code,
    comp_ret_cab_code,
    comp_bkg_class,
    comp_ret_bkg_class,
    comp_seats,
    comp_ret_seats,
    comp_equip_code,
    comp_ret_equip_code,
    comp_pos,
    comp_channel,
    path,
    -- infra metadata (not in dictionary, exposed for filters / freshness)
    tenant_id,
    ingested_at,
    import_batch_id,
    source_file_id,
    tenant_code,
    business_type,
    report_date,
    report_date AS file_date,
    source_file,
    loaded_at
   FROM airline_cpi_snapshot
  WHERE ((tenant_code)::text = '{tenant_code}'::text)
"""


# ───────────────────────────────────────────────────────────────
# Post-022 (pre-023) view bodies — used by downgrade(). Includes
# fare_delta / fare_delta_pct and the legacy point-of fields.
# ───────────────────────────────────────────────────────────────

def _restore_snapshot_view_sql(tenant_code: str, view_name: str) -> str:
    return f"""\
CREATE VIEW {view_name} AS
 SELECT id,
    tenant_id,
    cap_date,
    cap_time,
    trip_type,
    ref_al,
    ref_flt_num,
    ref_org,
    ref_dst,
    ref_dep_date,
    ref_cab_code,
    ref_tot_fare,
    ref_base_fare,
    ref_tax,
    ref_yq,
    ref_seats,
    ref_curr,
    comp_al,
    comp_flt_num,
    comp_org,
    comp_dst,
    comp_dep_date,
    comp_cab_code,
    comp_tot_fare,
    comp_base_fare,
    comp_tax,
    comp_yq,
    comp_seats,
    comp_curr,
    pos,
    poa,
    (comp_tot_fare - ref_tot_fare) AS fare_delta,
        CASE
            WHEN (ref_tot_fare > (0)::numeric) THEN round((((comp_tot_fare - ref_tot_fare) / ref_tot_fare) * (100)::numeric), 2)
            ELSE NULL::numeric
        END AS fare_delta_pct,
    ingested_at,
    import_batch_id,
    source_file_id,
    tenant_code,
    business_type,
    report_date,
    report_date AS file_date,
    source_file,
    loaded_at,
    ref_dep_time,
    ref_arr_time,
    ref_stops,
    ref_via,
    ref_ff_code,
    ref_cab_name,
    ref_bkg_class,
    ref_yr,
    ref_anc_price,
    ref_anc_type,
    ref_equip_code,
    ref_ret_flt_num,
    ref_ret_dep_date,
    ref_ret_dep_time,
    ref_ret_arr_time,
    ref_ret_stops,
    ref_ret_via,
    ref_ret_cab_name,
    ref_ret_cab_code,
    ref_ret_bkg_class,
    ref_ret_seats,
    ref_ret_equip_code,
    comp_dep_time,
    comp_arr_time,
    comp_stops,
    comp_via,
    comp_ff_code,
    comp_cab_name,
    comp_bkg_class,
    comp_yr,
    comp_anc_price,
    comp_anc_type,
    comp_equip_code,
    comp_ret_flt_num,
    comp_ret_dep_date,
    comp_ret_dep_time,
    comp_ret_arr_time,
    comp_ret_stops,
    comp_ret_via,
    comp_ret_cab_name,
    comp_ret_cab_code,
    comp_ret_bkg_class,
    comp_ret_seats,
    comp_ret_equip_code,
    pod,
    poc,
    path
   FROM airline_cpi_snapshot
  WHERE ((tenant_code)::text = '{tenant_code}'::text)
"""


RESTORE_VW_JY_FARE_VS_LOAD = """\
CREATE VIEW vw_jy_fare_vs_load AS
 SELECT a.id AS pricing_id,
    a.cap_date,
    a.ref_al,
    a.ref_flt_num,
    a.ref_org,
    a.ref_dst,
    a.ref_dep_date,
    a.ref_tot_fare,
    a.ref_base_fare,
    a.ref_tax,
    a.ref_seats,
    a.comp_al,
    a.comp_tot_fare,
    a.comp_base_fare,
    (a.comp_tot_fare - a.ref_tot_fare) AS fare_delta,
        CASE
            WHEN (a.ref_tot_fare > (0)::numeric) THEN round((((a.comp_tot_fare - a.ref_tot_fare) / a.ref_tot_fare) * (100)::numeric), 2)
            ELSE NULL::numeric
        END AS fare_delta_pct,
    v.dep_time,
    v.eqp,
    v.days_left,
    v.current_booking,
    v.capacity,
    v.actual_seat_factor,
    v.forecasted_seat_factor,
    (v.capacity - v.current_booking) AS seats_available,
        CASE
            WHEN (v.capacity > 0) THEN round((((v.current_booking)::numeric / (v.capacity)::numeric) * (100)::numeric), 1)
            ELSE (0)::numeric
        END AS booking_pct,
    a.report_date AS pricing_report_date,
    v.report_date AS velocity_report_date,
    a.tenant_code,
    a.business_type,
    a.ref_dep_time,
    a.ref_arr_time,
    a.ref_stops,
    a.ref_via,
    a.ref_ff_code,
    a.ref_cab_name,
    a.ref_bkg_class,
    a.ref_yr,
    a.ref_anc_price,
    a.ref_anc_type,
    a.ref_equip_code,
    a.ref_ret_flt_num,
    a.ref_ret_dep_date,
    a.ref_ret_dep_time,
    a.ref_ret_arr_time,
    a.ref_ret_stops,
    a.ref_ret_via,
    a.ref_ret_cab_name,
    a.ref_ret_cab_code,
    a.ref_ret_bkg_class,
    a.ref_ret_seats,
    a.ref_ret_equip_code,
    a.comp_dep_time,
    a.comp_arr_time,
    a.comp_stops,
    a.comp_via,
    a.comp_ff_code,
    a.comp_cab_name,
    a.comp_bkg_class,
    a.comp_yr,
    a.comp_anc_price,
    a.comp_anc_type,
    a.comp_equip_code,
    a.comp_ret_flt_num,
    a.comp_ret_dep_date,
    a.comp_ret_dep_time,
    a.comp_ret_arr_time,
    a.comp_ret_stops,
    a.comp_ret_via,
    a.comp_ret_cab_name,
    a.comp_ret_cab_code,
    a.comp_ret_bkg_class,
    a.comp_ret_seats,
    a.comp_ret_equip_code,
    a.pod,
    a.poc,
    a.path
   FROM (airline_cpi_snapshot a
     JOIN velocity_snapshot v ON ((((v.origin)::text = (a.ref_org)::text) AND ((v.destination)::text = (a.ref_dst)::text) AND (v.dep_date = a.ref_dep_date) AND (('JY'::text || (v.dep_code)::text) = (a.ref_flt_num)::text))))
  WHERE (((a.tenant_code)::text = 'JY'::text) AND ((v.airline_code)::text = 'JY'::text) AND ((v.legseg_type)::text = 'Segment'::text) AND (v.leg_seg_order = 1))
"""


def upgrade() -> None:
    # 1. Drop fare-vs-load (no dependents on snapshot views, but drop
    #    early so subsequent table-column drops are unambiguous).
    op.execute("DROP VIEW IF EXISTS vw_jy_fare_vs_load")

    # 2. Drop snapshot views before mutating their underlying table.
    op.execute("DROP VIEW IF EXISTS vw_airline_cpi_jy_snapshot")
    op.execute("DROP VIEW IF EXISTS vw_airline_cpi_pw_snapshot")

    # 3. Add 4 new dictionary columns.
    op.add_column("airline_cpi_snapshot", sa.Column("ref_pos", sa.String(length=4), nullable=True))
    op.add_column("airline_cpi_snapshot", sa.Column("ref_channel", sa.String(length=20), nullable=True))
    op.add_column("airline_cpi_snapshot", sa.Column("comp_pos", sa.String(length=4), nullable=True))
    op.add_column("airline_cpi_snapshot", sa.Column("comp_channel", sa.String(length=20), nullable=True))

    # 4. Drop 4 legacy columns. pos and poa are NOT NULL with data —
    #    Postgres DROP COLUMN handles this without needing to relax
    #    constraints first.
    op.execute("ALTER TABLE airline_cpi_snapshot DROP COLUMN IF EXISTS poa")
    op.execute("ALTER TABLE airline_cpi_snapshot DROP COLUMN IF EXISTS pod")
    op.execute("ALTER TABLE airline_cpi_snapshot DROP COLUMN IF EXISTS poc")
    op.execute("ALTER TABLE airline_cpi_snapshot DROP COLUMN IF EXISTS pos")

    # 5. Recreate snapshot views with the 77 dict columns + infra.
    op.execute(_new_snapshot_view_sql("JY", "vw_airline_cpi_jy_snapshot"))
    op.execute(_new_snapshot_view_sql("PW", "vw_airline_cpi_pw_snapshot"))


def downgrade() -> None:
    # Reverse step 5: drop the new views first.
    op.execute("DROP VIEW IF EXISTS vw_airline_cpi_jy_snapshot")
    op.execute("DROP VIEW IF EXISTS vw_airline_cpi_pw_snapshot")

    # Reverse step 4: re-add the legacy columns. NOT NULL columns are
    # restored with empty-string defaults so the ADD COLUMN succeeds
    # without backfill — historical data is NOT recoverable.
    op.add_column(
        "airline_cpi_snapshot",
        sa.Column("pos", sa.String(length=4), nullable=False, server_default=""),
    )
    op.add_column(
        "airline_cpi_snapshot",
        sa.Column("poa", sa.String(length=4), nullable=False, server_default=""),
    )
    op.add_column("airline_cpi_snapshot", sa.Column("pod", sa.String(length=4), nullable=True))
    op.add_column("airline_cpi_snapshot", sa.Column("poc", sa.String(length=4), nullable=True))

    # Reverse step 3: drop the 4 new columns.
    op.drop_column("airline_cpi_snapshot", "ref_pos")
    op.drop_column("airline_cpi_snapshot", "ref_channel")
    op.drop_column("airline_cpi_snapshot", "comp_pos")
    op.drop_column("airline_cpi_snapshot", "comp_channel")

    # Reverse step 2: restore snapshot views with the post-022 SELECT.
    op.execute(_restore_snapshot_view_sql("JY", "vw_airline_cpi_jy_snapshot"))
    op.execute(_restore_snapshot_view_sql("PW", "vw_airline_cpi_pw_snapshot"))

    # Reverse step 1: recreate vw_jy_fare_vs_load with full original.
    op.execute(RESTORE_VW_JY_FARE_VS_LOAD)
