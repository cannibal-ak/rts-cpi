"""
RTS CPI — FastAPI Application Entry Point.
Registers all routers, CORS, and startup events.
Runs Alembic migrations on startup for dev convenience.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.routers import health, airline, cfl, alerts, audit, admin, tenant, stats, superset, ingestion



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

app.include_router(health.router)
app.include_router(airline.router)
app.include_router(cfl.router)
app.include_router(alerts.router)
app.include_router(audit.router)
app.include_router(admin.router)
app.include_router(tenant.router)
app.include_router(stats.router)
app.include_router(superset.router)
app.include_router(ingestion.router)


@app.get("/")
def root():
    return {
        "service": settings.app_name,
        "version": "0.2.0",
        "docs": "/docs",
        "tenant_header": "X-Tenant-ID",
        "demo_tenants": {
            "acme_airways": "a0000000-0000-0000-0000-000000000001",
            "baltic_ferries": "b0000000-0000-0000-0000-000000000002",
        },
    }
