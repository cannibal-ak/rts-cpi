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
from typing import Dict, Any
from fastapi import APIRouter, Depends, HTTPException
from app.core.config import settings
from app.core.deps import get_user_identity, get_user_roles

logger = logging.getLogger(__name__)

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
}

# Tenant -> per-tenant Superset dataset view names (for RLS filtering)
# Each dashboard now has its own dedicated dataset—no cross-tenant bleed.
TENANT_TABLES = {
    "JY":  ["vw_airline_cpi_jy_snapshot"],
    "PW":  ["vw_airline_cpi_pw_snapshot"],
    "FJL": ["vw_cfl_cpi_fjl_snapshot"],
}

# Legacy combined tables are no longer supported
DOMAIN_TABLES = {}


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
        """Get Superset-internal dataset IDs for the given table/view names."""
        if not table_names:
            return []
        cookies = await self._session_cookies_safe()
        async with httpx.AsyncClient(timeout=10.0) as c:
            resp = await c.get(f"{self.base_url}/api/v1/dataset/", cookies=cookies)
            if resp.status_code == 401:
                await self._login_session()
                resp = await c.get(f"{self.base_url}/api/v1/dataset/", cookies=self._session_cookies)
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


superset_client = SupersetClient()


# ── Endpoint ─────────────────────────────────────────────────

@router.get("/guest-token")
async def fetch_guest_token(
    dashboard_id: str,
    user_identity: str = Depends(get_user_identity),
    user_roles: list[str] = Depends(get_user_roles),
):
    """Return a Superset guest token + dashboard UUID for embedding."""

    # 1. Lookup dashboard config
    dash = DASHBOARDS.get(dashboard_id)
    if not dash:
        raise HTTPException(400, detail={
            "message": f"Unknown dashboard_id '{dashboard_id}'. Valid IDs: {list(DASHBOARDS.keys())}",
        })

    # 2. Access control
    is_admin = "TENANT_ADMIN" in user_roles
    if not is_admin and user_identity != dash["tenant"]:
        raise HTTPException(403, detail={
            "message": f"Access denied: '{dash['title']}' is restricted to {dash['tenant']} users.",
        })

    # 3. Build RLS rules (tenant-level row filtering for non-admins)
    #    Per-tenant views already filter by tenant_code, so RLS rules are a
    #    defense-in-depth measure.  We resolve the per-tenant dataset first,
    #    falling back to the combined domain dataset if the tenant-specific
    #    one hasn't been registered in Superset yet.
    rls_rules: list[dict] = []
    if not is_admin:
        table_names = TENANT_TABLES.get(dash["tenant"], DOMAIN_TABLES.get(dash["domain"], []))
        try:
            dataset_ids = await superset_client.resolve_dataset_ids(table_names)
        except Exception as e:
            logger.error(f"Dataset resolution failed: {e}")
            dataset_ids = []

        for ds_id in dataset_ids:
            rls_rules.append({"dataset": ds_id, "clause": f"tenant_code = '{user_identity}'"})

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
