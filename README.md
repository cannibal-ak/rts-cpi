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

### First-boot setup — SMTP encryption key

The `smtp_config` table (introduced in migration 027) stores the SMTP
password as Fernet ciphertext keyed by `CPI_SMTP_ENCRYPTION_KEY`. Generate
the key once and place it in `.env` before the admin saves any SMTP
credentials:

```bash
# Generate inside the running api container (uses the installed cryptography pkg)
docker exec cpi-api-1 python -c \
  "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# Then append to .env:
#   CPI_SMTP_ENCRYPTION_KEY=<the value printed above>
```

> **Back this key up.** Losing `CPI_SMTP_ENCRYPTION_KEY` permanently
> forfeits the ability to decrypt every SMTP password stored under it —
> the admin would have to delete the `smtp_config` row and re-enter the
> credentials from scratch. Store it in the same place you keep
> `POSTGRES_PASSWORD` and `JWT_SECRET_KEY` (password manager / KMS /
> sealed envelope).

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
| `admin@rts.com` | `rts` | `admin123` |
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
| Ingestion service | `apps/api/app/ingestion/` | Filename parser, two-stage upload service (Phase A overhaul) |
| Ingestion API | `apps/api/app/api/v1/ingestion.py` | `/api/v1/ingestion/*` upload → validate → commit endpoints |
| Ingestion staging | `apps/api/data/staging/{job_id}/` | Per-job staged uploads (git-ignored) |
| Legacy data archive | `apps/api/data/legacy-folder-watch-archive/` | Pre-overhaul folder-watch CSVs preserved for rollback |
| Infrastructure | `infra/` | DB init scripts, Superset config |
| Migrations | `apps/api/alembic/` | Alembic database migrations |
| Scripts | `scripts/` | Utility and seed scripts |

## Documentation

- [MIGRATION_GUIDE.txt](MIGRATION_GUIDE.txt) — Database migration guide
- [docs/AUTH.md](docs/AUTH.md) — Authentication flow, JWT, lockout, password policy
- [docs/SECRETS.md](docs/SECRETS.md) — Secrets management and rotation
- [docs/ingestion-uuid-discovery.md](docs/ingestion-uuid-discovery.md) — Phase A: ingestion overhaul UUID-bug findings + fix
- [docs/phase-a-schema-verification.txt](docs/phase-a-schema-verification.txt) — Phase A: alembic 018 schema verification snapshot
- [docs/phase-a-smoke-test-results.md](docs/phase-a-smoke-test-results.md) — Phase A: 10/10 live JY smoke-test results
- [CONTRIBUTING.md](CONTRIBUTING.md) — Contribution guidelines

## Project Status

**Phase 2 of 7 — Real authentication (JWT + bcrypt) complete.**
