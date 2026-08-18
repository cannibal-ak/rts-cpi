"""Add vw_jy_booking_pace — per-flight booking curve + sales-pace signal for JY.

JY asked for a booking curve (bookings accumulated by days-to-departure) with a
pace comparison and an ahead/behind flag feeding pricing priority.

Phase-0 discovery established what the data can actually support:

  * ``velocity_snapshot`` carries ``days_left``, ``current_booking`` and
    ``capacity`` natively, so the curve itself is available — but only over
    **DTD 0-45**, because the JY source file never carries a longer horizon.
  * Year-on-year comparison is impossible: JY history starts 2025-11-11, so
    zero of 4,590 recent departures have a counterpart ~365 days earlier.
  * Forecast comparison is impossible: ``forecasted_seat_factor`` is
    byte-identical to ``actual_seat_factor`` in 98.97% of JY rows.

So the only baseline the data supports is a cohort of recent comparable
departures — same route, same day-of-week — which is what this view builds.
It is deliberately NOT called a forecast.

Three data corrections are applied inside the view:

  1. ``dep_code`` is zero-padding-inconsistent — 98 of 173 JY flight numbers
     appear as both ``0111`` and ``111``, which splits one flight into two
     keys. ``ltrim(dep_code,'0')`` collapses them; this alone moves measured
     DTD completeness from 17.3% to 84.0%.
  2. ``days_left`` disagrees with ``dep_date - report_date`` on 15,658 rows
     (1.9%) and occasionally yields -1, so DTD is recomputed, not trusted.
  3. ``legseg_type='Leg'`` and ``compartment='Y'`` prevent double-counting the
     431,685 Segment rows against the 398,275 Leg rows.

**Why the anchored shape.** ``cap_date`` here is an *as-of anchor*, not the
row's own snapshot date. The app applies Superset RLS as ``cap_date = 'X'`` — a
single date — to every dataset in ``TENANT_CAPDATE_ONLY_TABLES``. A view that
simply exposed ``report_date AS cap_date`` would collapse to one snapshot and
render a single point instead of a curve. Anchoring means selecting one date
returns the whole history behind it. Verified by EXPLAIN: the ``cap_date``
predicate pushes down into both anchor scans, so the notional
145-snapshot x 830k-row cross product is never materialised (~660 ms/query).

Additive only: creates one new view. No existing view, table or column is
touched. Downgrade drops just this view.

Revision: 035
Revises: 034
Create Date: 2026-07-30
"""
from typing import Sequence, Union

from alembic import op


revision: str = "035"
down_revision: Union[str, None] = "034"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Minimum number of cohort observations at a given (route, day-of-week, DTD)
# before we are willing to call a flight ahead or behind pace. Below this the
# baseline is too thin to mean anything and the row reports 'No baseline'.
#
# 5, not 10. A 90-day window holds at most ~13 same-weekday departures on a
# route, and only ~55% of them carry an observation at any given DTD, so the
# natural cohort size here is 5-9 — measured on the 2026-07-15 anchor, 29,024
# of 66,744 rows land in that band and just 13,853 reach 10. A threshold of 10
# is structurally almost unreachable and would blank out the signal on nearly
# half the fleet.
_MIN_COHORT_OBS = 5

# Fraction above/below the cohort mean that counts as ahead/behind rather than
# on pace. +/-10% keeps the middle band wide enough not to flap day to day.
_PACE_BAND = 0.10

# Minimum cohort mean (in bookings) before a percentage comparison is
# meaningful. Far from departure the baseline is often ~1 booking, where a
# flight sitting at 0 computes as -100% and would be flagged 'Behind' despite
# the gap being a single seat. Measured on the 2026-07-15 anchor: a quarter of
# all 'Behind' flags at DTD 40-45 came from baselines below this line. Rows
# under it report 'Too early' instead of a direction.
_MIN_COHORT_BASELINE = 3.0

_CREATE_VIEW = f"""
CREATE VIEW vw_jy_booking_pace AS
WITH dedup AS (
    -- One row per (snapshot, departure, DTD). The aggregate collapses the rare
    -- duplicate grain rows (differing dep_time / leg_seg_order) that would
    -- otherwise double-count a departure at a single DTD point.
    SELECT
        report_date,
        dep_date,
        ltrim(dep_code, '0')                AS flight_no,
        city_pair,
        origin,
        destination,
        eqp,
        (dep_date - report_date)            AS dtd,
        max(current_booking)                AS current_booking,
        max(capacity)                       AS capacity,
        max(actual_seat_factor)             AS actual_seat_factor
    FROM velocity_snapshot
    WHERE airline_code = 'JY'
      AND legseg_type  = 'Leg'
      AND compartment  = 'Y'
      AND (dep_date - report_date) BETWEEN 0 AND 45
    GROUP BY 1, 2, 3, 4, 5, 6, 7, 8
),
anchors AS (
    SELECT DISTINCT report_date AS cap_date
    FROM velocity_snapshot
    WHERE airline_code = 'JY'
),
live AS (
    -- The curve as it stood on the anchor date: every observation taken up to
    -- the anchor, for departures still in the future at that point.
    SELECT a.cap_date, d.*
    FROM anchors a
    JOIN dedup   d
      ON d.report_date <= a.cap_date
     AND d.dep_date    >  a.cap_date
),
cohort AS (
    -- Baseline: mean bookings at the same DTD across same-route,
    -- same-day-of-week departures that had ALREADY flown as of the anchor.
    -- Restricting to dep_date < cap_date is what keeps the baseline honest —
    -- it can never borrow information from the future.
    SELECT
        a.cap_date,
        d.city_pair,
        EXTRACT(dow FROM d.dep_date)::int   AS dow,
        d.dtd,
        avg(d.current_booking)              AS coh_avg_booking,
        count(*)                            AS coh_obs
    FROM anchors a
    JOIN dedup   d
      ON d.dep_date <  a.cap_date
     AND d.dep_date >= a.cap_date - 90
    GROUP BY 1, 2, 3, 4
)
SELECT
    l.cap_date,
    l.report_date                                           AS snapshot_date,
    -- True on the single observation taken ON the anchor date, i.e. the most
    -- recent reading for that flight as of cap_date. Filtering a chart to this
    -- gives one exact row per flight (its current pace) instead of forcing an
    -- aggregate across the whole curve. Dense daily snapshots make this
    -- equivalent to 'smallest DTD' without paying for a window function.
    (l.report_date = l.cap_date)                            AS is_latest_obs,
    l.dep_date,
    l.flight_no,
    l.city_pair,
    LEFT(l.city_pair, 3) || ' -> ' || RIGHT(l.city_pair, 3) AS route,
    l.origin,
    l.destination,
    l.eqp,
    l.dtd,
    l.current_booking,
    l.capacity,
    l.actual_seat_factor,
    CASE WHEN l.capacity > 0
         THEN round(l.current_booking::numeric / l.capacity * 100, 1)
    END                                                     AS booking_pct,
    round(c.coh_avg_booking, 2)                             AS cohort_avg_booking,
    c.coh_obs                                               AS cohort_observations,
    round(l.current_booking - c.coh_avg_booking, 2)         AS pace_delta,
    CASE
        WHEN c.coh_avg_booking IS NULL
          OR c.coh_obs < {_MIN_COHORT_OBS}
          OR c.coh_avg_booking < {_MIN_COHORT_BASELINE} THEN NULL
        ELSE round(
            (l.current_booking - c.coh_avg_booking) / c.coh_avg_booking * 100, 1)
    END                                                     AS pace_delta_pct,
    CASE
        WHEN c.coh_avg_booking IS NULL
          OR c.coh_obs < {_MIN_COHORT_OBS} THEN 'No baseline'
        WHEN c.coh_avg_booking < {_MIN_COHORT_BASELINE} THEN 'Too early'
        WHEN (l.current_booking - c.coh_avg_booking)
             / c.coh_avg_booking >  {_PACE_BAND} THEN 'Ahead'
        WHEN (l.current_booking - c.coh_avg_booking)
             / c.coh_avg_booking < -{_PACE_BAND} THEN 'Behind'
        ELSE 'On pace'
    END                                                     AS pace_band
FROM live l
LEFT JOIN cohort c
       ON c.cap_date  = l.cap_date
      AND c.city_pair = l.city_pair
      AND c.dow       = EXTRACT(dow FROM l.dep_date)::int
      AND c.dtd       = l.dtd
"""


def upgrade() -> None:
    op.execute(_CREATE_VIEW)


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS vw_jy_booking_pace")
