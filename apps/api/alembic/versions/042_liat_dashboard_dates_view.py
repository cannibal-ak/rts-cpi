"""Liat Air date picker: offer only dates the whole dashboard can render.

The Liat (5L) counterpart of migration 039 (vw_da_dashboard_dates): the
cap-date picker reads _DASHBOARD_DATE_VIEW, and pointing it at the fare view
alone lets it offer a date with zero velocity rows — the guest token's RLS
clause then empties the Booking / Seat Factor / Capacity chart on first load.
Intersecting the two feeds guarantees every date the picker offers renders
every tab. See 039's docstring for the full DA case study.

ONE DELIBERATE DIFFERENCE FROM 039: no fail-on-empty guard. 039 could insist
on a non-empty view because DreamAir's data was loaded before the migration
ran. Liat's data arrives AFTER this ships (the client uploads through the
ingestion UI), and the api entrypoint runs `alembic upgrade head` on boot —
a hard fail here would take the entire API down for every tenant until 5L
data existed. An empty view just means an empty date picker until the first
upload commits, which is the correct behaviour for a not-yet-loaded tenant.

Revision ID: 042
Revises: 041
Create Date: 2026-08-25
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "042"
down_revision: Union[str, None] = "041"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

VIEW = "vw_5l_dashboard_dates"

# The column MUST be named cap_date: list_available_dates issues
# `SELECT DISTINCT cap_date FROM <view> ORDER BY cap_date DESC` against it.
CREATE_SQL = f"""
CREATE VIEW {VIEW} AS
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
    conn.execute(sa.text(f"DROP VIEW IF EXISTS {VIEW}"))
