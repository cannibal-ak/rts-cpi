"""Pure read queries for the alerts evaluator. No writes, no session ownership.

THE ONE RULE THIS MODULE EXISTS TO ENFORCE: every statement that touches the
snapshot pins `cap_date` to a single value with an equality.

That is not style. Measured on the live dev database against the DA partition:

    cap_date IN (<31-date subquery>) : 968 ms, 900k buffers, 137k disk reads,
                                       14 MB external-merge spill, and a full
                                       scan of the tenant partition
    cap_date = '2026-08-12'          : 5.9 ms, 927 buffers, bitmap index scan

A 164x difference. The planner abandons ix_air_snap_<tenant>_grid the moment
cap_date stops being an equality. So the evaluator runs the aggregate twice —
once per capture — and joins the two small result sets in Python (75 x 75 rows).
Two 10 ms queries plus a dict lookup beat one 968 ms query by two orders of
magnitude, and they cannot spill.

`airline.py:113` documents the same invariant for the grid. Same table, same
reason.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.alerts.views import resolve_view

# Departure-horizon buckets, as a SQL expression. Postgres date - date yields a
# 0-based integer number of days.
#
# The bounds are INCLUSIVE of the day named in the label: '00-07' is days 0-7,
# '08-14' is 8-14, '15-30' is 15 onward. Getting this wrong is not cosmetic —
# the bucket string is user-facing (it is a tunable, it is printed verbatim into
# every alert message, and it is baked into scope_key and dedupe_key), so an
# off-by-one silently files a departure 7 days out under "08–14 days out".
# An earlier version used < 7 / < 14, which shifted every bucket a day early.
_BUCKET_SQL = """
        CASE WHEN ref_dep_date - cap_date < 8  THEN '00-07'
             WHEN ref_dep_date - cap_date < 15 THEN '08-14'
             ELSE                                   '15-30' END
"""


@dataclass(frozen=True)
class CompetitorFare:
    """One competitor's cheapest available fare on a route x window."""
    route: str
    origin: str
    destination: str
    window: str
    competitor: str
    fare: float
    currency: str | None
    observations: int


@dataclass(frozen=True)
class OwnFare:
    """Our own cheapest available fare on a route x window.

    Aggregated INDEPENDENTLY of comp_al, which is the crux of the position
    rules. Every snapshot row pairs us against exactly one competitor, so our
    fare is replicated across the competitor fan-out; grouping by route and
    window alone collapses that back to the single true cheapest fare we offer.
    """
    route: str
    origin: str
    destination: str
    window: str
    fare: float
    currency: str | None
    competitor_count: int


@dataclass(frozen=True)
class CaptureAggregate:
    cap_date: date
    competitors: dict[tuple[str, str, str], CompetitorFare]  # (route, window, comp)
    own: dict[tuple[str, str], OwnFare]                      # (route, window)

    @property
    def group_count(self) -> int:
        return len(self.competitors) + len(self.own)


def _f(value) -> float | None:
    """Decimal -> float.

    min(comp_tot_fare) comes back as Decimal, and json.dumps raises on Decimal.
    Every number that can reach a payload goes through here.
    """
    return None if value is None else float(value)


def latest_cap_date(db: Session, tenant_code: str, before: date | None = None) -> date | None:
    """Newest capture date present, optionally strictly before a given date.

    Anchoring on the data rather than the wall clock is not a demo
    accommodation — it is simply correct. Real feeds skip weekends and holidays
    (DA has no 2026-08-08 or 2026-08-09), so `CURRENT_DATE - 1` would produce
    nothing every Monday for every tenant.

    Index-only scan on ix_air_snap_<tenant>_grid; measured 0.064 ms.
    """
    view = resolve_view(tenant_code)
    if before is None:
        sql = f"SELECT max(cap_date) FROM {view}"
        params = {}
    else:
        sql = f"SELECT max(cap_date) FROM {view} WHERE cap_date < :before"
        params = {"before": before}
    return db.execute(text(sql), params).scalar()


def recent_cap_dates(
    db: Session, tenant_code: str, limit: int = 400, before: date | None = None
) -> list[date]:
    """Capture dates, newest first, optionally only those before a given date.

    `before` is not a convenience. Callers that need the captures preceding a
    SPECIFIC capture (the baseline search) must push that bound into SQL rather
    than fetching the newest N overall and filtering in Python: for any target
    older than those N, the filter empties the list and the caller concludes
    there is no baseline when in fact there are hundreds.
    """
    view = resolve_view(tenant_code)
    where = "WHERE cap_date < :before" if before is not None else ""
    params: dict = {"lim": limit}
    if before is not None:
        params["before"] = before
    rows = db.execute(
        text(f"SELECT DISTINCT cap_date FROM {view} {where} ORDER BY cap_date DESC LIMIT :lim"),
        params,
    ).scalars().all()
    return list(rows)


def capture_row_counts(db: Session, tenant_code: str, cap_dates: list[date]) -> dict[date, int]:
    """Row count per capture, for the completeness guard.

    A literal IN list of bound dates is fine here — it is the *subquery* form
    that makes the planner give up on the partial index, and this reads the
    grouped counts rather than the fare columns.
    """
    if not cap_dates:
        return {}
    view = resolve_view(tenant_code)
    rows = db.execute(
        text(f"""
            SELECT cap_date, count(*) AS n
              FROM {view}
             WHERE cap_date = ANY(CAST(:dates AS date[]))
             GROUP BY cap_date
        """),
        {"dates": [d.isoformat() for d in cap_dates]},
    ).all()
    return {r.cap_date: int(r.n) for r in rows}


def capture_row_counts_since(db: Session, tenant_code: str, since: date) -> dict[date, int]:
    """Row count per capture from `since` onward — the backfill's completeness input.

    A single range scan rather than one pinned count per capture: this reads
    only cap_date, so it stays an index-only scan on ix_air_snap_<tenant>_grid.
    Measured at 112 ms over 60 captures with no spill. The cap_date-equality
    invariant applies to the *fare aggregates*, which touch the wide columns;
    counting the index key over a range does not degenerate the same way.
    """
    view = resolve_view(tenant_code)
    rows = db.execute(
        text(f"""
            SELECT cap_date, count(*) AS n
              FROM {view}
             WHERE cap_date >= :since
             GROUP BY cap_date
        """),
        {"since": since},
    ).all()
    return {r.cap_date: int(r.n) for r in rows}


def load_capture(db: Session, tenant_code: str, cap_date: date) -> CaptureAggregate:
    """Both aggregate grains for ONE pinned capture date, in one scan.

    `base` is MATERIALIZED so the two aggregates share a single pass over the
    partition rather than scanning it twice. The two result shapes are unioned
    with a discriminator instead of joined, because they have different
    cardinality — competitors are per route x window x carrier, ours is per
    route x window.

    The `> 0` filters are the no-fare exclusion. A fare of 0.00 in this feed
    means "no fare / not on sale", not a price of zero. Applying it inside the
    aggregate's WHERE (rather than wrapping in NULLIF) is what keeps the partial
    index ix_air_snap_<tenant>_pricerec usable, and correctly makes a group with
    no priced inventory vanish rather than report 0.00.
    """
    view = resolve_view(tenant_code)
    sql = f"""
        WITH base AS MATERIALIZED (
            SELECT ref_org, ref_dst,
                   {_BUCKET_SQL} AS bkt,
                   comp_al, ref_curr, comp_curr, ref_tot_fare, comp_tot_fare
              FROM {view}
             WHERE cap_date = :cap
               AND ref_dep_date >= cap_date
               AND ref_dep_date <  cap_date + 30
        ),
        comp_agg AS (
            SELECT ref_org, ref_dst, bkt, comp_al,
                   min(comp_tot_fare) AS fare,
                   min(comp_curr)     AS curr,
                   count(*)           AS obs
              FROM base
             WHERE comp_tot_fare > 0
             GROUP BY 1, 2, 3, 4
        ),
        da_agg AS (
            SELECT ref_org, ref_dst, bkt,
                   min(ref_tot_fare)       AS fare,
                   min(ref_curr)           AS curr,
                   count(DISTINCT comp_al) AS competitor_count,
                   count(*)                AS obs
              FROM base
             WHERE ref_tot_fare > 0
             GROUP BY 1, 2, 3
        )
        SELECT 'comp' AS kind, ref_org, ref_dst, bkt, comp_al,
               fare, curr, NULL::bigint AS competitor_count, obs
          FROM comp_agg
        UNION ALL
        SELECT 'own', ref_org, ref_dst, bkt, NULL,
               fare, curr, competitor_count, obs
          FROM da_agg
    """
    rows = db.execute(text(sql), {"cap": cap_date}).all()

    competitors: dict[tuple[str, str, str], CompetitorFare] = {}
    own: dict[tuple[str, str], OwnFare] = {}

    for r in rows:
        route = f"{r.ref_org}-{r.ref_dst}"
        if r.kind == "comp":
            competitors[(route, r.bkt, r.comp_al)] = CompetitorFare(
                route=route, origin=r.ref_org, destination=r.ref_dst,
                window=r.bkt, competitor=r.comp_al,
                fare=_f(r.fare), currency=r.curr, observations=int(r.obs),
            )
        else:
            own[(route, r.bkt)] = OwnFare(
                route=route, origin=r.ref_org, destination=r.ref_dst,
                window=r.bkt, fare=_f(r.fare), currency=r.curr,
                competitor_count=int(r.competitor_count or 0),
            )

    return CaptureAggregate(cap_date=cap_date, competitors=competitors, own=own)


def last_emitted_state(
    db: Session, tenant_id: str, scope_key: str, before: date
) -> str | None:
    """The state most recently recorded for a scope, for edge-triggered rules.

    One indexed probe into alert_event via ix_alert_event_scope_observed. There
    are at most ~29 position scopes per capture, so this is cheaper than any
    extra state table would be — and it cannot drift from the events, because it
    *is* the events.
    """
    return db.execute(
        text("""
            SELECT payload ->> 'state'
              FROM alert_event
             WHERE tenant_id = CAST(:tid AS uuid)
               AND scope_key = :scope
               AND observed_at < :before
             ORDER BY observed_at DESC, triggered_at DESC
             LIMIT 1
        """),
        {"tid": tenant_id, "scope": scope_key, "before": before},
    ).scalar()
