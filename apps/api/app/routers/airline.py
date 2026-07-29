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
from app.schemas.airline import AirlineSnapshotOut
from app.schemas.velocity import VelocitySnapshotOut
from app.schemas.filters import FilterMetadataOut

router = APIRouter(
    prefix="/api/v1/airline",
    tags=["airline"],
)

# Raised from 100 so a client can pull a page in one request instead of ten.
# The default stays at 20 — callers that don't ask are unaffected.
MAX_PAGE_SIZE = 1000

# Deliberately long. Snapshot data is ingested once a day, so the newest
# available date is stable for hours — a 10-minute staleness window is
# harmless. It matters because on airline_cpi_snapshot there is currently no
# index covering (tenant_code, cap_date), so `max(cap_date)` is a ~25s
# sequential scan of ~9.4M rows. Caching it for 10 minutes rather than 60
# seconds cuts that cost by an order of magnitude while the index is pending.
# Once ix_air_snap_<tenant>_grid exists this becomes an index-only scan and
# the TTL can safely drop back to 60s.
_LATEST_DATE_TTL = 600.0
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
    AIRLINE_VIEW_MAP = {"JY": "vw_airline_cpi_jy_snapshot", "PW": "vw_airline_cpi_pw_snapshot", "ALT": "vw_airline_cpi_alt_snapshot", "WM": "vw_airline_cpi_wm_snapshot"}
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
    order_by = "ORDER BY cap_date DESC, cap_time DESC, id DESC"

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
    AIRLINE_TENANTS = {"JY", "PW", "ALT", "WM"}
    if is_platform_admin(user_identity, user_roles):
        effective_tenant = tenant  # platform admin can pick or see all
    else:
        if user_identity not in AIRLINE_TENANTS:
            raise HTTPException(status_code=403, detail="Not Authorized")
        effective_tenant = user_identity  # locked to own tenant

    result = []

    # Date list — sourced from the SAME tenant view(s) the grid queries, keyed
    # on cap_date (the column the snapshots filter matches). Previously this
    # merged filename-parsed dates + DISTINCT report_date; a date could be
    # offered whose rows carry a different cap_date, giving an empty grid on
    # select. Enumerating cap_date guarantees every option returns rows.
    AIRLINE_VIEW_MAP = {"JY": "vw_airline_cpi_jy_snapshot", "PW": "vw_airline_cpi_pw_snapshot", "ALT": "vw_airline_cpi_alt_snapshot", "WM": "vw_airline_cpi_wm_snapshot"}
    date_tenants = [effective_tenant] if effective_tenant else ["JY", "PW", "ALT", "WM"]
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
    AIRLINE_VIEW_MAP = {"JY": "vw_airline_cpi_jy_snapshot", "PW": "vw_airline_cpi_pw_snapshot", "ALT": "vw_airline_cpi_alt_snapshot", "WM": "vw_airline_cpi_wm_snapshot"}
    view_tenants = [effective_tenant] if effective_tenant else ["JY", "PW", "ALT", "WM"]
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
    AIRLINE_VIEW_MAP = {"JY": "vw_airline_cpi_jy_snapshot", "PW": "vw_airline_cpi_pw_snapshot", "ALT": "vw_airline_cpi_alt_snapshot", "WM": "vw_airline_cpi_wm_snapshot"}
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

    data_sql = text(f"SELECT * FROM {view_name} {where_str} ORDER BY cap_date DESC, cap_time DESC, id DESC LIMIT 5000")
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


# ── Velocity endpoints (multi-tenant: JY + PW) ──────────────────────

VELOCITY_VIEW_MAP = {
    "JY": "vw_velocity_jy_snapshot",
    "PW": "vw_velocity_pw_snapshot",
    "ALT": "vw_velocity_alt_snapshot",
    "WM": "vw_velocity_wm_snapshot",
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
