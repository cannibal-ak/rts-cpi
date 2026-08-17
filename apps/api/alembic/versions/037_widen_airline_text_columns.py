"""Widen four families of ``airline_cpi_snapshot`` text columns that truncate real data.

The WinAir (WM) feed exposed four columns whose declared widths are narrower
than the values the source files actually carry. The source is correct; the
ingest INSERT clips it. Measured against WM's live rows on 2026-08-11:

    column family      source value                              stored as
    ─────────────────  ────────────────────────────────────────  ──────────
    *_dep/arr_time     "18:25"                                   "18:2"
    *_bkg_class        "Saver"                                   "Save"
    *_flt_num          "WM-853/WM-2835"  (connections)           "WM-853/WM-"
    *_equip_code       "ATR42-500/ATR42-500/ATR42-500/ATR42-500" clipped at 32

The time columns are the sharpest case: JY and PW send ``HHMM`` (4 chars) so
varchar(4) fit, but WM sends ``HH:MM`` (5 chars) and silently lost the units
digit of the minute — "18:2" is ambiguous between 18:20 and 18:29, and no
flight duration can be derived from it. Connection itineraries concatenate
per-leg values with "/", so flight number and equipment overflow on any
multi-leg fare.

This widens all 20 affected columns (4 families x ref/comp x outbound/return).
Widening a varchar is a catalogue-only change in PostgreSQL — no table rewrite
— so this is fast even at ~9.4M rows. The matching ingest fix lives in
``app/ingestion/service.py::_insert_airline_rows_legacy``; the ORM lengths in
``app/models/airline.py`` are updated to agree.

Views pin the type of every column they project, so PostgreSQL refuses to
ALTER a column while a dependent view exists. The four tenant views are
therefore dropped and recreated. They are recreated from their own
``pg_get_viewdef()`` output rather than from a definition retyped here, so
they come back column-for-column identical — this migration widens columns and
changes nothing else. The dependent views are DISCOVERED from ``pg_depend``
rather than hardcoded, because views on this table have been created
out-of-band before (``vw_airline_cpi_wm_snapshot`` in 034) and a stale list
would fail the ALTER.

Grants are replayed as SELECT/INSERT/UPDATE/DELETE to ``cpi_app``, matching the
``arwd`` ACL the four views carry today. View ownership stays with ``cpi``
(alembic's connection role), which matters: these views run with the owner's
rights, and the base table's row-level security is evaluated against that
owner.

``downgrade`` narrows back the same way. It will fail if any stored value is
by then longer than the original width — which is the point: the old widths
cannot hold the data this migration exists to preserve. Clear or truncate the
offending rows first if a downgrade is genuinely required.

Revision: 037
Revises: 036
Create Date: 2026-08-11
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "037"
down_revision: Union[str, None] = "036"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "airline_cpi_snapshot"

# (column, widened length, original length). Ordered by family for review.
_COLUMNS: list[tuple[str, int, int]] = [
    # Times — source is "HH:MM" (5) for WM, "HHMM" (4) for JY/PW. 8 leaves
    # room for a seconds-bearing or zone-suffixed variant without another
    # migration.
    ("ref_dep_time", 8, 4),
    ("ref_arr_time", 8, 4),
    ("ref_ret_dep_time", 8, 4),
    ("ref_ret_arr_time", 8, 4),
    ("comp_dep_time", 8, 4),
    ("comp_arr_time", 8, 4),
    ("comp_ret_dep_time", 8, 4),
    ("comp_ret_arr_time", 8, 4),
    # Booking class / brand name — "Saver", "Value", "Flex Plus".
    ("ref_bkg_class", 16, 4),
    ("ref_ret_bkg_class", 16, 4),
    ("comp_bkg_class", 16, 4),
    ("comp_ret_bkg_class", 16, 4),
    # Flight number — single leg is "WM-857"; connections concatenate
    # per-leg numbers with "/". 64 holds a 6-leg itinerary.
    ("ref_flt_num", 64, 10),
    ("ref_ret_flt_num", 64, 10),
    ("comp_flt_num", 64, 10),
    ("comp_ret_flt_num", 64, 10),
    # Equipment — same per-leg concatenation, longer tokens ("ATR42-500").
    ("ref_equip_code", 128, 32),
    ("ref_ret_equip_code", 128, 32),
    ("comp_equip_code", 128, 32),
    ("comp_ret_equip_code", 128, 32),
]

# Matches the `arwd` ACL the four tenant views carry today. Replayed rather
# than reduced to SELECT, so the recreated views keep the privileges the
# application role already had.
_VIEW_GRANTS = "SELECT, INSERT, UPDATE, DELETE"


def _dependent_views(conn) -> list[str]:
    """Views that project columns of TABLE, so must be dropped before ALTER.

    Discovered rather than hardcoded — a view added outside alembic (as
    vw_airline_cpi_wm_snapshot once was) still has to be handled, and a
    stale hardcoded list would surface as a confusing ALTER failure.
    """
    return list(
        conn.execute(
            sa.text(
                """
                SELECT DISTINCT dependent.relname
                FROM   pg_depend d
                JOIN   pg_rewrite r         ON r.oid = d.objid
                JOIN   pg_class dependent   ON dependent.oid = r.ev_class
                JOIN   pg_class src         ON src.oid = d.refobjid
                WHERE  src.relname = :table
                  AND  dependent.relkind = 'v'
                ORDER  BY 1
                """
            ),
            {"table": TABLE},
        ).scalars()
    )


def _resize(conn, columns: list[tuple[str, int]]) -> None:
    """Drop dependent views, resize columns, recreate the views verbatim."""
    views = _dependent_views(conn)

    # Capture each definition BEFORE dropping anything — once a view is gone
    # its definition is unrecoverable, and a failure midway would leave the
    # tenant views missing entirely.
    definitions: list[tuple[str, str]] = []
    for view in views:
        # CAST(... AS regclass), not `:v::regclass` — SQLAlchemy's text()
        # parser reads the leading colon of the `::` cast as the start of
        # another bind parameter and emits invalid SQL.
        body = conn.execute(
            sa.text("SELECT pg_get_viewdef(CAST(:v AS regclass), true)"), {"v": view}
        ).scalar()
        if not body:
            raise RuntimeError(f"could not read definition of view {view}")
        definitions.append((view, body))

    for view, _ in definitions:
        conn.execute(sa.text(f"DROP VIEW {view}"))

    for column, length in columns:
        conn.execute(
            sa.text(
                f"ALTER TABLE {TABLE} ALTER COLUMN {column} "
                f"TYPE VARCHAR({length})"
            )
        )

    for view, body in definitions:
        conn.execute(sa.text(f"CREATE VIEW {view} AS {body}"))
        conn.execute(sa.text(f"GRANT {_VIEW_GRANTS} ON {view} TO cpi_app"))


def upgrade() -> None:
    conn = op.get_bind()
    _resize(conn, [(c, new) for c, new, _ in _COLUMNS])


def downgrade() -> None:
    conn = op.get_bind()
    _resize(conn, [(c, old) for c, _, old in _COLUMNS])
