# Project Structure

## Monorepo Layout
```text
CPI/
+--- apps/
|   +--- api/               # FastAPI backend service
|   \--- web/               # React + Vite frontend SPA
+--- assets/                # Static assets (RTS_Logo.png)
+--- docs/                  # Documentation
+--- infra/                 # Infrastructure configs (init-db.sql, superset_config.py)
\--- scripts/               # Global shell scripts (check_rls.sh, reset_data.sh)
```

## Service Map
- **cpi-api-1** (FastAPI): Exposes REST APIs, handles business logic, auth, and triggers ingestion.
- **cpi-web-1** (Vite/React/Nginx): Frontend application serving the user interface.
- **cpi-postgres-1** (PostgreSQL 16): Primary datastore, enforcing RLS.
- **cpi-redis-1** (Redis): Caching layer.
- **cpi-rabbitmq-1** (RabbitMQ): Message broker (available, though ingestion runs synchronously).
- **cpi-superset-1** (Apache Superset 3.1.0): Embedded analytics and dashboard delivery.
