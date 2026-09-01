#!/usr/bin/env python3
"""Mint UNSCOPED Superset guest tokens for the four parity tenants via the
CPI API in-container (TestClient + dependency overrides — MFA-gated tenants
cannot log in interactively). Unscoped (no cap_date) on purpose: the color
verifier must see every series the data can build; a cap_date-scoped PASS
hides label_colors gaps (the DA Exp lesson, 2026-08-19).

Usage: docker exec -e PYTHONPATH=/app cpi-api-1 python /tmp/mint_guest_tokens.py
Prints JSON {tenant: {app_dashboard_id, superset_dash, token}}.

Identity constants verified against app_user/tenant on dev 2026-09-01; the
same ids exist on prod (seeded migrations).
"""
import json

from fastapi.testclient import TestClient

from app.core import deps
from app.main import app

TENANTS = {
    # slug: (app dashboard id, superset dash id, tenant_id, user sub, email)
    "jy": ("1", 1, "dd000000-0000-0000-0000-000000000001",
           "22222222-0000-0000-0000-000000000001", "jy@airline.com"),
    "pw": ("2", 3, "bb000000-0000-0000-0000-000000000001",
           "33333333-0000-0000-0000-000000000001", "pw@airline.com"),
    "wm": ("5", 6, "ff000000-0000-0000-0000-000000000001",
           "66666666-0000-0000-0000-000000000001", "wm@airline.com"),
    "da": ("6", 7, "ab000000-0000-0000-0000-000000000001",
           "77777777-0000-0000-0000-000000000001", "da@airline.com"),
}

out = {}
for slug, (app_id, sup_id, tenant_id, sub, email) in TENANTS.items():
    fake = {
        "sub": sub, "tenant_id": tenant_id, "tenant_slug": slug,
        "roles": ["TENANT_ADMIN"], "email": email,
        "must_change_password": False, "token_type": "access",
    }
    app.dependency_overrides[deps.get_current_user] = lambda f=fake: f
    app.dependency_overrides[deps.enforce_password_change] = lambda f=fake: f
    app.dependency_overrides[deps.require_mfa_satisfied] = lambda f=fake: f
    client = TestClient(app)
    r = client.get(f"/api/v1/superset/guest-token?dashboard_id={app_id}")
    out[slug] = {
        "app_dashboard_id": app_id,
        "superset_dash": sup_id,
        "status": r.status_code,
        "token": (r.json().get("token") if r.status_code == 200 else r.text[:200]),
    }

print(json.dumps(out, indent=1))
