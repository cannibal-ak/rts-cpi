"""Airline CPI endpoints — tenant-aware DB queries with filter hardening."""

from datetime import datetime
from fastapi import APIRouter, Query, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select, func, distinct, text
import io
from openpyxl import Workbook
from fastapi.responses import StreamingResponse

from app.core.deps import get_tenant_db, sanitize_filter, sanitize_date, RequireRoles, get_user_roles, get_user_identity, is_platform_admin
from app.models.airline import AirlineCpiSnapshot
from app.schemas.common import PaginatedResponse, PageInfo
from app.schemas.airline import AirlineSnapshotOut
from app.schemas.filters import FilterMetadataOut

router = APIRouter(
    prefix="/api/v1/airline",
    tags=["airline"],
    dependencies=[Depends(RequireRoles("TENANT_ADMIN", "DATA_ENGINEER", "ANALYST", "REVENUE_MANAGER", "AUDITOR", "AIRLINE_USER"))]
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
