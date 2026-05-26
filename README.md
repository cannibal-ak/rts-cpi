# Altitude CPI — Competitor Pricing Intelligence
> **Revenue Technology Services (RTS)** | Internal Platform | Multi-Tenant SaaS
Altitude CPI is a pricing analytics platform that ingests competitor fare data for airline and cruise tenants, processes it through automated pipelines, and surfaces insights via interactive Superset dashboards and a React frontend.
---
## Architecture
```
┌─────────────┐     ┌─────────────┐     ┌──────────────┐
│  cpi-web     │     │  cpi-api     │     │  cpi-superset │
│  React/Vite  │────▶│  FastAPI     │────▶│  Apache 3.1   │
│  :9090       │     │  :8000       │     │  :8088        │
└─────────────┘     └──────┬───────┘     └──────────────┘
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
        ┌──────────┐ ┌──────────┐ ┌──────────┐
        │ Postgres │ │  Redis   │ │ RabbitMQ │
        │  :5432   │ │  :6379   │ │  :5672   │
        └──────────┘ └──────────┘ └──────────┘
```
All services run as Docker Compose containers on host **IN1PSDOCKER** (192.168.101.10), bind-mounted to `/home/ankitprajapati/CPI`.
---
## Quick Start
```bash
# SSH into the host
ssh ankitprajapati@192.168.101.10
# Navigate to project
cd /home/ankitprajapati/CPI
# Check status of all containers
docker compose ps
# Start all services (if stopped)
docker compose up -d
# Stop all services
docker compose down
# View logs (last 50 lines, all services)
docker compose logs --tail=50
# View logs for a specific service
docker compose logs --tail=50 cpi-api-1
# Restart a single service
docker compose restart cpi-api-1
# Rebuild after code changes
docker compose up -d --build
```
---
## Services & Access
| Service | URL | Credentials |
|---------|-----|-------------|
| Frontend (Web App) | http://192.168.101.10:9090 | Use login credentials below |
| API Docs (Swagger) | http://192.168.101.10:8000/docs | Open access |
| Superset Dashboards | http://192.168.101.10:8088 | admin / admin |
| RabbitMQ Management | http://192.168.101.10:15672 | guest / guest |
| PostgreSQL | 192.168.101.10:5432 | User: `cpi` / Pass: `cpi_secret` / DB: `cpi_db` |
| Redis | 192.168.101.10:6379 | No auth |
---
## Application Login Credentials
The platform uses JWT authentication with bcrypt password hashing. First login forces a mandatory password change. Account lockout activates after repeated failed attempts.
| Role | Tenant | Email (Login ID) | Password |
|------|--------|-----------------|----------|
| Super Admin | — | admin@rts.com | Rtsadmin@123 |
| Airline | JY | jy@airline.com | JYairline@123 |
| Airline | PW | pw@airline.com | PWairline@123 |
| Cruise | FJL | fjl@cruise.com | FJLcruise@123 |
---
## Data Ingestion
### File Naming Conventions
The ingestion pipeline uses regex-based filename matching. **Files that don't match the exact pattern are silently skipped** — this is the most common failure mode.
**CPI / Pricing files (xlsx only):**
| Tenant | Format | Example |
|--------|--------|---------|
| JY | `JY_DDMMYY.xlsx` | `JY_051125.xlsx` |
| PW | `PW_DDMMYY.xlsx` | `PW_051125.xlsx` |
**Velocity files (csv or xlsx):**
| Tenant | Format | Example |
|--------|--------|---------|
| JY | `JY_VL_DDMMYY.{csv\|xlsx}` | `JY_VL_051125.csv` |
| PW | `PW_VL_DDMMYY.{csv\|xlsx}` | `PW_VL_051125.xlsx` |
- Extension is case-insensitive (.csv, .CSV, .xlsx, .XLSX)
- Prefix must be uppercase (JY_VL_, PW_VL_)
### SFTP Ingestion Paths
Files land on the host via SFTP and are picked up by the ingestion pipeline:
```
/home/ankitprajapati/CPI/dev-sftp-mount/jy/    ← JY files
/home/ankitprajapati/CPI/dev-sftp-mount/pw/    ← PW files
```
### Triggering Ingestion
Data ingestion is triggered via the admin UI (login as `admin@rts.com`). The Celery worker (`cpi-worker`) and beat scheduler (`cpi-beat`) handle background processing via RabbitMQ.
---
## Project Structure
```
CPI/
├── apps/
│   ├── api/              # FastAPI backend
│   │   ├── app/          # Application code
│   │   │   ├── routers/  # API endpoints
│   │   │   ├── models/   # SQLAlchemy models
│   │   │   ├── schemas/  # Pydantic schemas
│   │   │   └── services/ # Business logic
│   │   ├── alembic/      # Database migrations
│   │   └── data/         # Ingestion data directories
│   └── web/              # React/Vite frontend
│       └── src/
│           ├── api/      # API client
│           ├── components/
│           └── pages/
├── infra/
│   └── superset_config.py  # Superset config (custom color schemes)
├── nginx/                # Reverse proxy configuration
├── docker-compose.yml    # Service orchestration
├── .env                  # Environment variables (secrets)
└── .gitignore
```
---
## Database
```bash
# Connect to the database
docker exec -it cpi-postgres-1 psql -U cpi -d cpi_db
# Run migrations (after code changes)
docker exec -it cpi-api-1 alembic upgrade head
# Check current migration version
docker exec -it cpi-api-1 alembic current
```
The database uses Row-Level Security (RLS) for tenant data isolation. Each tenant's data is scoped by `airline_code` filters.
---
## Superset Dashboards
Three dashboards are configured:
| ID | Dashboard | Tenant | Key Feature |
|----|-----------|--------|-------------|
| 1 | JY CPI | JY | Ref vs Competitor fare analysis |
| 2 | FJL CPI | FJL | 4-tab layout (Overview, By Dep/Cap Date, Competitive Monitor) |
| 3 | PW CPI | PW | 8 charts with custom precisionAir color scheme |
Superset login: `admin / admin` at http://192.168.101.10:8088
The custom `precisionAir` color scheme is defined in `infra/superset_config.py` and must not be removed.
---
## Troubleshooting
**Container won't start:**
```bash
docker compose logs <service-name>    # Check for errors
docker compose up -d --build          # Rebuild from source
```
**API returns 500 errors:**
```bash
docker exec -it cpi-api-1 /bin/bash   # Enter the container
cat /tmp/api.log                       # Check application logs
```
**Database connection issues:**
```bash
docker exec -it cpi-postgres-1 pg_isready -U cpi
```
**Ingestion files not processing:**
1. Verify filename matches the exact pattern (see naming conventions above)
2. Check the Celery worker logs: `docker compose logs --tail=100 cpi-worker`
3. Verify RabbitMQ is healthy: http://192.168.101.10:15672
**Superset dashboard not loading:**
```bash
docker compose restart cpi-superset-1
```
**Web app shows "unhealthy":**
This is a known benign issue — the Docker healthcheck probes the wrong internal port. The web app is functional; access it at http://192.168.101.10:9090 to confirm.
---
## Source Code
| Item | Detail |
|------|--------|
| Repository | `github.com/cannibal-ak/rts-cpi` (private) |
| Branch | `master` |
| Clone | `git clone git@github.com:cannibal-ak/rts-cpi.git` |
---
## Configuration
All runtime configuration is in the `.env` file at the project root. This file is gitignored and contains database credentials, API keys, and service connection strings. **Do not commit `.env` to version control.**
Key environment variables are consumed by `docker-compose.yml` and passed to the containers at startup.
---
*Altitude CPI v2.0 — Revenue Technology Services (RTS) — Internal Use Only*
