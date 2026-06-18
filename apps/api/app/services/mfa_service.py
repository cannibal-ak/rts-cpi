"""MFA (TOTP) service — pure TOTP/recovery helpers + small DB-aware helpers.

Reuse, not reinvention:
  - the TOTP secret is encrypted at rest with ``app.core.crypto`` (Fernet /
    CPI_KEK) by the caller — this module only generates/verifies the secret.
  - recovery codes are persisted ONLY as ``app.core.security.hash_token``
    (SHA-256) digests; the plaintext is returned to the user exactly once.

SECURITY: secrets and recovery codes are NEVER logged here. TOTP comparison
is constant-time (``hmac.compare_digest``). A replay guard rejects any code
whose time-step has already been consumed (``last_used_step``).
"""

import hmac
import secrets
from datetime import datetime, timedelta, timezone

import pyotp
from sqlalchemy.orm import Session

from app.core.security import hash_token
from app.models.mfa_recovery_code import MfaRecoveryCode

# TOTP parameters (RFC 6238 defaults — must match the authenticator app).
TOTP_PERIOD = 30
TOTP_DIGITS = 6
TOTP_WINDOW = 1  # accept the step before / current / after: {-1, 0, +1}
ISSUER_NAME = "Altitude AI"

RECOVERY_CODE_COUNT = 10

# Verify-attempt throttle — mirrors the login lockout in app/routers/auth.py.
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_MINUTES = 15


# ── TOTP secret + provisioning ───────────────────

def generate_secret() -> str:
    """A fresh base32 TOTP secret."""
    return pyotp.random_base32()


def provisioning_uri(secret: str, email: str) -> str:
    """otpauth:// URI for QR enrollment (issuer 'Altitude AI')."""
    return pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name=ISSUER_NAME)


# ── TOTP verification (replay-guarded, constant-time) ─

def verify_totp(secret, code, last_used_step=None, for_time=None):
    """Verify a TOTP code across the step window.

    Returns ``(ok, matched_step)``:
      - ``(True, step)``  — valid and not a replay; caller stores ``step``
        as the new ``last_used_step``.
      - ``(False, step)`` — code matched a step already used (replay).
      - ``(False, None)`` — no match / malformed.
    """
    code = (code or "").strip()
    if not (code.isdigit() and len(code) == TOTP_DIGITS):
        return (False, None)

    now = for_time or datetime.now(timezone.utc)
    totp = pyotp.TOTP(secret, digits=TOTP_DIGITS, interval=TOTP_PERIOD)
    base_step = int(now.timestamp() // TOTP_PERIOD)

    for offset in range(-TOTP_WINDOW, TOTP_WINDOW + 1):
        expected = totp.at(now, offset)
        if hmac.compare_digest(expected, code):
            step = base_step + offset
            if last_used_step is not None and step <= last_used_step:
                return (False, step)  # replay
            return (True, step)
    return (False, None)


# ── Recovery codes ───────────────────────────────

def generate_recovery_codes(n=RECOVERY_CODE_COUNT):
    """Return ``n`` human-typable one-time codes in ``xxxx-xxxx`` form.

    Plaintext only — the caller persists ``hash_token(code)`` rows and shows
    the plaintext list to the user a single time.
    """
    codes = []
    for _ in range(n):
        raw = secrets.token_hex(4)  # 8 hex chars
        codes.append(f"{raw[:4]}-{raw[4:]}")
    return codes


def verify_and_consume_recovery_code(db: Session, user_id, code, for_time=None) -> bool:
    """Find an UNUSED recovery code matching ``code`` for the user and mark it
    used (single-use). Returns True on success. Caller commits."""
    now = for_time or datetime.now(timezone.utc)
    digest = hash_token((code or "").strip())
    row = (
        db.query(MfaRecoveryCode)
        .filter(
            MfaRecoveryCode.user_id == user_id,
            MfaRecoveryCode.code_hash == digest,
            MfaRecoveryCode.used_at.is_(None),
        )
        .first()
    )
    if row is None:
        return False
    row.used_at = now
    return True


def recovery_codes_remaining(db: Session, user_id) -> int:
    return (
        db.query(MfaRecoveryCode)
        .filter(
            MfaRecoveryCode.user_id == user_id,
            MfaRecoveryCode.used_at.is_(None),
        )
        .count()
    )


# ── Lockout helpers (operate on a user_mfa row) ──

def is_locked(mfa, now=None) -> bool:
    now = now or datetime.now(timezone.utc)
    return mfa.locked_until is not None and mfa.locked_until > now


def register_failure(mfa, now=None) -> None:
    """Increment the failure counter; lock for LOCKOUT_MINUTES at the cap."""
    now = now or datetime.now(timezone.utc)
    mfa.failed_attempts = (mfa.failed_attempts or 0) + 1
    if mfa.failed_attempts >= MAX_FAILED_ATTEMPTS:
        mfa.locked_until = now + timedelta(minutes=LOCKOUT_MINUTES)


def register_success(mfa, matched_step=None) -> None:
    """Reset the throttle and advance the replay guard on a good verify."""
    mfa.failed_attempts = 0
    mfa.locked_until = None
    if matched_step is not None:
        mfa.last_used_step = matched_step
