"""Harden vw_cfl_cpi_fjl_snapshot with defensive data-quality filters.

The view was previously a plain ``WHERE tenant_code = 'FJL'`` passthrough
over ``cfl_cpi_snapshot``. A scraper regression on 2026-05-22 produced
9 rows with empty-string ``dest`` and ``total_fare = 0.00`` — these
surfaced as broken "HIR → " / "LAR → " routes in the FJL KPI panels.

To prevent any future scraper hiccups from polluting the dashboard,
the view now also excludes ``dest`` rows that are blank/whitespace and
fare rows with no fare attached. Bad rows are still in the base table
(for forensics / replay) but invisible to every FJL KPI builder and
Superset chart that reads through the view.

This migration captures the manual ``CREATE OR REPLACE VIEW`` that was
applied to the live DB on 2026-05-28, so a fresh-from-scratch rebuild
preserves the filter.

Downgrade restores the previous filter-less definition (tenant scope
only) — note this differs from the original 011 view, which used a
shorter column list; the 024 dictionary expansion and subsequent
manual touch-ups widened the projection to the current shape.

Revision: 029
Revises: 028
Create Date: 2026-05-28
"""
from typing import Sequence, Union

from alembic import op


revision: str = "029"
down_revision: Union[str, None] = "028"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Column projection — must match the current live definition. Kept as a
# constant so upgrade() and downgrade() can't drift on the column list.
_FJL_VIEW_COLS = """
    id,
    tenant_id,
    cap_date,
    cap_time,
    trip_type,
    source,
    org,
    dest,
    out_dep_date,
    out_dep_time,
    out_arr_date,
    out_arr_time,
    prod_family,
    out_equip_name,
    out_cab_type,
    out_cabin_desc,
    out_seat_type,
    out_num_cabs,
    out_seat_fare,
    out_num_seats,
    total_fare,
    out_per_pax_fare,
    out_veh_fare,
    out_cab_fare,
    out_taxes,
    out_num_pax,
    veh_size,
    curr_code,
    out_avail,
    ret_dep_date,
    ret_dep_time,
    ret_arr_date,
    ret_arr_time,
    ret_equip_name,
    ret_cab_type,
    ret_cab_desc,
    ret_seat_type,
    ret_avail,
    ret_per_pax_fare,
    ret_num_pax,
    ret_veh_fare,
    ret_cab_fare,
    ret_num_cabs,
    ret_seat_fare,
    ret_num_seats,
    ret_taxes,
    tot_per_pax_fare,
    tot_num_pax,
    tot_veh_fare,
    tot_cab_fare,
    tot_num_cabs,
    tot_seat_fare,
    tot_num_seats,
    tot_taxes,
    duration,
    ingested_at,
    import_batch_id,
    source_file_id,
    tenant_code,
    business_type,
    report_date,
    report_date AS file_date,
    source_file,
    loaded_at
"""


def upgrade() -> None:
    # DROP + CREATE (per project convention) loses GRANTs, so re-issue
    # the SELECT grant to cpi_app that 011 originally established.
    op.execute("DROP VIEW IF EXISTS vw_cfl_cpi_fjl_snapshot;")
    op.execute(f"""
        CREATE VIEW vw_cfl_cpi_fjl_snapshot AS
        SELECT {_FJL_VIEW_COLS}
        FROM cfl_cpi_snapshot
        WHERE tenant_code = 'FJL'
          AND TRIM(BOTH FROM dest) <> ''
          AND total_fare > 0;
    """)
    op.execute("GRANT SELECT ON vw_cfl_cpi_fjl_snapshot TO cpi_app;")


def downgrade() -> None:
    # Restore the unfiltered (tenant-scope-only) projection.
    op.execute("DROP VIEW IF EXISTS vw_cfl_cpi_fjl_snapshot;")
    op.execute(f"""
        CREATE VIEW vw_cfl_cpi_fjl_snapshot AS
        SELECT {_FJL_VIEW_COLS}
        FROM cfl_cpi_snapshot
        WHERE tenant_code = 'FJL';
    """)
    op.execute("GRANT SELECT ON vw_cfl_cpi_fjl_snapshot TO cpi_app;")
