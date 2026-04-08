# RTS CPI — Cost Performance Intelligence

Multi-tenant, compliance-ready cost performance analytics platform for airline and rail freight operations, built on RTS enterprise principles.

## Architecture Overview

CPI follows a microservices architecture orchestrated via Docker Compose. A FastAPI backend enforces PostgreSQL Row-Level Security (RLS) for tenant isolation, exposes a RESTful API consumed by a React/Vite frontend, and delegates analytics to embedded Apache Superset dashboards. RabbitMQ handles asynchronous ingestion jobs; Redis provides caching and session storage.

## Tech Stack

| Layer | Technology | Purpose |
|---|---|---|
| API | FastAPI (Python) | REST endpoints, RBAC, RLS enforcement |
| Frontend | React 18 + Vite | SPA with MUI components |
| Database | PostgreSQL 16 | System of record, RLS-based multi-tenancy |
| Analytics | Apache Superset | Embedded dashboards and ad-hoc analysis |
| Messaging | RabbitMQ | Async job queue (data ingestion, notifications) |
| Cache | Redis | Caching, rate limiting, session store |
| Orchestration | Docker Compose | Local and production container orchestration |

## Quick Start

```bash
# 1. Clone the repository
git clone <repo-url> && cd CPI

# 2. Set up environment
cp .env.example .env
# Edit .env with your values (see docs/SECRETS.md for guidance)

# 3. Start all services
docker compose up -d

# 4. Access the application
# API:       http://localhost:8000
# Frontend:  http://localhost:5173
# Superset:  http://localhost:8088
```

## Environment Setup

1. Copy `.env.example` to `.env`.
2. Replace placeholder values with real credentials (see [docs/SECRETS.md](docs/SECRETS.md) for generation commands).
3. Never commit `.env` to version control.

## Authentication

Phase 2 uses real JWT authentication with bcrypt-hashed passwords and forced
first-login password change. See [docs/AUTH.md](docs/AUTH.md) for the full
authentication flow, token lifetime, lockout policy, and password requirements.

### Canonical Demo Users

Migration 016 seeds 4 canonical users with temporary passwords. All users
**must change their password on first login** (12+ chars, mixed case, digit,
special character).

| Email | Tenant | Temp Password |
|---|---|---|
| `admin@skywave.com` | `skywave` | `admin123` |
| `jy@airline.com` | `jy` | `airline123` |
| `pw@airline.com` | `pw` | `airline123` |
| `fjl@cruise.com` | `fjl` | `cruise123` |

```bash
# Verify passwords are seeded (idempotent)
docker compose exec api python scripts/seed_auth_passwords.py
```

RBAC roles available: `TENANT_ADMIN`, `DATA_ENGINEER`, `ANALYST`, `REVENUE_MANAGER`, `AUDITOR`, `AIRLINE_USER`, `CRUISE_USER`.

Default Superset credentials: `admin` / (set in `.env`).

## Module Map

| Module | Path | Description |
|---|---|---|
| API core | `apps/api/app/core/` | Configuration, database, RLS middleware |
| API models | `apps/api/app/models/` | SQLAlchemy models (tenant-scoped) |
| API routers | `apps/api/app/routers/` | REST endpoints |
| API schemas | `apps/api/app/schemas/` | Pydantic request/response schemas |
| API services | `apps/api/app/services/` | Business logic layer |
| Airline JY/PW | `apps/api/app/routers/` | JY and PW airline cost modules |
| CFL FJL | `apps/api/app/routers/` | CFL freight journal line ingestion |
| Frontend | `apps/web/src/` | React SPA (pages, components, hooks) |
| Data ingestion | `apps/api/data/` | CSV/XLSX staging area (git-ignored) |
| Infrastructure | `infra/` | DB init scripts, Superset config |
| Migrations | `apps/api/alembic/` | Alembic database migrations |
| Scripts | `scripts/` | Utility and seed scripts |

## Documentation

- [MIGRATION_GUIDE.txt](MIGRATION_GUIDE.txt) — Database migration guide
- [docs/AUTH.md](docs/AUTH.md) — Authentication flow, JWT, lockout, password policy
- [docs/SECRETS.md](docs/SECRETS.md) — Secrets management and rotation
- [CONTRIBUTING.md](CONTRIBUTING.md) — Contribution guidelines

## Project Status

**Phase 2 of 7 — Real authentication (JWT + bcrypt) complete.**
