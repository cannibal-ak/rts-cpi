"""Phase 3 tests — MFA-based password reset (init enumeration-safety + verify).

Calls init()/verify() handlers directly against the transactional db_session
fixture (all writes rolled back), with no SMTP involved. Run only this file:
    pytest tests/test_password_reset_mfa.py -q
"""

import types
import uuid
from datetime import datetime, timedelta, timezone

import pyotp
import pytest
from fastapi import HTTPException
from jose import jwt

from app.core import crypto
from app.core.config import settings
from app.core.security import hash_token
from app.models.mfa_recovery_code import MfaRecoveryCode
from app.models.user import AppUser
from app.models.user_mfa import UserMfa
from app.routers.password_reset_mfa import InitRequest, VerifyRequest, init, verify
from app.services.auth_service import (
    create_password_reset_token,
    decode_password_reset_token,
    verify_password,
)

NEW_PW = "NewReset2026!ab"


def _user(db, email):
    u = db.query(AppUser).filter(AppUser.email == email).first()
    if u is None:
        pytest.skip(f"{email} not present")
    return u


def _enroll(db, user, *, secret=None, last_used_step=None):
    db.query(UserMfa).filter(UserMfa.user_id == user.id).delete()
    secret = secret or pyotp.random_base32()
    db.add(UserMfa(
        tenant_id=user.tenant_id, user_id=user.id, enabled=True,
        secret_ciphertext=crypto.encrypt_str(secret), last_used_step=last_used_step,
    ))
    db.flush()
    return secret


def _req():
    return types.SimpleNamespace(client=types.SimpleNamespace(host="127.0.0.1"))


# 1) init is enumeration-safe: identical shape; internal eligibility differs
def test_init_enumeration_safe(db_session):
    jy = _user(db_session, "jy@airline.com")
    _enroll(db_session, jy)

    r_known = init(InitRequest(email="jy@airline.com"), _req(), db=db_session)
    r_unknown = init(InitRequest(email="nobody-xyz@example.com"), _req(), db=db_session)

    assert set(r_known.model_dump().keys()) == set(r_unknown.model_dump().keys())
    assert r_known.message == r_unknown.message
    assert r_known.expires_in == r_unknown.expires_in
    # Internal eligibility differs (encoded in the token, not the shape).
    assert decode_password_reset_token(r_known.reset_token)["eligible"] is True
    assert decode_password_reset_token(r_unknown.reset_token)["eligible"] is False


# 2) correct TOTP -> password actually changes + must_change_password cleared
def test_verify_totp_resets_password(db_session):
    jy = _user(db_session, "jy@airline.com")
    jy.must_change_password = True
    secret = _enroll(db_session, jy)
    orig_hash = jy.password_hash
    token = create_password_reset_token(str(jy.id), str(jy.tenant_id), True)

    resp = verify(VerifyRequest(reset_token=token, code=pyotp.TOTP(secret).now(),
                                new_password=NEW_PW), db=db_session)
    assert resp.success is True

    u = db_session.query(AppUser).filter(AppUser.id == jy.id).first()
    assert u.password_hash != orig_hash
    assert verify_password(NEW_PW, u.password_hash) is True
    assert u.must_change_password is False


# 3) wrong code -> 401 + lockout increments
def test_verify_wrong_code_increments_lockout(db_session):
    jy = _user(db_session, "jy@airline.com")
    _enroll(db_session, jy)
    token = create_password_reset_token(str(jy.id), str(jy.tenant_id), True)

    with pytest.raises(HTTPException) as ei:
        verify(VerifyRequest(reset_token=token, code="000000", new_password=NEW_PW), db=db_session)
    assert ei.value.status_code == 401
    mfa = db_session.query(UserMfa).filter(UserMfa.user_id == jy.id).first()
    assert mfa.failed_attempts == 1


# 4) ineligible token -> 401
def test_verify_ineligible_token(db_session):
    token = create_password_reset_token(str(uuid.uuid4()), "00000000-0000-0000-0000-000000000000", False)
    with pytest.raises(HTTPException) as ei:
        verify(VerifyRequest(reset_token=token, code="123456", new_password=NEW_PW), db=db_session)
    assert ei.value.status_code == 401


# 5) expired token -> 401
def test_verify_expired_token(db_session):
    jy = _user(db_session, "jy@airline.com")
    _enroll(db_session, jy)
    now = datetime.now(timezone.utc)
    expired = jwt.encode(
        {"sub": str(jy.id), "tenant_id": str(jy.tenant_id), "eligible": True,
         "token_type": "pwd_reset", "iat": now - timedelta(minutes=20),
         "exp": now - timedelta(minutes=1), "jti": str(uuid.uuid4())},
        settings.jwt_secret_key, algorithm=settings.jwt_algorithm,
    )
    with pytest.raises(HTTPException) as ei:
        verify(VerifyRequest(reset_token=expired, code="123456", new_password=NEW_PW), db=db_session)
    assert ei.value.status_code == 401


# 6) recovery-code path resets the password (single-use)
def test_verify_recovery_code_resets(db_session):
    jy = _user(db_session, "jy@airline.com")
    _enroll(db_session, jy)
    codes = mfa_recovery = ["abcd-1234", "ffff-0000"]
    for c in codes:
        db_session.add(MfaRecoveryCode(tenant_id=jy.tenant_id, user_id=jy.id, code_hash=hash_token(c)))
    db_session.flush()
    orig_hash = jy.password_hash
    token = create_password_reset_token(str(jy.id), str(jy.tenant_id), True)

    resp = verify(VerifyRequest(reset_token=token, code="abcd-1234", new_password=NEW_PW,
                                is_recovery=True), db=db_session)
    assert resp.success is True
    u = db_session.query(AppUser).filter(AppUser.id == jy.id).first()
    assert verify_password(NEW_PW, u.password_hash) is True
    # code consumed
    row = db_session.query(MfaRecoveryCode).filter(
        MfaRecoveryCode.user_id == jy.id, MfaRecoveryCode.code_hash == hash_token("abcd-1234")
    ).first()
    assert row.used_at is not None


# 7) replay — same TOTP twice is rejected
def test_verify_totp_replay_rejected(db_session):
    jy = _user(db_session, "jy@airline.com")
    secret = _enroll(db_session, jy)
    code = pyotp.TOTP(secret).now()

    t1 = create_password_reset_token(str(jy.id), str(jy.tenant_id), True)
    r1 = verify(VerifyRequest(reset_token=t1, code=code, new_password=NEW_PW), db=db_session)
    assert r1.success is True

    t2 = create_password_reset_token(str(jy.id), str(jy.tenant_id), True)
    with pytest.raises(HTTPException) as ei:
        verify(VerifyRequest(reset_token=t2, code=code, new_password=NEW_PW + "x"), db=db_session)
    assert ei.value.status_code == 401
