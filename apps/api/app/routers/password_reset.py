"""Password reset endpoints — request code, verify code, reset password.

UNAUTHENTICATED endpoints. Locked-out users invoke these without a JWT.
Protection layers in lieu of auth:
  - Per-email rate limit on /forgot-password (3/hour).
  - Per-token attempt limit on /verify-reset-code and /reset-password (5).
  - 5-minute TTL on every code.
  - Email-enumeration resistance: identical generic response whether or
    not the user exists, and identical response when rate-limited.
"""

import logging
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.user import AppUser
from app.models.password_reset_token import PasswordResetToken
from app.schemas.password_reset import (
    PasswordResetRequest,
    PasswordResetVerify,
    PasswordResetNewPassword,
    PasswordResetResponse,
)
from app.services.auth_service import (
    hash_password,
    validate_password_strength,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/auth", tags=["password-reset"])

CODE_TTL_MINUTES = 5
MAX_CODE_ATTEMPTS = 5
RATE_LIMIT_PER_HOUR = 3

GENERIC_REQUEST_MESSAGE = (
    "If an account exists with this email, a verification code has been generated."
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _generate_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def _client_ip(req: Request) -> str | None:
    return req.client.host if req.client else None


def _find_active_token(db: Session, email: str) -> PasswordResetToken | None:
    return (
        db.query(PasswordResetToken)
        .filter(
            PasswordResetToken.email == email,
            PasswordResetToken.used == False,  # noqa: E712 — SQLAlchemy idiom
            PasswordResetToken.expires_at > _now(),
        )
        .order_by(PasswordResetToken.created_at.desc())
        .first()
    )


# ── POST /forgot-password ────────────────────────

@router.post("/forgot-password", response_model=PasswordResetResponse)
def forgot_password(
    body: PasswordResetRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    email = body.email.lower()

    user = (
        db.query(AppUser)
        .filter(AppUser.email == email, AppUser.is_active == True)  # noqa: E712
        .first()
    )
    if not user:
        # Don't reveal that the email isn't registered.
        return PasswordResetResponse(success=True, message=GENERIC_REQUEST_MESSAGE)

    # Per-email rate limit: 3 tokens / hour.
    one_hour_ago = _now() - timedelta(hours=1)
    recent_count = (
        db.query(PasswordResetToken)
        .filter(
            PasswordResetToken.email == email,
            PasswordResetToken.created_at >= one_hour_ago,
        )
        .count()
    )
    if recent_count >= RATE_LIMIT_PER_HOUR:
        logger.warning(
            "Password reset rate-limited for %s (%d in last hour)", email, recent_count
        )
        return PasswordResetResponse(success=True, message=GENERIC_REQUEST_MESSAGE)

    # Invalidate any previously unused tokens for this email.
    db.query(PasswordResetToken).filter(
        PasswordResetToken.email == email,
        PasswordResetToken.used == False,  # noqa: E712
    ).update({PasswordResetToken.used: True})

    code = _generate_code()
    token = PasswordResetToken(
        user_id=user.id,
        email=email,
        code=code,
        expires_at=_now() + timedelta(minutes=CODE_TTL_MINUTES),
        ip_address=_client_ip(request),
    )
    db.add(token)
    db.commit()

    logger.info(
        "Password reset code issued for %s (expires in %d min)", email, CODE_TTL_MINUTES
    )

    return PasswordResetResponse(
        success=True,
        message=GENERIC_REQUEST_MESSAGE,
        # TODO: REMOVE admin_debug_code when SMTP email delivery is implemented.
        admin_debug_code=code,
    )


# ── POST /verify-reset-code ──────────────────────

@router.post("/verify-reset-code", response_model=PasswordResetResponse)
def verify_reset_code(body: PasswordResetVerify, db: Session = Depends(get_db)):
    email = body.email.lower()
    token = _find_active_token(db, email)

    if not token:
        return PasswordResetResponse(success=False, message="Invalid or expired code.")

    if token.attempts >= MAX_CODE_ATTEMPTS:
        return PasswordResetResponse(
            success=False,
            message="Too many failed attempts. Request a new code.",
        )

    if token.code != body.code:
        token.attempts += 1
        db.commit()
        return PasswordResetResponse(success=False, message="Invalid code.")

    # Verified — DO NOT mark used yet; that happens on actual password reset.
    return PasswordResetResponse(success=True, message="Code verified.")


# ── POST /reset-password ─────────────────────────

@router.post("/reset-password", response_model=PasswordResetResponse)
def reset_password(body: PasswordResetNewPassword, db: Session = Depends(get_db)):
    email = body.email.lower()

    # Cheap pre-check first, no side effects.
    is_valid, error_msg = validate_password_strength(body.new_password)
    if not is_valid:
        return PasswordResetResponse(success=False, message=error_msg)

    token = _find_active_token(db, email)
    if not token:
        return PasswordResetResponse(success=False, message="Invalid or expired code.")
    if token.attempts >= MAX_CODE_ATTEMPTS:
        return PasswordResetResponse(
            success=False,
            message="Too many failed attempts. Request a new code.",
        )
    if token.code != body.code:
        token.attempts += 1
        db.commit()
        return PasswordResetResponse(success=False, message="Invalid code.")

    user = (
        db.query(AppUser)
        .filter(AppUser.id == token.user_id, AppUser.is_active == True)  # noqa: E712
        .first()
    )
    if not user:
        return PasswordResetResponse(success=False, message="User no longer active.")

    user.password_hash = hash_password(body.new_password)
    user.must_change_password = False
    user.password_changed_at = _now()
    # Clear lockout if any.
    user.failed_login_count = 0
    user.locked_until = None

    token.used = True
    db.commit()

    logger.info("Password reset completed for %s", email)
    return PasswordResetResponse(success=True, message="Password reset successfully.")
