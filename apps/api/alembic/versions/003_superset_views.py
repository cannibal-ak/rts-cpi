"""Tenant-safe Superset views (vw_*).

These views wrap the RLS-protected tables so Superset can query them.
When Superset connects as cpi_app role with SET app.current_tenant,
views automatically filter to the correct tenant.

Revision ID: 003
Revises: 002
Create Date: 2026-03-05
"""
from typing import Sequence, Union
from alembic import op

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── vw_airline_cpi_snapshot ────────────────────
    op.execute("""
        CREATE OR REPLACE VIEW vw_airline_cpi_snapshot AS
        SELECT
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
            -- Derived analytics columns
            (comp_tot_fare - ref_tot_fare)          AS fare_delta,
            CASE WHEN ref_tot_fare > 0
                 THEN round(((comp_tot_fare - ref_tot_fare) / ref_tot_fare * 100)::numeric, 2)
                 ELSE NULL
            END                                     AS fare_delta_pct,
            ingested_at,
            import_batch_id,
            source_file_id
        FROM airline_cpi_snapshot;
    """)

    # ── vw_cfl_cpi_snapshot ───────────────────────
    op.execute("""
        CREATE OR REPLACE VIEW vw_cfl_cpi_snapshot AS
        SELECT
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
            source_file_id
        FROM cfl_cpi_snapshot;
    """)

    # ── vw_import_jobs ────────────────────────────
    op.execute("""
        CREATE OR REPLACE VIEW vw_import_jobs AS
        SELECT
            j.id,
            j.tenant_id,
            j.domain,
            j.status,
            j.records_total,
            j.records_valid,
            j.records_rejected,
            j.started_at,
            j.completed_at,
            CASE WHEN j.records_total > 0
                 THEN round((j.records_valid::numeric / j.records_total * 100), 1)
                 ELSE 0
            END AS success_rate_pct,
            ss.display_name AS source_name,
            sf.file_name
        FROM import_job j
        LEFT JOIN source_system ss ON ss.id = j.source_system_id
        LEFT JOIN source_file sf ON sf.id = j.source_file_id;
    """)

    # ── vw_alert_events ───────────────────────────
    op.execute("""
        CREATE OR REPLACE VIEW vw_alert_events AS
        SELECT
            ae.id,
            ae.tenant_id,
            ae.rule_id,
            ae.rule_name,
            ae.triggered_at,
            ae.severity,
            ae.message,
            ae.delivery_status,
            ar.domain      AS rule_domain,
            ar.rule_type   AS rule_type,
            ar.is_active   AS rule_is_active
        FROM alert_event ae
        JOIN alert_rule ar ON ar.id = ae.rule_id;
    """)

    # Grant cpi_app access to views
    op.execute("GRANT SELECT ON vw_airline_cpi_snapshot TO cpi_app;")
    op.execute("GRANT SELECT ON vw_cfl_cpi_snapshot TO cpi_app;")
    op.execute("GRANT SELECT ON vw_import_jobs TO cpi_app;")
    op.execute("GRANT SELECT ON vw_alert_events TO cpi_app;")


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS vw_alert_events;")
    op.execute("DROP VIEW IF EXISTS vw_import_jobs;")
    op.execute("DROP VIEW IF EXISTS vw_cfl_cpi_snapshot;")
    op.execute("DROP VIEW IF EXISTS vw_airline_cpi_snapshot;")
