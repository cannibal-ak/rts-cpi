"""Airline CPI endpoints — tenant-aware DB queries with filter hardening."""

from datetime import datetime
from fastapi import APIRouter, Query, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select, func, distinct, text
import io
from openpyxl import Workbook
from fastapi.responses import StreamingResponse

from app.core.deps import get_tenant_db, sanitize_filter, sanitize_date, get_user_roles, get_user_identity, is_platform_admin
from app.models.airline import AirlineCpiSnapshot
from app.schemas.common import PaginatedResponse, PageInfo
from app.schemas.airline import AirlineSnapshotOut
from app.schemas.velocity import JyVelocitySnapshotOut
from app.schemas.filters import FilterMetadataOut

router = APIRouter(
    prefix="/api/v1/airline",
    tags=["airline"],
)


@router.get("/snapshots", response_model=PaginatedResponse[AirlineSnapshotOut])
def list_snapshots(
    db: Session = Depends(get_tenant_db),
    user_roles: list[str] = Depends(get_user_roles),
    user_identity: str = Depends(get_user_identity),
    tenant: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    file_date: str | None = None,
    airline: str | None = None,
):
    # Enforce tenant scoping — non-platform users are locked to their own airline
    AIRLINE_VIEW_MAP = {"JY": "vw_airline_cpi_jy_snapshot", "PW": "vw_airline_cpi_pw_snapshot"}
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

    # Build Raw SQL query for performance and to use specifically crafted views
    where_clauses = []
    params = {"limit": page_size, "offset": (page - 1) * page_size}

    if file_date:
        where_clauses.append("cap_date = :file_date")
        params["file_date"] = file_date
    if airline:
        where_clauses.append("ref_al = :airline")
        params["airline"] = airline

    where_str = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
    
    # Count query
    count_sql = text(f"SELECT count(*) FROM {view_name} {where_str}")
    total = db.execute(count_sql, params).scalar()

    # Data query
    data_sql = text(f"SELECT * FROM {view_name} {where_str} ORDER BY cap_date DESC, cap_time DESC LIMIT :limit OFFSET :offset")
    rows = db.execute(data_sql, params).mappings().all()

    return PaginatedResponse(
        items=rows,
        page_info=PageInfo(total=total, page=page, page_size=page_size,
                           has_next=((page - 1) * page_size + page_size) < total),
    )


@router.get("/filter-metadata", response_model=list[FilterMetadataOut])
def get_filter_metadata(
    db: Session = Depends(get_tenant_db),
    user_roles: list[str] = Depends(get_user_roles),
    user_identity: str = Depends(get_user_identity),
    tenant: str | None = Query(None),
):
    # Enforce tenant scoping — non-platform users locked to own airline
    AIRLINE_TENANTS = {"JY", "PW"}
    if is_platform_admin(user_identity, user_roles):
        effective_tenant = tenant  # platform admin can pick or see all
    else:
        if user_identity not in AIRLINE_TENANTS:
            raise HTTPException(status_code=403, detail="Not Authorized")
        effective_tenant = user_identity  # locked to own tenant

    from app.core.file_dates import get_available_file_dates

    import os
    # Paths and defaults
    data_path = os.environ.get("CPI_DATA_PATH", "/app/data")
    if not os.path.exists(data_path):
        data_path = os.path.join(os.getcwd(), "data")

    result = []
    
    # Dates from filenames - filter by resolved tenant
    search_tenants = [effective_tenant] if effective_tenant else ["JY", "PW"]
    file_dates = get_available_file_dates(data_path, search_tenants)
    if file_dates == ["No file dates available"]:
        file_dates = []

    # Dates from database
    db_dates_query = select(distinct(AirlineCpiSnapshot.report_date)).where(AirlineCpiSnapshot.report_date != None)
    if effective_tenant:
        db_dates_query = db_dates_query.where(AirlineCpiSnapshot.tenant_code == effective_tenant)
    else:
        db_dates_query = db_dates_query.where(AirlineCpiSnapshot.tenant_code.in_(["JY", "PW"]))
    
    db_dates = [d.isoformat() for d in db.execute(db_dates_query).scalars().all() if d]
    
    # Merge and sort
    all_dates = sorted(list(set(file_dates + db_dates)), reverse=True)
    if not all_dates:
        all_dates = ["No file dates available"]
        
    result.append({"field": "file_date", "label": "File Date", "values": all_dates})

    # Airline filter — scoped to resolved tenant
    if effective_tenant:
        vals = [effective_tenant]
    else:
        vals = ["JY", "PW"]  # only reachable by platform admin with no tenant param
        
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
    AIRLINE_VIEW_MAP = {"JY": "vw_airline_cpi_jy_snapshot", "PW": "vw_airline_cpi_pw_snapshot"}
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

    where_clauses = []
    params = {}

    if file_date:
        where_clauses.append("cap_date = :file_date")
        params["file_date"] = file_date
    if airline:
        where_clauses.append("ref_al = :airline")
        params["airline"] = airline

    where_str = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
    
    data_sql = text(f"SELECT * FROM {view_name} {where_str} ORDER BY cap_date DESC, cap_time DESC LIMIT 5000")
    rows = db.execute(data_sql, params).mappings().all()

    wb = Workbook()
    ws = wb.active
    ws.title = "Airline CPI Export"

    # Headers
    headers = [
        "Capture Date", "Capture Time", "Trip Type", 
        "Ref Airline", "Ref Flt Num", "Ref Org", "Ref Dst", "Ref Dep Date", "Ref Cabin", "Ref Fare",
        "Comp Airline", "Comp Flt Num", "Comp Org", "Comp Dst", "Comp Dep Date", "Comp Cabin", "Comp Fare",
        "POS", "POA"
    ]
    ws.append(headers)

    # Data
    for r in rows:
        ws.append([
            r.cap_date.isoformat(), r.cap_time.isoformat(), r.trip_type,
            r.ref_al, r.ref_flt_num, r.ref_org, r.ref_dst, r.ref_dep_date.isoformat(), r.ref_cab_code, float(r.ref_tot_fare),
            r.comp_al, r.comp_flt_num, r.comp_org, r.comp_dst, r.comp_dep_date.isoformat(), r.comp_cab_code, float(r.comp_tot_fare),
            r.pos, r.poa
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


# ── Velocity endpoints (JY only) ────────────────────────────────────

VELOCITY_VIEW = "vw_jy_velocity_snapshot"
VELOCITY_TENANTS = {"JY"}


def _resolve_velocity_tenant(user_identity: str, user_roles: list[str], tenant: str | None) -> str:
    """Validate scope and return effective tenant — only JY is valid for velocity."""
    if is_platform_admin(user_identity, user_roles):
        effective = tenant or "JY"
    else:
        if user_identity not in VELOCITY_TENANTS:
            raise HTTPException(status_code=403, detail="Not Authorized")
        if tenant and tenant != user_identity:
            raise HTTPException(status_code=400, detail="Velocity data only available for JY tenant")
        effective = user_identity
    if effective not in VELOCITY_TENANTS:
        raise HTTPException(status_code=400, detail="Velocity data only available for JY tenant")
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


@router.get("/velocity/snapshots", response_model=PaginatedResponse[JyVelocitySnapshotOut])
def list_velocity_snapshots(
    db: Session = Depends(get_tenant_db),
    user_roles: list[str] = Depends(get_user_roles),
    user_identity: str = Depends(get_user_identity),
    tenant: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    file_date: str | None = None,
    origin: str | None = None,
    destination: str | None = None,
    city_pair: str | None = None,
    days_left: str | None = None,
):
    _resolve_velocity_tenant(user_identity, user_roles, tenant)

    file_date = sanitize_date(file_date, "file_date")
    origin = sanitize_filter(origin, "origin")
    destination = sanitize_filter(destination, "destination")
    city_pair = sanitize_filter(city_pair, "city_pair")
    days_left_int = _parse_days_left(days_left)

    where_str, params = _build_velocity_where(file_date, origin, destination, city_pair, days_left_int)
    params["limit"] = page_size
    params["offset"] = (page - 1) * page_size

    count_sql = text(f"SELECT count(*) FROM {VELOCITY_VIEW} {where_str}")
    total = db.execute(count_sql, params).scalar() or 0

    data_sql = text(
        f"SELECT * FROM {VELOCITY_VIEW} {where_str} "
        "ORDER BY dep_date DESC, dep_time DESC LIMIT :limit OFFSET :offset"
    )
    rows = db.execute(data_sql, params).mappings().all()

    return PaginatedResponse(
        items=rows,
        page_info=PageInfo(total=total, page=page, page_size=page_size,
                           has_next=((page - 1) * page_size + page_size) < total),
    )


@router.get("/velocity/filter-metadata", response_model=list[FilterMetadataOut])
def get_velocity_filter_metadata(
    db: Session = Depends(get_tenant_db),
    user_roles: list[str] = Depends(get_user_roles),
    user_identity: str = Depends(get_user_identity),
    tenant: str | None = Query(None),
):
    _resolve_velocity_tenant(user_identity, user_roles, tenant)

    result = []

    file_dates = db.execute(text(
        f"SELECT DISTINCT report_date FROM {VELOCITY_VIEW} "
        "WHERE report_date IS NOT NULL ORDER BY report_date DESC"
    )).scalars().all()
    result.append({"field": "file_date", "label": "File Date",
                   "values": [d.isoformat() for d in file_dates] or ["No file dates available"]})

    origins = db.execute(text(
        f"SELECT DISTINCT origin FROM {VELOCITY_VIEW} "
        "WHERE origin IS NOT NULL AND origin <> '' ORDER BY origin"
    )).scalars().all()
    result.append({"field": "origin", "label": "Origin", "values": list(origins)})

    destinations = db.execute(text(
        f"SELECT DISTINCT destination FROM {VELOCITY_VIEW} "
        "WHERE destination IS NOT NULL AND destination <> '' ORDER BY destination"
    )).scalars().all()
    result.append({"field": "destination", "label": "Destination", "values": list(destinations)})

    city_pairs = db.execute(text(
        f"SELECT DISTINCT city_pair FROM {VELOCITY_VIEW} "
        "WHERE city_pair IS NOT NULL AND city_pair <> '' ORDER BY city_pair"
    )).scalars().all()
    result.append({"field": "city_pair", "label": "City Pair", "values": list(city_pairs)})

    days = db.execute(text(
        f"SELECT DISTINCT days_left FROM {VELOCITY_VIEW} ORDER BY days_left"
    )).scalars().all()
    result.append({"field": "days_left", "label": "Days Left",
                   "values": [str(d) for d in days]})

    return result


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
    _resolve_velocity_tenant(user_identity, user_roles, tenant)

    file_date = sanitize_date(file_date, "file_date")
    origin = sanitize_filter(origin, "origin")
    destination = sanitize_filter(destination, "destination")
    city_pair = sanitize_filter(city_pair, "city_pair")
    days_left_int = _parse_days_left(days_left)

    where_str, params = _build_velocity_where(file_date, origin, destination, city_pair, days_left_int)

    data_sql = text(
        f"SELECT * FROM {VELOCITY_VIEW} {where_str} "
        "ORDER BY dep_date DESC, dep_time DESC LIMIT 5000"
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
