"""Phase 2C tests — two-step /login branch + forced-enrollment gate.

Calls the login() handler and require_mfa_satisfied() directly against the
transactional db_session fixture (all writes rolled back), with
settings.mfa_enforced monkeypatched. Run only this file:
    pytest tests/test_mfa_phase2c.py -q
"""

import json
import types

import pytest
from fastapi import HTTPException
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.deps import mfa_required_for, require_mfa_satisfied
from app.models.user import AppUser
from app.models.user_mfa import UserMfa
from app.routers.auth import LoginRequest, TokenResponse, login
from app.services.auth_service import hash_password

PW = "Phase2cTest!xx9"


def _user(db, email):
    u = db.query(AppUser).filter(AppUser.email == email).first()
    if u is None:
        pytest.skip(f"{email} not present in DB")
    return u


def _fake_request(path="/api/v1/airline/cpi"):
    return types.SimpleNamespace(url=types.SimpleNamespace(path=path))


def _reset(db, user, *, exempt):
    user.password_hash = hash_password(PW)
    user.mfa_exempt = exempt
    user.failed_login_count = 0
    user.locked_until = None
    db.query(UserMfa).filter(UserMfa.user_id == user.id).delete()
    db.flush()


def _enable_mfa(db, user):
    db.add(UserMfa(tenant_id=user.tenant_id, user_id=user.id, enabled=True, secret_ciphertext=b"x"))
    db.flush()


@pytest.fixture
def enforce_on(monkeypatch):
    monkeypatch.setattr(settings, "mfa_enforced", True)


# 1) enrolled, non-exempt, non-admin -> /login returns the challenge
def test_login_enrolled_required_returns_challenge(db_session, enforce_on):
    user = _user(db_session, "jy@airline.com")
    _reset(db_session, user, exempt=False)
    _enable_mfa(db_session, user)

    resp = login(LoginRequest(email="jy@airline.com", password=PW), db=db_session)
    assert isinstance(resp, JSONResponse)
    body = json.loads(resp.body)
    assert body.get("mfa_required") is True
    assert body.get("challenge_expires_in") == 300
    assert "mfa_challenge_token" in body
    assert "access_token" not in body and "refresh_token" not in body


# 2) not-enrolled, non-exempt -> full tokens BUT gate raises mfa_setup_required
def test_login_not_enrolled_required_tokens_then_gate_blocks(db_session, enforce_on):
    user = _user(db_session, "jy@airline.com")
    _reset(db_session, user, exempt=False)

    resp = login(LoginRequest(email="jy@airline.com", password=PW), db=db_session)
    assert isinstance(resp, TokenResponse)
    assert resp.access_token and resp.refresh_token

    cu = {"sub": str(user.id), "roles": ["TENANT_ADMIN"], "tenant_slug": "jy"}
    with pytest.raises(HTTPException) as ei:
        require_mfa_satisfied(_fake_request(), current_user=cu, db=db_session)
    assert ei.value.status_code == 403
    assert ei.value.detail["code"] == "mfa_setup_required"


# 3a) mfa_exempt -> full tokens, gate passes
def test_exempt_user_tokens_and_gate_passes(db_session, enforce_on):
    user = _user(db_session, "jy@airline.com")
    _reset(db_session, user, exempt=True)

    resp = login(LoginRequest(email="jy@airline.com", password=PW), db=db_session)
    assert isinstance(resp, TokenResponse)
    cu = {"sub": str(user.id), "roles": ["TENANT_ADMIN"], "tenant_slug": "jy"}
    assert require_mfa_satisfied(_fake_request(), current_user=cu, db=db_session) == cu
    assert mfa_required_for(user, ["TENANT_ADMIN"], "jy") is False


# 3b) super-admin (RTS platform) -> full tokens, gate passes
def test_platform_admin_tokens_and_gate_passes(db_session, enforce_on):
    user = _user(db_session, "admin@rts.com")
    _reset(db_session, user, exempt=False)

    resp = login(LoginRequest(email="admin@rts.com", password=PW), db=db_session)
    assert isinstance(resp, TokenResponse)
    cu = {"sub": str(user.id), "roles": ["TENANT_ADMIN"], "tenant_slug": "rts"}
    assert require_mfa_satisfied(_fake_request(), current_user=cu, db=db_session) == cu
    assert mfa_required_for(user, ["TENANT_ADMIN"], "rts") is False


# 4) flag OFF -> even an enrolled user gets full tokens (resting state)
def test_flag_off_full_tokens_even_if_enrolled(db_session, monkeypatch):
    monkeypatch.setattr(settings, "mfa_enforced", False)
    user = _user(db_session, "jy@airline.com")
    _reset(db_session, user, exempt=False)
    _enable_mfa(db_session, user)

    resp = login(LoginRequest(email="jy@airline.com", password=PW), db=db_session)
    assert isinstance(resp, TokenResponse)
    cu = {"sub": str(user.id), "roles": ["TENANT_ADMIN"], "tenant_slug": "jy"}
    # gate inert when flag off
    assert require_mfa_satisfied(_fake_request(), current_user=cu, db=db_session) == cu
