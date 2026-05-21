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


# ── Custom categorical color palettes (RTS CPI brand) ──
# Color ORDER matters: standalone Chart-view rendering does NOT apply per-series
# label_colors for metric-only charts (charts where the "series" comes from the
# metric label, not a groupby dimension). Those charts use palette[index] in
# legend order. Most PW charts are this kind, with two metrics sorted by
# descending sum, so the higher-value series (typically comp_* or forecasted_*)
# gets palette[0] and the lower-value series (typically ref_* or actual_*) gets
# palette[1]. We therefore put forest green at [0] and gold at [1] so the
# standalone view visually matches the dashboard view, which DOES honor
# label_colors (comp_* = green, ref_* = gold). See discussion 2026-05-21.
EXTRA_CATEGORICAL_COLOR_SCHEMES = [
    {
        "id": "rts_cpi_palette",
        "description": "RTS CPI Brand Palette",
        "label": "RTS CPI",
        "isDefault": False,
        "colors": [
            "#2B6B2B",  # forest green — comp_* metrics (also forecasted leader)
            "#C5981B",  # gold — ref_* / actual / single-metric KPIs
            "#3D8B3D",  # medium green — secondary green accent
            "#D4652F",  # orange — TC carrier accent
            "#E4049C",  # pink — Coa carrier
            "#8B5CF6",  # purple — KQ carrier
            "#1A6B8A",  # teal — Fli carrier
            "#06B6D4",  # cyan — fallback
            "#64748B",  # slate — fallback
            "#0070C0",  # blue — fallback
        ],
    },
]

# ── Gold-first variant of rts_cpi_palette ──
# For single-metric KPI charts (capacity, current_booking, etc.) where
# label_colors maps the metric to gold (#C5981B). Standalone Chart-view
# can't honor label_colors for metric-only charts, so these charts pick
# color_scheme=rts_cpi_palette_kpi instead, putting gold at palette[0].
EXTRA_CATEGORICAL_COLOR_SCHEMES = EXTRA_CATEGORICAL_COLOR_SCHEMES + [
    {
        "id": "rts_cpi_palette_kpi",
        "description": "RTS CPI Palette — gold-first variant for single-metric KPIs",
        "label": "RTS CPI (KPI)",
        "isDefault": False,
        "colors": [
            "#C5981B",  # gold — primary for own-airline KPI metrics
            "#2B6B2B",  # forest green — secondary
            "#3D8B3D",  # medium green
            "#D4652F",  # orange
            "#E4049C",  # pink
            "#8B5CF6",  # purple
            "#1A6B8A",  # teal
            "#06B6D4",  # cyan
            "#64748B",  # slate
            "#0070C0",  # blue
        ],
    },
]


# ── Cache-bust for bind-mounted patched JS chunks ─────────────────────
# Superset serves /static/assets/* with Cache-Control: public, max-age=31536000
# (1 year). When we bind-mount a patched chunk at the same filename, the hash
# in the URL is unchanged, so browsers serve the cached old content forever.
# This after_request hook overrides Cache-Control for the specific patched
# files only — every other asset keeps its long cache for performance.
_PATCHED_CHUNK_PATHS = {
    "/static/assets/3871.c687a6d83eaaee71a216.entry.js",
}

def _no_cache_for_patched_chunks(response):
    from flask import request
    if request.path in _PATCHED_CHUNK_PATHS:
        response.headers["Cache-Control"] = "no-cache, must-revalidate"
        response.headers.pop("Expires", None)
    return response

def FLASK_APP_MUTATOR(app):
    app.after_request(_no_cache_for_patched_chunks)


# ── interCaribbean + RTS branded palette (chart series colors) ──
EXTRA_CATEGORICAL_COLOR_SCHEMES = EXTRA_CATEGORICAL_COLOR_SCHEMES + [
    {
        "id": "ic_branded",
        "description": "interCaribbean Airways branded palette",
        "label": "interCaribbean Branded",
        "isDefault": False,
        "colors": [
            "#049CFC",  # ocean near — JY reference
            "#E4049C",  # heritage magenta
            "#8CD404",  # fertile green
            "#04049C",  # ocean deep
            "#F59E0B",  # amber
            "#06B6D4",  # cyan
            "#8B5CF6",  # purple
            "#64748B",  # slate
        ],
    },
]

# ── Fjord Line branded palette (FJL dashboard) ──
EXTRA_CATEGORICAL_COLOR_SCHEMES = EXTRA_CATEGORICAL_COLOR_SCHEMES + [
    {
        "id": "fjl_branded",
        "description": "Fjord Line branded red palette",
        "label": "Fjord Line Branded",
        "isDefault": False,
        "colors": [
            "#E53935",  # vibrant red — primary
            "#FF7043",  # coral
            "#EF5350",  # medium red
            "#F44336",  # standard red
            "#FF8A65",  # peach
            "#FFAB91",  # light salmon
            "#D32F2F",  # deeper red — contrast
            "#FF5252",  # bright red accent
            "#78909C",  # blue-gray — Sold Out etc.
            "#B0BEC5",  # light gray
        ],
    },
]

# ── Explore form_data cache (per-open snapshot) ──
# Standalone /explore/ loads via ?form_data_key=<uuid> which reads from this
# cache instead of the chart's persisted params/query_context. Default TTL
# is days, which makes stale snapshots outlive any backend chart edits.
# Short-circuit that by expiring entries quickly (60s) so per-open snapshots
# always rebuild from the live chart definition.
EXPLORE_FORM_DATA_CACHE_CONFIG = {
    "CACHE_TYPE": "SupersetMetastoreCache",
    "CACHE_DEFAULT_TIMEOUT": 60,
    "REFRESH_TIMEOUT_ON_RETRIEVAL": True,
}
