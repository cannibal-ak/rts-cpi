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
