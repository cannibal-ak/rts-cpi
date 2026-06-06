"""Superset guest-token endpoint for embedded dashboard launch.

Flow:
  1. Frontend calls GET /api/v1/superset/guest-token?dashboard_id=1|2|3
  2. Backend validates access, looks up the dashboard config
  3. Backend authenticates to Superset (JWT) and requests a guest token
  4. Frontend receives {token, dashboard_uuid, dashboard_title}
  5. Frontend uses the Superset Embedded SDK to render the dashboard

Why UUIDs are stored here instead of fetched from the Superset API:
  Superset 3.1.0 with SQLite stores UUIDs as binary blobs. The REST API
  serializes them as null, making dynamic UUID resolution impossible.
  These UUIDs are read from `SELECT uuid FROM dashboards` inside the
  Superset container and stored here as the source of truth.
"""

import httpx
import logging
import re
from datetime import datetime
from typing import Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.database import get_db
from app.core.deps import get_user_identity, get_user_roles, is_platform_admin

logger = logging.getLogger(__name__)

# Surface lines via uvicorn — see project_logging_convention.md.
_log = logging.getLogger("uvicorn.error")

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _validate_cap_date(value: str, field: str) -> str:
    """Validate YYYY-MM-DD strings before injecting into an RLS WHERE clause.

    Why: cap_date_* params land verbatim inside a string SQL clause sent to
    Superset as part of the guest token RLS rules. A strict regex + strptime
    is the only thing keeping that from being SQLi.
    """
    if not _DATE_RE.match(value or ""):
        raise HTTPException(400, detail={"message": f"Invalid {field}: must be YYYY-MM-DD"})
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(400, detail={"message": f"Invalid {field}: not a real date"})
    return value


def _cap_date_adhoc_filters(
    cap_date_eq: Optional[str],
    cap_date_from: Optional[str],
    cap_date_to: Optional[str],
) -> list[dict]:
    """Build Superset SIMPLE adhoc_filters on cap_date, mirroring the guest-token
    RLS semantics exactly: single day -> ``cap_date == eq``; range ->
    ``cap_date >= from`` AND ``cap_date <= to`` (inclusive). Single day wins if
    both are supplied. Values are validated YYYY-MM-DD (same guard as the RLS
    path). Returns [] when no cap_date params were supplied — callers treat that
    as a 400.
    """
    def _f(op: str, val: str) -> dict:
        return {
            "clause": "WHERE",
            "subject": "cap_date",
            "operator": op,
            "comparator": val,
            "expressionType": "SIMPLE",
        }

    if cap_date_eq:
        _validate_cap_date(cap_date_eq, "cap_date_eq")
        return [_f("==", cap_date_eq)]
    if cap_date_from and cap_date_to:
        _validate_cap_date(cap_date_from, "cap_date_from")
        _validate_cap_date(cap_date_to, "cap_date_to")
        if cap_date_from > cap_date_to:
            raise HTTPException(400, detail={"message": "cap_date_from must be <= cap_date_to"})
        return [_f(">=", cap_date_from), _f("<=", cap_date_to)]
    return []

router = APIRouter(prefix="/api/v1/superset", tags=["superset"])

# ── Dashboard registry ──────────────────────────────────────
# Each entry maps a short app-level ID to its Superset metadata.
# To update: run inside the superset container:
#   python3 -c "
#     import sys, uuid; sys.path.insert(0,'/app')
#     from superset.app import create_app; app=create_app()
#     with app.app_context():
#       from superset import db; from sqlalchemy import text
#       for r in db.session.execute(text('SELECT id,dashboard_title,uuid FROM dashboards')):
#         u = uuid.UUID(bytes=r[2]) if isinstance(r[2],bytes) else r[2]
#         print(f'{r[0]}: {r[1]} -> {u}')
#   "

DASHBOARDS = {
    "1": {
        "title": "Airline CPI JY Dashboard",
        "superset_id": 1,                                          # numeric ID inside Superset
        "uuid": "09306f15-d655-49e5-b58b-94ae069f562a",           # dashboards.uuid
        "embedded_uuid": "163e8222-1e54-4ba7-8dab-9c2f60714731",  # embedded_dashboards.uuid (for SDK)
        "domain": "airline",
        "tenant": "JY",
    },
    "2": {
        "title": "Airline CPI PW Dashboard",
        "superset_id": 3,                                          # Superset ID=3 (not 2!)
        "uuid": "8ed3397b-5a40-4f0b-aacf-ed48445cda97",
        "embedded_uuid": "900e298e-d8f9-40c0-9a72-b10517d7a8b9",
        "domain": "airline",
        "tenant": "PW",
    },
    "3": {
        "title": "Cruise/Ferry CPI Dashboard",
        "superset_id": 2,                                          # Superset ID=2 (not 3!)
        "uuid": "fed83fe0-2080-4c00-b568-dfe150e64cd9",
        "embedded_uuid": "f22acf01-088c-4110-8be3-191bb4a44613",
        "domain": "cfl",
        "tenant": "FJL",
    },
    "4": {
        "title": "Airline CPI ALT Dashboard",
        "superset_id": 5,                                          # Superset ID=5
        "uuid": "df9365eb-a4c2-47bd-bc2a-ee6a925954fa",
        "embedded_uuid": "04a5c649-1478-4d6e-a7b2-c81e7312c286",
        "domain": "airline",
        "tenant": "ALT",
    },
}

# Tenant -> per-tenant Superset dataset view names (for RLS filtering).
# These datasets MUST expose a tenant_code column — they get both the
# tenant_code RLS clause AND any optional cap_date clause.
# Each dashboard now has its own dedicated dataset—no cross-tenant bleed.
TENANT_TABLES = {
    "JY":  ["vw_airline_cpi_jy_snapshot"],
    "PW":  ["vw_airline_cpi_pw_snapshot"],
    "FJL": ["vw_cfl_cpi_fjl_snapshot"],
    "ALT": ["vw_airline_cpi_alt_snapshot"],
}

# Tenant -> Superset virtual/derived datasets that need cap_date RLS but
# do NOT have a tenant_code column. These are typically KPI virtual datasets
# whose inner SQL already references a per-tenant view (so tenant isolation
# is enforced by construction). They get ONLY the cap_date clause — applying
# the tenant_code clause would error ("column does not exist") because their
# SELECT does not project tenant_code.
#
# IMPORTANT: every dataset a tenant dashboard's charts query must be listed
# here (or in TENANT_TABLES). The cap_date RLS clause is keyed by dataset id,
# so any chart whose dataset is missing from these maps will silently ignore
# the DateFilterToggle's selection and return all dates.
TENANT_CAPDATE_ONLY_TABLES = {
    "JY":  [
        "jy_all_airlines_fares",
        "jy_velocity_normalized",
        "jy_pricing_recommendations",
    ],
    "PW":  [
        "pw_all_carriers_fares",
        "pw_velocity_normalized",
    ],
    "ALT": [
        "alt_all_airlines_fares",
        "alt_velocity_normalized",
        "alt_pricing_recommendations",
    ],
    "FJL": [
        "vds_cfl_cheapest_competitor",
        "FJL Pricing — Fare by Dep Date (Aggregated)",
        "FJL Pricing — Fare by Cap Date (Aggregated)",
        "FJL Pricing — Fare Monitor (Row-Level)",
    ],
}

# FJL currency scoping. FJL fares are stored as PER-CURRENCY rows (native
# scraped values, never FX-converted), so syncing the app's currency selector
# into Superset means ANDing a currency row-filter onto the cap_date RLS clause.
# Unlike cap_date (uniform `cap_date` column everywhere), the currency column
# name differs by dataset: the row-level views project `curr_code`, while the
# aggregated virtual datasets project it as `currency`. Keyed by Superset
# dataset id so the right column is used per dataset. Datasets absent from this
# map (all JY/PW datasets, dataset 22 which has no currency column) get the
# plain cap_date-only clause, unchanged.
FJL_CURRENCY_COLUMN_BY_DATASET = {
    5: "curr_code", 16: "curr_code",
    19: "currency", 20: "currency", 21: "currency",
    23: "currency", 24: "currency",  # not on dashboard 2, harmless
}
ALLOWED_FJL_CURRENCIES = {"NOK", "EUR", "DKK"}


# ── Superset client ─────────────────────────────────────────

class SupersetClient:
    """Minimal Superset client.  Uses JWT auth for guest token generation
    and session auth for dataset resolution."""

    def __init__(self):
        self.base_url = settings.superset_url
        self.username = settings.superset_admin_user
        self.password = settings.superset_admin_pass
        self._jwt_token: str | None = None
        self._session_cookies: dict | None = None

    # ── Auth helpers ──

    async def _login_jwt(self):
        async with httpx.AsyncClient(timeout=10.0) as c:
            resp = await c.post(
                f"{self.base_url}/api/v1/security/login",
                json={"username": self.username, "password": self.password, "provider": "db"},
            )
            if resp.status_code != 200:
                raise Exception(f"Superset JWT login failed ({resp.status_code})")
            self._jwt_token = resp.json()["access_token"]

    async def _login_session(self):
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=False) as c:
            page = await c.get(f"{self.base_url}/login/")
            cookies = dict(page.cookies)
            resp = await c.post(
                f"{self.base_url}/login/",
                data={"username": self.username, "password": self.password},
                cookies=cookies,
                follow_redirects=False,
            )
            if resp.status_code not in (200, 302):
                raise Exception(f"Superset session login failed ({resp.status_code})")
            self._session_cookies = {**cookies, **dict(resp.cookies)}

    async def _jwt_headers(self) -> dict:
        if not self._jwt_token:
            await self._login_jwt()
        return {"Authorization": f"Bearer {self._jwt_token}"}

    async def _session_cookies_safe(self) -> dict:
        if not self._session_cookies:
            await self._login_session()
        return self._session_cookies  # type: ignore

    # ── Dataset resolution (for RLS) ──

    async def resolve_dataset_ids(self, table_names: list[str]) -> list[int]:
        """Get Superset-internal dataset IDs for the given table/view names.

        Superset's /api/v1/dataset/ paginates with page_size=20 by default, so
        any dataset beyond the 20th would silently be invisible to the RLS
        attachment loop. Pass a rison-encoded large page_size to fetch them
        all in one go — the registry never approaches that count.
        """
        if not table_names:
            return []
        cookies = await self._session_cookies_safe()
        url = f"{self.base_url}/api/v1/dataset/?q=(page:0,page_size:1000)"
        async with httpx.AsyncClient(timeout=10.0) as c:
            resp = await c.get(url, cookies=cookies)
            if resp.status_code == 401:
                await self._login_session()
                resp = await c.get(url, cookies=self._session_cookies)
            resp.raise_for_status()
            all_ds = resp.json().get("result", [])
            return [d["id"] for d in all_ds if d.get("table_name") in table_names]

    # ── Guest token generation ──

    async def create_guest_token(
        self, dashboard_id: int, user_identity: str, rls_rules: list[dict],
    ) -> str:
        """Request a guest token from Superset for the given dashboard.

        IMPORTANT: The resource 'id' must be the Superset **numeric** dashboard ID
        (not the dashboard UUID or embedded UUID).  Superset 3.1.0's
        ``has_guest_access`` first checks ``str(resource['id']) == str(dashboard.id)``
        which is the numeric ID comparison.  The UUID-based fallback is broken when
        SQLite stores UUIDs as binary blobs because ``str(binary_uuid)`` produces
        ``b'\\x...'`` instead of a proper UUID string.
        """
        payload = {
            "user": {
                "username": user_identity,
                "first_name": user_identity,
                "last_name": "User",
            },
            "resources": [{"type": "dashboard", "id": str(dashboard_id)}],
            "rls": rls_rules,
        }
        headers = await self._jwt_headers()
        async with httpx.AsyncClient(timeout=10.0) as c:
            resp = await c.post(
                f"{self.base_url}/api/v1/security/guest_token/",
                json=payload,
                headers=headers,
            )
            if resp.status_code == 401:
                await self._login_jwt()
                headers = await self._jwt_headers()
                resp = await c.post(
                    f"{self.base_url}/api/v1/security/guest_token/",
                    json=payload,
                    headers=headers,
                )
            if resp.status_code != 200:
                body = resp.text[:300]
                raise Exception(f"Guest token failed ({resp.status_code}): {body}")
            return resp.json()["token"]

    # ── Explore form_data_key (Chart-view date overlay) ──

    async def get_chart_meta(self, slice_id: int) -> dict:
        """Resolve a slice's datasource + viz_type from Superset.

        The chart REST payload has no usable top-level datasource_id; it lives in
        ``params.datasource`` as ``"<id>__<type>"`` (e.g. ``"13__table"``). Uses
        admin session cookies — same flow as list_dashboard_charts.
        """
        cookies = await self._session_cookies_safe()
        url = f"{self.base_url}/api/v1/chart/{slice_id}"
        async with httpx.AsyncClient(timeout=10.0) as c:
            resp = await c.get(url, cookies=cookies)
            if resp.status_code == 401:
                await self._login_session()
                resp = await c.get(url, cookies=self._session_cookies)
            resp.raise_for_status()
            result = resp.json()["result"]
        import json as _json
        params = _json.loads(result.get("params") or "{}")
        ds = params.get("datasource") or ""        # "13__table"
        ds_id, _, ds_type = ds.partition("__")
        if not ds_id or not ds_type:
            raise Exception(f"Could not resolve datasource for slice {slice_id}")
        return {
            "datasource_id": int(ds_id),
            "datasource_type": ds_type,
            "viz_type": params.get("viz_type"),
        }

    async def mint_form_data_key(
        self, datasource_id: int, datasource_type: str, chart_id: int, form_data_json: str,
    ) -> str:
        """Mint a Superset explore form_data_key (a stored form_data overlay).

        POST /api/v1/explore/form_data is a WRITE: JWT bearer auth 403s
        (see project_superset_auth.md), so we authenticate with admin session
        cookies PLUS a CSRF token. The token is cookie-bound, so we carry the
        cookie the csrf endpoint returns into the POST, with X-CSRFToken +
        Referer headers (mirrors how Superset's own UI submits writes).
        """
        cookies = await self._session_cookies_safe()
        async with httpx.AsyncClient(timeout=10.0) as c:
            csrf_resp = await c.get(
                f"{self.base_url}/api/v1/security/csrf_token/",
                cookies=cookies, headers={"Referer": self.base_url},
            )
            if csrf_resp.status_code == 401:
                await self._login_session()
                cookies = self._session_cookies  # type: ignore
                csrf_resp = await c.get(
                    f"{self.base_url}/api/v1/security/csrf_token/",
                    cookies=cookies, headers={"Referer": self.base_url},
                )
            csrf_resp.raise_for_status()
            csrf = csrf_resp.json()["result"]
            # The csrf fetch may rotate the session cookie — carry it forward.
            cookies = {**cookies, **dict(csrf_resp.cookies)}

            resp = await c.post(
                f"{self.base_url}/api/v1/explore/form_data",
                json={
                    "datasource_id": datasource_id,
                    "datasource_type": datasource_type,
                    "chart_id": chart_id,
                    "form_data": form_data_json,
                },
                cookies=cookies,
                headers={"X-CSRFToken": csrf, "Referer": self.base_url},
            )
            if resp.status_code not in (200, 201):
                body = resp.text[:300]
                raise Exception(f"form_data mint failed ({resp.status_code}): {body}")
            return resp.json()["key"]


superset_client = SupersetClient()


# ── Endpoint ─────────────────────────────────────────────────

@router.get("/guest-token")
async def fetch_guest_token(
    dashboard_id: str,
    cap_date_eq: Optional[str] = None,
    cap_date_from: Optional[str] = None,
    cap_date_to: Optional[str] = None,
    currency: Optional[str] = None,
    user_identity: str = Depends(get_user_identity),
    user_roles: list[str] = Depends(get_user_roles),
):
    """Return a Superset guest token + dashboard UUID for embedding.

    Optional cap_date_* params append an extra RLS clause so chart queries
    are server-side scoped to a single day (cap_date_eq) or a window
    (cap_date_from..cap_date_to). The React DateFilterToggle drives this.

    Optional `currency` (FJL only: NOK | EUR | DKK) ANDs a per-dataset currency
    row-filter onto the cap_date clause so the FJL app currency selector scopes
    every chart to a single currency. The React Currency dropdown drives this.
    """

    # 1. Lookup dashboard config
    dash = DASHBOARDS.get(dashboard_id)
    if not dash:
        raise HTTPException(400, detail={
            "message": f"Unknown dashboard_id '{dashboard_id}'. Valid IDs: {list(DASHBOARDS.keys())}",
        })

    # 2. Access control
    #    Platform admins (rts tenant) manage pipelines and tenants — they
    #    do not consume tenant dashboards. Tenant users only access their own
    #    dashboard.  Note: the previous ``is_admin = "TENANT_ADMIN" in user_roles``
    #    check was structurally broken — every authenticated user receives
    #    TENANT_ADMIN via get_user_roles (deps.py), so the bypass fired for
    #    everyone. Use is_platform_admin() which is identity-based.
    if is_platform_admin(user_identity, user_roles):
        raise HTTPException(403, detail={
            "message": "Platform administrators do not have access to tenant dashboards. Sign in as the tenant to view its dashboard.",
        })
    if user_identity != dash["tenant"]:
        raise HTTPException(403, detail={
            "message": f"Access denied: '{dash['title']}' is restricted to {dash['tenant']} users.",
        })

    # 3. Build RLS rules (tenant-level row filtering).
    #    Per-tenant views already filter by tenant_code, so RLS rules are a
    #    defense-in-depth measure. Platform admins were short-circuited above,
    #    so by this point we always have a tenant user whose identity matches
    #    the dashboard's tenant.
    rls_rules: list[dict] = []
    tenant_tables = TENANT_TABLES.get(dash["tenant"], [])
    capdate_only_tables = TENANT_CAPDATE_ONLY_TABLES.get(dash["tenant"], [])
    try:
        tenant_dataset_ids = await superset_client.resolve_dataset_ids(tenant_tables)
    except Exception as e:
        logger.error(f"Tenant dataset resolution failed: {e}")
        tenant_dataset_ids = []
    try:
        capdate_only_dataset_ids = (
            await superset_client.resolve_dataset_ids(capdate_only_tables)
            if capdate_only_tables else []
        )
    except Exception as e:
        logger.error(f"Cap-date-only dataset resolution failed: {e}")
        capdate_only_dataset_ids = []

    # tenant_code clause: only datasets that actually have a tenant_code column.
    for ds_id in tenant_dataset_ids:
        rls_rules.append({"dataset": ds_id, "clause": f"tenant_code = '{user_identity}'"})

    # 3b. Optional cap_date scoping.
    #     Validate first (regex + strptime) — these strings are interpolated
    #     into a SQL clause string sent to Superset. Single day wins over range
    #     if both are present.
    cap_date_clause: Optional[str] = None
    if cap_date_eq:
        _validate_cap_date(cap_date_eq, "cap_date_eq")
        cap_date_clause = f"cap_date = '{cap_date_eq}'"
    elif cap_date_from and cap_date_to:
        _validate_cap_date(cap_date_from, "cap_date_from")
        _validate_cap_date(cap_date_to, "cap_date_to")
        if cap_date_from > cap_date_to:
            raise HTTPException(400, detail={"message": "cap_date_from must be <= cap_date_to"})
        cap_date_clause = f"cap_date >= '{cap_date_from}' AND cap_date <= '{cap_date_to}'"

    # 3c. Optional FJL currency scoping. Like cap_date, this value is
    #     interpolated into an RLS clause string, so it must be validated
    #     against a fixed allow-list — never interpolate unvalidated input.
    if currency is not None:
        currency = currency.upper()
        if currency not in ALLOWED_FJL_CURRENCIES:
            raise HTTPException(400, detail={
                "message": f"Invalid currency: must be one of {sorted(ALLOWED_FJL_CURRENCIES)}",
            })

    # cap_date clause: applies to BOTH the tenant view datasets and the
    # cap-date-only KPI virtual datasets. Both groups have a cap_date column.
    # For FJL, AND a per-dataset currency row-filter onto the same rule when a
    # currency was supplied (column name varies by dataset — see
    # FJL_CURRENCY_COLUMN_BY_DATASET). Datasets not in that map keep the exact
    # cap_date-only clause they had before.
    if cap_date_clause:
        for ds_id in tenant_dataset_ids + capdate_only_dataset_ids:
            clause = cap_date_clause
            if currency and ds_id in FJL_CURRENCY_COLUMN_BY_DATASET:
                clause += f" AND {FJL_CURRENCY_COLUMN_BY_DATASET[ds_id]} = '{currency}'"
            rls_rules.append({"dataset": ds_id, "clause": clause})

    # 4. Get guest token (use numeric Superset ID – see create_guest_token docstring)
    try:
        token = await superset_client.create_guest_token(
            dashboard_id=dash["superset_id"],
            user_identity=user_identity,
            rls_rules=rls_rules,
        )
    except Exception as e:
        logger.error(f"Guest token error for '{dash['title']}': {e}")
        raise HTTPException(500, detail={"message": f"Superset guest token failed: {e}"})

    return {
        "token": token,
        "dashboard_uuid": dash["uuid"],              # for guest token resource ref
        "embedded_uuid": dash["embedded_uuid"],      # for Superset Embedded SDK id
        "dashboard_title": dash["title"],
    }


# ── Chart manifest endpoint (chart-selector panel + isolated chart view) ────

def _walk_layout(layout: dict, node_id: str, out: list[int]) -> None:
    """Depth-first walk of the dashboard layout to collect chart IDs in render order."""
    node = layout.get(node_id) or {}
    if node.get("type") == "CHART":
        cid = (node.get("meta") or {}).get("chartId")
        if cid is not None:
            try:
                out.append(int(cid))
            except (TypeError, ValueError):
                pass
    for child_id in node.get("children", []) or []:
        _walk_layout(layout, child_id, out)


def _extract_chart_order(position_json_str: str | None) -> list[int]:
    """Return slice_ids in dashboard-layout order (top-to-bottom, left-to-right).

    position_json is a flat dict keyed by component id; ROOT contains a tree
    of GRID -> ROW -> CHART nodes whose `children` arrays preserve order.
    """
    if not position_json_str:
        return []
    import json as _json
    try:
        layout = _json.loads(position_json_str)
    except Exception:
        return []
    root_id = next(
        (k for k, v in layout.items() if isinstance(v, dict) and v.get("type") == "ROOT"),
        None,
    )
    if not root_id:
        return []
    out: list[int] = []
    _walk_layout(layout, root_id, out)
    return out


def _is_kpi(viz_type: str | None) -> bool:
    """KPI = big_number / big_number_total / big_number_with_trendline."""
    return bool(viz_type and viz_type.startswith("big_number"))


@router.get("/dashboards/{dashboard_id}/charts")
async def list_dashboard_charts(
    dashboard_id: str,
    user_identity: str = Depends(get_user_identity),
    user_roles: list[str] = Depends(get_user_roles),
):
    """Return the chart manifest (KPIs + analytics) for a Superset dashboard.

    Used by the dashboard chart-selector panel and isolated chart view.

    Implementation note: we authenticate to Superset via admin **session
    cookies**, not the JWT bearer token.  The JWT login returns a Gamma-scoped
    token (PUBLIC_ROLE_LIKE = Gamma) for which `/api/v1/dashboard/` returns
    `count: 0`.  The existing `SupersetClient._login_session()` flow already
    establishes an admin session — we reuse it here.
    """
    # 1. Lookup dashboard (reuses the existing registry)
    dash = DASHBOARDS.get(dashboard_id)
    if not dash:
        raise HTTPException(404, detail={
            "message": f"Unknown dashboard_id '{dashboard_id}'. Valid IDs: {list(DASHBOARDS.keys())}",
        })

    # 2. Access control — mirror the guest-token endpoint.
    #    is_platform_admin() is identity-based (rts tenant), not role-based.
    #    Every authenticated user gets TENANT_ADMIN via get_user_roles (deps.py),
    #    so a role-based admin check would let every tenant bypass tenant
    #    isolation — see the equivalent fix on fetch_guest_token().
    if is_platform_admin(user_identity, user_roles):
        raise HTTPException(403, detail={
            "message": "Platform administrators do not have access to tenant dashboards. Sign in as the tenant to view its dashboard.",
        })
    if user_identity != dash["tenant"]:
        raise HTTPException(403, detail={
            "message": f"Access denied: '{dash['title']}' is restricted to {dash['tenant']} users.",
        })

    superset_id = dash["superset_id"]

    # 3. Fetch charts + dashboard detail via admin session cookies
    try:
        cookies = await superset_client._session_cookies_safe()
        async with httpx.AsyncClient(timeout=10.0) as c:
            charts_resp = await c.get(
                f"{superset_client.base_url}/api/v1/dashboard/{superset_id}/charts",
                cookies=cookies,
            )
            if charts_resp.status_code == 401:
                await superset_client._login_session()
                cookies = superset_client._session_cookies  # type: ignore
                charts_resp = await c.get(
                    f"{superset_client.base_url}/api/v1/dashboard/{superset_id}/charts",
                    cookies=cookies,
                )
            charts_resp.raise_for_status()
            charts_data = charts_resp.json().get("result", []) or []

            detail_resp = await c.get(
                f"{superset_client.base_url}/api/v1/dashboard/{superset_id}",
                cookies=cookies,
            )
            position_json = ""
            if detail_resp.status_code == 200:
                position_json = (detail_resp.json().get("result") or {}).get("position_json") or ""
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Chart manifest fetch failed for dashboard {dashboard_id}: {e}")
        raise HTTPException(502, detail={"message": f"Could not fetch chart list from Superset: {e}"})

    # 4. Build chart records, sorted by layout position (fallback: slice_id asc)
    order = _extract_chart_order(position_json)
    order_index = {cid: idx for idx, cid in enumerate(order)}

    items: list[dict] = []
    for ch in charts_data:
        slice_id = ch.get("id")
        if slice_id is None:
            continue
        viz_type = (ch.get("form_data") or {}).get("viz_type")
        items.append({
            "slice_id": int(slice_id),
            "slice_name": ch.get("slice_name") or f"Chart {slice_id}",
            "viz_type": viz_type,
            "description": ch.get("description"),
            "is_kpi": _is_kpi(viz_type),
        })

    items.sort(key=lambda x: (order_index.get(x["slice_id"], 10_000), x["slice_id"]))

    return {
        "dashboard_id": int(superset_id),
        "dashboard_app_id": dashboard_id,
        "dashboard_title": dash["title"],
        "charts": items,
    }


# ── Available-dates endpoint (drives the React DateFilterToggle) ────────────

# Map each app dashboard id to the PostgreSQL view whose cap_date column the
# DateFilterToggle should enumerate. Mirrors TENANT_TABLES but is its own
# constant so a tenant can have multiple Superset datasets without forcing
# us to pick one for the date dropdown.
_DASHBOARD_DATE_VIEW = {
    "1": "vw_airline_cpi_jy_snapshot",
    "2": "vw_airline_cpi_pw_snapshot",
    "3": "vw_cfl_cpi_fjl_snapshot",
    "4": "vw_airline_cpi_alt_snapshot",
}

# Whitelist of view names we'll ever query from this endpoint. The view name
# is interpolated into the SQL string (psycopg can't bind identifiers), so
# this whitelist is the only thing preventing identifier injection if the
# mapping above is ever extended carelessly.
_ALLOWED_DATE_VIEWS = set(_DASHBOARD_DATE_VIEW.values())


@router.get("/dashboards/{dashboard_id}/available-dates")
def list_available_dates(
    dashboard_id: str,
    db: Session = Depends(get_db),
    user_identity: str = Depends(get_user_identity),
    user_roles: list[str] = Depends(get_user_roles),
):
    """Return distinct cap_date values for a dashboard's tenant view, newest first.

    Tenant-scoped: platform admins are rejected (they don't consume tenant
    dashboards), and a tenant user can only enumerate their own dashboard's
    dates. The underlying views already filter by tenant_code so we don't add
    a WHERE clause — but we still gate access at the dashboard level.
    """
    dash = DASHBOARDS.get(dashboard_id)
    if not dash:
        raise HTTPException(404, detail={
            "message": f"Unknown dashboard_id '{dashboard_id}'. Valid IDs: {list(DASHBOARDS.keys())}",
        })

    if is_platform_admin(user_identity, user_roles):
        raise HTTPException(403, detail={
            "message": "Platform administrators do not have access to tenant dashboards.",
        })
    if user_identity != dash["tenant"]:
        raise HTTPException(403, detail={
            "message": f"Access denied: '{dash['title']}' is restricted to {dash['tenant']} users.",
        })

    view_name = _DASHBOARD_DATE_VIEW.get(dashboard_id)
    if not view_name or view_name not in _ALLOWED_DATE_VIEWS:
        raise HTTPException(500, detail={"message": f"No date view configured for dashboard '{dashboard_id}'"})

    try:
        rows = db.execute(
            text(f"SELECT DISTINCT cap_date FROM {view_name} ORDER BY cap_date DESC")
        ).fetchall()
    except Exception as e:
        _log.error(f"[available-dates] query failed on {view_name}: {e}")
        raise HTTPException(500, detail={"message": f"Could not load available dates: {e}"})

    dates = [r[0].isoformat() if r[0] is not None else None for r in rows]
    dates = [d for d in dates if d]

    return {"dashboard_id": dashboard_id, "dates": dates}


# ── Chart-view date overlay (form_data_key) ─────────────────────────────────

@router.get("/charts/{slice_id}/form-data-key")
async def fetch_chart_form_data_key(
    slice_id: int,
    cap_date_eq: Optional[str] = None,
    cap_date_from: Optional[str] = None,
    cap_date_to: Optional[str] = None,
    user_identity: str = Depends(get_user_identity),
    user_roles: list[str] = Depends(get_user_roles),
):
    """Mint a Superset explore form_data_key that overlays a cap_date filter onto
    a saved chart, for the standalone Chart-view iframe.

    Why: the explore SPA's URL-param registry does NOT include raw ``form_data``
    — it silently drops it and renders the chart's saved (unfiltered) config. It
    DOES honor ``form_data_key``. So we mint a key whose form_data carries ONLY
    the cap_date adhoc_filter(s); loading
    ``/explore/?slice_id=ID&standalone=1&form_data_key=KEY`` keeps the saved viz
    and applies the filter. cap_date semantics mirror the guest-token RLS exactly
    (single -> ==; range -> >= AND <=).

    Additive and independent of the guest-token / RLS / embed path. The form_data
    is built server-side from the validated cap_date params only — no client-
    supplied form_data is accepted (no arbitrary-form_data injection).
    """
    # Build the cap_date overlay from validated params (reuses the RLS guard).
    filters = _cap_date_adhoc_filters(cap_date_eq, cap_date_from, cap_date_to)
    if not filters:
        raise HTTPException(400, detail={
            "message": "A cap_date filter is required (cap_date_eq, or cap_date_from + cap_date_to).",
        })

    # Resolve the slice's datasource (required by the form_data POST) and
    # viz_type (decides whether series B needs filtering too).
    try:
        meta = await superset_client.get_chart_meta(slice_id)
    except Exception as e:
        _log.error(f"[form-data-key] chart meta lookup failed for slice {slice_id}: {e}")
        raise HTTPException(502, detail={
            "message": f"Could not resolve chart {slice_id} from Superset: {e}",
        })

    form_data: dict = {"adhoc_filters": filters}
    # mixed_timeseries renders a second, independent query series whose filters
    # live in adhoc_filters_b — scope it to the same cap_date so both series match.
    if meta.get("viz_type") == "mixed_timeseries":
        form_data["adhoc_filters_b"] = filters

    import json as _json
    try:
        key = await superset_client.mint_form_data_key(
            datasource_id=meta["datasource_id"],
            datasource_type=meta["datasource_type"],
            chart_id=slice_id,
            form_data_json=_json.dumps(form_data),
        )
    except Exception as e:
        _log.error(f"[form-data-key] mint failed for slice {slice_id}: {e}")
        raise HTTPException(502, detail={
            "message": f"Could not mint Superset form_data_key: {e}",
        })

    return {"key": key}
