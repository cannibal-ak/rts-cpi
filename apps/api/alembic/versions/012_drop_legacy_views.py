"""Drop legacy combined snapshot views.

The application now uses tenant-specific views (e.g., vw_airline_cpi_jy_snapshot).
The old combined views are no longer needed.

Revision ID: 012
Revises: 011
Create Date: 2026-03-19
"""
from typing import Sequence, Union
from alembic import op

revision: str = "012"
down_revision: Union[str, None] = "011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("DROP VIEW IF EXISTS vw_cfl_cpi_snapshot;")
    op.execute("DROP VIEW IF EXISTS vw_airline_cpi_snapshot;")


def downgrade() -> None:
    # We can't easily restore the exact same logic here without duplicating it,
    # but for a downgrade we can recreate them with the basic structure.
    # Reusing logic from 011 basically.
    
    _AIRLINE_COLS = """
                id, tenant_id, cap_date, cap_time, trip_type,
                ref_al, ref_flt_num, ref_org, ref_dst, ref_dep_date, ref_cab_code,
                ref_tot_fare, ref_base_fare, ref_tax, ref_yq, ref_seats, ref_curr,
                comp_al, comp_flt_num, comp_org, comp_dst, comp_dep_date, comp_cab_code,
                comp_tot_fare, comp_base_fare, comp_tax, comp_yq, comp_seats, comp_curr,
                pos, poa,
                (comp_tot_fare - ref_tot_fare)          AS fare_delta,
                CASE WHEN ref_tot_fare > 0
                     THEN round(((comp_tot_fare - ref_tot_fare) / ref_tot_fare * 100)::numeric, 2)
                     ELSE NULL
                END                                     AS fare_delta_pct,
                ingested_at, import_batch_id, source_file_id,
                tenant_code, business_type, report_date, report_date AS file_date, source_file, loaded_at
    """
    
    _CFL_COLS = """
                id, tenant_id, cap_date, cap_time, trip_type, source, org, dest,
                out_dep_date, out_dep_time, prod_family, out_equip_name, out_cab_type,
                total_fare, out_per_pax_fare, out_veh_fare, out_cab_fare, out_taxes,
                out_num_pax, veh_size, curr_code, out_avail,
                ingested_at, import_batch_id, source_file_id,
                tenant_code, business_type, report_date, report_date AS file_date, source_file, loaded_at
    """

    op.execute(f"CREATE OR REPLACE VIEW vw_airline_cpi_snapshot AS SELECT {_AIRLINE_COLS} FROM airline_cpi_snapshot;")
    op.execute(f"CREATE OR REPLACE VIEW vw_cfl_cpi_snapshot AS SELECT {_CFL_COLS} FROM cfl_cpi_snapshot;")
    op.execute("GRANT SELECT ON vw_airline_cpi_snapshot TO cpi_app;")
    op.execute("GRANT SELECT ON vw_cfl_cpi_snapshot TO cpi_app;")
