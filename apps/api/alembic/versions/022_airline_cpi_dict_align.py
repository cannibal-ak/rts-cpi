"""airline_cpi_snapshot dict-align: add 47 cols + recreate 3 views

Phase 2A of the airline-CPI dictionary alignment work. Brings
airline_cpi_snapshot from 41 to 88 physical columns (30 dictionary
columns previously present + 47 new dictionary columns + 11
infrastructure columns). All new columns are nullable; no defaults;
no NOT NULL constraints; no new indexes (deferred).

The 47 new columns are grouped into six clusters:

* Reference flight - outbound additions (11): existing schedule/stops/
  fare-component coverage gap filled with HHMM clock fields, RefVia,
  RefFFCode, RefCabName, RefBkgClass, RefYR, RefAncPrice, RefAncType,
  and the canonical equipment column ref_equip_code (unifies JY's
  RefAircraft and PW's RefEquipCode source headers).
* Reference flight - return-leg (11): JY-only return-flight Ref* fields
  (PW source has no return-flight columns; PW rows leave NULL).
* Competitor - outbound additions (11): comp_dep_time, comp_arr_time,
  comp_stops, comp_via, comp_ff_code, comp_cab_name, comp_bkg_class,
  comp_yr, comp_anc_price, comp_anc_type, and comp_equip_code.
* Competitor - return-leg (11): JY-only Comp*Ret* fields.
* Point-of-* (2): pod, poc - PW source carries these; JY rows leave NULL.
* Provenance (1): path - dictionary-required but absent from both
  source files today; permanently NULL until source teams add it.

Migration also recreates three views to expose the new columns:

* vw_airline_cpi_jy_snapshot   (CREATE OR REPLACE - prefix-extension)
* vw_airline_cpi_pw_snapshot   (CREATE OR REPLACE - prefix-extension)
* vw_jy_fare_vs_load           (DROP + CREATE per discovery directive
                                in the migration plan)

Downgrade reverses everything: drops vw_jy_fare_vs_load and recreates
its ORIGINAL definition; CREATE OR REPLACE restores the two snapshot
views to their pre-022 SELECT-lists; reverse-order DROP COLUMN removes
the 47 new columns.

Refs: docs/airline-cpi-migration-plan-20260506.md (Sections 6.2, 7.1, 7.2)
Migration target: cpi-postgres-1 / cpi_db.

Revision ID: 022
Revises: 021
Create Date: 2026-05-08
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "022"
down_revision: Union[str, None] = "021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ───────────────────────────────────────────────────────────────
# 47 new columns, grouped by cluster. All nullable=True. No defaults.
# Order within NEW_COLUMNS is the order they will be ADD COLUMN'd in
# upgrade() and (reversed) DROP COLUMN'd in downgrade().
# ───────────────────────────────────────────────────────────────

NEW_COLUMNS: list[sa.Column] = [
    # Cluster: Reference flight - outbound additions (11)
    sa.Column("ref_dep_time", sa.String(length=4), nullable=True),
    sa.Column("ref_arr_time", sa.String(length=4), nullable=True),
    sa.Column("ref_stops", sa.Integer(), nullable=True),
    sa.Column("ref_via", sa.String(length=4), nullable=True),
    sa.Column("ref_ff_code", sa.String(length=20), nullable=True),
    sa.Column("ref_cab_name", sa.String(length=20), nullable=True),
    sa.Column("ref_bkg_class", sa.String(length=4), nullable=True),
    sa.Column("ref_yr", sa.Numeric(12, 2), nullable=True),
    sa.Column("ref_anc_price", sa.Numeric(12, 2), nullable=True),
    sa.Column("ref_anc_type", sa.String(length=20), nullable=True),
    sa.Column("ref_equip_code", sa.String(length=32), nullable=True),

    # Cluster: Reference flight - return-leg (11) - JY-only
    sa.Column("ref_ret_flt_num", sa.String(length=10), nullable=True),
    sa.Column("ref_ret_dep_date", sa.Date(), nullable=True),
    sa.Column("ref_ret_dep_time", sa.String(length=4), nullable=True),
    sa.Column("ref_ret_arr_time", sa.String(length=4), nullable=True),
    sa.Column("ref_ret_stops", sa.Integer(), nullable=True),
    sa.Column("ref_ret_via", sa.String(length=4), nullable=True),
    sa.Column("ref_ret_cab_name", sa.String(length=20), nullable=True),
    sa.Column("ref_ret_cab_code", sa.String(length=4), nullable=True),
    sa.Column("ref_ret_bkg_class", sa.String(length=4), nullable=True),
    sa.Column("ref_ret_seats", sa.Integer(), nullable=True),
    sa.Column("ref_ret_equip_code", sa.String(length=32), nullable=True),

    # Cluster: Competitor - outbound additions (11)
    sa.Column("comp_dep_time", sa.String(length=4), nullable=True),
    sa.Column("comp_arr_time", sa.String(length=4), nullable=True),
    sa.Column("comp_stops", sa.Integer(), nullable=True),
    sa.Column("comp_via", sa.String(length=4), nullable=True),
    sa.Column("comp_ff_code", sa.String(length=20), nullable=True),
    sa.Column("comp_cab_name", sa.String(length=20), nullable=True),
    sa.Column("comp_bkg_class", sa.String(length=4), nullable=True),
    sa.Column("comp_yr", sa.Numeric(12, 2), nullable=True),
    sa.Column("comp_anc_price", sa.Numeric(12, 2), nullable=True),
    sa.Column("comp_anc_type", sa.String(length=20), nullable=True),
    sa.Column("comp_equip_code", sa.String(length=32), nullable=True),

    # Cluster: Competitor - return-leg (11) - JY-only
    sa.Column("comp_ret_flt_num", sa.String(length=10), nullable=True),
    sa.Column("comp_ret_dep_date", sa.Date(), nullable=True),
    sa.Column("comp_ret_dep_time", sa.String(length=4), nullable=True),
    sa.Column("comp_ret_arr_time", sa.String(length=4), nullable=True),
    sa.Column("comp_ret_stops", sa.Integer(), nullable=True),
    sa.Column("comp_ret_via", sa.String(length=4), nullable=True),
    sa.Column("comp_ret_cab_name", sa.String(length=20), nullable=True),
    sa.Column("comp_ret_cab_code", sa.String(length=4), nullable=True),
    sa.Column("comp_ret_bkg_class", sa.String(length=4), nullable=True),
    sa.Column("comp_ret_seats", sa.Integer(), nullable=True),
    sa.Column("comp_ret_equip_code", sa.String(length=32), nullable=True),

    # Cluster: Point-of-* (PW source carries these) (2)
    sa.Column("pod", sa.String(length=4), nullable=True),
    sa.Column("poc", sa.String(length=4), nullable=True),

    # Cluster: Provenance (1)
    sa.Column("path", sa.String(length=50), nullable=True),
]


# ───────────────────────────────────────────────────────────────
# View bodies. Captured live from cpi-postgres-1:cpi_db on
# 2026-05-08 via pg_views and verified byte-for-byte against the
# Phase-1 capture in docs/airline-cpi-migration-plan-20260506.md
# Section 6.2.
#
# UPGRADE_* bodies = ORIGINAL_* + 47 new columns appended in the
# same cluster order as NEW_COLUMNS (after `loaded_at` for the
# snapshot views; after the existing analytics columns for the
# fare-vs-load view, prefixed `a.` because they live in
# airline_cpi_snapshot which is aliased as `a` in that join).
# ───────────────────────────────────────────────────────────────

# 47 new column names in the order they appear in NEW_COLUMNS,
# used both for the snapshot-view appends and (with `a.` prefix)
# for the fare-vs-load view append.
_NEW_COL_NAMES: list[str] = [c.name for c in NEW_COLUMNS]

_NEW_COL_LIST_PLAIN = ",\n    ".join(_NEW_COL_NAMES)
_NEW_COL_LIST_A_PREFIXED = ",\n    ".join(f"a.{n}" for n in _NEW_COL_NAMES)


ORIGINAL_VW_AIRLINE_CPI_JY = """\
CREATE VIEW vw_airline_cpi_jy_snapshot AS
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
    loaded_at
   FROM airline_cpi_snapshot
  WHERE ((tenant_code)::text = 'JY'::text)
"""

ORIGINAL_VW_AIRLINE_CPI_PW = """\
CREATE VIEW vw_airline_cpi_pw_snapshot AS
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
    loaded_at
   FROM airline_cpi_snapshot
  WHERE ((tenant_code)::text = 'PW'::text)
"""

ORIGINAL_VW_JY_FARE_VS_LOAD = """\
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
    a.business_type
   FROM (airline_cpi_snapshot a
     JOIN velocity_snapshot v ON ((((v.origin)::text = (a.ref_org)::text) AND ((v.destination)::text = (a.ref_dst)::text) AND (v.dep_date = a.ref_dep_date) AND (('JY'::text || (v.dep_code)::text) = (a.ref_flt_num)::text))))
  WHERE (((a.tenant_code)::text = 'JY'::text) AND ((v.airline_code)::text = 'JY'::text) AND ((v.legseg_type)::text = 'Segment'::text) AND (v.leg_seg_order = 1))
"""


def _upgrade_view_airline_cpi(tenant_code: str, view_name: str) -> str:
    """Build the CREATE OR REPLACE VIEW body for the JY/PW snapshot view
    with the 47 new columns appended after `loaded_at`."""
    return f"""\
CREATE OR REPLACE VIEW {view_name} AS
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
    {_NEW_COL_LIST_PLAIN}
   FROM airline_cpi_snapshot
  WHERE ((tenant_code)::text = '{tenant_code}'::text)
"""


UPGRADE_VW_AIRLINE_CPI_JY = _upgrade_view_airline_cpi("JY", "vw_airline_cpi_jy_snapshot")
UPGRADE_VW_AIRLINE_CPI_PW = _upgrade_view_airline_cpi("PW", "vw_airline_cpi_pw_snapshot")

UPGRADE_VW_JY_FARE_VS_LOAD = f"""\
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
    {_NEW_COL_LIST_A_PREFIXED}
   FROM (airline_cpi_snapshot a
     JOIN velocity_snapshot v ON ((((v.origin)::text = (a.ref_org)::text) AND ((v.destination)::text = (a.ref_dst)::text) AND (v.dep_date = a.ref_dep_date) AND (('JY'::text || (v.dep_code)::text) = (a.ref_flt_num)::text))))
  WHERE (((a.tenant_code)::text = 'JY'::text) AND ((v.airline_code)::text = 'JY'::text) AND ((v.legseg_type)::text = 'Segment'::text) AND (v.leg_seg_order = 1))
"""


# ───────────────────────────────────────────────────────────────
# upgrade / downgrade
# ───────────────────────────────────────────────────────────────

def upgrade() -> None:
    # 1. Add the 47 new columns to airline_cpi_snapshot. Order matches
    #    NEW_COLUMNS (cluster-by-cluster). All nullable; no defaults.
    for col in NEW_COLUMNS:
        op.add_column("airline_cpi_snapshot", col)

    # 2. Recreate the two per-tenant snapshot views with the new
    #    columns appended. CREATE OR REPLACE is safe here because the
    #    new SELECT-list is a strict prefix-extension of the original.
    op.execute(UPGRADE_VW_AIRLINE_CPI_JY)
    op.execute(UPGRADE_VW_AIRLINE_CPI_PW)

    # 3. Recreate vw_jy_fare_vs_load via DROP + CREATE (the migration
    #    plan flagged column-aliasing as a CREATE-OR-REPLACE risk for
    #    this view; DROP+CREATE is the safe path).
    op.execute("DROP VIEW IF EXISTS vw_jy_fare_vs_load")
    op.execute(UPGRADE_VW_JY_FARE_VS_LOAD)


def downgrade() -> None:
    # 1. Drop all three views FIRST. They reference the 47 new columns
    #    (in their post-022 bodies), so we must remove the views before
    #    we can DROP COLUMN. CREATE OR REPLACE cannot be used here
    #    because PostgreSQL only allows CREATE OR REPLACE to ADD
    #    columns at the end of a view's SELECT-list, never to remove
    #    columns. So all three drops are unconditional.
    op.execute("DROP VIEW IF EXISTS vw_jy_fare_vs_load")
    op.execute("DROP VIEW IF EXISTS vw_airline_cpi_pw_snapshot")
    op.execute("DROP VIEW IF EXISTS vw_airline_cpi_jy_snapshot")

    # 2. Drop the 47 new columns in REVERSE order so dependent objects
    #    (none expected at this stage) unwind cleanly.
    for col in reversed(NEW_COLUMNS):
        op.drop_column("airline_cpi_snapshot", col.name)

    # 3. Recreate the three views with their ORIGINAL bodies (verbatim
    #    from the live capture in Phase 1). Order: snapshot views first
    #    (vw_jy_fare_vs_load is independent so order is not strict).
    op.execute(ORIGINAL_VW_AIRLINE_CPI_JY)
    op.execute(ORIGINAL_VW_AIRLINE_CPI_PW)
    op.execute(ORIGINAL_VW_JY_FARE_VS_LOAD)
