"""Statistics and dashboard helper endpoints."""

from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import select, func, desc

from app.core.database import get_db
from app.core.deps import get_user_roles, get_user_identity, is_platform_admin
from app.models.airline import AirlineCpiSnapshot
from app.models.cfl import CflCpiSnapshot
from pydantic import BaseModel
from typing import List

router = APIRouter(
    prefix="/api/v1/stats",
    tags=["stats"],
)

# 48h is the conventional CPI ingestion latency window.
STALE_HOURS = 48


class DataFreshnessOut(BaseModel):
    domain: str
    report_date: str | None
    last_capture_at: str | None
    last_import_at: str | None
    record_count: int
    status: str


def compute_module_freshness(db: Session, model, tenant_code: str, domain_name: str) -> DataFreshnessOut:
    """Compute a freshness summary for one (model, tenant_code) pair.

    Shared with the admin dashboard so both surfaces report the same numbers.
    """
    now = datetime.now(timezone.utc)
    stale_threshold = now - timedelta(hours=STALE_HOURS)

    q_count = select(func.count(model.id)).where(model.tenant_code == tenant_code)
    count = db.scalar(q_count) or 0

    q_import = select(func.max(model.loaded_at)).where(model.tenant_code == tenant_code)
    last_import = db.scalar(q_import)

    q_report = select(func.max(model.report_date)).where(model.tenant_code == tenant_code)
    report_date_val = db.scalar(q_report)

    q_capture = (
        select(model.cap_date, model.cap_time)
        .where(model.tenant_code == tenant_code)
        .order_by(desc(model.cap_date), desc(model.cap_time))
        .limit(1)
    )
    last_capture = db.execute(q_capture).first()

    cap_str = None
    if last_capture:
        dt = datetime.combine(last_capture[0], last_capture[1])
        cap_str = dt.isoformat() + "Z"

    status = "fresh"
    if count == 0:
        status = "nodata"
    elif not last_import or last_import.replace(tzinfo=timezone.utc) < stale_threshold:
        status = "stale"

    return DataFreshnessOut(
        domain=domain_name,
        report_date=report_date_val.isoformat() if report_date_val else None,
        last_capture_at=cap_str,
        last_import_at=last_import.isoformat() + "Z" if last_import else None,
        record_count=count,
        status=status,
    )


@router.get("/freshness", response_model=List[DataFreshnessOut])
def get_data_freshness(
    db: Session = Depends(get_db),
    user_roles: list[str] = Depends(get_user_roles),
    user_identity: str = Depends(get_user_identity),
):
    """Calculate data freshness for all modules based on actual data."""
    results: List[DataFreshnessOut] = []
    is_admin = is_platform_admin(user_identity, user_roles)

    if is_admin or user_identity == "JY":
        results.append(compute_module_freshness(db, AirlineCpiSnapshot, "JY", "Airline CPI – JY"))
    if is_admin or user_identity == "PW":
        results.append(compute_module_freshness(db, AirlineCpiSnapshot, "PW", "Airline CPI – PW"))
    if is_admin or user_identity == "ALT":
        results.append(compute_module_freshness(db, AirlineCpiSnapshot, "ALT", "Airline CPI – SKY"))
    if is_admin or user_identity == "FJL":
        results.append(compute_module_freshness(db, CflCpiSnapshot, "FJL", "Cruise/Ferry CPI – FJL"))

    return results
