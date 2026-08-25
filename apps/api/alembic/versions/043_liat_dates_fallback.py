"""Liat date picker: fall back to fare dates while velocity is absent.

042 defined vw_5l_dashboard_dates as the INTERSECT of the fare and velocity
feeds (the DreamAir pattern from 039), so a date is only offered when every
dashboard tab can render it. That is the right steady state, but Liat's
feeds arrive in stages: the client loaded pricing first (8 capture dates,
2026-08-09..24) and velocity comes later. With zero velocity rows the
intersection is empty, so the picker showed "Cap date: unavailable" while
the freshness chip correctly said data existed.

The view now degrades explicitly: while the velocity feed has NO rows at
all, offer every fare date (the only tab that could render, the pricing
charts, can render all of them); the moment the first velocity row commits,
the predicate flips and the view is 042's intersection again, unprompted.
A PARTIALLY-loaded velocity feed therefore behaves exactly as on DreamAir —
fare-only dates are dropped — which is intended: at that point the Velocity
tab exists and a date that opens it blank is worse than a shorter list.

The `NOT EXISTS` arm is O(1) (any-row probe); the `IN` arm only runs once
velocity has rows and scans the velocity view's DISTINCT report_dates —
small, and nothing like the per-row `cap_date IN (subquery)` shape that bit
the alerts engine.

Revision ID: 043
Revises: 042
Create Date: 2026-08-26
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "043"
down_revision: Union[str, None] = "042"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

VIEW = "vw_5l_dashboard_dates"

# The column MUST stay named cap_date: list_available_dates issues
# `SELECT DISTINCT cap_date FROM <view> ORDER BY cap_date DESC` against it.
CREATE_SQL = f"""
CREATE OR REPLACE VIEW {VIEW} AS
SELECT cap_date FROM (
    SELECT DISTINCT cap_date FROM vw_airline_cpi_5l_snapshot
) fare_dates
WHERE NOT EXISTS (SELECT 1 FROM vw_velocity_5l_snapshot)
   OR cap_date IN (SELECT DISTINCT report_date FROM vw_velocity_5l_snapshot)
"""

# 042's definition, restored on downgrade.
RESTORE_042_SQL = f"""
CREATE OR REPLACE VIEW {VIEW} AS
SELECT cap_date FROM (
    SELECT DISTINCT cap_date FROM vw_airline_cpi_5l_snapshot
    INTERSECT
    SELECT DISTINCT report_date FROM vw_velocity_5l_snapshot
) q
"""


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text(CREATE_SQL))
    conn.execute(sa.text(f"GRANT SELECT ON {VIEW} TO cpi_app"))


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text(RESTORE_042_SQL))
    conn.execute(sa.text(f"GRANT SELECT ON {VIEW} TO cpi_app"))
