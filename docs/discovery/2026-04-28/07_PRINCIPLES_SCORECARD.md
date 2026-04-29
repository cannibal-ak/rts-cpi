# RTS Principles Compliance Scorecard

- **A1 Microservices**: [PARTIAL] Platform acts as a modular monolith (single FastAPI app) rather than independent deployable microservices.
- **A2 Modular & à-la-carte**: [COMPLIANT] Features controlled dynamically via `TenantFeature` model.
- **A3 Multi-tenancy**: [COMPLIANT] Strict Row-Level Security (RLS) in PostgreSQL.
- **A4 Compliance by design**: [PARTIAL] Audit events table exists, but log export functionality is unverified.
- **A5 RBAC**: [COMPLIANT] Implemented via `RoleBinding` model and FastAPI dependencies.
- **A6 Secure login**: [COMPLIANT] Bcrypt, account lockout, and forced password reset implemented.
- **A7 Platform agnostic**: [COMPLIANT] Fully dockerized Python/React stack.
- **A8 Universal deployment**: [COMPLIANT] Standardized `docker-compose.yml`.
- **A9 Enterprise-grade & 100% production-ready**: [GAP] Test suite is completely absent. User/Tenant admin UI is missing.
