# Tech Stack Inventory

## Backend
- **Framework**: FastAPI (>=0.111, <1)
- **Runtime**: Python >=3.11
- **Database ORM**: SQLAlchemy (>=2.0, <3)
- **Migrations**: Alembic (>=1.13, <2)
- **Validation**: Pydantic (>=2.7, <3)
- **Auth**: python-jose[cryptography] (>=3.3, <4), passlib[bcrypt] (>=1.7, <2)
- **Server**: Uvicorn (>=0.29, <1)

## Frontend
- **Framework**: React 18.3.1
- **Build Tool**: Vite 5.4.14
- **UI Components**: MUI (Material-UI) 5.16.14
- **State/Routing**: React Router 6.22.0
- **Analytics Integration**: @superset-ui/embedded-sdk 0.3.0

## Database
- **Engine**: PostgreSQL 16-alpine
- **Current Alembic Head**: `016_canonical_demo_users.py`

## Analytics (Superset)
- **Version**: Apache Superset 3.1.0
- **Config**: Custom `superset_config.py` mounted into container
- **Security Mods**: Embedded Superset enabled, CORS configured for frontend IPs, Public role set to "Gamma", Guest tokens utilized.

## Docker & Orchestration
- Managed via `docker-compose.yml` with 6 services.
- Profiles: `dev` for web, `superset` for BI engine.
