"""Airline CPI endpoints — tenant-aware DB queries with filter hardening."""

from datetime import datetime
from fastapi import APIRouter, Query, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select, func, distinct, text
import io
from openpyxl import Workbook
from fastapi.responses import StreamingResponse

from app.core.cache import cached
from app.core.deps import get_tenant_db, sanitize_filter, sanitize_date, get_user_roles, get_user_identity, is_platform_admin
from app.models.airline import AirlineCpiSnapshot
from app.schemas.common import PaginatedResponse, PageInfo
from app.schemas.airline import (
    AirlineSnapshotOut,
    NoFareDayOut,
    PriceHistoryPointOut,
    PriceHistoryResponse,
    PricePointOut,
    PricePointsResponse,
)
from app.schemas.velocity import VelocitySnapshotOut
from app.schemas.filters import FilterMetadataOut

router = APIRouter(
    prefix="/api/v1/airline",
    tags=["airline"],
)

# Raised from 100 so a client can pull a page in one request instead of ten.
# The default stays at 20 — callers that don't ask are unaffected.
MAX_PAGE_SIZE = 1000

# Tenant code → the view that tenant is allowed to read. This whitelist is
# the injection guard: view names are interpolated into raw SQL, so they may
# only ever come from here. The older handlers each declare an identical map
# inline, which shadows this one harmlessly; they are left as they are.
#
# ONBOARDING A TENANT TOUCHES ALL OF THEM. Adding a code here alone is not
# enough — the inline copies in list_snapshots, get_filter_metadata and
# export_snapshots shadow this one, and get_filter_metadata additionally
# carries two hardcoded all-tenant lists. Miss one and that endpoint 403s for
# the new tenant while the others work, which reads as a permissions bug
# rather than a missing map entry. Grep for the previous tenant's code and
# expect a hit in every one of them.
AIRLINE_VIEW_MAP = {
    "JY": "vw_airline_cpi_jy_snapshot",
    "PW": "vw_airline_cpi_pw_snapshot",
    "ALT": "vw_airline_cpi_alt_snapshot",
    "WM": "vw_airline_cpi_wm_snapshot",
    "DA": "vw_airline_cpi_da_snapshot",
    "5L": "vw_airline_cpi_5l_snapshot",
}

# 60s is enough: with ix_air_snap_<tenant>_grid in place, `max(cap_date)` is an
# index-only scan reading ~4 pages (0.17ms on production), so there is nothing
# to amortise. Keeping the window short means a freshly ingested date shows up
# in the grid within a minute.
_LATEST_DATE_TTL = 60.0
_COUNT_TTL = 60.0
_METADATA_TTL = 300.0


def _latest_date(db: Session, view_name: str, column: str) -> str | None:
    """Newest value of `column` in a tenant view, memoised briefly.

    Used to pin a date when the caller supplies none. `column` is never
    user-supplied — every call site passes a literal.
    """
    def _produce() -> str | None:
        val = db.execute(text(f"SELECT max({column}) FROM {view_name}")).scalar()
        return val.isoformat() if val else None

    return cached(("latest_date", view_name, column), _LATEST_DATE_TTL, _produce)


def _cached_count(db: Session, view_name: str, where_str: str, filter_params: dict) -> int:
    """count(*) memoised on the exact filter set.

    A grid that pages through a result set re-sends an identical count with
    every page; a short TTL collapses those into one. `filter_params` must
    exclude limit/offset or the key never repeats and the cache is dead weight.
    """
    key = ("count", view_name, where_str, tuple(sorted(filter_params.items())))

    def _produce() -> int:
        return db.execute(text(f"SELECT count(*) FROM {view_name} {where_str}"),
                          filter_params).scalar() or 0

    return cached(key, _COUNT_TTL, _produce)


@router.get("/snapshots", response_model=PaginatedResponse[AirlineSnapshotOut])
def list_snapshots(
    db: Session = Depends(get_tenant_db),
    user_roles: list[str] = Depends(get_user_roles),
    user_identity: str = Depends(get_user_identity),
    tenant: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=MAX_PAGE_SIZE),
    file_date: str | None = None,
    airline: str | None = None,
    with_total: bool = Query(True, description="Set false to skip count(*) on repeat pages."),
):
    # Enforce tenant scoping — non-platform users are locked to their own airline
    AIRLINE_VIEW_MAP = {"JY": "vw_airline_cpi_jy_snapshot", "PW": "vw_airline_cpi_pw_snapshot", "ALT": "vw_airline_cpi_alt_snapshot", "WM": "vw_airline_cpi_wm_snapshot", "DA": "vw_airline_cpi_da_snapshot", "5L": "vw_airline_cpi_5l_snapshot"}
    if is_platform_admin(user_identity, user_roles):
        effective_tenant = tenant or "JY"  # platform admin can pick, defaults to JY
    else:
        if user_identity not in AIRLINE_VIEW_MAP:
            raise HTTPException(status_code=403, detail="Not Authorized")
        effective_tenant = user_identity  # locked to own tenant, ignore ?tenant param

    if effective_tenant not in AIRLINE_VIEW_MAP:
        raise HTTPException(status_code=400, detail="Invalid tenant for airline module")
    view_name = AIRLINE_VIEW_MAP[effective_tenant]

    # Sanitize filters
    file_date = sanitize_date(file_date, "file_date")
    airline = sanitize_filter(airline, "airline")

    # ── Never emit a query without a cap_date equality. ───────────────────
    # Without this, an absent file_date produced an empty WHERE and a full
    # unfiltered scan of the whole snapshot table (~9.4M rows, ~30s per
    # request). We PIN the newest cap_date rather than returning 400: the grid
    # legitimately calls this with no filters on first paint, and a 400 there
    # is a blank screen for every user. Pinning degrades gracefully.
    if not file_date:
        file_date = _latest_date(db, view_name, "cap_date")
        if file_date is None:
            # Genuinely empty tenant — say so without scanning to find out.
            return PaginatedResponse(
                items=[],
                page_info=PageInfo(total=0, page=page, page_size=page_size,
                                   has_next=False, applied_file_date=None),
            )

    # Build Raw SQL query for performance and to use specifically crafted views
    where_clauses = ["cap_date = :file_date"]
    filter_params: dict = {"file_date": file_date}

    if airline:
        where_clauses.append("ref_al = :airline")
        filter_params["airline"] = airline

    where_str = f"WHERE {' AND '.join(where_clauses)}"
    params = {**filter_params, "limit": page_size, "offset": (page - 1) * page_size}

    # ── Ordering needs a unique tiebreaker. ───────────────────────────────
    # An entire capture batch shares one (cap_date, cap_time), so sorting on
    # those alone is not a total order: under LIMIT/OFFSET, Postgres may return
    # tied rows in a different sequence per page, silently duplicating some
    # rows across pages and dropping others. Appending `id` makes the order
    # deterministic. This is a correctness fix, not just a performance one.
    #
    # The leading boolean floats complete comparisons to the front: a 0/NULL
    # fare means sold out / not on sale, never a real price, so only rows
    # with BOTH fares carry a meaningful Delta/Δ%. The UI renders those two
    # columns on the same both-sides test — keep the conditions in lockstep.
    order_by = (
        "ORDER BY (COALESCE(ref_tot_fare, 0) > 0 AND COALESCE(comp_tot_fare, 0) > 0) DESC, "
        "cap_date DESC, cap_time DESC, id DESC"
    )

    data_sql = text(f"SELECT * FROM {view_name} {where_str} {order_by} LIMIT :limit OFFSET :offset")
    rows = db.execute(data_sql, params).mappings().all()

    # count(*) is memoised on the filter set — a client paging through a result
    # set no longer pays for a fresh full count on every page.
    if with_total:
        total = _cached_count(db, view_name, where_str, filter_params)
    else:
        total = 0

    return PaginatedResponse(
        items=rows,
        page_info=PageInfo(total=total, page=page, page_size=page_size,
                           has_next=((page - 1) * page_size + page_size) < total,
                           applied_file_date=file_date,
                           total_is_cached=not with_total),
    )


@router.get("/filter-metadata", response_model=list[FilterMetadataOut])
def get_filter_metadata(
    db: Session = Depends(get_tenant_db),
    user_roles: list[str] = Depends(get_user_roles),
    user_identity: str = Depends(get_user_identity),
    tenant: str | None = Query(None),
):
    # Enforce tenant scoping — non-platform users locked to own airline
    AIRLINE_TENANTS = {"JY", "PW", "ALT", "WM", "DA", "5L"}
    if is_platform_admin(user_identity, user_roles):
        effective_tenant = tenant  # platform admin can pick or see all
    else:
        if user_identity not in AIRLINE_TENANTS:
            raise HTTPException(status_code=403, detail="Not Authorized")
        effective_tenant = user_identity  # locked to own tenant

    # Both sweeps below are full DISTINCT scans of the tenant view(s) and ran
    # uncached on every grid mount — the one grid-adjacent read the 3034363
    # perf pass missed (velocity's metadata got a 300s memo). Same helper,
    # same TTL, keyed on the resolved tenant so a platform admin's all-tenant
    # response never shares an entry with a tenant user's.
    def _produce() -> list[dict]:
        result = []

        # Date list — sourced from the SAME tenant view(s) the grid queries, keyed
        # on cap_date (the column the snapshots filter matches). Previously this
        # merged filename-parsed dates + DISTINCT report_date; a date could be
        # offered whose rows carry a different cap_date, giving an empty grid on
        # select. Enumerating cap_date guarantees every option returns rows.
        AIRLINE_VIEW_MAP = {"JY": "vw_airline_cpi_jy_snapshot", "PW": "vw_airline_cpi_pw_snapshot", "ALT": "vw_airline_cpi_alt_snapshot", "WM": "vw_airline_cpi_wm_snapshot", "DA": "vw_airline_cpi_da_snapshot", "5L": "vw_airline_cpi_5l_snapshot"}
        date_tenants = [effective_tenant] if effective_tenant else ["JY", "PW", "ALT", "WM", "DA", "5L"]
        date_set = set()
        for dt in date_tenants:
            dv = AIRLINE_VIEW_MAP.get(dt)
            if not dv:
                continue
            date_set.update(db.execute(text(
                f"SELECT DISTINCT cap_date FROM {dv} WHERE cap_date IS NOT NULL"
            )).scalars().all())
        all_dates = sorted((d.isoformat() for d in date_set), reverse=True)
        if not all_dates:
            all_dates = ["No file dates available"]

        result.append({"field": "file_date", "label": "File Date", "values": all_dates})

        # Airline filter — sourced from the actual ref_al values of the same
        # tenant view the snapshots query uses. The tenant_code can differ from
        # the airline code carried in the data (e.g. ALT → ref_al 'SKY'), so we
        # must read DISTINCT ref_al rather than echo the tenant code.
        view_tenants = [effective_tenant] if effective_tenant else ["JY", "PW", "ALT", "WM", "DA", "5L"]
        vals = []
        for vt in view_tenants:
            view_name = AIRLINE_VIEW_MAP.get(vt)
            if not view_name:
                continue
            vals.extend(db.execute(text(
                f"SELECT DISTINCT ref_al FROM {view_name} "
                "WHERE ref_al IS NOT NULL AND ref_al <> '' ORDER BY ref_al"
            )).scalars().all())

        result.append({"field": "airline", "label": "Airline", "values": vals})

        return result

    return cached(("airline_filter_meta", effective_tenant or "ALL"), _METADATA_TTL, _produce)


@router.get("/export")
def export_snapshots(
    db: Session = Depends(get_tenant_db),
    user_roles: list[str] = Depends(get_user_roles),
    user_identity: str = Depends(get_user_identity),
    tenant: str | None = Query(None),
    file_date: str | None = None,
    airline: str | None = None,
):
    # Enforce tenant scoping — non-platform users locked to own airline
    AIRLINE_VIEW_MAP = {"JY": "vw_airline_cpi_jy_snapshot", "PW": "vw_airline_cpi_pw_snapshot", "ALT": "vw_airline_cpi_alt_snapshot", "WM": "vw_airline_cpi_wm_snapshot", "DA": "vw_airline_cpi_da_snapshot", "5L": "vw_airline_cpi_5l_snapshot"}
    if is_platform_admin(user_identity, user_roles):
        effective_tenant = tenant or "JY"
    else:
        if user_identity not in AIRLINE_VIEW_MAP:
            raise HTTPException(status_code=403, detail="Not Authorized")
        effective_tenant = user_identity

    if effective_tenant not in AIRLINE_VIEW_MAP:
        raise HTTPException(status_code=400, detail="Invalid tenant for airline module")
    view_name = AIRLINE_VIEW_MAP[effective_tenant]

    # Sanitize filters
    file_date = sanitize_date(file_date, "file_date")
    airline = sanitize_filter(airline, "airline")

    # Same rule as the grid: never scan the whole table. Pin the newest
    # cap_date when the caller omits one.
    if not file_date:
        file_date = _latest_date(db, view_name, "cap_date")

    where_clauses = []
    params = {}

    if file_date:
        where_clauses.append("cap_date = :file_date")
        params["file_date"] = file_date
    if airline:
        where_clauses.append("ref_al = :airline")
        params["airline"] = airline

    where_str = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

    # Same ordering as the grid (complete comparisons first) so the exported
    # sheet reads in the order the user sees on screen.
    data_sql = text(
        f"SELECT * FROM {view_name} {where_str} "
        "ORDER BY (COALESCE(ref_tot_fare, 0) > 0 AND COALESCE(comp_tot_fare, 0) > 0) DESC, "
        "cap_date DESC, cap_time DESC, id DESC LIMIT 5000"
    )
    rows = db.execute(data_sql, params).mappings().all()

    wb = Workbook()
    ws = wb.active
    ws.title = "Airline CPI Export"

    # Headers
    headers = [
        "Capture Date", "Capture Time", "Trip Type",
        "Ref Airline", "Ref Flt Num", "Ref Org", "Ref Dst", "Ref Dep Date", "Ref Cabin", "Ref Fare",
        "Comp Airline", "Comp Flt Num", "Comp Org", "Comp Dst", "Comp Dep Date", "Comp Cabin", "Comp Fare",
    ]
    ws.append(headers)

    # Data
    for r in rows:
        ws.append([
            r.cap_date.isoformat(), r.cap_time.isoformat(), r.trip_type,
            r.ref_al, r.ref_flt_num, r.ref_org, r.ref_dst, r.ref_dep_date.isoformat(), r.ref_cab_code, float(r.ref_tot_fare),
            r.comp_al, r.comp_flt_num, r.comp_org, r.comp_dst, r.comp_dep_date.isoformat(), r.comp_cab_code, float(r.comp_tot_fare),
        ])

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)

    filename = f"airline_cpi_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


# ── Price points — unaggregated fares for charting ──────────────────
#
# /snapshots returns stored rows: a reference fare and a competitor fare
# paired on one row. A chart needs the opposite shape — every airline's
# fare as its own point — so these endpoints unpivot the two halves into a
# single stream of observations.
#
# Two things this deliberately does NOT do:
#
#   * It does not page. The grid pages and the frontend walks every page,
#     which is what produced the July 2026 request storm; a chart wants one
#     bounded request instead. Requiring origin+destination is what makes
#     that safe — one route on one capture date is a few hundred points.
#   * It does not reuse Superset's wm_all_airlines_fares dataset, which
#     performs a similar UNION. That dataset backs the live WM dashboard,
#     omits arrival time / cabin / booking class / seats / equipment /
#     currency, and does not dedupe.
#
# Dedup matters: a reference flight is stored once per competitor it was
# compared against, so the same WinAir fare appears four times on a
# four-competitor route. Every ref_* column is identical across those
# copies, so SELECT DISTINCT over the projection collapses them exactly.

# One route on one capture date runs to a few hundred points; 20k is a
# backstop against a pathological route, not an expected ceiling. Note the
# cap is applied PER MARKET with a floor of 1000 (see list_price_points), so
# a 20-route request can return up to ~20k rows rather than being held to
# this number overall — the trade for never silently dropping a whole route.
MAX_PRICE_POINTS = 20000

# A chart cannot say anything useful about more markets than this, and it
# bounds the row-constructor IN list and the worst-case response size.
MAX_ROUTES_PER_REQUEST = 20

# Bounds the history scan for tenants whose snapshot table is large. WM (the
# only caller today) holds ~170k rows so the window is academic there, but an
# unbounded scan on JY's millions would not be.
_HISTORY_WINDOW_DAYS = 180


def _resolve_airline_view(
    user_identity: str, user_roles: list[str], tenant: str | None
) -> tuple[str, str]:
    """Resolve (tenant_code, view_name) under the same rules as /snapshots.

    Platform admins may name a tenant; everyone else is pinned to their own
    and the ?tenant= param is ignored. The whitelist is what keeps the view
    name safe to interpolate. Only the new price-point endpoints use this —
    the older handlers inline the same map and are left alone.
    """
    if is_platform_admin(user_identity, user_roles):
        effective_tenant = tenant or "JY"
    else:
        if user_identity not in AIRLINE_VIEW_MAP:
            raise HTTPException(status_code=403, detail="Not Authorized")
        effective_tenant = user_identity

    if effective_tenant not in AIRLINE_VIEW_MAP:
        raise HTTPException(status_code=400, detail="Invalid tenant for airline module")
    return effective_tenant, AIRLINE_VIEW_MAP[effective_tenant]


def _parse_clock(value: str | None) -> int | None:
    """Minutes past midnight from a feed clock string, or None.

    Accepts both shapes in the wild: "HH:MM" (WinAir) and "HHMM" (JY/PW).
    Anything else — blank, partial, non-numeric — is None rather than a
    guess, because a wrong departure time is worse than a missing one.
    """
    if not value:
        return None
    raw = value.strip().replace(":", "")
    if len(raw) != 4 or not raw.isdigit():
        return None
    hours, minutes = int(raw[:2]), int(raw[2:])
    if hours > 23 or minutes > 59:
        return None
    return hours * 60 + minutes


def _duration_minutes(dep: str | None, arr: str | None) -> int | None:
    """Elapsed minutes between two feed clock strings.

    No feed carries an elapsed-time column, so this is the only source of
    flight duration. An arrival earlier than the departure is read as
    crossing midnight and wraps by a day — which is also how a red-eye
    legitimately looks. Connections give total journey time, since arr_time
    is the final leg's arrival.
    """
    start, end = _parse_clock(dep), _parse_clock(arr)
    if start is None or end is None:
        return None
    return (end - start) if end >= start else (end + 1440 - start)


# Both halves of the union project the same columns in the same order.
# `{side}` is 'ref' or 'comp'; origin/destination fall back to the reference
# market when a competitor row carries no O&D of its own.
_PRICE_POINT_SIDE_SQL = """
    SELECT DISTINCT
        ref_org || '-' || ref_dst                        AS market,
        {side}_al                                        AS airline,
        '{role}'                                         AS role,
        NULLIF({side}_flt_num, '')                       AS flt_num,
        COALESCE(NULLIF({side}_org, ''), ref_org)        AS origin,
        COALESCE(NULLIF({side}_dst, ''), ref_dst)        AS destination,
        {side}_dep_date                                  AS dep_date,
        NULLIF({side}_dep_time, '')                      AS dep_time,
        NULLIF({side}_arr_time, '')                      AS arr_time,
        {side}_stops                                     AS stops,
        NULLIF({side}_via, '')                           AS via,
        NULLIF({side}_cab_code, '')                      AS cab_code,
        NULLIF({side}_cab_name, '')                      AS cab_name,
        NULLIF({side}_bkg_class, '')                     AS bkg_class,
        NULLIF({side}_ff_code, '')                       AS ff_code,
        NULLIF({side}_equip_code, '')                    AS equip_code,
        {side}_seats                                     AS seats,
        NULLIF({side}_curr, '')                          AS curr,
        {side}_base_fare                                 AS base_fare,
        {side}_tax                                       AS tax,
        {side}_yq                                        AS yq,
        {side}_yr                                        AS yr,
        {side}_tot_fare                                  AS tot_fare,
        NULLIF(trip_type, '')                            AS trip_type,
        cap_date,
        cap_time
    FROM {view}
    WHERE {where}
"""


# Why a fare cell holds 0. Ingestion coerces two distinct source cases to
# zero (the fare columns are NOT NULL): a sold-out flight arrives with its
# fares written as 0, while a not-yet-on-sale day arrives blank. The cases
# stay separable after the coercion — a sold-out reference row still carries
# its stops count, a sold-out competitor row still carries a flight number,
# and blank-block rows carry neither.
_AVAILABILITY_STATUS_CASE = {
    "ref": (
        "CASE WHEN ref_tot_fare > 0 THEN 'on_sale' "
        "WHEN ref_stops IS NULL THEN 'not_on_sale' ELSE 'sold_out' END"
    ),
    "comp": (
        "CASE WHEN comp_tot_fare > 0 THEN 'on_sale' "
        "WHEN COALESCE(comp_flt_num, '') <> '' THEN 'sold_out' ELSE 'not_on_sale' END"
    ),
}

# Availability is a whole-day statement, so only the grouping grain is
# projected. `market` must be built exactly as _PRICE_POINT_SIDE_SQL builds
# it — markers join to their fare line on that string.
_AVAILABILITY_SIDE_SQL = """
    SELECT
        ref_org || '-' || ref_dst                        AS market,
        {side}_al                                        AS airline,
        {side}_dep_date                                  AS dep_date,
        {status_case}                                    AS status
    FROM {view}
    WHERE {where}
"""


def _parse_routes(routes: str | None, origin: str | None, destination: str | None) -> list[tuple[str, str]]:
    """Requested markets as (origin, destination) pairs.

    Two accepted forms: `routes=EIS-SXM,ANU-BGI` for the multi-select case,
    or a single `origin`/`destination` pair, which keeps one-route calls
    readable from curl and from the history endpoint. Duplicates collapse and
    order is preserved, so the caller's first pick stays first in the legend.
    """
    pairs: list[tuple[str, str]] = []

    for part in (routes or "").split(","):
        part = part.strip()
        if not part:
            continue
        cleaned = sanitize_filter(part, "routes")
        # "ORG-DST". Station codes are 3-4 chars, so anything else is a
        # malformed pair rather than something to be guessed at.
        halves = (cleaned or "").split("-")
        if len(halves) != 2 or not all(2 <= len(h.strip()) <= 4 for h in halves):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid route {part!r}; expected ORG-DST, e.g. EIS-SXM",
            )
        pairs.append((halves[0].strip().upper(), halves[1].strip().upper()))

    if not pairs:
        org = sanitize_filter(origin, "origin")
        dst = sanitize_filter(destination, "destination")
        if org and dst:
            pairs.append((org.upper(), dst.upper()))

    deduped: list[tuple[str, str]] = []
    for pair in pairs:
        if pair not in deduped:
            deduped.append(pair)
    return deduped


@router.get("/price-points", response_model=PricePointsResponse)
def list_price_points(
    db: Session = Depends(get_tenant_db),
    user_roles: list[str] = Depends(get_user_roles),
    user_identity: str = Depends(get_user_identity),
    tenant: str | None = Query(None),
    routes: str | None = Query(
        None, description="Comma-separated ORG-DST pairs, e.g. EIS-SXM,ANU-BGI."
    ),
    origin: str | None = Query(None, description="Single-route form: origin, e.g. EIS."),
    destination: str | None = Query(None, description="Single-route form: destination, e.g. SXM."),
    cap_date: str | None = Query(None, description="Capture date; defaults to the newest."),
    airlines: str | None = Query(None, description="Comma-separated airline codes."),
    dep_from: str | None = Query(None),
    dep_to: str | None = Query(None),
    stops: int | None = Query(None, ge=0),
    flt_num: str | None = Query(None),
    trip_type: str | None = Query(None, description="OW or RT; a row-level itinerary attribute."),
    include_availability: bool = Query(
        False, description="Set true to also classify each airline's no-fare days."
    ),
):
    """Every fare observed on the requested routes on one capture date, one point each."""
    _, view_name = _resolve_airline_view(user_identity, user_roles, tenant)

    market_pairs = _parse_routes(routes, origin, destination)
    if not market_pairs:
        raise HTTPException(
            status_code=400,
            detail="At least one route is required (routes=ORG-DST or origin= and destination=)",
        )
    if len(market_pairs) > MAX_ROUTES_PER_REQUEST:
        raise HTTPException(
            status_code=400,
            detail=f"At most {MAX_ROUTES_PER_REQUEST} routes per request",
        )
    cap_date = sanitize_date(cap_date, "cap_date")
    dep_from = sanitize_date(dep_from, "dep_from")
    dep_to = sanitize_date(dep_to, "dep_to")
    flt_num = sanitize_filter(flt_num, "flt_num")
    trip_type = sanitize_filter(trip_type, "trip_type")
    airline_list = [
        code for code in
        (sanitize_filter(part.strip(), "airlines") for part in (airlines or "").split(",") if part.strip())
        if code
    ]

    # Same rule as the grid: a query without a cap_date equality scans the
    # whole table, so pin the newest capture when the caller omits one.
    route_labels = [f"{org}-{dst}" for org, dst in market_pairs]

    if not cap_date:
        cap_date = _latest_date(db, view_name, "cap_date")
        if cap_date is None:
            return PricePointsResponse(cap_date=None, routes=route_labels, points=[])

    params: dict = {
        "cap_date": cap_date,
        # +1 so a full page tells us rows were dropped rather than guessing.
        "limit": MAX_PRICE_POINTS + 1,
    }
    # A row-constructor IN list, one bound pair per requested market. Built
    # by index rather than as a single ANY(array) so Postgres sees ordinary
    # equality on (ref_org, ref_dst) and can still use an index on them.
    market_terms = []
    for i, (org, dst) in enumerate(market_pairs):
        params[f"org{i}"] = org
        params[f"dst{i}"] = dst
        market_terms.append(f"(:org{i}, :dst{i})")
    market_clause = f"(ref_org, ref_dst) IN ({', '.join(market_terms)})"
    if airline_list:
        params["airlines"] = airline_list
    if dep_from:
        params["dep_from"] = dep_from
    if dep_to:
        params["dep_to"] = dep_to
    if stops is not None:
        params["stops"] = stops
    if flt_num:
        params["flt_num"] = flt_num
    if trip_type:
        params["trip_type"] = trip_type

    def _side_sql(side: str, role: str) -> str:
        # The market predicate is always the REFERENCE O&D, on both halves:
        # a competitor row is that competitor's offer in the host's market,
        # and the dashboard's "Route (O&D)" filter is built the same way.
        # Filtering the competitor half on its own O&D would silently drop
        # rows whose comp_org is blank.
        clauses = [
            "cap_date = :cap_date",
            market_clause,
            f"{side}_tot_fare > 0",
        ]
        if airline_list:
            clauses.append(f"{side}_al = ANY(:airlines)")
        if dep_from:
            clauses.append(f"{side}_dep_date >= :dep_from")
        if dep_to:
            clauses.append(f"{side}_dep_date <= :dep_to")
        if stops is not None:
            clauses.append(f"{side}_stops = :stops")
        if flt_num:
            clauses.append(f"{side}_flt_num = :flt_num")
        if trip_type:
            # Not side-prefixed: one snapshot row is one itinerary observation,
            # so its trip_type covers the reference and competitor halves alike.
            clauses.append("trip_type = :trip_type")
        return _PRICE_POINT_SIDE_SQL.format(
            side=side, role=role, view=view_name, where=" AND ".join(clauses)
        )

    # Cap PER MARKET, not across the whole result. A single global LIMIT with a
    # market-ordered sort silently deletes whole later routes while the earlier
    # ones look complete — on a comparison chart that reads as "this route has
    # no fares" rather than "we stopped fetching", which is the worst possible
    # way to be wrong. The floor of 1000 keeps a small selection generous.
    per_route_limit = max(1000, MAX_PRICE_POINTS // len(market_pairs))
    # +1 per market is the truncation sentinel: seeing the extra row is how we
    # know that market had more to give.
    params["per_route_limit"] = per_route_limit + 1

    # Columns are projected explicitly rather than SELECT * so the window
    # function's `rn` cannot leak into PricePointOut(**row).
    projection = (
        "market, airline, role, flt_num, origin, destination, dep_date, dep_time, "
        "arr_time, stops, via, cab_code, cab_name, bkg_class, ff_code, equip_code, "
        "seats, curr, base_fare, tax, yq, yr, tot_fare, trip_type, cap_date, cap_time"
    )
    row_order = "dep_date, dep_time NULLS LAST, airline, tot_fare"
    sql = text(
        f"SELECT {projection} FROM ("
        f"  SELECT p.*, ROW_NUMBER() OVER (PARTITION BY market ORDER BY {row_order}) AS rn"
        f"  FROM ({_side_sql('ref', 'reference')} UNION ALL {_side_sql('comp', 'competitor')}) p"
        f") q WHERE rn <= :per_route_limit "
        f"ORDER BY market, {row_order}"
    )
    rows = db.execute(sql, params).mappings().all()

    # Any market that produced the sentinel row had more fares than we drew.
    per_market: dict[str, int] = {}
    for row in rows:
        per_market[row["market"]] = per_market.get(row["market"], 0) + 1
    truncated_routes = sorted(m for m, n in per_market.items() if n > per_route_limit)
    kept: dict[str, int] = {}
    trimmed = []
    for row in rows:
        seen = kept.get(row["market"], 0)
        if seen >= per_route_limit:
            continue
        kept[row["market"]] = seen + 1
        trimmed.append(row)
    rows = trimmed

    points = [
        PricePointOut(
            **row,
            duration_min=_duration_minutes(row["dep_time"], row["arr_time"]),
            dbd=(row["dep_date"] - row["cap_date"]).days,
        )
        for row in rows
    ]

    # ── No-fare days — whole-day availability classification ──────────────
    # A no-fare day produces no point above, which a chart renders as a
    # silent gap. When asked, name the gap per (market, airline, day). Zero-
    # fare rows are the subject here, so the `{side}_tot_fare > 0` predicate
    # is deliberately absent; the GROUP BY absorbs the per-competitor
    # duplication of reference rows. One sold-out flight is enough to call
    # the day sold out (bool_or), and any purchasable fare disqualifies the
    # day entirely (HAVING). A stops or flt_num filter suppresses the
    # markers instead of scoping them — a no-fare day carries NULL stops and
    # a blank flight number, so it cannot honestly satisfy either filter —
    # and the flag tells the caller why they vanished.
    no_fare_days: list[NoFareDayOut] = []
    availability_suppressed = False
    if include_availability:
        if stops is not None or flt_num:
            availability_suppressed = True
        else:

            def _availability_sql(side: str) -> str:
                # Same cap_date/market/airline/dep-window predicates as the
                # points, so markers and lines describe the same selection.
                # The comp guard drops wholly-blank competitor halves: no
                # airline code means no line to attach a marker to.
                clauses = ["cap_date = :cap_date", market_clause]
                if side == "comp":
                    clauses.append("comp_al <> ''")
                if airline_list:
                    clauses.append(f"{side}_al = ANY(:airlines)")
                if dep_from:
                    clauses.append(f"{side}_dep_date >= :dep_from")
                if dep_to:
                    clauses.append(f"{side}_dep_date <= :dep_to")
                # Unlike stops/flt_num, trip_type is populated on no-fare rows
                # too (it names the itinerary asked about, not the flight that
                # answered), so it scopes the markers rather than suppressing
                # them: "no RT fare all day" is a well-posed statement.
                if trip_type:
                    clauses.append("trip_type = :trip_type")
                return _AVAILABILITY_SIDE_SQL.format(
                    side=side,
                    status_case=_AVAILABILITY_STATUS_CASE[side],
                    view=view_name,
                    where=" AND ".join(clauses),
                )

            avail_sql = text(
                "SELECT market, airline, dep_date, "
                "CASE WHEN bool_or(status = 'sold_out') THEN 'sold_out' "
                "ELSE 'not_on_sale' END AS status "
                f"FROM ({_availability_sql('ref')} UNION ALL {_availability_sql('comp')}) s "
                "GROUP BY market, airline, dep_date "
                "HAVING NOT bool_or(status = 'on_sale') "
                "ORDER BY market, dep_date, airline"
            )
            # The points params minus the row caps, which this query has no
            # binds for.
            avail_params = {
                k: v for k, v in params.items()
                if k not in ("limit", "per_route_limit")
            }
            cap_date_obj = datetime.strptime(cap_date, "%Y-%m-%d").date()
            no_fare_days = [
                NoFareDayOut(**row, dbd=(row["dep_date"] - cap_date_obj).days)
                for row in db.execute(avail_sql, avail_params).mappings().all()
            ]

    # One currency per airline tenant in practice; None signals a mix rather
    # than picking a winner and mislabelling the axis.
    currencies = {p.curr for p in points if p.curr}
    return PricePointsResponse(
        cap_date=cap_date,
        routes=route_labels,
        currency=currencies.pop() if len(currencies) == 1 else None,
        truncated=bool(truncated_routes),
        truncated_routes=truncated_routes,
        points=points,
        no_fare_days=no_fare_days,
        availability_suppressed=availability_suppressed,
    )


@router.get("/price-points/history", response_model=PriceHistoryResponse)
def price_point_history(
    db: Session = Depends(get_tenant_db),
    user_roles: list[str] = Depends(get_user_roles),
    user_identity: str = Depends(get_user_identity),
    tenant: str | None = Query(None),
    origin: str = Query(...),
    destination: str = Query(...),
    airline: str = Query(...),
    dep_date: str = Query(...),
    flt_num: str | None = Query(None),
    trip_type: str | None = Query(None, description="OW or RT; a row-level itinerary attribute."),
):
    """How one flight's fare moved across capture dates.

    Backs the sparkline on a price card. Needs more than one capture loaded
    to draw anything — a tenant with a single capture date returns a single
    point, which is honest rather than empty.
    """
    _, view_name = _resolve_airline_view(user_identity, user_roles, tenant)

    origin = sanitize_filter(origin, "origin")
    destination = sanitize_filter(destination, "destination")
    airline = sanitize_filter(airline, "airline")
    flt_num = sanitize_filter(flt_num, "flt_num")
    trip_type = sanitize_filter(trip_type, "trip_type")
    dep_date = sanitize_date(dep_date, "dep_date")
    if not (origin and destination and airline and dep_date):
        raise HTTPException(
            status_code=400,
            detail="origin, destination, airline and dep_date are required",
        )

    params: dict = {
        "org": origin.upper(),
        "dst": destination.upper(),
        "al": airline.upper(),
        "dep_date": dep_date,
        "window": _HISTORY_WINDOW_DAYS,
    }
    if flt_num:
        params["flt_num"] = flt_num
    if trip_type:
        params["trip_type"] = trip_type

    def _side_sql(side: str) -> str:
        clauses = [
            "ref_org = :org",
            "ref_dst = :dst",
            f"{side}_al = :al",
            f"{side}_dep_date = :dep_date",
            f"{side}_tot_fare > 0",
            # Keeps the scan bounded on large tenants without needing the
            # caller to know the capture range. CAST(), not `::date` —
            # SQLAlchemy's text() parser reads the leading colon of a `::`
            # cast as the start of another bind parameter.
            "cap_date >= CAST(:dep_date AS date) - CAST(:window AS integer) * INTERVAL '1 day'",
        ]
        if flt_num:
            clauses.append(f"{side}_flt_num = :flt_num")
        if trip_type:
            # Not side-prefixed, same as list_price_points: one snapshot row
            # is one itinerary observation, so its trip_type covers the
            # reference and competitor halves alike. Without this, a tenant
            # carrying both OW and RT rows (5L) gets a history that mixes the
            # two fares of the same flight/date into one zigzag line.
            clauses.append("trip_type = :trip_type")
        return (
            f"SELECT DISTINCT cap_date, cap_time, {side}_tot_fare AS tot_fare, "
            f"{side}_seats AS seats, NULLIF({side}_curr, '') AS curr "
            f"FROM {view_name} WHERE {' AND '.join(clauses)}"
        )

    sql = text(
        f"{_side_sql('ref')} UNION ALL {_side_sql('comp')} ORDER BY cap_date, cap_time"
    )
    rows = db.execute(sql, params).mappings().all()

    dep_date_obj = datetime.strptime(dep_date, "%Y-%m-%d").date()
    currencies = {r["curr"] for r in rows if r["curr"]}
    return PriceHistoryResponse(
        airline=airline.upper(),
        flt_num=flt_num,
        trip_type=trip_type,
        origin=origin.upper(),
        destination=destination.upper(),
        dep_date=dep_date_obj,
        curr=currencies.pop() if len(currencies) == 1 else None,
        points=[
            PriceHistoryPointOut(
                cap_date=r["cap_date"],
                cap_time=r["cap_time"],
                tot_fare=r["tot_fare"],
                seats=r["seats"],
                dbd=(dep_date_obj - r["cap_date"]).days,
            )
            for r in rows
        ],
    )


# ── Velocity endpoints (multi-tenant: JY, PW, ALT, WM, DA, 5L) ─────────

VELOCITY_VIEW_MAP = {
    "JY": "vw_velocity_jy_snapshot",
    "PW": "vw_velocity_pw_snapshot",
    "ALT": "vw_velocity_alt_snapshot",
    "WM": "vw_velocity_wm_snapshot",
    "DA": "vw_velocity_da_snapshot",
    "5L": "vw_velocity_5l_snapshot",
}
VELOCITY_TENANTS = set(VELOCITY_VIEW_MAP.keys())


def _resolve_velocity_tenant(user_identity: str, user_roles: list[str], tenant: str | None) -> str:
    """Validate scope and return effective tenant code for velocity."""
    if is_platform_admin(user_identity, user_roles):
        effective = tenant or "JY"
    else:
        if user_identity not in VELOCITY_TENANTS:
            raise HTTPException(status_code=403, detail="Not Authorized")
        if tenant and tenant != user_identity:
            raise HTTPException(status_code=400, detail="Tenant scope mismatch")
        effective = user_identity
    if effective not in VELOCITY_TENANTS:
        raise HTTPException(status_code=400, detail="Invalid tenant for velocity module")
    return effective


def _parse_days_left(days_left: str | None) -> int | None:
    if days_left is None or str(days_left).strip() == "":
        return None
    try:
        return int(str(days_left).strip())
    except ValueError:
        raise HTTPException(status_code=400, detail="Filter 'days_left' must be an integer")


def _build_velocity_where(file_date, origin, destination, city_pair, days_left_int):
    where_clauses = []
    params: dict = {}
    if file_date:
        where_clauses.append("report_date = :file_date")
        params["file_date"] = file_date
    if origin:
        where_clauses.append("origin = :origin")
        params["origin"] = origin
    if destination:
        where_clauses.append("destination = :destination")
        params["destination"] = destination
    if city_pair:
        where_clauses.append("city_pair = :city_pair")
        params["city_pair"] = city_pair
    if days_left_int is not None:
        where_clauses.append("days_left = :days_left")
        params["days_left"] = days_left_int
    where_str = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
    return where_str, params


@router.get("/velocity/snapshots", response_model=PaginatedResponse[VelocitySnapshotOut])
def list_velocity_snapshots(
    db: Session = Depends(get_tenant_db),
    user_roles: list[str] = Depends(get_user_roles),
    user_identity: str = Depends(get_user_identity),
    tenant: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=MAX_PAGE_SIZE),
    file_date: str | None = None,
    origin: str | None = None,
    destination: str | None = None,
    city_pair: str | None = None,
    days_left: str | None = None,
    with_total: bool = Query(True, description="Set false to skip count(*) on repeat pages."),
):
    effective_tenant = _resolve_velocity_tenant(user_identity, user_roles, tenant)
    view_name = VELOCITY_VIEW_MAP[effective_tenant]

    file_date = sanitize_date(file_date, "file_date")
    origin = sanitize_filter(origin, "origin")
    destination = sanitize_filter(destination, "destination")
    city_pair = sanitize_filter(city_pair, "city_pair")
    days_left_int = _parse_days_left(days_left)

    # Pin the newest report_date when the caller supplies none — see the same
    # guard in list_snapshots. Velocity filters on report_date (not cap_date).
    if not file_date:
        file_date = _latest_date(db, view_name, "report_date")
        if file_date is None:
            return PaginatedResponse(
                items=[],
                page_info=PageInfo(total=0, page=page, page_size=page_size,
                                   has_next=False, applied_file_date=None),
            )

    where_str, filter_params = _build_velocity_where(file_date, origin, destination, city_pair, days_left_int)
    params = {**filter_params, "limit": page_size, "offset": (page - 1) * page_size}

    # `id` tiebreaker — (dep_date, dep_time) is not unique, so without it
    # LIMIT/OFFSET paging can duplicate and drop rows. See list_snapshots.
    data_sql = text(
        f"SELECT * FROM {view_name} {where_str} "
        "ORDER BY dep_date DESC, dep_time DESC, id DESC LIMIT :limit OFFSET :offset"
    )
    rows = db.execute(data_sql, params).mappings().all()

    total = _cached_count(db, view_name, where_str, filter_params) if with_total else 0

    return PaginatedResponse(
        items=rows,
        page_info=PageInfo(total=total, page=page, page_size=page_size,
                           has_next=((page - 1) * page_size + page_size) < total,
                           applied_file_date=file_date,
                           total_is_cached=not with_total),
    )


@router.get("/velocity/filter-metadata", response_model=list[FilterMetadataOut])
def get_velocity_filter_metadata(
    db: Session = Depends(get_tenant_db),
    user_roles: list[str] = Depends(get_user_roles),
    user_identity: str = Depends(get_user_identity),
    tenant: str | None = Query(None),
):
    effective_tenant = _resolve_velocity_tenant(user_identity, user_roles, tenant)
    view_name = VELOCITY_VIEW_MAP[effective_tenant]

    # Five DISTINCT scans over the full velocity table. These change only when
    # a new file is ingested, so they are cached for 5 minutes rather than
    # recomputed on every page mount.
    def _produce() -> list[dict]:
        result = []

        file_dates = db.execute(text(
            f"SELECT DISTINCT report_date FROM {view_name} "
            "WHERE report_date IS NOT NULL ORDER BY report_date DESC"
        )).scalars().all()
        result.append({"field": "file_date", "label": "File Date",
                       "values": [d.isoformat() for d in file_dates] or ["No file dates available"]})

        origins = db.execute(text(
            f"SELECT DISTINCT origin FROM {view_name} "
            "WHERE origin IS NOT NULL AND origin <> '' ORDER BY origin"
        )).scalars().all()
        result.append({"field": "origin", "label": "Origin", "values": list(origins)})

        destinations = db.execute(text(
            f"SELECT DISTINCT destination FROM {view_name} "
            "WHERE destination IS NOT NULL AND destination <> '' ORDER BY destination"
        )).scalars().all()
        result.append({"field": "destination", "label": "Destination", "values": list(destinations)})

        city_pairs = db.execute(text(
            f"SELECT DISTINCT city_pair FROM {view_name} "
            "WHERE city_pair IS NOT NULL AND city_pair <> '' ORDER BY city_pair"
        )).scalars().all()
        result.append({"field": "city_pair", "label": "City Pair", "values": list(city_pairs)})

        days = db.execute(text(
            f"SELECT DISTINCT days_left FROM {view_name} ORDER BY days_left"
        )).scalars().all()
        result.append({"field": "days_left", "label": "Days Left",
                       "values": [str(d) for d in days]})

        return result

    return cached(("velocity_filter_meta", view_name), _METADATA_TTL, _produce)


@router.get("/velocity/export")
def export_velocity_snapshots(
    db: Session = Depends(get_tenant_db),
    user_roles: list[str] = Depends(get_user_roles),
    user_identity: str = Depends(get_user_identity),
    tenant: str | None = Query(None),
    file_date: str | None = None,
    origin: str | None = None,
    destination: str | None = None,
    city_pair: str | None = None,
    days_left: str | None = None,
):
    effective_tenant = _resolve_velocity_tenant(user_identity, user_roles, tenant)
    view_name = VELOCITY_VIEW_MAP[effective_tenant]

    file_date = sanitize_date(file_date, "file_date")
    origin = sanitize_filter(origin, "origin")
    destination = sanitize_filter(destination, "destination")
    city_pair = sanitize_filter(city_pair, "city_pair")
    days_left_int = _parse_days_left(days_left)

    # Same rule as the grid: never scan the whole table.
    if not file_date:
        file_date = _latest_date(db, view_name, "report_date")

    where_str, params = _build_velocity_where(file_date, origin, destination, city_pair, days_left_int)

    data_sql = text(
        f"SELECT * FROM {view_name} {where_str} "
        "ORDER BY dep_date DESC, dep_time DESC, id DESC LIMIT 5000"
    )
    rows = db.execute(data_sql, params).mappings().all()

    wb = Workbook()
    ws = wb.active
    ws.title = "Airline Velocity Export"

    headers = [
        "Dep Date", "Dep Time", "Origin", "Destination", "City Pair",
        "Eqp", "Compartment", "Leg/Seg Type", "Leg/Seg Order",
        "Days Left", "Capacity", "Current Booking", "Seats Available",
        "Booking %", "Actual SF %", "Forecasted SF %",
        "Report Date", "Source File",
    ]
    ws.append(headers)

    for r in rows:
        ws.append([
            r.dep_date.isoformat() if r.dep_date else "",
            r.dep_time or "",
            r.origin, r.destination, r.city_pair,
            r.eqp, r.compartment, r.legseg_type, r.leg_seg_order,
            r.days_left, r.capacity, r.current_booking, r.seats_available,
            float(r.booking_pct) if r.booking_pct is not None else 0.0,
            r.actual_seat_factor, r.forecasted_seat_factor,
            r.report_date.isoformat() if r.report_date else "",
            r.source_file or "",
        ])

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)

    filename = f"airline_velocity_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
