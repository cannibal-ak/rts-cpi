"""Statistics and dashboard helper endpoints."""

from datetime import datetime, timedelta, timezone
import uuid
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import select, func, desc

from app.core.database import get_db
from app.core.deps import RequireRoles, get_user_roles, get_user_identity
from app.models.airline import AirlineCpiSnapshot
from app.models.cfl import CflCpiSnapshot
from app.models.ingestion import ImportJob
from pydantic import BaseModel
from typing import List

router = APIRouter(
    prefix="/api/v1/stats",
    tags=["stats"],
    dependencies=[Depends(RequireRoles("TENANT_ADMIN", "DATA_ENGINEER", "ANALYST", "REVENUE_MANAGER", "AUDITOR"))]
)

class DataFreshnessOut(BaseModel):
    domain: str
    last_capture_at: str | None
    last_import_at: str | None
    record_count: int
    status: str

@router.get("/freshness", response_model=List[DataFreshnessOut])
def get_data_freshness(
    db: Session = Depends(get_db),
    user_roles: list[str] = Depends(get_user_roles),
    user_identity: str = Depends(get_user_identity),
):
    """Calculate data freshness for all modules based on actual data."""
    results = []
    now = datetime.now(timezone.utc)
    stale_threshold = now - timedelta(hours=48) # 48h for CPI typical latency

    def get_module_stats(model, tenant_code, domain_name):
        q_count = select(func.count(model.id)).where(model.tenant_code == tenant_code)
        count = db.scalar(q_count) or 0
        
        q_import = select(func.max(model.loaded_at)).where(model.tenant_code == tenant_code)
        last_import = db.scalar(q_import)
        
        q_capture = select(model.cap_date, model.cap_time).where(model.tenant_code == tenant_code).order_by(desc(model.cap_date), desc(model.cap_time)).limit(1)
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
            last_capture_at=cap_str,
            last_import_at=last_import.isoformat() + "Z" if last_import else None,
            record_count=count,
            status=status
        )

    # 1. Airline CPI – JY
    if "TENANT_ADMIN" in user_roles or user_identity == "JY":
        results.append(get_module_stats(AirlineCpiSnapshot, "JY", "Airline CPI – JY"))
    
    # 2. Airline CPI – PW
    if "TENANT_ADMIN" in user_roles or user_identity == "PW":
        results.append(get_module_stats(AirlineCpiSnapshot, "PW", "Airline CPI – PW"))
        
    # 3. Cruise/Ferry CPI – FJL
    if "TENANT_ADMIN" in user_roles or user_identity == "FJL":
        results.append(get_module_stats(CflCpiSnapshot, "FJL", "Cruise/Ferry CPI – FJL"))

    return results
