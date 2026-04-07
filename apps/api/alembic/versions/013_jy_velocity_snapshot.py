"""JY Velocity (booking/load factor) snapshot table and view.

Creates jy_velocity_snapshot to store daily flight velocity data:
  - Seat bookings, capacity, load factors per flight/route/date
  - Joins to airline_cpi_snapshot via flight number + dep date + route

Also creates:
  - vw_jy_velocity_snapshot view for Superset
  - RLS policies for tenant isolation
  - Indexes for common query patterns

Revision ID: 013
Revises: 012
Create Date: 2026-04-02
"""
from typing import Sequence, Union
from alembic import op

revision: str = "013"
down_revision: Union[str, None] = "012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Create the velocity snapshot table ────────────────
    op.execute("""
        CREATE TABLE jy_velocity_snapshot (
            id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            tenant_id       UUID NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
            import_batch_id UUID REFERENCES import_batch(id),

            -- Flight identity
            dep_date        DATE        NOT NULL,
            dep_time        VARCHAR(8)  NOT NULL,
            dep_code        VARCHAR(10) NOT NULL,
            city_pair       VARCHAR(8)  NOT NULL,
            origin          VARCHAR(4)  NOT NULL,
            destination     VARCHAR(4)  NOT NULL,
            eqp             VARCHAR(8)  NOT NULL,

            -- Leg/Segment breakdown
            legseg_type     VARCHAR(10) NOT NULL,
            leg_seg_order   INTEGER     NOT NULL DEFAULT 1,

            -- Booking & capacity
            days_left       INTEGER     NOT NULL DEFAULT 0,
            compartment     VARCHAR(4)  NOT NULL DEFAULT 'Y',
            current_booking INTEGER     NOT NULL DEFAULT 0,
            capacity        INTEGER     NOT NULL DEFAULT 0,
            actual_seat_factor      INTEGER NOT NULL DEFAULT 0,
            forecasted_seat_factor  INTEGER NOT NULL DEFAULT 0,

            -- Tenant segregation & metadata (same pattern as airline_cpi_snapshot)
            data_owner      VARCHAR(32),
            tenant_code     VARCHAR(16),
            business_type   VARCHAR(16),
            report_date     DATE,
            source_file     VARCHAR(256),
            loaded_at       TIMESTAMPTZ DEFAULT now(),
            ingested_at     TIMESTAMPTZ DEFAULT now()
        );
    """)

    # ── Indexes ───────────────────────────────────────────
    op.execute("CREATE INDEX ix_vel_tenant        ON jy_velocity_snapshot (tenant_id);")
    op.execute("CREATE INDEX ix_vel_tenant_code   ON jy_velocity_snapshot (tenant_code);")
    op.execute("CREATE INDEX ix_vel_dep_date      ON jy_velocity_snapshot (dep_date);")
    op.execute("CREATE INDEX ix_vel_dep_code      ON jy_velocity_snapshot (dep_code);")
    op.execute("CREATE INDEX ix_vel_city_pair     ON jy_velocity_snapshot (city_pair);")
    op.execute("CREATE INDEX ix_vel_origin        ON jy_velocity_snapshot (origin);")
    op.execute("CREATE INDEX ix_vel_destination   ON jy_velocity_snapshot (destination);")
    op.execute("CREATE INDEX ix_vel_report_date   ON jy_velocity_snapshot (report_date);")
    op.execute("CREATE INDEX ix_vel_legseg_type   ON jy_velocity_snapshot (legseg_type);")
    op.execute("CREATE INDEX idx_vel_data_owner   ON jy_velocity_snapshot (data_owner);")

    # ── Enable RLS ────────────────────────────────────────
    op.execute("ALTER TABLE jy_velocity_snapshot ENABLE ROW LEVEL SECURITY;")

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

    # ── Grant cpi_app access ──────────────────────────────
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON jy_velocity_snapshot TO cpi_app;")

    # ── Superset view ─────────────────────────────────────
    op.execute("""
        CREATE OR REPLACE VIEW vw_jy_velocity_snapshot AS
        SELECT
            id,
            tenant_id,
            dep_date,
            dep_time,
            dep_code,
            city_pair,
            origin,
            destination,
            eqp,
            legseg_type,
            leg_seg_order,
            days_left,
            compartment,
            current_booking,
            capacity,
            actual_seat_factor,
            forecasted_seat_factor,
            -- Derived columns
            (capacity - current_booking)            AS seats_available,
            CASE WHEN capacity > 0
                 THEN round((current_booking::numeric / capacity * 100), 1)
                 ELSE 0
            END                                     AS booking_pct,
            data_owner,
            tenant_code,
            business_type,
            report_date,
            report_date                             AS file_date,
            source_file,
            loaded_at,
            ingested_at
        FROM jy_velocity_snapshot
        WHERE tenant_code = 'JY';
    """)

    op.execute("GRANT SELECT ON vw_jy_velocity_snapshot TO cpi_app;")


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS vw_jy_velocity_snapshot;")
    op.execute("DROP TABLE IF EXISTS jy_velocity_snapshot CASCADE;")
