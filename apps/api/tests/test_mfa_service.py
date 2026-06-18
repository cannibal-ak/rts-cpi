"""Focused unit tests for app.services.mfa_service (Phase 2B).

Scope: secret generation, encrypt/decrypt round-trip via app.core.crypto,
TOTP happy path, replay rejection, ±1 step window tolerance, lockout after
5 failures, and recovery-code single-use. Deliberately narrow — run with
``pytest tests/test_mfa_service.py -q`` (the full suite has unrelated
pre-existing failures).
"""

import base64
from datetime import datetime, timedelta, timezone

import pyotp

from app.core import crypto
from app.core.security import hash_token
from app.models.mfa_recovery_code import MfaRecoveryCode
from app.models.user_mfa import UserMfa
from app.services import mfa_service


def test_generate_secret_is_base32():
    s = mfa_service.generate_secret()
    assert isinstance(s, str) and len(s) >= 16
    # Decodes as base32 (pyotp uses the standard alphabet) — no exception.
    base64.b32decode(s)


def test_encrypt_decrypt_roundtrip():
    s = mfa_service.generate_secret()
    ct = crypto.encrypt_str(s)
    assert isinstance(ct, bytes)
    assert ct != s.encode()  # actually encrypted, not stored plaintext
    assert crypto.decrypt_str(ct) == s


def test_verify_happy_path():
    s = mfa_service.generate_secret()
    now = datetime.now(timezone.utc)
    code = pyotp.TOTP(s).at(now)
    ok, step = mfa_service.verify_totp(s, code, None, for_time=now)
    assert ok is True
    assert step == int(now.timestamp() // mfa_service.TOTP_PERIOD)


def test_replay_rejected():
    s = mfa_service.generate_secret()
    now = datetime.now(timezone.utc)
    code = pyotp.TOTP(s).at(now)
    ok, step = mfa_service.verify_totp(s, code, None, for_time=now)
    assert ok is True
    # Same code, now with last_used_step == step → must be rejected as replay.
    ok2, step2 = mfa_service.verify_totp(s, code, step, for_time=now)
    assert ok2 is False
    assert step2 == step


def test_window_tolerance():
    s = mfa_service.generate_secret()
    now = datetime.now(timezone.utc)
    code_prev = pyotp.TOTP(s).at(now - timedelta(seconds=mfa_service.TOTP_PERIOD))
    code_next = pyotp.TOTP(s).at(now + timedelta(seconds=mfa_service.TOTP_PERIOD))
    assert mfa_service.verify_totp(s, code_prev, None, for_time=now)[0] is True
    assert mfa_service.verify_totp(s, code_next, None, for_time=now)[0] is True
    # Two steps away is outside the window → rejected.
    far = pyotp.TOTP(s).at(now - timedelta(seconds=3 * mfa_service.TOTP_PERIOD))
    assert mfa_service.verify_totp(s, far, None, for_time=now)[0] is False


def test_lockout_after_5_failures():
    mfa = UserMfa(failed_attempts=0)
    for _ in range(mfa_service.MAX_FAILED_ATTEMPTS):
        mfa_service.register_failure(mfa)
    assert mfa.failed_attempts == mfa_service.MAX_FAILED_ATTEMPTS
    assert mfa_service.is_locked(mfa) is True
    # A success clears the throttle and advances the replay step.
    mfa_service.register_success(mfa, matched_step=123)
    assert mfa.failed_attempts == 0
    assert mfa.locked_until is None
    assert mfa.last_used_step == 123
    assert mfa_service.is_locked(mfa) is False


def test_recovery_code_single_use(db_session, admin_user):
    codes = mfa_service.generate_recovery_codes(3)
    for c in codes:
        db_session.add(
            MfaRecoveryCode(
                tenant_id=admin_user["tenant_id"],
                user_id=admin_user["id"],
                code_hash=hash_token(c),
            )
        )
    db_session.flush()

    # First use succeeds.
    assert mfa_service.verify_and_consume_recovery_code(db_session, admin_user["id"], codes[0]) is True
    db_session.flush()
    # Second use of the same code fails (single-use).
    assert mfa_service.verify_and_consume_recovery_code(db_session, admin_user["id"], codes[0]) is False
    # An unknown code fails.
    assert mfa_service.verify_and_consume_recovery_code(db_session, admin_user["id"], "zzzz-zzzz") is False
    # Two unused codes remain.
    assert mfa_service.recovery_codes_remaining(db_session, admin_user["id"]) == 2
