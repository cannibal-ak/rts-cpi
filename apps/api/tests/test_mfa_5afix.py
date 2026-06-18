"""Phase 5A-FIX tests — enroll/confirm no longer burns a TOTP step, and the
contract is body-shaped. Calls the router handlers directly against the
transactional db_session fixture (all writes rolled back). Run only this file:
    pytest tests/test_mfa_5afix.py -q
"""

import pyotp
import pytest
from fastapi import HTTPException

from app.models.mfa_recovery_code import MfaRecoveryCode
from app.models.user import AppUser
from app.models.user_mfa import UserMfa
from app.routers.mfa import ConfirmRequest, VerifyRequest, enroll_start, enroll_confirm, verify
from app.services.auth_service import create_mfa_challenge_token

EMAIL = "jy@airline.com"


def _user(db):
    u = db.query(AppUser).filter(AppUser.email == EMAIL).first()
    if u is None:
        pytest.skip(f"{EMAIL} not present")
    return u


def _clear(db, u):
    db.query(MfaRecoveryCode).filter(MfaRecoveryCode.user_id == u.id).delete()
    db.query(UserMfa).filter(UserMfa.user_id == u.id).delete()
    db.flush()


def _cu(u):
    return {"sub": str(u.id), "tenant_id": str(u.tenant_id), "email": u.email}


def _enroll(db, u):
    """Enroll via the real handlers; returns the TOTP secret."""
    secret = enroll_start(db=db, current_user=_cu(u))["secret"]
    enroll_confirm(ConfirmRequest(code=pyotp.TOTP(secret).now()), db=db, current_user=_cu(u))
    return secret


def test_enroll_confirm_leaves_last_used_step_null(db_session):
    u = _user(db_session); _clear(db_session, u)
    _enroll(db_session, u)
    mfa = db_session.query(UserMfa).filter(UserMfa.user_id == u.id).first()
    assert mfa.enabled is True
    assert mfa.last_used_step is None


def test_first_verify_same_window_succeeds(db_session):
    u = _user(db_session); _clear(db_session, u)
    secret = _enroll(db_session, u)
    # SAME window as enroll/confirm — no sleep. Pre-fix this 401'd.
    tok = create_mfa_challenge_token(str(u.id), str(u.tenant_id))
    resp = verify(VerifyRequest(mfa_token=tok, code=pyotp.TOTP(secret).now()), db=db_session)
    assert resp.access_token and resp.refresh_token


def test_verify_replay_still_rejected(db_session):
    u = _user(db_session); _clear(db_session, u)
    secret = _enroll(db_session, u)
    code = pyotp.TOTP(secret).now()
    tok1 = create_mfa_challenge_token(str(u.id), str(u.tenant_id))
    verify(VerifyRequest(mfa_token=tok1, code=code), db=db_session)  # consumes the step
    tok2 = create_mfa_challenge_token(str(u.id), str(u.tenant_id))
    with pytest.raises(HTTPException) as ei:
        verify(VerifyRequest(mfa_token=tok2, code=code), db=db_session)
    assert ei.value.status_code == 401


def test_contract_body_shape():
    # The backend reads the challenge token from the body field `mfa_token`.
    m = VerifyRequest(mfa_token="tok", code="123456")
    assert m.mfa_token == "tok" and m.is_recovery is False
    with pytest.raises(Exception):
        VerifyRequest(code="123456")  # mfa_token is required
