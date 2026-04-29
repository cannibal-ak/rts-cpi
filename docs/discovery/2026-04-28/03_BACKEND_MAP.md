# Backend Map

## Routers & Endpoints
- **Public**: `health.py`, `auth.py` (handles own auth)
- **Protected** (JWT + password change enforced): `airline.py`, `cfl.py`, `alerts.py`, `audit.py`, `admin.py`, `tenant.py`, `stats.py`, `superset.py`, `ingestion.py`
- **Role Gates**: Enforced via `RequireRoles` (e.g., `TENANT_ADMIN`, `DATA_ENGINEER`, `ANALYST`) and `RequirePlatformAdmin` in `deps.py`.

## Models
- **Auth & Multi-tenancy**: `Tenant`, `AppUser`, `RoleBinding`, `TenantFeature`
- **Data Domains**: `AirlineCpiSnapshot`, `CflCpiSnapshot`, `jy_velocity_snapshot`
- **Jobs & Audit**: `ImportJob`, `ImportBatch`, `IngestError`, `AuditEvent`

## Migrations & Schema
Head is at **016**:
- `001_initial_schema.py`: Schema setup
- `002_rls_policies.py`: Core RLS policies (`USING (tenant_id::text = coalesce(nullif(current_setting('app.current_tenant', true), ''), ...))`)
- `016_canonical_demo_users.py`: Establishes canonical tenants (`skywave`, `jy`, `pw`, `fjl`) and bcrypt user hashes.

## Auth Flow
Login (`/api/v1/auth/login`) -> Validates bcrypt hash -> Checks lockout -> Issues JWT and Refresh Token. Subsequent requests require `must_change_password=False`, otherwise they are blocked by `enforce_password_change` middleware (except `/change-password`).

## Ingestion Pipelines
- **Trigger**: `POST /api/v1/ingestion/ingest` runs `scripts/ingest_daily.py` synchronously.
- **Parser & Writer**: Script parses CSV/XLSX. JY flow requires a matched pair of Pricing and Velocity files. Loads data into `airline_cpi_snapshot` and `jy_velocity_snapshot`.
