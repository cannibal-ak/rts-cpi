"""
RTS CPI — FastAPI Application Entry Point.
Registers all routers, CORS, and startup events.
Runs Alembic migrations on startup for dev convenience.
"""

import logging
from contextlib import asynccontextmanager
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.deps import enforce_password_change
from app.routers import health, auth, password_reset, airline, cfl, alerts, audit, admin, tenant, stats, superset
from app.routers import (
    admin_ingestion_runs,
    admin_ingestion_schedules,
    admin_sftp_connections,
    admin_password_management,
    admin_dashboard,
)
from app.api.v1 import ingestion as ingestion_v2
from app.services import redbeat_sync

# Lifespan logs route through uvicorn.error because app.* loggers
# don't propagate in this container (no app-level basicConfig).
# Revisit if/when a unified logging config is introduced.
logger = logging.getLogger("uvicorn.error")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # In dev, Alembic migrations are run via entrypoint script.
    # Tables are created by migration 001, not create_all.
    try:
        with SessionLocal() as db:
            summary = redbeat_sync.reconcile_all(db)
        logger.info(
            "redbeat reconcile on startup: added=%d removed=%d kept=%d",
            len(summary["added"]),
            len(summary["removed"]),
            len(summary["kept"]),
        )
    except Exception as e:
        logger.warning(
            "redbeat reconcile failed on startup (continuing): %s", e,
        )
    yield

app = FastAPI(
    title=settings.app_name,
    version="0.2.0",
    description="Competitor Pricing Intelligence API — modular monolith with tenant isolation",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Public routers (no auth required)
app.include_router(health.router)

# Auth router (handles its own auth)
app.include_router(auth.router)

# Password reset endpoints — unauthenticated by design (user is locked out).
# Protected by per-email rate limits and per-token attempt limits.
app.include_router(password_reset.router)

# Protected routers — JWT + forced password change enforced
_protected = [Depends(enforce_password_change)]
app.include_router(airline.router, dependencies=_protected)
app.include_router(cfl.router, dependencies=_protected)
app.include_router(alerts.router, dependencies=_protected)
app.include_router(audit.router, dependencies=_protected)
app.include_router(admin.router, dependencies=_protected)
app.include_router(tenant.router, dependencies=_protected)
app.include_router(stats.router, dependencies=_protected)
app.include_router(superset.router, dependencies=_protected)

# Phase 3 SFTP-driven ingestion admin routers. Each declares
# RequirePlatformAdmin() at the APIRouter level; the _protected
# wrapper here adds the password-change gate (same pattern as
# admin.router above).
app.include_router(admin_sftp_connections.router, dependencies=_protected)
app.include_router(admin_ingestion_schedules.router, dependencies=_protected)
app.include_router(admin_ingestion_runs.router, dependencies=_protected)

# Admin Password Management — list users, reset code queue, generate code,
# force reset. Router-level RequirePlatformAdmin + the _protected
# password-change gate mirror the other admin routers above.
app.include_router(admin_password_management.router, dependencies=_protected)

# Admin Dashboard — platform health + per-tenant data summary for the
# admin Home page. Router-level RequirePlatformAdmin + _protected gate
# match the other admin routers.
app.include_router(admin_dashboard.router, dependencies=_protected)

# Phase A ingestion router — Data Ops (manual upload + jobs view).
# Admin-only; uses _protected pattern like every other admin router.
app.include_router(ingestion_v2.router, dependencies=_protected)

@app.get("/")
def root():
    return {
        "service": settings.app_name,
        "version": "0.2.0",
        "docs": "/docs",
        "auth": "/api/v1/auth/login",
    }
