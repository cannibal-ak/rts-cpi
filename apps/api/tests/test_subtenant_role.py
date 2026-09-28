"""Focused tests for the TENANT_USER ("Subtenant") role (Phase 1).

Mirrors the direct-handler-call convention of tests/test_user_deactivate.py:
service/handler functions are invoked against the transactional ``db_session``
fixture (all writes rolled back at test end). No TestClient/HTTP layer.

Run ONLY this file (the full suite has known-unrelated failures):
    pytest tests/test_subtenant_role.py -q

Covers:
  a/b/c) get_user_roles no longer silently upgrades; honours the filtered list.
  d)     invite accepts TENANT_USER only; rejects TENANT_ADMIN, bogus roles and
         the RTS platform tenant.
  e)     RequirePlatformAdmin now guards GET /user-roles and POST /update-roles
         (guard logic -> 403 for non-platform; wiring assertion on both routes).
"""

import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import text

from app.core.deps import VALID_ROLES, get_user_roles, RequirePlatformAdmin
from app.models.user import AppUser, RoleBinding
from app.routers.admin_password_management import invite_user
from app.schemas.admin_password import AdminInviteUserRequest
from app.routers import tenant as tenant_router_mod


# ── (a/b/c) get_user_roles: filtered, never upgraded ─────────────────────────

def test_get_user_roles_keeps_tenant_user():
    """TENANT_USER survives the filter and is NOT upgraded to TENANT_ADMIN."""
    assert get_user_roles(current_user={"roles": ["TENANT_USER"]}) == ["TENANT_USER"]


def test_get_user_roles_empty_stays_empty():
    """Empty role list yields [] — the old `or ['TENANT_ADMIN']` fallback is gone."""
    assert get_user_roles(current_user={"roles": []}) == []
    # missing key behaves the same
    assert get_user_roles(current_user={}) == []


def test_get_user_roles_admin_regression():
    """TENANT_ADMIN still passes through unchanged."""
    assert get_user_roles(current_user={"roles": ["TENANT_ADMIN"]}) == ["TENANT_ADMIN"]


def test_get_user_roles_drops_unknown():
    """Unknown roles are filtered out; a lone bogus role yields []."""
    assert get_user_roles(current_user={"roles": ["WIZARD"]}) == []
    assert get_user_roles(
        current_user={"roles": ["TENANT_ADMIN", "WIZARD", "TENANT_USER"]}
    ) == ["TENANT_ADMIN", "TENANT_USER"]


def test_valid_roles_contains_both():
    assert VALID_ROLES == {"TENANT_ADMIN", "TENANT_USER"}


# ── (d) invite role validation ───────────────────────────────────────────────

def _jy_tenant_id(db):
    tid = db.execute(
        text("SELECT tenant_id FROM app_user WHERE email='jy@airline.com'")
    ).scalar()
    if tid is None:
        pytest.skip("jy@airline.com tenant not present")
    return tid


def _purge_email(db, email):
    """Remove any prior throwaway rows for this email (global-unique email)."""
    rows = db.query(AppUser).filter(AppUser.email == email).all()
    for u in rows:
        db.query(RoleBinding).filter(RoleBinding.user_id == u.id).delete(
            synchronize_session=False
        )
        db.execute(
            text("DELETE FROM password_reset_token WHERE user_id = :uid"),
            {"uid": str(u.id)},
        )
        db.delete(u)
    db.flush()


@pytest.mark.parametrize("role", ["TENANT_USER"])
def test_invite_accepts_valid_roles(db_session, monkeypatch, role):
    """invite_user creates the user + a RoleBinding with the requested role."""
    # Don't actually send mail — keep the test offline/deterministic.
    monkeypatch.setattr(
        "app.routers.admin_password_management.send_invite_email",
        lambda *a, **k: True,
    )
    tid = _jy_tenant_id(db_session)
    email = f"subtest-{role.lower()}@airline.com"
    _purge_email(db_session, email)

    body = AdminInviteUserRequest(
        email=email, display_name="Subtenant Test", tenant_id=tid, role=role,
    )
    resp = invite_user(body, db=db_session)

    assert str(resp.email).lower() == email
    binding = (
        db_session.query(RoleBinding)
        .filter(RoleBinding.user_id == resp.user_id)
        .first()
    )
    assert binding is not None and binding.role == role


def test_invite_rejects_bogus_role(db_session):
    """A role outside VALID_ROLES is rejected with 400 before any DB write."""
    tid = _jy_tenant_id(db_session)
    body = AdminInviteUserRequest(
        email="subtest-bogus@airline.com",
        display_name="Bogus", tenant_id=tid, role="WIZARD",
    )
    with pytest.raises(HTTPException) as ei:
        invite_user(body, db=db_session)
    assert ei.value.status_code == 400
    assert "Unsupported role" in str(ei.value.detail)


def test_invite_rejects_tenant_admin_role(db_session, monkeypatch):
    """Invites only create Subtenants: TENANT_ADMIN is a 400 and nothing is written."""
    monkeypatch.setattr(
        "app.routers.admin_password_management.send_invite_email",
        lambda *a, **k: pytest.fail("invite email must not be sent"),
    )
    tid = _jy_tenant_id(db_session)
    email = "subtest-admin-invite@airline.com"
    _purge_email(db_session, email)
    body = AdminInviteUserRequest(
        email=email, display_name="Admin Invite", tenant_id=tid, role="TENANT_ADMIN",
    )
    with pytest.raises(HTTPException) as ei:
        invite_user(body, db=db_session)
    assert ei.value.status_code == 400
    assert "Subtenant" in str(ei.value.detail)
    assert db_session.query(AppUser).filter(AppUser.email == email).first() is None


def test_invite_rejects_rts_platform_tenant(db_session, monkeypatch):
    """No user of any role can be invited into the RTS platform tenant."""
    monkeypatch.setattr(
        "app.routers.admin_password_management.send_invite_email",
        lambda *a, **k: pytest.fail("invite email must not be sent"),
    )
    rts_id = db_session.execute(
        text("SELECT id FROM tenant WHERE upper(slug) = 'RTS'")
    ).scalar()
    if rts_id is None:
        pytest.skip("RTS platform tenant not present")
    email = "subtest-rts-invite@airline.com"
    _purge_email(db_session, email)
    body = AdminInviteUserRequest(
        email=email, display_name="RTS Invite", tenant_id=rts_id, role="TENANT_USER",
    )
    with pytest.raises(HTTPException) as ei:
        invite_user(body, db=db_session)
    assert ei.value.status_code == 400
    assert "RTS platform tenant" in str(ei.value.detail)
    assert db_session.query(AppUser).filter(AppUser.email == email).first() is None


def test_invite_schema_default_is_least_privilege():
    """Default role is TENANT_USER (least privilege) when the UI omits it."""
    body = AdminInviteUserRequest(
        email="x@airline.com", display_name="X",
        tenant_id=uuid.uuid4(),
    )
    assert body.role == "TENANT_USER"


# ── (e) RequirePlatformAdmin guards the two tenant role routes ────────────────

def test_require_platform_admin_logic():
    """Guard passes for the RTS platform admin, 403s for everyone else."""
    guard = RequirePlatformAdmin()

    # platform admin: RTS identity + TENANT_ADMIN -> allowed (returns roles)
    assert guard(user_roles=["TENANT_ADMIN"], user_identity="RTS") == ["TENANT_ADMIN"]

    # non-platform tenant admin -> 403
    with pytest.raises(HTTPException) as ei1:
        guard(user_roles=["TENANT_ADMIN"], user_identity="JY")
    assert ei1.value.status_code == 403

    # a Subtenant (even in RTS) -> 403 (no TENANT_ADMIN role)
    with pytest.raises(HTTPException) as ei2:
        guard(user_roles=["TENANT_USER"], user_identity="RTS")
    assert ei2.value.status_code == 403


def _route_deps(path, method):
    # APIRouter stores routes with its prefix already applied, e.g.
    # "/api/v1/tenant/user-roles" — match on the declared suffix.
    for r in tenant_router_mod.router.routes:
        if getattr(r, "path", "").endswith(path) and method in getattr(r, "methods", set()):
            return r.dependencies
    raise AssertionError(f"route {method} {path} not found")


@pytest.mark.parametrize(
    "path,method",
    [("/user-roles", "GET"), ("/update-roles", "POST")],
)
def test_tenant_role_routes_are_guarded(path, method):
    """Each route carries a route-level RequirePlatformAdmin dependency."""
    deps = _route_deps(path, method)
    # Each entry is a fastapi Depends marker; .dependency is the callable.
    found = any(isinstance(getattr(d, "dependency", None), RequirePlatformAdmin) for d in deps)
    assert found, f"{method} {path} is missing the RequirePlatformAdmin guard"
