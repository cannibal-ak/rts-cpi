"""
Superset configuration for local dev.

Connects to the same Postgres instance as the CPI app,
but uses a separate schema for Superset's own metadata.
"""
import os

# ── Superset metadata DB ──
# Use SQLite for Superset's own metadata (simplest for local dev)
SQLALCHEMY_DATABASE_URI = "sqlite:////app/superset_home/superset.db"

# ── Secret key ──
SECRET_KEY = os.environ.get("SUPERSET_SECRET_KEY", "rts-cpi-local-dev-key-change-in-prod")

# ── Feature flags ──
FEATURE_FLAGS = {
    "ENABLE_TEMPLATE_PROCESSING": True,
    "EMBEDDED_SUPERSET": True,              # Allow dashboard embedding
    "EMBEDDABLE_CHARTS": True,              # Allow chart embeds
    "DASHBOARD_VIRTUALIZATION": True,       # Performance
}

# ── Guest token / embedding auth ──
GUEST_ROLE_NAME = "Gamma"                   # Role assigned to guest-token users
GUEST_TOKEN_JWT_SECRET = SECRET_KEY         # Sign guest JWTs with the same secret
GUEST_TOKEN_JWT_EXP_SECONDS = 600           # 10-minute guest token lifetime
GUEST_TOKEN_HEADER_NAME = "X-GuestToken"

# ── CSRF and embedding ──
WTF_CSRF_ENABLED = False          # Disable for local dev API access
ENABLE_CORS = True
CORS_OPTIONS = {
    "origins": ["http://localhost:5173", "http://localhost:8080", "http://localhost:3000", "http://192.168.101.10:8080", "http://192.168.101.10:9090", "http://192.168.101.10:5173"],
    "supports_credentials": True,
    "allow_headers": ["Authorization", "Content-Type", "X-CSRFToken", "X-Tenant-ID", "X-User-Identity", "X-User-Roles"],
}

# ── Allow iframe embedding from CPI frontend ──
HTTP_HEADERS = {
    "X-Frame-Options": "ALLOWALL",
}
TALISMAN_ENABLED = False  # Disable Content-Security-Policy for local dev

# ── Allow public dashboards (no login required for iframe) ──
PUBLIC_ROLE_LIKE = "Gamma"

# ── Default database connection (CPI Postgres) ──
SQLALCHEMY_EXAMPLES_URI = None     # Don't load example data

# Superset needs a manual database connection setup
# via the UI or CLI pointing to:
#   postgresql://cpi_app:cpi_app_secret@postgres:5432/cpi_db
# with engine_params:
#   {"connect_args": {"options": "-c app.current_tenant=<tenant_uuid>"}}
# This is documented in the SupersetPage setup guide.

