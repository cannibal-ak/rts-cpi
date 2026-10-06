"""WM / PW partial filter-value indexes on airline_cpi_snapshot.

The fare-history endpoint (/airline/price-points/history) and the dashboard
filter-value queries reach airline_cpi_snapshot through the per-tenant views,
filtered on ref_org / ref_dst / departure date / cap_date. DA, 5L and JY each
have a partial ix_air_snap_<t>_filtervals index for exactly that; WM and PW
never got one, so their history query scans (prod EXPLAIN cost about 395k for
WM and 1.09M for PW, against 17-6,110 for the indexed tenants). Definitions
mirror the live DA index column for column with only the tenant literal
swapped; WM is DA's twin, and PW's filter bar was brought to the same set.

Built CONCURRENTLY so ingestion keeps writing while the PW index (about 5.5M
rows on prod) builds. That cannot run inside a transaction, hence the
autocommit block. A CONCURRENTLY build that fails part way leaves an INVALID
index behind, which IF NOT EXISTS would then skip for good, so an invalid
leftover is dropped and rebuilt.

On prod, run this BEFORE swapping the api (compose run ... alembic upgrade
head): the api entrypoint runs `alembic upgrade head` before gunicorn starts,
and a multi-minute build there would hold the api down.

Pure SQL, no app imports (040's rule).

Revision ID: 049
Revises: 048
Create Date: 2026-10-06
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "049"
down_revision: Union[str, None] = "048"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# index name -> tenant_code of the partition it covers
_INDEXES = {
    "ix_air_snap_wm_filtervals": "WM",
    "ix_air_snap_pw_filtervals": "PW",
}

# Same columns, same order, as ix_air_snap_da_filtervals / _5l_filtervals.
_COLUMNS = "ref_org, ref_dst, ref_dep_date, cap_date, ref_flt_num, ref_stops, comp_stops, comp_al"


def upgrade() -> None:
    with op.get_context().autocommit_block():
        conn = op.get_bind()
        for name, tenant in _INDEXES.items():
            valid = conn.execute(
                sa.text(
                    "SELECT i.indisvalid FROM pg_index i "
                    "JOIN pg_class c ON c.oid = i.indexrelid WHERE c.relname = :name"
                ),
                {"name": name},
            ).scalar()
            if valid is False:
                conn.execute(sa.text(f"DROP INDEX CONCURRENTLY IF EXISTS {name}"))
            conn.execute(sa.text(
                f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {name} "
                f"ON airline_cpi_snapshot ({_COLUMNS}) "
                f"WHERE tenant_code::text = '{tenant}'"
            ))


def downgrade() -> None:
    with op.get_context().autocommit_block():
        conn = op.get_bind()
        for name in _INDEXES:
            conn.execute(sa.text(f"DROP INDEX CONCURRENTLY IF EXISTS {name}"))
