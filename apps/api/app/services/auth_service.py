"""Authentication service — password hashing, JWT tokens, validation."""

import re
import uuid
from datetime import datetime, timedelta, timezone

from jose import jwt, JWTError, ExpiredSignatureError
from passlib.context import CryptContext

from app.core.config import settings

# ── Password hashing ─────────────────────────────

_pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=settings.bcrypt_rounds)


def hash_password(plain: str) -> str:
    return _pwd_ctx.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return _pwd_ctx.verify(plain, hashed)


# ── Password strength validation ─────────────────

def validate_password_strength(plain: str) -> tuple[bool, str]:
    """Returns (is_valid, error_message). Empty error_message on success."""
    if len(plain) < settings.password_min_length:
        return False, f"Password must be at least {settings.password_min_length} characters"
    if not re.search(r"[A-Z]", plain):
        return False, "Password must contain at least one uppercase letter"
    if not re.search(r"[a-z]", plain):
        return False, "Password must contain at least one lowercase letter"
    if not re.search(r"\d", plain):
        return False, "Password must contain at least one digit"
    if not re.search(r"[!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>/?`~]", plain):
        return False, "Password must contain at least one special character"
    return True, ""


# ── JWT token creation ───────────────────────────

def create_access_token(subject: dict, expires_delta: timedelta | None = None) -> str:
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=settings.jwt_access_token_expire_minutes))
    payload = {
        **subject,
        "token_type": "access",
        "iat": datetime.now(timezone.utc),
        "exp": expire,
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_refresh_token(subject: dict) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=settings.jwt_refresh_token_expire_days)
    payload = {
        **subject,
        "token_type": "refresh",
        "iat": datetime.now(timezone.utc),
        "exp": expire,
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


# ── MFA challenge token ──────────────────────────
# Short-lived, single-purpose token minted by a (future, Phase 2C) two-step
# login once the password is verified but TOTP is still pending. It carries
# ONLY enough identity to look up the user_mfa row at /verify; it is NOT an
# access token and decode_mfa_challenge_token() rejects any other token_type.
# get_current_user already requires token_type == "access", so a challenge
# token can never be used as an access token.

MFA_CHALLENGE_EXPIRE_MINUTES = 5


def create_mfa_challenge_token(user_id: str, tenant_id: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "tenant_id": str(tenant_id),
        "token_type": "mfa_challenge",
        "iat": now,
        "exp": now + timedelta(minutes=MFA_CHALLENGE_EXPIRE_MINUTES),
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


# ── JWT token decoding ───────────────────────────

class TokenError(Exception):
    """Raised when a token is invalid or expired."""
    pass


class TokenExpiredError(TokenError):
    pass


def decode_token(token: str) -> dict:
    """Decode and verify a JWT token. Raises TokenError or TokenExpiredError."""
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        if "sub" not in payload:
            raise TokenError("Token missing 'sub' claim")
        return payload
    except ExpiredSignatureError:
        raise TokenExpiredError("Token has expired")
    except JWTError as e:
        raise TokenError(f"Invalid token: {e}")


def decode_mfa_challenge_token(token: str) -> dict:
    """Decode a token and REQUIRE token_type == 'mfa_challenge'.

    Raises TokenExpiredError / TokenError (incl. when the token_type is
    anything else) so an access/refresh token can never satisfy /verify.
    """
    payload = decode_token(token)
    if payload.get("token_type") != "mfa_challenge":
        raise TokenError("Not an mfa_challenge token")
    return payload


# ── Password-reset (MFA-based, Phase 3) token ────
# Issued unauthenticated by /api/v1/auth/password-reset/mfa/init once an
# email is submitted. The `eligible` flag keeps the init response identical
# whether or not the account exists / has MFA: ineligible callers receive a
# token with a random, non-resolvable sub and eligible=false.

PWD_RESET_EXPIRE_MINUTES = 10


def create_password_reset_token(user_id: str, tenant_id: str, eligible: bool) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "tenant_id": str(tenant_id),
        "eligible": bool(eligible),
        "token_type": "pwd_reset",
        "iat": now,
        "exp": now + timedelta(minutes=PWD_RESET_EXPIRE_MINUTES),
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_password_reset_token(token: str) -> dict:
    """Decode and REQUIRE token_type == 'pwd_reset'.

    Raises TokenExpiredError / TokenError (incl. when token_type is anything
    else) so an access / refresh / mfa_challenge token cannot satisfy the
    MFA-based password reset.
    """
    payload = decode_token(token)
    if payload.get("token_type") != "pwd_reset":
        raise TokenError("Not a pwd_reset token")
    return payload
