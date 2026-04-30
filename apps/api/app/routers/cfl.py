"""CFL endpoints — tenant-aware DB queries with filter hardening."""

from fastapi import APIRouter, Query, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select, func, distinct, text
from datetime import datetime
import io
from openpyxl import Workbook
from fastapi.responses import StreamingResponse

from app.core.deps import get_tenant_db, sanitize_filter, sanitize_date, get_user_roles, get_user_identity, is_platform_admin
from app.models.cfl import CflCpiSnapshot
from app.schemas.common import PaginatedResponse, PageInfo
from app.schemas.cfl import CflSnapshotOut
from app.schemas.filters import FilterMetadataOut

router = APIRouter(
    prefix="/api/v1/cfl",
    tags=["cfl"],
)


@router.get("/snapshots", response_model=PaginatedResponse[CflSnapshotOut])
def list_snapshots(
    db: Session = Depends(get_tenant_db),
    user_roles: list[str] = Depends(get_user_roles),
    user_identity: str = Depends(get_user_identity),
    tenant: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    file_date: str | None = None,
    operator: str | None = None,
):
    # Enforce tenant scoping — only FJL users and platform admins may access CFL data
    if not is_platform_admin(user_identity, user_roles):
        if user_identity != "FJL":
            raise HTTPException(status_code=403, detail="Not Authorized")
    if tenant and tenant != "FJL":
        raise HTTPException(status_code=400, detail="Invalid tenant for CFL module")
    view_name = "vw_cfl_cpi_fjl_snapshot"

    file_date = sanitize_date(file_date, "file_date")
    operator = sanitize_filter(operator, "operator")

    where_clauses = []
    params = {"limit": page_size, "offset": (page - 1) * page_size}

    if file_date:
        where_clauses.append("cap_date = :file_date")
        params["file_date"] = file_date
    if operator:
        where_clauses.append("source = :operator")
        params["operator"] = operator

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
    # Enforce tenant scoping — only FJL users and platform admins may access CFL metadata
    if not is_platform_admin(user_identity, user_roles):
        if user_identity != "FJL":
            raise HTTPException(status_code=403, detail="Not Authorized")

    from app.core.file_dates import get_available_file_dates
    import os
    
    # Path inside container
    data_path = os.environ.get("CPI_DATA_PATH", "/app/data")
    if not os.path.exists(data_path):
        data_path = os.path.join(os.getcwd(), "data")

    result = []
    # Dates from filenames - filter by tenant if provided
    search_tenants = [tenant] if tenant else ["FJL"]
    file_dates = get_available_file_dates(data_path, search_tenants)
    if file_dates == ["No file dates available"]:
        file_dates = []

    # Dates from database
    db_dates_query = select(distinct(CflCpiSnapshot.report_date)).where(CflCpiSnapshot.report_date != None)
    if tenant:
        db_dates_query = db_dates_query.where(CflCpiSnapshot.tenant_code == tenant)
    else:
        db_dates_query = db_dates_query.where(CflCpiSnapshot.tenant_code == "FJL")
    
    db_dates = [d.isoformat() for d in db.execute(db_dates_query).scalars().all() if d]
    
    # Merge and sort
    all_dates = sorted(list(set(file_dates + db_dates)), reverse=True)
    if not all_dates:
        all_dates = ["No file dates available"]
        
    result.append({"field": "file_date", "label": "File Date", "values": all_dates})

    # Operator filter — always scoped to FJL for CFL module
    vals = ["FJL"]
        
    result.append({"field": "operator", "label": "Airline / Operator", "values": vals})

    return result


@router.get("/export")
def export_snapshots(
    db: Session = Depends(get_tenant_db),
    user_roles: list[str] = Depends(get_user_roles),
    user_identity: str = Depends(get_user_identity),
    tenant: str | None = Query(None),
    file_date: str | None = None,
    operator: str | None = None,
):
    # Enforce tenant scoping — only FJL users and platform admins may export CFL data
    if not is_platform_admin(user_identity, user_roles):
        if user_identity != "FJL":
            raise HTTPException(status_code=403, detail="Not Authorized")
    if tenant and tenant != "FJL":
        raise HTTPException(status_code=400, detail="Invalid tenant for CFL module")
    view_name = "vw_cfl_cpi_fjl_snapshot"

    # Sanitize filters
    file_date = sanitize_date(file_date, "file_date")
    operator = sanitize_filter(operator, "operator")

    where_clauses = []
    params = {}

    if file_date:
        where_clauses.append("cap_date = :file_date")
        params["file_date"] = file_date
    if operator:
        where_clauses.append("source = :operator")
        params["operator"] = operator

    where_str = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
    
    data_sql = text(f"SELECT * FROM {view_name} {where_str} ORDER BY cap_date DESC, cap_time DESC LIMIT 5000")
    rows = db.execute(data_sql, params).mappings().all()

    wb = Workbook()
    ws = wb.active
    ws.title = "Cruise Ferry CPI Export"

    # Headers
    headers = [
        "Capture Date", "Capture Time", "Trip Type", 
        "Operator/Source", "Origin Port", "Destination Port", 
        "Dep Date", "Dep Time", "Equipment", "Cabin Type",
        "Total Fare", "Pax Fare", "Veh Fare", "Cab Fare", "Taxes",
        "Num Pax", "Veh Size", "Currency", "Availability"
    ]
    ws.append(headers)

    # Data
    for r in rows:
        ws.append([
            r.cap_date.isoformat(), r.cap_time.isoformat(), r.trip_type,
            r.source, r.org, r.dest,
            r.out_dep_date.isoformat() if r.out_dep_date else "", 
            r.out_dep_time.isoformat() if r.out_dep_time else "",
            r.out_equip_name, r.out_cab_type,
            float(r.total_fare), float(r.out_per_pax_fare), float(r.out_veh_fare or 0), 
            float(r.out_cab_fare or 0), float(r.out_taxes),
            r.out_num_pax, r.veh_size, r.curr_code, r.out_avail
        ])

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)

    filename = f"cruise_ferry_cpi_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
