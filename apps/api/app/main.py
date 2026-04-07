"""
RTS CPI — FastAPI Application Entry Point.
Registers all routers, CORS, and startup events.
Runs Alembic migrations on startup for dev convenience.
"""

from contextlib import asynccontextmanager
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.deps import enforce_password_change
from app.routers import health, auth, airline, cfl, alerts, audit, admin, tenant, stats, superset, ingestion


@asynccontextmanager
async def lifespan(app: FastAPI):
    # In dev, Alembic migrations are run via entrypoint script.
    # Tables are created by migration 001, not create_all.
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
app.include_router(ingestion.router, dependencies=_protected)


@app.get("/")
def root():
    return {
        "service": settings.app_name,
        "version": "0.2.0",
        "docs": "/docs",
        "auth": "/api/v1/auth/login",
    }
