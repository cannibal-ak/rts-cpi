# NOTE: This module serves the System Overview page
# (health checks, tenant summaries), NOT Superset dashboards.
# File rename to admin_system.py deferred until branch
# reconciliation.

"""Admin dashboard endpoints — platform health + per-tenant data summary.

Both endpoints are guarded by ``RequirePlatformAdmin`` at the router level,
matching the other ``admin_*`` routers. main.py adds the password-change
gate via the ``_protected`` wrapper.

Endpoints
---------
- ``GET /api/v1/admin/dashboard/health``
    Probes DB, Redis, RabbitMQ, Superset, SFTP, plus the API itself. Each
    probe is wrapped in its own try/except with a short timeout so one
    slow service can't block the response.

- ``GET /api/v1/admin/dashboard/tenant-summary``
    Aggregates SFTP connection state, schedule info, latest ingestion run,
    and data freshness (reused from ``stats.compute_module_freshness``)
    for each non-platform tenant.
"""

from __future__ import annotations

import logging
import socket
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
import redis as redis_lib
from fastapi import APIRouter, Depends
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.deps import RequirePlatformAdmin
from app.models.airline import AirlineCpiSnapshot
from app.models.cfl import CflCpiSnapshot
from app.models.sftp import IngestionRun, IngestionSchedule, SftpConnection
from app.models.tenant import Tenant
from app.routers.stats import compute_module_freshness
from app.schemas.admin_dashboard import (
    PlatformHealthResponse,
    ServiceHealthItem,
    TenantDataSummary,
    TenantSummaryResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/admin/dashboard",
    tags=["Admin - Dashboard"],
    dependencies=[Depends(RequirePlatformAdmin())],
)


# Per-probe timeout in seconds. One slow service must not block the page.
_PROBE_TIMEOUT_S = 3.0

# Platform tenant slug — excluded from the tenant-summary list.
_PLATFORM_TENANT_SLUG = "rts"

# Maps tenant slug → (snapshot model, tenant_type) for the freshness query.
# tenant_code in snapshot tables is uppercased (see schemas/sftp.py note);
# tenant.slug is lowercase. Snapshot lookup uses slug.upper().
_TENANT_TYPE_BY_SLUG = {
    "jy": ("airline", AirlineCpiSnapshot),
    "pw": ("airline", AirlineCpiSnapshot),
    "fjl": ("cruise", CflCpiSnapshot),
}


def _ms(start: datetime) -> int:
    return int((datetime.now(timezone.utc) - start).total_seconds() * 1000)


def _check_database(db: Session) -> ServiceHealthItem:
    start = datetime.now(timezone.utc)
    try:
        db.execute(text("SELECT 1"))
        return ServiceHealthItem(name="Database", status="healthy", response_time_ms=_ms(start))
    except Exception as exc:  # noqa: BLE001 — surface as unhealthy
        logger.warning("dashboard health: database probe failed: %s", exc)
        return ServiceHealthItem(
            name="Database",
            status="unhealthy",
            response_time_ms=_ms(start),
            details=str(exc)[:200],
        )


def _check_redis() -> ServiceHealthItem:
    start = datetime.now(timezone.utc)
    try:
        client = redis_lib.from_url(
            settings.redis_url,
            socket_connect_timeout=_PROBE_TIMEOUT_S,
            socket_timeout=_PROBE_TIMEOUT_S,
        )
        if client.ping():
            return ServiceHealthItem(name="Redis", status="healthy", response_time_ms=_ms(start))
        return ServiceHealthItem(
            name="Redis", status="unhealthy", response_time_ms=_ms(start), details="PING returned falsy"
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("dashboard health: redis probe failed: %s", exc)
        return ServiceHealthItem(
            name="Redis",
            status="unhealthy",
            response_time_ms=_ms(start),
            details=str(exc)[:200],
        )


def _check_rabbitmq() -> ServiceHealthItem:
    """Use TCP connect on the AMQP port. The mgmt API isn't always exposed
    and we only need to know the broker is reachable, not interrogate it."""
    start = datetime.now(timezone.utc)
    host, port = "rabbitmq", 5672
    try:
        with socket.create_connection((host, port), timeout=_PROBE_TIMEOUT_S):
            return ServiceHealthItem(name="RabbitMQ", status="healthy", response_time_ms=_ms(start))
    except Exception as exc:  # noqa: BLE001
        logger.warning("dashboard health: rabbitmq probe failed: %s", exc)
        return ServiceHealthItem(
            name="RabbitMQ",
            status="unhealthy",
            response_time_ms=_ms(start),
            details=str(exc)[:200],
        )


def _check_superset() -> ServiceHealthItem:
    start = datetime.now(timezone.utc)
    url = settings.superset_url.rstrip("/") + "/health"
    try:
        resp = httpx.get(url, timeout=_PROBE_TIMEOUT_S)
        if resp.status_code == 200:
            return ServiceHealthItem(name="Superset", status="healthy", response_time_ms=_ms(start))
        return ServiceHealthItem(
            name="Superset",
            status="unhealthy",
            response_time_ms=_ms(start),
            details=f"HTTP {resp.status_code}",
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("dashboard health: superset probe failed: %s", exc)
        return ServiceHealthItem(
            name="Superset",
            status="unhealthy",
            response_time_ms=_ms(start),
            details=str(exc)[:200],
        )


def _check_sftp(db: Session) -> ServiceHealthItem:
    """SFTP has no live broker — report 'configured' iff at least one active
    connection row exists. This mirrors how the rest of the admin UI talks
    about SFTP state."""
    start = datetime.now(timezone.utc)
    try:
        active = db.scalar(
            select(func.count(SftpConnection.id)).where(SftpConnection.is_active.is_(True))
        ) or 0
        if active > 0:
            return ServiceHealthItem(
                name="SFTP",
                status="healthy",
                response_time_ms=_ms(start),
                details=f"{active} active connection(s)",
            )
        return ServiceHealthItem(
            name="SFTP",
            status="unknown",
            response_time_ms=_ms(start),
            details="No active SFTP connections configured",
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("dashboard health: sftp probe failed: %s", exc)
        return ServiceHealthItem(
            name="SFTP",
            status="unhealthy",
            response_time_ms=_ms(start),
            details=str(exc)[:200],
        )


@router.get("/health", response_model=PlatformHealthResponse)
def get_platform_health(db: Session = Depends(get_db)) -> PlatformHealthResponse:
    """Probe each platform service and return their health states."""
    services = [
        ServiceHealthItem(name="API", status="healthy", response_time_ms=0),
        _check_database(db),
        _check_redis(),
        _check_rabbitmq(),
        _check_superset(),
        _check_sftp(db),
    ]
    return PlatformHealthResponse(services=services, checked_at=datetime.now(timezone.utc))


def _freshness_status(last_capture: Optional[datetime], total_records: int) -> str:
    """fresh <24h | stale 24–72h | critical >72h | no_data when no rows."""
    if total_records == 0 or last_capture is None:
        return "no_data"
    now = datetime.now(timezone.utc)
    if last_capture.tzinfo is None:
        last_capture = last_capture.replace(tzinfo=timezone.utc)
    delta = now - last_capture
    if delta < timedelta(hours=24):
        return "fresh"
    if delta < timedelta(hours=72):
        return "stale"
    return "critical"


def _latest_run_for_tenant(db: Session, tenant_code: str) -> Optional[IngestionRun]:
    """Latest run for any schedule belonging to this tenant (case-insensitive
    tenant_code match — schedules store mixed-case codes)."""
    stmt = (
        select(IngestionRun)
        .join(IngestionSchedule, IngestionSchedule.id == IngestionRun.schedule_id)
        .where(func.upper(IngestionSchedule.tenant_code) == tenant_code.upper())
        .order_by(IngestionRun.started_at.desc())
        .limit(1)
    )
    return db.execute(stmt).scalar_one_or_none()


def _build_tenant_summary(db: Session, tenant: Tenant) -> TenantDataSummary:
    """Aggregate one tenant's card data."""
    slug = (tenant.slug or "").lower()
    tenant_type, snapshot_model = _TENANT_TYPE_BY_SLUG.get(slug, ("airline", AirlineCpiSnapshot))
    code = slug.upper()

    # SFTP — active connection for this tenant (case-insensitive)
    sftp_conn: Optional[SftpConnection] = db.execute(
        select(SftpConnection)
        .where(func.upper(SftpConnection.tenant_code) == code, SftpConnection.is_active.is_(True))
        .limit(1)
    ).scalar_one_or_none()

    # Schedule — most recent enabled schedule for this tenant
    schedule: Optional[IngestionSchedule] = db.execute(
        select(IngestionSchedule)
        .where(func.upper(IngestionSchedule.tenant_code) == code)
        .order_by(IngestionSchedule.is_enabled.desc(), IngestionSchedule.updated_at.desc())
        .limit(1)
    ).scalar_one_or_none()

    # Latest ingestion run via schedule join
    latest_run = _latest_run_for_tenant(db, code)

    # Freshness — reuse the shared helper to keep parity with /stats/freshness
    freshness = compute_module_freshness(db, snapshot_model, code, tenant.display_name)

    last_capture_dt: Optional[datetime] = None
    if freshness.last_capture_at:
        # Helper returns ISO ending with "Z". Parse permissively.
        cap_str = freshness.last_capture_at.rstrip("Z")
        try:
            last_capture_dt = datetime.fromisoformat(cap_str).replace(tzinfo=timezone.utc)
        except ValueError:
            last_capture_dt = None

    latest_data_date = None
    if freshness.report_date:
        try:
            latest_data_date = datetime.fromisoformat(freshness.report_date).date()
        except ValueError:
            latest_data_date = None

    return TenantDataSummary(
        tenant_id=tenant.id,
        tenant_name=tenant.display_name,
        tenant_type=tenant_type,
        airline_code=code,
        sftp_connected=sftp_conn is not None,
        sftp_last_pull=latest_run.started_at if latest_run else None,
        sftp_last_pull_status=latest_run.status if latest_run else None,
        latest_data_date=latest_data_date,
        last_capture_at=last_capture_dt,
        freshness_status=_freshness_status(last_capture_dt, freshness.record_count),
        total_records=freshness.record_count,
        next_scheduled_run=schedule.next_run_at if schedule else None,
        schedule_enabled=bool(schedule.is_enabled) if schedule else False,
        last_run_status=latest_run.status if latest_run else None,
        last_run_id=latest_run.id if latest_run else None,
        last_run_at=latest_run.started_at if latest_run else None,
    )


@router.get("/tenant-summary", response_model=TenantSummaryResponse)
def get_tenant_summary(db: Session = Depends(get_db)) -> TenantSummaryResponse:
    """Aggregated per-tenant data for the admin Home page cards."""
    tenants = (
        db.execute(
            select(Tenant)
            .where(Tenant.slug != _PLATFORM_TENANT_SLUG, Tenant.is_active.is_(True))
            .order_by(Tenant.slug)
        )
        .scalars()
        .all()
    )
    return TenantSummaryResponse(tenants=[_build_tenant_summary(db, t) for t in tenants])
