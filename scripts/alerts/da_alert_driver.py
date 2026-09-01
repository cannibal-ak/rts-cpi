"""Drive the alerts API in-container as DA's TENANT_ADMIN via TestClient.

Usage: python da_alert_driver.py <spec.json>
spec.json = [{"method": "GET", "path": "/api/v1/alerts/rules"}, ...]
Read-only unless a PATCH/POST /run call is in the spec.
"""
import json
import sys

from fastapi.testclient import TestClient

from app.core import deps
from app.main import app

FAKE = {
    "sub": "77777777-0000-0000-0000-000000000001",
    "tenant_id": "ab000000-0000-0000-0000-000000000001",
    "tenant_slug": "da",
    "roles": ["TENANT_ADMIN"],
    "email": "da@airline.com",
    "must_change_password": False,
    "token_type": "access",
}

app.dependency_overrides[deps.get_current_user] = lambda: FAKE
app.dependency_overrides[deps.enforce_password_change] = lambda: FAKE
app.dependency_overrides[deps.require_mfa_satisfied] = lambda: FAKE

client = TestClient(app)

out = []
for call in json.load(open(sys.argv[1])):
    r = client.request(call["method"], call["path"], json=call.get("body"))
    ct = r.headers.get("content-type", "")
    out.append({
        "path": call["path"],
        "label": call.get("label"),
        "status": r.status_code,
        "resp": r.json() if ct.startswith("application/json") else r.text[:800],
    })
print(json.dumps(out, indent=1, default=str))
