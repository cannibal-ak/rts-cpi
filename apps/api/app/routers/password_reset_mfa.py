"""MFA-based password reset — UNAUTHENTICATED, additive (Phase 3).

Lets a user who forgot their password reset it by proving possession via
their authenticator (TOTP) or a one-time recovery code — no email / SMTP.
This router is mounted WITHOUT the _protected gate and is INDEPENDENT of the
MFA_ENFORCED flag: it works for any enrolled user.

The existing email/SMTP reset router (app/routers/password_reset.py) is NOT
touched and stays available; this lives under a non-colliding prefix.

Enumeration-safety: /init ALWAYS returns 200 with an identical shape and
message regardless of whether the account exists or has MFA. Ineligible
callers still receive a (useless) reset_token. /verify returns a single
generic error for every "can't proceed" case.

SECURITY: secrets, codes, and passwords are never logged.
"""

import logging
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from app.core import crypto
from app.core.database import get_db, get_db_rls, set_tenant_context
from app.models.password_reset_token import PasswordResetToken
from app.models.user import AppUser
from app.models.user_mfa import UserMfa
from app.services import audit, mfa_service
from app.services.auth_service import (
    TokenError,
    TokenExpiredError,
    create_password_reset_token,
    decode_password_reset_token,
    hash_password,
    validate_password_strength,
)

# uvicorn.error so internal lines surface in `docker logs cpi-api-1`.
logger = logging.getLogger("uvicorn.error")

router = APIRouter(prefix="/api/v1/auth/password-reset/mfa", tags=["password-reset-mfa"])

RATE_LIMIT_PER_HOUR = 3
RESET_TOKEN_TTL_SECONDS = 600  # 10 min — matches PWD_RESET_EXPIRE_MINUTES
PLACEHOLDER_TENANT = "00000000-0000-0000-0000-000000000000"

GENERIC_INIT_MESSAGE = (
    "If the account exists and has an authenticator set up, enter a code to continue."
)
GENERIC_INVALID = "Invalid or expired reset."


# ── Schemas ──────────────────────────────────────

class InitRequest(BaseModel):
    email: EmailStr


class InitResponse(BaseModel):
    reset_token: str
    expires_in: int
    message: str


class VerifyRequest(BaseModel):
    reset_token: str
    code: str
    new_password: str
    is_recovery: bool = False


class GenericResponse(BaseModel):
    success: bool
    message: str


# ── POST /init ───────────────────────────────────

@router.post("/init", response_model=InitResponse)
def init(body: InitRequest, request: Request, db: Session = Depends(get_db)):
    email = body.email.lower()
    eligible = False
    sub = str(uuid.uuid4())                 # non-resolvable for ineligible callers
    tenant_for_token = PLACEHOLDER_TENANT

    # Per-email rate limit — same pattern as forgot-password (count recent rows).
    one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
    recent = (
        db.query(PasswordResetToken)
        .filter(
            PasswordResetToken.email == email,
            PasswordResetToken.purpose == "mfa_reset",
            PasswordResetToken.created_at >= one_hour_ago,
        )
        .count()
    )
    rate_limited = recent >= RATE_LIMIT_PER_HOUR

    user = (
        db.query(AppUser)
        .filter(AppUser.email == email, AppUser.is_active == True)  # noqa: E712
        .first()
    )

    if user is not None and not rate_limited:
        mfa = db.query(UserMfa).filter(UserMfa.user_id == user.id).first()
        if mfa is not None and mfa.enabled:
            eligible = True
            sub = str(user.id)
            tenant_for_token = str(user.tenant_id)
        # Rate-limit marker row (FK requires a real user). Carries no code.
        db.add(
            PasswordResetToken(
                user_id=user.id,
                email=email,
                purpose="mfa_reset",
                expires_at=datetime.now(timezone.utc) + timedelta(seconds=RESET_TOKEN_TTL_SECONDS),
                ip_address=request.client.host if request.client else None,
            )
        )
        audit.record(
            db,
            tenant_id=user.tenant_id,
            actor=email,
            action="password_reset.mfa_init",
            target_type="app_user",
            target_id=str(user.id),
            outcome="success" if eligible else "failure",
        )
        db.commit()
    else:
        # Unknown email or rate-limited — no DB row (no tenant to attribute),
        # internal log only. Response below stays generic + identical.
        logger.info(
            "mfa password-reset init: eligible=%s rate_limited=%s", eligible, rate_limited
        )

    token = create_password_reset_token(sub, tenant_for_token, eligible)
    return InitResponse(
        reset_token=token,
        expires_in=RESET_TOKEN_TTL_SECONDS,
        message=GENERIC_INIT_MESSAGE,
    )


# ── POST /verify ─────────────────────────────────

@router.post("/verify", response_model=GenericResponse)
def verify(body: VerifyRequest, db: Session = Depends(get_db_rls)):
    try:
        payload = decode_password_reset_token(body.reset_token)
    except TokenExpiredError:
        raise HTTPException(status_code=401, detail=GENERIC_INVALID)
    except TokenError:
        raise HTTPException(status_code=401, detail=GENERIC_INVALID)

    if not payload.get("eligible"):
        raise HTTPException(status_code=401, detail=GENERIC_INVALID)

    user_id = payload["sub"]
    tenant_id = payload["tenant_id"]
    # Tenant context FROM THE TOKEN so RLS exposes the user_mfa row and permits
    # the app_user password UPDATE (no access token here).
    set_tenant_context(db, str(tenant_id))

    user = db.query(AppUser).filter(
        AppUser.id == user_id, AppUser.is_active == True  # noqa: E712
    ).first()
    mfa = db.query(UserMfa).filter(UserMfa.user_id == user_id).first() if user else None
    if user is None or mfa is None or not mfa.enabled:
        raise HTTPException(status_code=401, detail=GENERIC_INVALID)

    if mfa_service.is_locked(mfa):
        raise HTTPException(status_code=423, detail="Too many attempts. Try again later.")

    # Validate the new password BEFORE consuming any code (cheap, no side
    # effects) — same policy as /change-password, mirrors reset_password.
    is_valid, error_msg = validate_password_strength(body.new_password)
    if not is_valid:
        raise HTTPException(status_code=400, detail=error_msg)

    if body.is_recovery:
        ok = mfa_service.verify_and_consume_recovery_code(db, user_id, body.code)
        step = None
    else:
        secret = crypto.decrypt_str(bytes(mfa.secret_ciphertext))
        ok, step = mfa_service.verify_totp(secret, body.code, mfa.last_used_step)

    if not ok:
        mfa_service.register_failure(mfa)
        audit.record(
            db,
            tenant_id=uuid.UUID(tenant_id),
            actor=user.email,
            action="password_reset.mfa_failed",
            target_type="app_user",
            target_id=str(user_id),
            outcome="failure",
        )
        db.commit()
        raise HTTPException(status_code=401, detail=GENERIC_INVALID)

    # Success — reset the password (reuse the app's bcrypt hashing).
    user.password_hash = hash_password(body.new_password)
    user.must_change_password = False
    user.password_changed_at = datetime.now(timezone.utc)
    user.failed_login_count = 0
    user.locked_until = None
    mfa_service.register_success(mfa, step)

    audit.record(
        db,
        tenant_id=uuid.UUID(tenant_id),
        actor=user.email,
        action="password_reset.mfa_succeeded",
        target_type="app_user",
        target_id=str(user_id),
    )
    db.commit()
    # NOTE: there is no server-side session/refresh revocation in this app
    # (refresh tokens are stateless JWTs; logout is client-side). Existing
    # tokens therefore remain valid until expiry — a known limitation, not
    # addressed here. We do NOT auto-login.
    return GenericResponse(success=True, message="Password has been reset. Please sign in.")
