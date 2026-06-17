"""Password reset endpoints — request code, verify code, reset password.

UNAUTHENTICATED endpoints. Locked-out users invoke these without a JWT.
Protection layers in lieu of auth:
  - Per-email rate limit on /forgot-password (3/hour).
  - Per-token attempt limit on /verify-reset-code and /reset-password (5).
  - 5-minute TTL on every code.
  - Email-enumeration resistance: identical generic response whether or
    not the user exists, and identical response when rate-limited.
  - When SMTP is configured, the code is delivered by email; the
    response NEVER carries the code (closes the prior debug-leak path).
  - When SMTP is NOT configured, the code is still persisted and the
    admin can pull it from the Recent Reset Codes table as a manual-
    share fallback. The response still never carries the code.
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
    InviteVerifyRequest,
    InviteVerifyResponse,
    InviteAcceptRequest,
)
from app.services import smtp_service
from app.services.auth_service import (
    hash_password,
    validate_password_strength,
)
from app.core.security import hash_token

# uvicorn.error so these lines are visible in `docker logs cpi-api-1`
# (per the project's logging convention — app.* loggers are silent in
# this container).
logger = logging.getLogger("uvicorn.error")

router = APIRouter(prefix="/api/v1/auth", tags=["password-reset"])

CODE_TTL_MINUTES = 5
MAX_CODE_ATTEMPTS = 5
RATE_LIMIT_PER_HOUR = 3
INVITE_TTL_HOURS = 48

GENERIC_REQUEST_MESSAGE = (
    "If an account exists with this email, a verification code has been generated."
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _generate_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def _client_ip(req: Request) -> str | None:
    return req.client.host if req.client else None


def _find_active_token(
    db: Session, email: str, purpose: str = "reset"
) -> PasswordResetToken | None:
    return (
        db.query(PasswordResetToken)
        .filter(
            PasswordResetToken.email == email,
            PasswordResetToken.purpose == purpose,
            PasswordResetToken.used == False,  # noqa: E712 — SQLAlchemy idiom
            PasswordResetToken.expires_at > _now(),
        )
        .order_by(PasswordResetToken.created_at.desc())
        .first()
    )


def _find_invite_token(db: Session, raw_token: str) -> PasswordResetToken | None:
    """Look up an active invite token by its sha256 hash (no email needed)."""
    return (
        db.query(PasswordResetToken)
        .filter(
            PasswordResetToken.token_hash == hash_token(raw_token),
            PasswordResetToken.purpose == "invite",
            PasswordResetToken.used == False,  # noqa: E712
            PasswordResetToken.expires_at > _now(),
        )
        .order_by(PasswordResetToken.created_at.desc())
        .first()
    )


def _create_reset_token(
    db: Session, *, user_id, email: str, ip_address: str | None = None
) -> str:
    """Issue a fresh hashed reset code: invalidate prior unused reset tokens,
    persist token_hash (code column left NULL), return the plaintext code so
    the caller can email it. Shared by forgot-password and admin send-reset-email.
    """
    db.query(PasswordResetToken).filter(
        PasswordResetToken.email == email,
        PasswordResetToken.purpose == "reset",
        PasswordResetToken.used == False,  # noqa: E712
    ).update({PasswordResetToken.used: True})

    code = _generate_code()
    token = PasswordResetToken(
        user_id=user_id,
        email=email,
        token_hash=hash_token(code),
        purpose="reset",
        expires_at=_now() + timedelta(minutes=CODE_TTL_MINUTES),
        ip_address=ip_address,
    )
    db.add(token)
    db.commit()
    return code


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

    code = _create_reset_token(
        db, user_id=user.id, email=email, ip_address=_client_ip(request)
    )

    logger.info(
        "Password reset code issued for %s (expires in %d min)", email, CODE_TTL_MINUTES
    )

    # Email delivery. We deliberately swallow SMTP errors here so the
    # response stays identical to the "no such user" / rate-limited
    # paths — leaking whether SMTP is broken would also leak that the
    # email exists. The admin can recover the code from the Recent
    # Reset Codes table.
    if smtp_service.get_smtp_config(db) is None:
        logger.warning(
            "Password reset for %s: smtp_config not configured — code is "
            "only available via the admin Recent Reset Codes table.",
            email,
        )
    else:
        sent = smtp_service.send_password_reset_email(
            db, to_email=email, code=code, expiry_minutes=CODE_TTL_MINUTES,
        )
        if not sent:
            logger.error(
                "Password reset for %s: SMTP delivery failed — code remains "
                "available via the admin Recent Reset Codes table.",
                email,
            )

    return PasswordResetResponse(
        success=True,
        message=GENERIC_REQUEST_MESSAGE,
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

    if token.token_hash != hash_token(body.code):
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
    if token.token_hash != hash_token(body.code):
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


# ── POST /verify-invite ──────────────────────────

@router.post("/verify-invite", response_model=InviteVerifyResponse)
def verify_invite(body: InviteVerifyRequest, db: Session = Depends(get_db)):
    token = _find_invite_token(db, body.token)
    if not token:
        return InviteVerifyResponse(valid=False)
    return InviteVerifyResponse(valid=True, email=token.email)


# ── POST /accept-invite ──────────────────────────

@router.post("/accept-invite", response_model=PasswordResetResponse)
def accept_invite(body: InviteAcceptRequest, db: Session = Depends(get_db)):
    is_valid, error_msg = validate_password_strength(body.new_password)
    if not is_valid:
        return PasswordResetResponse(success=False, message=error_msg)

    token = _find_invite_token(db, body.token)
    if not token:
        return PasswordResetResponse(success=False, message="Invalid or expired invite.")

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
    user.failed_login_count = 0
    user.locked_until = None

    token.used = True
    db.commit()

    logger.info("Invite accepted for %s", token.email)
    return PasswordResetResponse(success=True, message="Account activated. You can now sign in.")
