"""DreamAir date picker: offer only dates the whole dashboard can render.

DreamAir's two feeds do not cover the same days. Its demo data is PW's Jan-Jun
2026 source re-badged, and PW's velocity feed has gaps and stops one day before
its fare feed: 162 fare capture dates, but only 147 of them have velocity.

The cap-date picker reads _DASHBOARD_DATE_VIEW, which pointed at the fare view,
so it offered all 162 and defaulted to the newest -- 2026-06-30, a date with
zero velocity rows. The guest token's RLS clause (cap_date = '2026-06-30') is
applied to da_velocity_normalized, so the Booking / Seat Factor / Capacity chart
returned no rows and rendered empty on first load. Verified: 0 rows on
2026-06-30, 60 rows on 2026-06-29.

This view intersects the two feeds so every date the picker offers renders every
tab. The 15 dropped dates carry fares but no velocity, so the Velocity tab was
empty on them regardless -- what is lost is fare-only browsing on 9% of days,
which is a better trade for a demo tenant than a dashboard that opens half blank.

WinAir does not need this: its fare and velocity feeds both end 2026-07-29, so
its picker never offers a date its velocity chart cannot render. The view is
deliberately DA-only rather than a generic change to how every tenant's dates
are derived.

Revision ID: 039
Revises: 038
Create Date: 2026-08-19
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "039"
down_revision: Union[str, None] = "038"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

VIEW = "vw_da_dashboard_dates"

# The column MUST be named cap_date: list_available_dates issues
# `SELECT DISTINCT cap_date FROM <view> ORDER BY cap_date DESC` against it.
CREATE_SQL = f"""
CREATE VIEW {VIEW} AS
SELECT cap_date FROM (
    SELECT DISTINCT cap_date FROM vw_airline_cpi_da_snapshot
    INTERSECT
    SELECT DISTINCT report_date FROM vw_velocity_da_snapshot
) q
"""


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text(CREATE_SQL))
    conn.execute(sa.text(f"GRANT SELECT ON {VIEW} TO cpi_app"))

    # A picker with no dates would leave the dashboard unusable, so fail the
    # migration rather than ship an empty view.
    n = conn.execute(sa.text(f"SELECT count(*) FROM {VIEW}")).scalar()
    if not n:
        raise RuntimeError(
            f"{VIEW} is empty - the DA fare and velocity feeds share no dates. "
            "Check that both vw_airline_cpi_da_snapshot and "
            "vw_velocity_da_snapshot have rows before running this."
        )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text(f"DROP VIEW IF EXISTS {VIEW}"))
