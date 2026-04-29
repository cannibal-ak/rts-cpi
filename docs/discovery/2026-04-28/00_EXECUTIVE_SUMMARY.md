# CPI Project Discovery — Executive Summary

## Overview
This read-only discovery exercise mapped the current state of the Competitor Pricing Intelligence (CPI) project. The repository structure, tech stack, backend, frontend, and Superset analytics were inventoried. 

## Key Findings
- **Platform Foundation**: The core modular monolith (FastAPI + React) and Docker Compose infrastructure are deployed and stable. 
- **Authentication**: Phase 2 auth is fully merged and active, including JWTs, bcrypt hashing, account lockout (15m after 5 attempts), and forced first-time password changes.
- **Tenant Isolation**: Row-Level Security (RLS) policies are active at the database level (`002_rls_policies.py`), using `app.current_tenant` to strictly isolate data.
- **Ingestion Pipelines**: JY paired ingestion (CPI + Velocity) is implemented. However, a critical bug was identified in data attribution (see below).
- **Missing Elements**: The Phase 3 test suite is entirely missing (`apps/api/tests/` is empty). Additionally, the frontend lacks the admin UI for user and tenant management.

## Critical Architectural Issue Identified
**JY Ingestion Data Attribution Bug (Severity: High)**
The `scripts/ingest_daily.py` script hardcodes the **Skywave admin tenant UUID** (`a0000000-0000-0000-0000-000000000001`) for the JY tenant instead of JY's own canonical UUID (`dd000000-0000-0000-0000-000000000001`). Due to strict database RLS, any data ingested for JY using this script will be invisible to JY users. (See [08_OPEN_QUESTIONS.md](08_OPEN_QUESTIONS.md) for details).

## Links to Detailed Discovery Reports
- [01_PROJECT_STRUCTURE.md](01_PROJECT_STRUCTURE.md)
- [02_TECH_STACK.md](02_TECH_STACK.md)
- [03_BACKEND_MAP.md](03_BACKEND_MAP.md)
- [04_FRONTEND_MAP.md](04_FRONTEND_MAP.md)
- [05_SUPERSET_MAP.md](05_SUPERSET_MAP.md)
- [06_IMPLEMENTATION_STATUS.md](06_IMPLEMENTATION_STATUS.md)
- [07_PRINCIPLES_SCORECARD.md](07_PRINCIPLES_SCORECARD.md)
- [08_OPEN_QUESTIONS.md](08_OPEN_QUESTIONS.md)
- [09_TECH_DEBT.md](09_TECH_DEBT.md)
- [10_ROADMAP.md](10_ROADMAP.md)
