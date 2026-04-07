"""Joined view: JY fare pricing + velocity load factor data.

Joins airline_cpi_snapshot (pricing) with jy_velocity_snapshot (bookings)
on flight number + origin + destination + departure date.

Only includes Segment-level velocity rows to avoid double-counting from Legs.

Revision ID: 014
Revises: 013
Create Date: 2026-04-02
"""
from typing import Sequence, Union
from alembic import op

revision: str = "014"
down_revision: Union[str, None] = "013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE OR REPLACE VIEW vw_jy_fare_vs_load AS
        SELECT
            a.id                    AS pricing_id,
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
            (a.comp_tot_fare - a.ref_tot_fare)          AS fare_delta,
            CASE WHEN a.ref_tot_fare > 0
                 THEN round(((a.comp_tot_fare - a.ref_tot_fare) / a.ref_tot_fare * 100)::numeric, 2)
                 ELSE NULL
            END                                         AS fare_delta_pct,
            v.dep_time,
            v.eqp,
            v.days_left,
            v.current_booking,
            v.capacity,
            v.actual_seat_factor,
            v.forecasted_seat_factor,
            (v.capacity - v.current_booking)            AS seats_available,
            CASE WHEN v.capacity > 0
                 THEN round((v.current_booking::numeric / v.capacity * 100), 1)
                 ELSE 0
            END                                         AS booking_pct,
            a.report_date                               AS pricing_report_date,
            v.report_date                               AS velocity_report_date,
            a.tenant_code,
            a.business_type
        FROM airline_cpi_snapshot a
        INNER JOIN jy_velocity_snapshot v
            ON  v.origin      = a.ref_org
            AND v.destination = a.ref_dst
            AND v.dep_date    = a.ref_dep_date
            AND ('JY' || v.dep_code) = a.ref_flt_num
        WHERE a.tenant_code = 'JY'
          AND v.tenant_code = 'JY'
          AND v.legseg_type = 'Segment'
          AND v.leg_seg_order = 1;
    """)

    op.execute("GRANT SELECT ON vw_jy_fare_vs_load TO cpi_app;")


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS vw_jy_fare_vs_load;")
