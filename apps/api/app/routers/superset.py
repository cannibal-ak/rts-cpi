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

import asyncio
import httpx
import json
import logging
import re
import time
import prison
from datetime import datetime
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.database import get_db
from app.core.deps import get_user_identity, get_user_roles, is_platform_admin

logger = logging.getLogger(__name__)

# Surface lines via uvicorn — see project_logging_convention.md.
_log = logging.getLogger("uvicorn.error")

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# Superset dataset name -> id map. Provisioned out-of-band and effectively
# static, but re-resolved periodically so a re-provisioned dataset is picked up.
_DATASET_MAP_TTL_SECONDS = 300.0

# Distinct-value lists backing the external filter bar's dropdowns. Each entry
# costs a real query against a virtual dataset, and one page load asks for every
# filter at once, so they are cached briefly. Keyed by (dataset_id, column).
_FILTER_VALUES_TTL_SECONDS = 300.0
_filter_values_cache: dict[tuple[int, str], tuple[float, list[str]]] = {}


def _sort_filter_values(values: list[str]) -> list[str]:
    """Order dropdown options the way a reader expects.

    Superset returns them in query order, which for a numeric column like
    ``days_left`` means 42, 29, 4. Sort numerically when every value is a
    number, otherwise alphabetically.
    """
    try:
        return sorted(values, key=float)
    except (TypeError, ValueError):
        return sorted(values)


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
    "5": {
        "title": "Airline CPI WM Dashboard",
        "superset_id": 6,                                          # Superset ID=6
        # PROD uuids — this Superset instance's dashboard 6 rows, not dev's.
        "uuid": "c1fccfa8-9755-453c-a5ed-140e04590891",
        "embedded_uuid": "a2a2f211-d861-4c6b-869b-aa20602ef6c7",
        "domain": "airline",
        "tenant": "WM",
        # Native filters WinAir does not want in the global filter bar, keyed by
        # the column each one targets. Superset's own native_filter_configuration
        # is never modified — dashboard 6 still defines all eleven and its
        # in-iframe panel is unchanged; this only suppresses them on our side.
        #
        # Keyed by column rather than by filter id because ids are opaque strings
        # that exist only inside Superset's metadata, so an id list could not be
        # checked against anything in this repo. Columns appear in the tenant
        # views and the provisioning script. An entry matching no filter is
        # logged — see the stale-entry check in get_dashboard_filter_config.
        #
        # Kept: route (Route O&D), flt_num (Flight Number), days_left, stops.
        "hidden_filter_columns": {
            "airline",              # Airline
            "dtd_bucket",           # Days to Departure
            "price_status",         # Price Position
            "recommendation",       # Pricing Action
            "lowest_competitor",    # Cheapest Competitor
            "eqp",                  # Aircraft
            "legseg_type",          # Leg/Segment
        },
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
    "WM":  ["vw_airline_cpi_wm_snapshot"],
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
    "WM":  [
        "wm_all_airlines_fares",
        "wm_all_airlines_fares_availability",
        "wm_pricing_recommendations",
        "wm_velocity_normalized",
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
        self._dataset_map_cache: dict[str, int] | None = None
        self._dataset_map_at: float = 0.0

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

    @staticmethod
    def _raw_session_cookie(resp) -> Optional[str]:
        """Read the ``session`` cookie value straight from the raw Set-Cookie
        header, bypassing httpx's cookie jar.

        Prod Superset sets the session cookie with ``Secure`` + a Domain pinned
        to the public host (needed for the cross-site embed). We reach Superset
        over the internal ``http://superset:8088``, where httpx's jar DROPS that
        cookie (Secure over http, domain mismatch) — leaving us with no session,
        so the form_data mint 502'd with "CSRF session token is missing". Replaying
        the raw value as an explicit cookie keeps the admin session alive. Harmless
        on dev (the cookie is present in the header there too).
        """
        for raw in resp.headers.get_list("set-cookie"):
            m = re.match(r"\s*session=([^;]+)", raw)
            if m:
                return m.group(1)
        return None

    async def _login_session(self):
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=False) as c:
            page = await c.get(f"{self.base_url}/login/")
            # Read the session cookie raw — the jar drops the Secure/domain-pinned
            # prod cookie (see _raw_session_cookie).
            sess = self._raw_session_cookie(page)
            cookies = {"session": sess} if sess else dict(page.cookies)
            # Prod has WTF_CSRF_ENABLED=True, so the login form requires its hidden
            # csrf_token field. Dev (CSRF off) renders no such field — include it
            # only when present so both configs keep working.
            data = {"username": self.username, "password": self.password}
            m = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', page.text)
            if m:
                data["csrf_token"] = m.group(1)
            resp = await c.post(
                f"{self.base_url}/login/",
                data=data,
                cookies=cookies,
                headers={"Referer": f"{self.base_url}/login/"},
                follow_redirects=False,
            )
            if resp.status_code not in (200, 302):
                raise Exception(f"Superset session login failed ({resp.status_code})")
            # Carry the post-login (rotated, authenticated) session forward, read
            # raw for the same jar reason; fall back to the pre-login session, then
            # the jar, so the CSRF-off dev path is unaffected.
            post = self._raw_session_cookie(resp)
            if post:
                self._session_cookies = {"session": post}
            elif sess:
                self._session_cookies = {"session": sess}
            else:
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

        # The name->id map is stable (datasets are provisioned out-of-band), but
        # this listing is issued on EVERY guest-token request — twice, once per
        # RLS group — and the SDK re-fetches a guest token on a refresh timer.
        # A short TTL keeps it correct if a dataset is re-provisioned while
        # removing it from the hot path.
        now = time.monotonic()
        if self._dataset_map_cache and now - self._dataset_map_at < _DATASET_MAP_TTL_SECONDS:
            name_to_id = self._dataset_map_cache
        else:
            cookies = await self._session_cookies_safe()
            url = f"{self.base_url}/api/v1/dataset/?q=(page:0,page_size:1000)"
            async with httpx.AsyncClient(timeout=10.0) as c:
                resp = await c.get(url, cookies=cookies)
                if resp.status_code == 401:
                    await self._login_session()
                    resp = await c.get(url, cookies=self._session_cookies)
                resp.raise_for_status()
                all_ds = resp.json().get("result", [])
            name_to_id = {d["table_name"]: d["id"] for d in all_ds if d.get("table_name")}
            self._dataset_map_cache = name_to_id
            self._dataset_map_at = now

        return [name_to_id[n] for n in table_names if n in name_to_id]

    # ── Generic authenticated calls ──

    async def _session_get(self, path: str, timeout: float = 15.0) -> dict:
        """GET a Superset API path with admin session cookies, re-auth once on 401."""
        cookies = await self._session_cookies_safe()
        async with httpx.AsyncClient(timeout=timeout) as c:
            resp = await c.get(f"{self.base_url}{path}", cookies=cookies)
            if resp.status_code == 401:
                await self._login_session()
                resp = await c.get(f"{self.base_url}{path}", cookies=self._session_cookies)
            resp.raise_for_status()
            return resp.json()

    async def _session_post(self, path: str, body: dict, timeout: float = 30.0) -> dict:
        """POST to a Superset API path with admin session cookies + CSRF token.

        Superset guards POST routes with CSRF. ``WTF_CSRF_ENABLED`` is False in
        the dev config but NOT in production, so code written against dev alone
        would silently skip a step prod requires — we always do the full dance
        (this mirrors the prod ``mint_form_data_key`` flow). JWT bearer auth
        403s on these routes, hence session cookies. The CSRF fetch can rotate
        the session cookie, so carry the rotated jar into the POST.
        """
        cookies = await self._session_cookies_safe()
        async with httpx.AsyncClient(timeout=timeout) as c:
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
            merged = {**cookies, **dict(csrf_resp.cookies)}
            resp = await c.post(
                f"{self.base_url}{path}", json=body, cookies=merged,
                headers={"X-CSRFToken": csrf, "Referer": self.base_url},
            )
            resp.raise_for_status()
            return resp.json()

    async def mint_form_data_key(
        self, datasource_id: int, datasource_type: str, chart_id: int, form_data_json: str,
    ) -> str:
        """Store an explore form_data overlay in Superset and return its key.

        ``POST /api/v1/explore/form_data`` is a write, so it rides _session_post's
        admin-session + CSRF flow (JWT bearer 403s on it).

        Superset only reuses a key when a ``tab_id`` is supplied. We send none, so
        every call mints a fresh random key — two tenants can never collide on one
        cache entry, and a stale key is never handed back out.
        """
        data = await self._session_post(
            "/api/v1/explore/form_data",
            {
                "datasource_id": datasource_id,
                "datasource_type": datasource_type,
                "chart_id": chart_id,
                "form_data": form_data_json,
            },
            timeout=10.0,
        )
        key = data.get("key")
        if not key:
            raise Exception(f"form_data mint returned no key: {str(data)[:200]}")
        return key

    async def mint_permalink(self, superset_id: int, state: dict) -> str:
        """Store a dashboard view (active tab + filter state) and return its key.

        The Embedded SDK has no setter for either, and Superset reads them once
        at mount. A permalink is the one supported way in: the caller passes the
        key back as the ``permalink_key`` URL param and Superset restores the
        whole state from it.

        A write, so it rides _session_post's admin-session + CSRF flow. Each call
        mints a fresh key; the stored value is a state snapshot, not tenant data.
        """
        # The body IS the state schema - Superset loads request.json straight
        # into DashboardPermalinkStateSchema, so wrapping it in {"state": ...}
        # fails validation with a 400.
        data = await self._session_post(
            f"/api/v1/dashboard/{superset_id}/permalink", state, timeout=10.0,
        )
        key = data.get("key")
        if not key:
            raise Exception(f"permalink mint returned no key: {str(data)[:200]}")
        return key

    # ── Native filter introspection (for the out-of-iframe filter bar) ──

    async def get_native_filters(self, superset_id: int) -> list[dict]:
        """Return a dashboard's ``native_filter_configuration``, or [] if absent.

        This is the dashboard's OWN filter definition — the same one that draws
        Superset's left-hand filter panel. Reading it (rather than hardcoding a
        filter list) is what keeps an external filter bar 1:1 with the dashboard
        when filters are added or retargeted in Superset.
        """
        data = await self._session_get(f"/api/v1/dashboard/{superset_id}")
        raw = (data.get("result") or {}).get("json_metadata") or "{}"
        try:
            meta = json.loads(raw)
        except json.JSONDecodeError:
            _log.error(f"[filter-config] dashboard {superset_id} has unparseable json_metadata")
            return []
        return meta.get("native_filter_configuration") or []

    async def fetch_column_values(
        self, dataset_id: int, column: str, row_limit: int = 1000,
    ) -> list[str]:
        """Distinct values for a dataset column, via Superset's own chart-data API.

        Superset's native filter populates its dropdown the same way, so the
        options rendered outside the iframe match the ones inside it. Going
        through Superset (rather than querying PostgreSQL) is also what lets
        this work for the WM datasets, which are *virtual* — their SQL lives
        only in Superset and has no view to select from.
        """
        payload = {
            "datasource": {"id": dataset_id, "type": "table"},
            "queries": [{
                "columns": [column],
                "metrics": [],
                "filters": [],
                "orderby": [],
                "annotation_layers": [],
                "row_limit": row_limit,
                "extras": {"having": "", "where": ""},
            }],
            "result_format": "json",
            "result_type": "results",
        }
        data = await self._session_post("/api/v1/chart/data", payload)
        rows = (data.get("result") or [{}])[0].get("data") or []
        values = [r.get(column) for r in rows]
        return _sort_filter_values(
            [str(v) for v in values if v is not None and str(v) != ""]
        )

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
            # The csrf fetch may rotate the session cookie — carry it forward,
            # reading raw (the jar drops the Secure/domain-pinned prod cookie).
            rotated = self._raw_session_cookie(csrf_resp)
            if rotated:
                cookies = {"session": rotated}

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


def _find_top_tabs(layout: dict, node_id: str) -> str | None:
    """Id of the outermost TABS node, or None on a dashboard without tabs."""
    node = layout.get(node_id) or {}
    if node.get("type") == "TABS":
        return node_id
    for child_id in node.get("children", []) or []:
        found = _find_top_tabs(layout, child_id)
        if found:
            return found
    return None


def _tabs_are_navigation(position_json_str: str | None) -> bool:
    """Is the strip ``_extract_top_tabs`` found actually the dashboard's navigation?

    ``_find_top_tabs`` takes the first TABS node depth-first, which is only the
    navigation when the dashboard is *built* as a tabbed dashboard. Measured on
    dev: WM (dash 6) and FJL (dash 2) wrap everything in a single TABS node —
    that is real navigation. JY (dash 1) and SKY (dash 5) instead stack five
    sections directly under GRID_ID, each with its own sub-tab strip, so the
    depth-first search returns the FIRST SECTION's sub-tabs ("Line / Bar /
    Table") as though they were the dashboard's sections. Production's WM
    dashboard has that same flat shape.

    That misread is pre-existing and harmless to the sidebar, which only offers
    the strip as extra links. It is NOT harmless to a navigation bar that hides
    Superset's own tab row: there the user would be left steering by three
    labels that address one section out of five.

    So this reports whether the strip is structurally the navigation — the TABS
    node is the sole child of the grid, or hangs directly off ROOT — and callers
    that need to trust it check this first. ``_extract_top_tabs`` is left exactly
    as it was, so existing consumers see no change.
    """
    if not position_json_str:
        return False
    try:
        layout = json.loads(position_json_str)
    except Exception:
        return False
    root_id = next(
        (k for k, v in layout.items() if isinstance(v, dict) and v.get("type") == "ROOT"),
        None,
    )
    if not root_id:
        return False
    tabs_id = _find_top_tabs(layout, root_id)
    if not tabs_id:
        return False

    root_children = (layout.get(root_id) or {}).get("children") or []
    if tabs_id in root_children:
        return True
    # The usual shape: ROOT -> GRID_ID -> TABS. Sole child, or the grid is
    # holding other content the tabs do not govern.
    for child_id in root_children:
        child = layout.get(child_id) or {}
        grand = child.get("children") or []
        if grand == [tabs_id]:
            return True
    return False


def _extract_top_tabs(position_json_str: str | None) -> list[dict]:
    """Return the dashboard's top-level tab strip as [{id, label}], in render order.

    Only the OUTERMOST strip. WinAir nests a second row of tabs inside each of
    its five sections (Line / Bar / Table ...); those are a detail of the section
    the user is already looking at, not a navigation target, so they stay out.

    The id is the layout component id (e.g. "TAB-wmNav2"), which is exactly what
    Superset's permalink ``activeTabs`` expects.
    """
    if not position_json_str:
        return []
    try:
        layout = json.loads(position_json_str)
    except Exception:
        return []
    root_id = next(
        (k for k, v in layout.items() if isinstance(v, dict) and v.get("type") == "ROOT"),
        None,
    )
    if not root_id:
        return []
    tabs_id = _find_top_tabs(layout, root_id)
    if not tabs_id:
        return []
    out: list[dict] = []
    for child_id in (layout.get(tabs_id) or {}).get("children", []) or []:
        node = layout.get(child_id) or {}
        if node.get("type") != "TAB":
            continue
        label = ((node.get("meta") or {}).get("text") or "").strip()
        out.append({"id": child_id, "label": label or child_id})
    return out


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


# ── Tab manifest endpoint (sidebar navigation into a tabbed dashboard) ─────

async def _dashboard_position_json(superset_id: int, ctx: str) -> str:
    """The dashboard's raw ``position_json``, via the admin session."""
    try:
        data = await superset_client._session_get(f"/api/v1/dashboard/{superset_id}")
    except Exception as e:
        _log.error(f"[{ctx}] could not read dashboard {superset_id}: {e}")
        raise HTTPException(502, detail={
            "message": f"Could not read the dashboard layout from Superset: {e}",
        })
    return (data.get("result") or {}).get("position_json") or ""


@router.get("/dashboards/{dashboard_id}/tabs")
async def list_dashboard_tabs(
    dashboard_id: str,
    user_identity: str = Depends(get_user_identity),
    user_roles: list[str] = Depends(get_user_roles),
):
    """The dashboard's top-level tabs, in the order Superset renders them.

    Read straight out of the dashboard's own ``position_json``, so the list
    stays 1:1 with the dashboard when a tab is renamed, added or reordered in
    Superset - the same principle as /filter-config reading the dashboard's own
    native_filter_configuration rather than hardcoding a filter list.

    Returns an empty list for dashboards with no tab strip, which callers should
    treat as "this dashboard is not tab-navigable" rather than as an error.
    """
    dash = _require_tenant_dashboard(dashboard_id, user_identity, user_roles)
    position_json = await _dashboard_position_json(dash["superset_id"], "tabs")
    return {
        "dashboard_id": int(dash["superset_id"]),
        "dashboard_app_id": dashboard_id,
        "tabs": _extract_top_tabs(position_json),
        # Additive. False means the strip above is a section's own sub-tabs
        # that the extractor could not distinguish from real navigation — see
        # _tabs_are_navigation. Callers that merely offer the tabs as links
        # (the sidebar) can ignore this; a caller that REPLACES Superset's tab
        # row must not proceed without it.
        "tabs_are_navigation": _tabs_are_navigation(position_json),
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
    "5": "vw_airline_cpi_wm_snapshot",
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
# PROD overlay endpoint, kept alongside the dashboard-scoped variant below —
# older cached frontends (PWA installs) still call this path.

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


# ── External native-filter bar ───────────────────────────────────────────────
#
# These two endpoints let the React app render a dashboard's native filters
# ABOVE the embedded iframe instead of inside Superset's left-hand panel.
#
# Why not RLS: the guest-token RLS path scopes by injecting SQL, which cannot
# express a filter's per-chart *scope*. On the WM dashboard that scope is the
# whole point — Price Position/Pricing Action/Cheapest Competitor apply to two
# charts, the velocity filters to one, Route to all ten. Native filters already
# encode that, so we drive them rather than reimplement them.
#
# How it reaches Superset: `filter-params` returns a rison-encoded dataMask that
# the caller passes to the Embedded SDK as `urlParams.native_filters`. Superset's
# dashboard bootstrap reads that URL param and hydrates its filter state from it.
# NOTE it does so exactly ONCE, on mount — so applying new values requires
# re-embedding the iframe. That is a property of Superset, not of this code, and
# it is why the UI batches changes behind an Apply button.


def _require_tenant_dashboard(
    dashboard_id: str, user_identity: str, user_roles: list[str],
) -> dict:
    """Resolve a dashboard from the registry and enforce tenant access.

    Same three checks the guest-token and charts endpoints make: known
    dashboard, not a platform admin (they administer tenants rather than
    consume their dashboards), and the caller's tenant owns this dashboard.
    """
    dash = DASHBOARDS.get(dashboard_id)
    if not dash:
        raise HTTPException(404, detail={
            "message": f"Unknown dashboard_id '{dashboard_id}'. Valid IDs: {list(DASHBOARDS.keys())}",
        })
    if is_platform_admin(user_identity, user_roles):
        raise HTTPException(403, detail={
            "message": "Platform administrators do not have access to tenant dashboards. Sign in as the tenant to view its dashboard.",
        })
    if user_identity != dash["tenant"]:
        raise HTTPException(403, detail={
            "message": f"Access denied: '{dash['title']}' is restricted to {dash['tenant']} users.",
        })
    return dash


def _filter_target(f: dict) -> tuple[Optional[int], Optional[str]]:
    """Extract (dataset_id, column_name) from a native filter's first target."""
    targets = f.get("targets") or []
    if not targets:
        return None, None
    t = targets[0] or {}
    return t.get("datasetId"), (t.get("column") or {}).get("name")


# ── Chart-view filter overlay (form_data_key) ───────────────────────────────
#
# Chart view loads /explore/?slice_id=N&standalone=1 ANONYMOUSLY against
# Superset's Public role (infra/SUPERSET_NOTES.md), so neither the guest token's
# cap_date RLS nor the dashboard's native filters reach it. The only channel the
# explore SPA honours is `form_data_key`: a server-stored form_data overlay,
# minted here and merged over the slice's saved config by Superset.
#
# Raw `form_data=` on the URL does NOT work — the explore SPA's URL-param
# registry drops it silently and renders the chart unfiltered.

_CHART_META_TTL_SECONDS = 60.0
_dash_chart_meta_cache: dict[int, tuple[float, dict[int, dict]]] = {}


async def _dashboard_chart_meta(superset_id: int) -> dict[int, dict]:
    """{slice_id: that slice's saved form_data} for every chart on a dashboard.

    One call serves three needs: the membership gate (is this slice on the
    caller's dashboard?), the native-filter scope fallback (which slice ids exist
    at all), and — the important one — the merge base, since the response carries
    each slice's saved adhoc_filters / viz_type / datasource.

    Short TTL on purpose, matching EXPLORE_FORM_DATA_CACHE_CONFIG's reasoning in
    infra/superset_config.py: this is the base a filter overlay is merged onto, so
    a chart edited in Superset must not keep producing overlays built on its old
    definition. One mint per chart switch is not a hot path.
    """
    now = time.monotonic()
    hit = _dash_chart_meta_cache.get(superset_id)
    if hit and now - hit[0] < _CHART_META_TTL_SECONDS:
        return hit[1]
    data = await superset_client._session_get(f"/api/v1/dashboard/{superset_id}/charts")
    meta: dict[int, dict] = {}
    for ch in data.get("result") or []:
        sid = ch.get("id")
        if sid is not None:
            meta[int(sid)] = ch.get("form_data") or {}
    _dash_chart_meta_cache[superset_id] = (now, meta)
    return meta


def _charts_in_scope(f: dict, all_slice_ids: list[int]) -> Optional[list[int]]:
    """Slice ids a native filter applies to, or None when unknowable.

    Superset writes ``chartsInScope`` whenever a filter's scope is saved, so that
    is the authority; dashboards saved by older versions carry only
    ``scope.excluded``, so derive from that instead.

    None means "this dashboard carries no scope information". Callers MUST read
    that as "applies everywhere", never as "applies nowhere" — a filter must not
    silently vanish from the bar because we failed to learn its scope.
    """
    raw = f.get("chartsInScope")
    if isinstance(raw, list):
        return [int(x) for x in raw if isinstance(x, int) and not isinstance(x, bool)]
    excluded = (f.get("scope") or {}).get("excluded")
    if isinstance(excluded, list):
        ex = {int(x) for x in excluded if isinstance(x, int) and not isinstance(x, bool)}
        return [sid for sid in all_slice_ids if sid not in ex]
    return None


def _adhoc_in(column: str, values: list[str], option_name: str) -> dict:
    """A Superset SIMPLE adhoc filter expressing ``column IN (values)``.

    The same three facts the dataMask path carries (col / op / val, see
    build_dashboard_filter_params) in explore's vocabulary: subject / operator /
    comparator. ``comparator`` is always a LIST for IN, including for
    single-select filters — a bare string is read as a one-element IN by some
    Superset versions and rejected by others, so one code path, no branch.

    ``filterOptionName`` must be unique within the array; Superset uses it as the
    React key for the filter pills.
    """
    return {
        "expressionType": "SIMPLE",
        "clause": "WHERE",
        "subject": column,
        "operator": "IN",
        "comparator": list(values),
        "filterOptionName": option_name,
    }


def _adhoc_cmp(column: str, operator: str, value: str, option_name: str) -> dict:
    """SIMPLE adhoc filter for a scalar comparison (``==`` / ``>=`` / ``<=``)."""
    return {
        "expressionType": "SIMPLE",
        "clause": "WHERE",
        "subject": column,
        "operator": operator,
        "comparator": value,
        "filterOptionName": option_name,
    }


def _cap_date_adhoc_filters(
    cap_date_eq: Optional[str],
    cap_date_from: Optional[str],
    cap_date_to: Optional[str],
) -> list[dict]:
    """cap_date overlay mirroring the guest-token RLS clause exactly.

    Single day -> ``cap_date == eq``; range -> ``>= from AND <= to``, inclusive at
    both ends. Single day wins when both are supplied, the same precedence
    fetch_guest_token uses, so Dashboard and Chart view can never disagree.

    Deliberately NOT a TEMPORAL_RANGE filter: Superset parses
    ``"2026-07-01 : 2026-07-15"`` as start-inclusive / end-EXCLUSIVE, which would
    quietly drop the last day of every range relative to Dashboard mode — exactly
    the class of bug this feature exists to close.

    [] is a legitimate result — the overlay may carry only native selections.
    """
    if cap_date_eq:
        _validate_cap_date(cap_date_eq, "cap_date_eq")
        return [_adhoc_cmp("cap_date", "==", cap_date_eq, "cpi_capdate_eq")]
    if cap_date_from and cap_date_to:
        _validate_cap_date(cap_date_from, "cap_date_from")
        _validate_cap_date(cap_date_to, "cap_date_to")
        if cap_date_from > cap_date_to:
            raise HTTPException(400, detail={"message": "cap_date_from must be <= cap_date_to"})
        return [
            _adhoc_cmp("cap_date", ">=", cap_date_from, "cpi_capdate_from"),
            _adhoc_cmp("cap_date", "<=", cap_date_to, "cpi_capdate_to"),
        ]
    return []


def _merge_adhoc_filters(saved: Any, ours: list[dict]) -> list[dict]:
    """Append our overlay to the slice's OWN saved adhoc_filters.

    This is the load-bearing part. Superset merges a form_data_key overlay with
    ``slice_form_data.update(overlay)`` — a top-level dict update — so an overlay
    carrying ``adhoc_filters`` REPLACES the saved list outright. Sending only our
    filters would delete whatever the chart was saved with and render
    plausible-looking wrong numbers with no error anywhere.

    Exactly one class of saved filter is dropped: a SIMPLE filter on a column we
    are also filtering. Keeping both ANDs them — a saved ``cap_date`` range under
    our ``cap_date ==`` is empty — so ours wins on that column and only there.

    Freeform ``expressionType: "SQL"`` entries are ALWAYS kept: we cannot tell
    which column they touch, and dropping one changes what the chart means.
    """
    owned = {f["subject"] for f in ours}
    kept: list[dict] = []
    for f in saved if isinstance(saved, list) else []:
        if not isinstance(f, dict):
            continue
        if f.get("expressionType") == "SIMPLE" and f.get("subject") in owned:
            continue
        kept.append(f)
    return kept + ours


def _hidden_filter_columns(dash: dict) -> set[str]:
    """Target columns whose native filters this API does not surface or honour.

    Lower-cased so the registry list reads naturally whatever case the filter's
    target happens to use. Dashboards without the key get an empty set, so their
    behaviour is unchanged.
    """
    return {c.lower() for c in (dash.get("hidden_filter_columns") or ())}


async def _column_values_cached(dataset_id: int, column: str) -> list[str]:
    key = (dataset_id, column)
    hit = _filter_values_cache.get(key)
    now = time.monotonic()
    if hit and now - hit[0] < _FILTER_VALUES_TTL_SECONDS:
        return hit[1]
    values = await superset_client.fetch_column_values(dataset_id, column)
    _filter_values_cache[key] = (now, values)
    return values


@router.get("/dashboards/{dashboard_id}/filter-config")
async def get_dashboard_filter_config(
    dashboard_id: str,
    user_identity: str = Depends(get_user_identity),
    user_roles: list[str] = Depends(get_user_roles),
):
    """Describe a dashboard's native filters, with their selectable values.

    Returns one entry per ``filter_select`` native filter so the app can render
    the dashboard's real filters without hardcoding either the filter list or
    the option lists. Other filter types (time range, numerical range) are
    skipped — they need different controls and no WM filter uses them today.
    """
    dash = _require_tenant_dashboard(dashboard_id, user_identity, user_roles)

    try:
        raw_filters = await superset_client.get_native_filters(dash["superset_id"])
    except Exception as e:
        _log.error(f"[filter-config] could not read dashboard {dash['superset_id']}: {e}")
        raise HTTPException(502, detail={
            "message": f"Could not read filter configuration from Superset: {e}",
        })

    hidden = _hidden_filter_columns(dash)
    matched: set[str] = set()

    selectable = []
    for f in raw_filters:
        if f.get("filterType") != "filter_select":
            continue
        ds_id, column = _filter_target(f)
        if not ds_id or not column:
            _log.error(f"[filter-config] filter {f.get('id')} has no usable target; skipping")
            continue
        if column.lower() in hidden:
            # Dropped above the gather below, so a suppressed filter also costs
            # no distinct-values query. That is why this lives here rather than
            # in the frontend's filters.map().
            matched.add(column.lower())
            continue
        selectable.append((f, ds_id, column))

    # A suppression entry that matched nothing means the dashboard moved under
    # us — column renamed, filter deleted — and the entry is now inert. That
    # fails OPEN: the filter reappears in the bar. Say so rather than let a user
    # discover it.
    for stale in sorted(hidden - matched):
        _log.error(
            f"[filter-config] dashboard {dashboard_id}: hidden_filter_columns entry "
            f"'{stale}' matched no native filter on Superset dashboard {dash['superset_id']}"
        )

    # One query per filter; issue them concurrently so a 10-filter dashboard
    # costs one round of latency rather than ten.
    results = await asyncio.gather(
        *(_column_values_cached(ds_id, col) for _, ds_id, col in selectable),
        return_exceptions=True,
    )

    # all_slice_ids is needed only for the scope.excluded fallback, so pay for
    # that lookup lazily. Dashboards Superset saved with chartsInScope — all of
    # ours today — cost nothing extra.
    all_slice_ids: list[int] = []
    if any("chartsInScope" not in f for f, _, _ in selectable):
        try:
            all_slice_ids = sorted((await _dashboard_chart_meta(dash["superset_id"])).keys())
        except Exception as e:
            _log.error(f"[filter-config] chart list failed for {dash['superset_id']}: {e}")

    out: list[dict] = []
    for (f, ds_id, column), values in zip(selectable, results):
        if isinstance(values, BaseException):
            # A filter whose values can't be loaded is still worth showing —
            # it renders empty and disabled rather than vanishing silently.
            _log.error(f"[filter-config] values failed for {f.get('id')} ({ds_id}.{column}): {values}")
            values = []
        control = f.get("controlValues") or {}
        out.append({
            "id": f["id"],
            "field": column,
            "label": f.get("name") or column,
            "description": f.get("description") or None,
            "dataset_id": ds_id,
            "multi_select": bool(control.get("multiSelect", True)),
            "values": values,
            # Which charts this filter reaches, from Superset's own scope config.
            # Chart view uses it to show only the filters that affect the chart
            # on screen. null = no scope info recorded == applies everywhere.
            "charts_in_scope": _charts_in_scope(f, all_slice_ids),
        })

    return {"dashboard_id": dashboard_id, "filters": out}


class FilterParamsRequest(BaseModel):
    """Selected values per native filter id, e.g. {"NATIVE_FILTER-Route": ["ANU → SLU"]}."""

    selections: Dict[str, List[str]] = Field(default_factory=dict)


def _build_data_mask(
    dash: dict,
    raw_filters: list[dict],
    selections: dict | None,
    dashboard_id: str,
    ctx: str,
) -> dict[str, dict]:
    """Turn {filter_id: [values]} into Superset's dataMask shape.

    Shared by /filter-params (which risons it into the ``native_filters`` URL
    param) and /permalink (which stores it as permalink state), so both honour
    exactly the same rules:

    * Unknown filter ids are ignored rather than trusted.
    * The column comes from the dashboard's own target definition, never from
      the request, so a caller cannot filter on an arbitrary column.
    * Suppressed filters are dropped on the write side too - without that a
      stale client could narrow the dashboard by a filter the bar never
      rendered, leaving the user no visible control to explain or clear it.
    * An empty selection is omitted entirely, which is what "All" means.

    Never interpolated into SQL - Superset parses it into its own filter state.
    """
    by_id = {f["id"]: f for f in raw_filters if f.get("id")}
    hidden = _hidden_filter_columns(dash)

    data_mask: dict[str, dict] = {}
    for filter_id, values in (selections or {}).items():
        f = by_id.get(filter_id)
        if not f:
            continue
        _, column = _filter_target(f)
        if not column:
            continue
        if column.lower() in hidden:
            _log.info(
                f"[{ctx}] dropping selection for suppressed filter "
                f"{filter_id} ({column}) on dashboard {dashboard_id}"
            )
            continue
        vals = [str(v) for v in (values or []) if v is not None and str(v) != ""]
        if not vals:
            continue
        data_mask[filter_id] = {
            "id": filter_id,
            "extraFormData": {"filters": [{"col": column, "op": "IN", "val": vals}]},
            "filterState": {"value": vals, "label": ", ".join(vals)},
            "ownState": {},
        }
    return data_mask


@router.post("/dashboards/{dashboard_id}/filter-params")
async def build_dashboard_filter_params(
    dashboard_id: str,
    body: FilterParamsRequest,
    user_identity: str = Depends(get_user_identity),
    user_roles: list[str] = Depends(get_user_roles),
):
    """Translate filter selections into a rison ``native_filters`` URL param.

    Pure transform, no side effects — nothing is stored in Superset. The caller
    passes the returned string to the Embedded SDK as
    ``dashboardUiConfig.urlParams.native_filters``.

    Only filter ids that actually exist on this dashboard are honoured, and the
    column comes from the dashboard's own target definition rather than from the
    request, so a caller cannot filter on an arbitrary column. Unlike the RLS
    path this value is never interpolated into SQL — Superset parses it into its
    own filter state — so there is no injection surface here.

    An empty selection is omitted entirely, which is what "All" means to a
    native filter. If nothing is selected the result is "" and the caller should
    drop the URL param so the dashboard uses its own defaults.
    """
    dash = _require_tenant_dashboard(dashboard_id, user_identity, user_roles)

    try:
        raw_filters = await superset_client.get_native_filters(dash["superset_id"])
    except Exception as e:
        _log.error(f"[filter-params] could not read dashboard {dash['superset_id']}: {e}")
        raise HTTPException(502, detail={
            "message": f"Could not read filter configuration from Superset: {e}",
        })

    data_mask = _build_data_mask(dash, raw_filters, body.selections, dashboard_id, "filter-params")

    return {"native_filters": prison.dumps(data_mask) if data_mask else ""}


class DashboardPermalinkRequest(BaseModel):
    """A dashboard view to store: which tab is open, and what is filtered."""

    active_tab: Optional[str] = None
    selections: Dict[str, List[str]] = Field(default_factory=dict)


@router.post("/dashboards/{dashboard_id}/permalink")
async def mint_dashboard_permalink(
    dashboard_id: str,
    body: DashboardPermalinkRequest,
    user_identity: str = Depends(get_user_identity),
    user_roles: list[str] = Depends(get_user_roles),
):
    """Store a dashboard view and return the key that reopens it.

    Exists because the Embedded SDK cannot set the active tab (or the filters)
    after mount - Superset reads both once, from the URL. So the caller mints a
    key here and hands it to the SDK as ``permalink_key``.

    The tab AND the filters go into the one permalink deliberately. Passing a
    permalink_key alongside a ``native_filters`` param would leave two sources
    of truth for filter state racing each other on mount; one snapshot cannot.

    ``active_tab`` is validated against the dashboard's real tab strip, so a
    caller cannot pin the view to an arbitrary layout id.
    """
    dash = _require_tenant_dashboard(dashboard_id, user_identity, user_roles)

    state: dict = {}

    if body.active_tab:
        position_json = await _dashboard_position_json(dash["superset_id"], "permalink")
        known = {t["id"] for t in _extract_top_tabs(position_json)}
        if body.active_tab not in known:
            raise HTTPException(400, detail={
                "message": f"Unknown tab '{body.active_tab}' on dashboard {dashboard_id}",
            })
        # anchor scrolls the tab into view; activeTabs is what actually selects it.
        state["activeTabs"] = [body.active_tab]
        state["anchor"] = body.active_tab

    if body.selections:
        try:
            raw_filters = await superset_client.get_native_filters(dash["superset_id"])
        except Exception as e:
            _log.error(f"[permalink] could not read filters for {dash['superset_id']}: {e}")
            raise HTTPException(502, detail={
                "message": f"Could not read filter configuration from Superset: {e}",
            })
        data_mask = _build_data_mask(
            dash, raw_filters, body.selections, dashboard_id, "permalink",
        )
        if data_mask:
            state["dataMask"] = data_mask

    if not state:
        # Nothing to pin. Say so rather than minting a key that changes nothing,
        # so the caller can drop the URL param and embed the plain dashboard.
        return {"key": None}

    try:
        key = await superset_client.mint_permalink(dash["superset_id"], state)
    except Exception as e:
        _log.error(f"[permalink] mint failed for dashboard {dashboard_id}: {e}")
        raise HTTPException(502, detail={
            "message": f"Could not create the dashboard permalink: {e}",
        })

    return {"key": key}


class ChartOverlayRequest(BaseModel):
    """What Chart view wants applied to one slice.

    Same cap_date vocabulary as the guest token, same selections vocabulary as
    /filter-params.
    """

    cap_date_eq: Optional[str] = None
    cap_date_from: Optional[str] = None
    cap_date_to: Optional[str] = None
    selections: Dict[str, List[str]] = Field(default_factory=dict)


@router.post("/dashboards/{dashboard_id}/charts/{slice_id}/form-data-key")
async def mint_chart_form_data_key(
    dashboard_id: str,
    slice_id: int,
    body: ChartOverlayRequest,
    user_identity: str = Depends(get_user_identity),
    user_roles: list[str] = Depends(get_user_roles),
):
    """Mint a Superset form_data_key applying Chart view's filters to one slice.

    Routed UNDER the dashboard rather than as a bare /charts/{slice_id}/… — that
    is the whole authorization story. A slice id carries no tenant, so a flat
    route would let any authenticated session mint a key for any slice in the
    deployment. Here _require_tenant_dashboard runs first (the same three checks
    guest-token, /charts and /filter-config make), and then the slice must
    actually belong to that dashboard.

    The overlay is built entirely server-side from validated cap_date params and
    the dashboard's OWN native filter definitions. The client sends filter ids and
    values; the COLUMN always comes from Superset's target definition, so a caller
    cannot filter on an arbitrary column (same rule as
    build_dashboard_filter_params).
    """
    dash = _require_tenant_dashboard(dashboard_id, user_identity, user_roles)

    try:
        chart_meta = await _dashboard_chart_meta(dash["superset_id"])
        raw_filters = await superset_client.get_native_filters(dash["superset_id"])
    except Exception as e:
        _log.error(f"[form-data-key] Superset read failed for dashboard {dash['superset_id']}: {e}")
        raise HTTPException(502, detail={
            "message": f"Could not read chart metadata from Superset: {e}",
        })

    saved_fd = chart_meta.get(slice_id)
    if saved_fd is None:
        # Phrased against the dashboard, not the slice: a "no such chart" message
        # would confirm to the caller whether a foreign slice id exists.
        raise HTTPException(404, detail={
            "message": f"Chart {slice_id} is not on dashboard '{dashboard_id}'.",
        })

    all_slice_ids = sorted(chart_meta.keys())
    by_id = {f["id"]: f for f in raw_filters if f.get("id")}
    hidden = _hidden_filter_columns(dash)

    ours = _cap_date_adhoc_filters(body.cap_date_eq, body.cap_date_from, body.cap_date_to)
    applied: list[dict] = []
    out_of_scope: list[dict] = []

    for filter_id, values in (body.selections or {}).items():
        f = by_id.get(filter_id)
        if not f:
            continue                          # unknown id — ignore rather than trust
        _, column = _filter_target(f)
        if not column:
            continue
        if column.lower() in hidden:
            continue                          # suppressed for this dashboard
        vals = [str(v) for v in (values or []) if v is not None and str(v) != ""]
        if not vals:
            continue                          # nothing selected == "All"
        label = f.get("name") or column
        scope = _charts_in_scope(f, all_slice_ids)
        if scope is not None and slice_id not in scope:
            # Superset would not apply this filter to this chart on the dashboard
            # either. Applying it here would make Chart view STRICTER than
            # Dashboard view, so report it instead and let the UI say "not used
            # by this chart" rather than quietly narrowing the data.
            out_of_scope.append({"id": filter_id, "label": label})
            continue
        ours.append(_adhoc_in(column, vals, f"cpi_{re.sub(r'[^A-Za-z0-9_]', '_', filter_id)}"))
        applied.append({"id": filter_id, "label": label, "column": column, "values": vals})

    if not ours:
        # Nothing to overlay. Say so rather than burning a Superset write and a
        # metastore cache row on an empty form_data; the client loads the plain URL.
        return {"key": None, "cap_date": None, "applied": [], "out_of_scope": out_of_scope}

    ds = saved_fd.get("datasource") or ""      # "32__table"
    ds_id, _, ds_type = ds.partition("__")
    if not ds_id.isdigit() or not ds_type:
        raise HTTPException(502, detail={
            "message": f"Could not resolve the datasource for chart {slice_id}.",
        })

    form_data: dict = {
        # slice_id is load-bearing, not decoration: Superset only merges the
        # slice's saved form_data when the resolved form_data carries one.
        "slice_id": slice_id,
        "adhoc_filters": _merge_adhoc_filters(saved_fd.get("adhoc_filters"), ours),
    }
    # A viz with a second, independent query keeps its filters in
    # adhoc_filters_b (mixed_timeseries is the only one registered in Superset
    # 3.1.0 — WM's velocity chart is one). Keying off the SAVED form_data rather
    # than a viz_type allow-list means a future two-query viz is covered with no
    # code change, and the viz_type clause still catches one saved without the key.
    if "adhoc_filters_b" in saved_fd or saved_fd.get("viz_type") == "mixed_timeseries":
        form_data["adhoc_filters_b"] = _merge_adhoc_filters(saved_fd.get("adhoc_filters_b"), ours)

    try:
        key = await superset_client.mint_form_data_key(
            datasource_id=int(ds_id),
            datasource_type=ds_type,
            chart_id=slice_id,
            form_data_json=json.dumps(form_data),
        )
    except Exception as e:
        _log.error(f"[form-data-key] mint failed for slice {slice_id}: {e}")
        raise HTTPException(502, detail={
            "message": f"Could not mint Superset form_data_key: {e}",
        })

    cap_date = body.cap_date_eq or (
        f"{body.cap_date_from} → {body.cap_date_to}"
        if body.cap_date_from and body.cap_date_to else None
    )
    return {"key": key, "cap_date": cap_date, "applied": applied, "out_of_scope": out_of_scope}
