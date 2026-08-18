"""CFL endpoints — tenant-aware DB queries with filter hardening."""

from fastapi import APIRouter, Query, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select, func, distinct, text
from datetime import datetime
import io
from openpyxl import Workbook
from fastapi.responses import StreamingResponse

from app.core.cache import cached
from app.core.deps import get_tenant_db, sanitize_filter, sanitize_date, get_user_roles, get_user_identity, is_platform_admin
from app.models.cfl import CflCpiSnapshot
from app.schemas.common import PaginatedResponse, PageInfo
from app.schemas.cfl import CflSnapshotOut
from app.schemas.filters import FilterMetadataOut

router = APIRouter(
    prefix="/api/v1/cfl",
    tags=["cfl"],
)

# Mirrors airline.py — see the rationale there.
MAX_PAGE_SIZE = 1000

# See the rationale in airline.py — ix_cfl_snap_fjl_grid makes max(cap_date) an
# index scan, so a short window costs nothing and keeps new dates visible.
_LATEST_DATE_TTL = 60.0
_COUNT_TTL = 60.0
_METADATA_TTL = 300.0


def _latest_date(db: Session, view_name: str, column: str) -> str | None:
    """Newest value of `column` in the tenant view, memoised briefly."""
    def _produce() -> str | None:
        val = db.execute(text(f"SELECT max({column}) FROM {view_name}")).scalar()
        return val.isoformat() if val else None

    return cached(("latest_date", view_name, column), _LATEST_DATE_TTL, _produce)


def _cached_count(db: Session, view_name: str, where_str: str, filter_params: dict) -> int:
    """count(*) memoised on the exact filter set."""
    key = ("count", view_name, where_str, tuple(sorted(filter_params.items())))

    def _produce() -> int:
        return db.execute(text(f"SELECT count(*) FROM {view_name} {where_str}"),
                          filter_params).scalar() or 0

    return cached(key, _COUNT_TTL, _produce)


@router.get("/snapshots", response_model=PaginatedResponse[CflSnapshotOut])
def list_snapshots(
    db: Session = Depends(get_tenant_db),
    user_roles: list[str] = Depends(get_user_roles),
    user_identity: str = Depends(get_user_identity),
    tenant: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=MAX_PAGE_SIZE),
    file_date: str | None = None,
    operator: str | None = None,
    with_total: bool = Query(True, description="Set false to skip count(*) on repeat pages."),
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

    # Never emit a query without a cap_date equality — an absent file_date
    # previously produced an empty WHERE and a full table scan. See airline.py.
    if not file_date:
        file_date = _latest_date(db, view_name, "cap_date")
        if file_date is None:
            return PaginatedResponse(
                items=[],
                page_info=PageInfo(total=0, page=page, page_size=page_size,
                                   has_next=False, applied_file_date=None),
            )

    where_clauses = ["cap_date = :file_date"]
    filter_params: dict = {"file_date": file_date}

    if operator:
        where_clauses.append("source = :operator")
        filter_params["operator"] = operator

    where_str = f"WHERE {' AND '.join(where_clauses)}"
    params = {**filter_params, "limit": page_size, "offset": (page - 1) * page_size}

    # `id` tiebreaker — (cap_date, cap_time) is not unique, so paging without it
    # can duplicate and drop rows. See airline.py.
    data_sql = text(f"SELECT * FROM {view_name} {where_str} "
                    "ORDER BY cap_date DESC, cap_time DESC, id DESC LIMIT :limit OFFSET :offset")
    rows = db.execute(data_sql, params).mappings().all()

    total = _cached_count(db, view_name, where_str, filter_params) if with_total else 0

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
    # Enforce tenant scoping — only FJL users and platform admins may access CFL metadata
    if not is_platform_admin(user_identity, user_roles):
        if user_identity != "FJL":
            raise HTTPException(status_code=403, detail="Not Authorized")

    # The DISTINCT sweep below ran uncached on every grid mount — memoised
    # 300s to match airline/velocity metadata. Single-tenant module, so the
    # view name alone is a sufficient key.
    view_name = "vw_cfl_cpi_fjl_snapshot"

    def _produce() -> list[dict]:
        result = []

        # Date list — sourced from the SAME tenant view the grid queries, keyed on
        # cap_date (the column the snapshots filter matches). Previously this merged
        # filename-parsed dates + DISTINCT report_date; a date could be offered
        # whose rows carry a different cap_date, giving an empty grid on select.
        # Enumerating cap_date guarantees every option returns rows.
        file_dates = db.execute(text(
            f"SELECT DISTINCT cap_date FROM {view_name} WHERE cap_date IS NOT NULL "
            "ORDER BY cap_date DESC"
        )).scalars().all()
        all_dates = [d.isoformat() for d in file_dates]
        if not all_dates:
            all_dates = ["No file dates available"]

        result.append({"field": "file_date", "label": "File Date", "values": all_dates})

        return result

    return cached(("cfl_filter_meta", view_name), _METADATA_TTL, _produce)


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

    # Same rule as the grid: never scan the whole table.
    if not file_date:
        file_date = _latest_date(db, view_name, "cap_date")

    where_clauses = []
    params = {}

    if file_date:
        where_clauses.append("cap_date = :file_date")
        params["file_date"] = file_date
    if operator:
        where_clauses.append("source = :operator")
        params["operator"] = operator

    where_str = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

    data_sql = text(f"SELECT * FROM {view_name} {where_str} ORDER BY cap_date DESC, cap_time DESC, id DESC LIMIT 5000")
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
