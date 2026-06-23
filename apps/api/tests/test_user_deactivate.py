"""Focused tests for the user deactivate/reactivate feature (Phase 1, A9).

Handlers are called directly against the transactional db_session fixture
(all writes rolled back at test end), mirroring tests/test_password_reset_mfa.py.

Run ONLY this file (the full suite has known-unrelated failures):
    pytest tests/test_user_deactivate.py -q
"""

import uuid

import pytest
from fastapi import HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.core import crypto
from app.core.config import settings
from app.models.user import AppUser
from app.models.user_mfa import UserMfa
from app.routers.admin_password_management import deactivate_user, reactivate_user
from app.routers.auth import login, refresh, LoginRequest, RefreshRequest
from app.services.auth_service import hash_password, create_refresh_token

PW = "TempPass2026!xy"
TEST_EMAIL = "deact-test@airline.com"


def _tenant_id(db):
    tid = db.execute(
        text("SELECT tenant_id FROM app_user WHERE email='jy@airline.com'")
    ).scalar()
    if tid is None:
        pytest.skip("jy@airline.com tenant not present")
    return tid


def _make_user(db, *, active=True):
    """Create a throwaway tenant user with a known password (rolled back)."""
    db.query(AppUser).filter(AppUser.email == TEST_EMAIL).delete()
    u = AppUser(
        tenant_id=_tenant_id(db),
        email=TEST_EMAIL,
        display_name="Deactivate Test",
        is_active=active,
        password_hash=hash_password(PW),
        must_change_password=False,
    )
    db.add(u)
    db.flush()
    return u


def _reload(db, user_id):
    return db.query(AppUser).filter(AppUser.id == user_id).first()


# 1) deactivate flips the flag -------------------------------------------------
def test_deactivate_flips_flag(db_session, admin_jwt_payload):
    u = _make_user(db_session, active=True)
    resp = deactivate_user(u.id, db=db_session, current_user=admin_jwt_payload)
    assert resp.status_code == 204
    assert _reload(db_session, u.id).is_active is False


# 2) deactivated user /login -> 403 -------------------------------------------
def test_deactivated_login_403(db_session):
    u = _make_user(db_session, active=False)
    with pytest.raises(HTTPException) as ei:
        login(LoginRequest(email=u.email, password=PW), db=db_session)
    assert ei.value.status_code == 403
    assert "disabled" in str(ei.value.detail).lower()


# 3) deactivated user refresh -> rejected -------------------------------------
def test_deactivated_refresh_rejected(db_session):
    u = _make_user(db_session, active=False)
    token = create_refresh_token({
        "sub": str(u.id), "tenant_id": str(u.tenant_id),
        "email": u.email, "roles": [], "tenant_slug": "jy",
    })
    with pytest.raises(HTTPException) as ei:
        refresh(RefreshRequest(refresh_token=token), db=db_session)
    assert ei.value.status_code in (401, 403)


# 4) reactivate restores login ------------------------------------------------
def test_reactivate_restores_login(db_session, admin_jwt_payload):
    u = _make_user(db_session, active=False)
    resp = reactivate_user(u.id, db=db_session, current_user=admin_jwt_payload)
    assert resp.status_code == 204
    assert _reload(db_session, u.id).is_active is True
    ok = login(LoginRequest(email=u.email, password=PW), db=db_session)
    assert getattr(ok, "access_token", None)
    assert ok.user["is_active"] is True


# 5) self-deactivate blocked --------------------------------------------------
def test_self_deactivate_blocked(db_session, admin_jwt_payload):
    with pytest.raises(HTTPException) as ei:
        deactivate_user(
            uuid.UUID(admin_jwt_payload["sub"]),
            db=db_session, current_user=admin_jwt_payload,
        )
    assert ei.value.status_code == 400


# 6) super-admin deactivate blocked (by a DIFFERENT admin actor) --------------
def test_superadmin_deactivate_blocked(db_session, admin_user):
    actor = {"sub": str(uuid.uuid4()), "tenant_id": str(admin_user["tenant_id"])}
    with pytest.raises(HTTPException) as ei:
        deactivate_user(admin_user["id"], db=db_session, current_user=actor)
    assert ei.value.status_code == 400
    assert "super" in str(ei.value.detail).lower()


# 7) tenant user is forbidden by the router-level RBAC guard ------------------
def test_tenant_user_forbidden_rbac(jy_jwt_payload):
    from app.core.deps import RequirePlatformAdmin, get_user_roles, get_user_identity
    roles = get_user_roles(jy_jwt_payload)
    identity = get_user_identity(jy_jwt_payload)
    with pytest.raises(HTTPException) as ei:
        RequirePlatformAdmin()(user_roles=roles, user_identity=identity)
    assert ei.value.status_code == 403


# 8) unauthenticated -> 401 ---------------------------------------------------
def test_unauth_401():
    from app.core.deps import get_current_user
    with pytest.raises(HTTPException) as ei:
        get_current_user(token=None, db=None)
    assert ei.value.status_code == 401


# REGRESSION A: active user login path unchanged (full tokens) ----------------
def test_active_user_login_unchanged(db_session):
    u = _make_user(db_session, active=True)
    resp = login(LoginRequest(email=u.email, password=PW), db=db_session)
    assert resp.access_token and resp.refresh_token
    assert resp.user["is_active"] is True


# REGRESSION B: active MFA-enrolled user still hits the MFA challenge ----------
# Proves the active-account gate sits BEFORE the MFA branch and does not
# alter MFA behaviour for active users.
def test_active_mfa_user_still_challenged(db_session, monkeypatch):
    u = _make_user(db_session, active=True)
    db_session.add(UserMfa(
        tenant_id=u.tenant_id, user_id=u.id, enabled=True,
        secret_ciphertext=crypto.encrypt_str("JBSWY3DPEHPK3PXP"),
    ))
    db_session.flush()
    monkeypatch.setattr(settings, "mfa_enforced", True)
    resp = login(LoginRequest(email=u.email, password=PW), db=db_session)
    assert isinstance(resp, JSONResponse)
    assert resp.status_code == 200
    assert b"mfa_challenge_token" in resp.body


# REGRESSION C: wrong password against an INACTIVE account still 401 ----------
# (no account-existence leak — only correct password reveals the 403).
def test_inactive_wrong_password_still_401(db_session):
    u = _make_user(db_session, active=False)
    with pytest.raises(HTTPException) as ei:
        login(LoginRequest(email=u.email, password="WrongPass!123"), db=db_session)
    assert ei.value.status_code == 401
    assert "disabled" not in str(ei.value.detail).lower()
