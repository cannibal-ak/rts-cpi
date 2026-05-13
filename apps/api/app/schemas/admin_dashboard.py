"""Pydantic schemas for the admin dashboard endpoints.

Back the two endpoints in ``app/routers/admin_dashboard.py``:
  - ``GET /api/v1/admin/dashboard/health``         → PlatformHealthResponse
  - ``GET /api/v1/admin/dashboard/tenant-summary`` → TenantSummaryResponse
"""

from datetime import date, datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel


class ServiceHealthItem(BaseModel):
    """Health status of one platform service."""

    name: str  # "API" | "Database" | "Redis" | "RabbitMQ" | "Superset" | "SFTP"
    status: str  # "healthy" | "unhealthy" | "unknown"
    response_time_ms: Optional[int] = None
    details: Optional[str] = None


class PlatformHealthResponse(BaseModel):
    services: List[ServiceHealthItem]
    checked_at: datetime


class TenantDataSummary(BaseModel):
    """Enhanced tenant card data — one entry per non-platform tenant."""

    tenant_id: UUID
    tenant_name: str
    tenant_type: str  # "airline" | "cruise"
    airline_code: str  # "JY" | "PW" | "FJL"

    # SFTP status
    sftp_connected: bool
    sftp_last_pull: Optional[datetime] = None
    sftp_last_pull_status: Optional[str] = None  # mirrors latest ingestion_run.status

    # Data freshness
    latest_data_date: Optional[date] = None       # actual file/report date
    last_capture_at: Optional[datetime] = None    # when it was ingested
    freshness_status: str  # "fresh" | "stale" | "critical" | "no_data"
    total_records: int

    # Schedule info
    next_scheduled_run: Optional[datetime] = None
    schedule_enabled: bool

    # Last ingestion result
    last_run_status: Optional[str] = None  # e.g. "SUCCESS" | "FAILED"
    last_run_id: Optional[UUID] = None
    last_run_at: Optional[datetime] = None


class TenantSummaryResponse(BaseModel):
    tenants: List[TenantDataSummary]
