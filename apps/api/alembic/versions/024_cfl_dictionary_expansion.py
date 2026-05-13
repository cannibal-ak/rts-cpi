"""CFL Dictionary expansion — add 33 missing columns to cfl_cpi_snapshot.

Brings the cfl_cpi_snapshot table from 20 data columns to 53 data columns,
matching the CFL Data Dictionary (columns #1 ID and #55 Path excluded by
design — those are not part of the ingested payload).

UPGRADE adds 33 nullable columns. Existing rows get NULL for the new
columns (correct — they were one-way outbound-only data).

DOWNGRADE drops the 33 columns in reverse order. The tenant view
vw_cfl_cpi_fjl_snapshot is NOT touched by this migration — it is
recreated separately in Phase 3 of the rollout to expose the new
columns. (Dropping/recreating the view is a separate concern from
this DDL-only column addition.)

Revision: 024
Revises: 023
Create Date: 2026-05-13
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "024"
down_revision: Union[str, None] = "023"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Column groups for readability — these line up with the Data Dictionary
# categories and match the order the spec lists them.

_OUTBOUND_ARRIVAL = [
    ("out_arr_date",     sa.Date()),
    ("out_arr_time",     sa.Time()),
]

_OUTBOUND_DESCS_SEATS = [
    ("out_cabin_desc",   sa.String(100)),
    ("out_seat_type",    sa.String(50)),
    ("out_num_cabs",     sa.Integer()),
    ("out_seat_fare",    sa.Numeric(12, 2)),
    ("out_num_seats",    sa.Integer()),
]

_RETURN_SCHEDULE_PRODUCT = [
    ("ret_dep_date",     sa.Date()),
    ("ret_dep_time",     sa.Time()),
    ("ret_arr_date",     sa.Date()),
    ("ret_arr_time",     sa.Time()),
    ("ret_equip_name",   sa.String(64)),
    ("ret_cab_type",     sa.String(50)),
    ("ret_cab_desc",     sa.String(100)),
    ("ret_seat_type",    sa.String(50)),
    ("ret_avail",        sa.String(16)),
]

_RETURN_FARES = [
    ("ret_per_pax_fare", sa.Numeric(12, 2)),
    ("ret_num_pax",      sa.Integer()),
    ("ret_veh_fare",     sa.Numeric(12, 2)),
    ("ret_cab_fare",     sa.Numeric(12, 2)),
    ("ret_num_cabs",     sa.Integer()),
    ("ret_seat_fare",    sa.Numeric(12, 2)),
    ("ret_num_seats",    sa.Integer()),
    ("ret_taxes",        sa.Numeric(12, 2)),
]

_TOTAL_FARES = [
    ("tot_per_pax_fare", sa.Numeric(12, 2)),
    ("tot_num_pax",      sa.Integer()),
    ("tot_veh_fare",     sa.Numeric(12, 2)),
    ("tot_cab_fare",     sa.Numeric(12, 2)),
    ("tot_num_cabs",     sa.Integer()),
    ("tot_seat_fare",    sa.Numeric(12, 2)),
    ("tot_num_seats",    sa.Integer()),
    ("tot_taxes",        sa.Numeric(12, 2)),
]

_DURATION = [
    ("duration",         sa.Integer()),
]

# Flat list in canonical upgrade order — used by upgrade()/downgrade()
_ALL_NEW_COLUMNS = (
    _OUTBOUND_ARRIVAL
    + _OUTBOUND_DESCS_SEATS
    + _RETURN_SCHEDULE_PRODUCT
    + _RETURN_FARES
    + _TOTAL_FARES
    + _DURATION
)
assert len(_ALL_NEW_COLUMNS) == 33, f"expected 33 new columns, got {len(_ALL_NEW_COLUMNS)}"


def upgrade() -> None:
    # All new columns are nullable so existing 52,430 rows are unaffected.
    for name, col_type in _ALL_NEW_COLUMNS:
        op.add_column(
            "cfl_cpi_snapshot",
            sa.Column(name, col_type, nullable=True),
        )


def downgrade() -> None:
    # Reverse order so dependent indexes (if any added later) drop cleanly.
    for name, _col_type in reversed(_ALL_NEW_COLUMNS):
        op.drop_column("cfl_cpi_snapshot", name)
