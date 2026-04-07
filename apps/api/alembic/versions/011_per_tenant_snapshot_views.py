"""Per-tenant snapshot views for physical dashboard separation.

Creates dedicated views per tenant so each Superset dashboard points at
its own dataset with no cross-tenant data leakage:

  vw_airline_cpi_jy_snapshot  — JY rows only from airline_cpi_snapshot
  vw_airline_cpi_pw_snapshot  — PW rows only from airline_cpi_snapshot
  vw_cfl_cpi_fjl_snapshot     — FJL rows only from cfl_cpi_snapshot

Each view keeps the exact same columns / datatypes as the existing combined
snapshot views, plus the tenant segregation fields (tenant_code, report_date,
source_file, loaded_at).  An extra `file_date` alias of `report_date` is
exposed for the Superset "File Date" native filter.

The original combined views (vw_airline_cpi_snapshot, vw_cfl_cpi_snapshot)
are kept intact for backward compatibility.

Revision ID: 011
Revises: 010
Create Date: 2026-03-19
"""
from typing import Sequence, Union
from alembic import op

revision: str = "011"
down_revision: Union[str, None] = "010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ── Shared column lists (match existing combined views) ──────────

_AIRLINE_COLS = """
            id,
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
            -- Derived analytics columns (same as vw_airline_cpi_snapshot)
            (comp_tot_fare - ref_tot_fare)          AS fare_delta,
            CASE WHEN ref_tot_fare > 0
                 THEN round(((comp_tot_fare - ref_tot_fare) / ref_tot_fare * 100)::numeric, 2)
                 ELSE NULL
            END                                     AS fare_delta_pct,
            ingested_at,
            import_batch_id,
            source_file_id,
            -- Tenant segregation fields
            tenant_code,
            business_type,
            report_date,
            report_date                             AS file_date,
            source_file,
            loaded_at
"""

_CFL_COLS = """
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
            prod_family,
            out_equip_name,
            out_cab_type,
            total_fare,
            out_per_pax_fare,
            out_veh_fare,
            out_cab_fare,
            out_taxes,
            out_num_pax,
            veh_size,
            curr_code,
            out_avail,
            ingested_at,
            import_batch_id,
            source_file_id,
            -- Tenant segregation fields
            tenant_code,
            business_type,
            report_date,
            report_date                             AS file_date,
            source_file,
            loaded_at
"""


def upgrade() -> None:
    # ── Per-tenant airline views ───────────────────────
    op.execute(f"""
        CREATE OR REPLACE VIEW vw_airline_cpi_jy_snapshot AS
        SELECT {_AIRLINE_COLS}
        FROM airline_cpi_snapshot
        WHERE tenant_code = 'JY';
    """)

    op.execute(f"""
        CREATE OR REPLACE VIEW vw_airline_cpi_pw_snapshot AS
        SELECT {_AIRLINE_COLS}
        FROM airline_cpi_snapshot
        WHERE tenant_code = 'PW';
    """)

    # ── Per-tenant CFL view ────────────────────────────
    op.execute(f"""
        CREATE OR REPLACE VIEW vw_cfl_cpi_fjl_snapshot AS
        SELECT {_CFL_COLS}
        FROM cfl_cpi_snapshot
        WHERE tenant_code = 'FJL';
    """)

    # ── Also update the combined views to include tenant segregation cols ──
    op.execute(f"""
        CREATE OR REPLACE VIEW vw_airline_cpi_snapshot AS
        SELECT {_AIRLINE_COLS}
        FROM airline_cpi_snapshot;
    """)

    op.execute(f"""
        CREATE OR REPLACE VIEW vw_cfl_cpi_snapshot AS
        SELECT {_CFL_COLS}
        FROM cfl_cpi_snapshot;
    """)

    # ── Grant access to cpi_app role ───────────────────
    op.execute("GRANT SELECT ON vw_airline_cpi_jy_snapshot  TO cpi_app;")
    op.execute("GRANT SELECT ON vw_airline_cpi_pw_snapshot  TO cpi_app;")
    op.execute("GRANT SELECT ON vw_cfl_cpi_fjl_snapshot     TO cpi_app;")


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS vw_cfl_cpi_fjl_snapshot;")
    op.execute("DROP VIEW IF EXISTS vw_airline_cpi_pw_snapshot;")
    op.execute("DROP VIEW IF EXISTS vw_airline_cpi_jy_snapshot;")

    # Restore original combined views (without tenant segregation cols)
    op.execute("""
        CREATE OR REPLACE VIEW vw_airline_cpi_snapshot AS
        SELECT
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
            ingested_at, import_batch_id, source_file_id
        FROM airline_cpi_snapshot;
    """)

    op.execute("""
        CREATE OR REPLACE VIEW vw_cfl_cpi_snapshot AS
        SELECT
            id, tenant_id, cap_date, cap_time, trip_type, source, org, dest,
            out_dep_date, out_dep_time, prod_family, out_equip_name, out_cab_type,
            total_fare, out_per_pax_fare, out_veh_fare, out_cab_fare, out_taxes,
            out_num_pax, veh_size, curr_code, out_avail,
            ingested_at, import_batch_id, source_file_id
        FROM cfl_cpi_snapshot;
    """)
