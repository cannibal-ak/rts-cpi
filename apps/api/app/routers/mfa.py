"""MFA (TOTP) endpoints — enroll / confirm / status / verify / disable.

Mounted at ``/api/v1/auth/mfa``. This router is ADDITIVE: it does not touch
``/login`` or the auth gate. It is deliberately NOT wrapped in the
``enforce_password_change`` (_protected) gate in main.py so that:
  - ``/verify`` is reachable pre-login with only an mfa_challenge token, and
  - enroll/confirm/status/disable stay reachable for not-yet-enrolled users.

Auth per route:
  - enroll/confirm/status/disable → access token (``get_current_user``),
    which already requires token_type == "access".
  - verify → mfa_challenge token in the body (NOT an access token); the
    tenant context for RLS is taken FROM that token.

SECURITY: the TOTP secret and recovery codes are never logged. The secret is
stored encrypted (app.core.crypto / CPI_KEK); recovery codes are stored as
SHA-256 hashes only.
"""

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core import crypto
from app.core.database import get_db_rls, set_tenant_context
from app.core.deps import get_current_user, get_tenant_db
from app.core.security import hash_token
from app.models.mfa_recovery_code import MfaRecoveryCode
from app.models.tenant import Tenant
from app.models.user import AppUser, RoleBinding
from app.models.user_mfa import UserMfa
from app.services import audit, mfa_service
from app.services.auth_service import (
    TokenError,
    TokenExpiredError,
    create_access_token,
    create_refresh_token,
    decode_mfa_challenge_token,
    verify_password,
)
# Reuse the EXACT subject/response builders used by /login so /verify mints
# an identical access+refresh pair (same claims: roles, tenant_slug, jti …).
from app.routers.auth import TokenResponse, _build_token_subject, _user_dict

router = APIRouter(prefix="/api/v1/auth/mfa", tags=["mfa"])


# ── Request schemas ──────────────────────────────

class ConfirmRequest(BaseModel):
    code: str


class VerifyRequest(BaseModel):
    mfa_token: str
    code: str
    is_recovery: bool = False


class DisableRequest(BaseModel):
    password: str
    code: str


# ── Helpers ──────────────────────────────────────

def _get_mfa(db: Session, user_id: UUID) -> UserMfa | None:
    return db.query(UserMfa).filter(UserMfa.user_id == user_id).first()


# ── POST /enroll/start (access) ──────────────────

@router.post("/enroll/start")
def enroll_start(
    db: Session = Depends(get_tenant_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = UUID(current_user["sub"])
    tenant_id = UUID(current_user["tenant_id"])

    mfa = _get_mfa(db, user_id)
    if mfa is not None and mfa.enabled:
        raise HTTPException(status_code=409, detail="MFA is already enabled")

    secret = mfa_service.generate_secret()
    if mfa is None:
        mfa = UserMfa(tenant_id=tenant_id, user_id=user_id)
        db.add(mfa)
    # (Re)start a pending enrollment — overwrite any prior unconfirmed secret.
    mfa.secret_ciphertext = crypto.encrypt_str(secret)
    mfa.enabled = False
    mfa.confirmed_at = None
    mfa.last_used_step = None
    mfa.failed_attempts = 0
    mfa.locked_until = None
    db.flush()

    uri = mfa_service.provisioning_uri(secret, current_user.get("email", ""))
    audit.record(
        db,
        tenant_id=tenant_id,
        actor=current_user["sub"],
        action="mfa.enroll_started",
        target_type="user_mfa",
        target_id=str(user_id),
    )
    db.commit()
    # `secret` is returned for manual (non-QR) entry; never logged.
    return {"provisioning_uri": uri, "secret": secret}


# ── POST /enroll/confirm (access) ────────────────

@router.post("/enroll/confirm")
def enroll_confirm(
    body: ConfirmRequest,
    db: Session = Depends(get_tenant_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = UUID(current_user["sub"])
    tenant_id = UUID(current_user["tenant_id"])

    mfa = _get_mfa(db, user_id)
    if mfa is None or mfa.secret_ciphertext is None:
        raise HTTPException(status_code=400, detail="No enrollment in progress")
    if mfa.enabled:
        raise HTTPException(status_code=409, detail="MFA is already enabled")
    if mfa_service.is_locked(mfa):
        raise HTTPException(status_code=423, detail="Too many attempts. Try again later.")

    secret = crypto.decrypt_str(bytes(mfa.secret_ciphertext))
    ok, step = mfa_service.verify_totp(secret, body.code, mfa.last_used_step)
    if not ok:
        mfa_service.register_failure(mfa)
        audit.record(
            db,
            tenant_id=tenant_id,
            actor=current_user["sub"],
            action="mfa.failed",
            target_type="user_mfa",
            target_id=str(user_id),
            outcome="failure",
        )
        db.commit()
        raise HTTPException(status_code=400, detail="Invalid code")

    mfa.enabled = True
    mfa.confirmed_at = datetime.now(timezone.utc)
    # Do NOT advance last_used_step on enrollment — leave it NULL so the
    # first login /verify in the SAME TOTP window is accepted. Only the
    # login verify() path consumes a step. This still clears the failure /
    # lockout counters (register_success with no step).
    mfa_service.register_success(mfa)

    codes = mfa_service.generate_recovery_codes()
    for c in codes:
        db.add(
            MfaRecoveryCode(
                tenant_id=tenant_id,
                user_id=user_id,
                code_hash=hash_token(c),
            )
        )
    audit.record(
        db,
        tenant_id=tenant_id,
        actor=current_user["sub"],
        action="mfa.enroll_confirmed",
        target_type="user_mfa",
        target_id=str(user_id),
    )
    db.commit()
    # Recovery codes are shown exactly once; only their hashes are stored.
    return {"recovery_codes": codes}


# ── GET /status (access) ─────────────────────────

@router.get("/status")
def status(
    db: Session = Depends(get_tenant_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = UUID(current_user["sub"])
    mfa = _get_mfa(db, user_id)
    user = db.query(AppUser).filter(AppUser.id == user_id).first()
    remaining = (
        mfa_service.recovery_codes_remaining(db, user_id)
        if (mfa is not None and mfa.enabled)
        else 0
    )
    return {
        "enrolled": mfa is not None and mfa.secret_ciphertext is not None,
        "enabled": bool(mfa is not None and mfa.enabled),
        "exempt": bool(user is not None and user.mfa_exempt),
        "recovery_codes_remaining": remaining,
    }


# ── POST /verify (mfa_challenge token, NOT access) ─

@router.post("/verify", response_model=TokenResponse)
def verify(body: VerifyRequest, db: Session = Depends(get_db_rls)):
    try:
        payload = decode_mfa_challenge_token(body.mfa_token)
    except TokenExpiredError:
        raise HTTPException(status_code=401, detail="MFA challenge expired")
    except TokenError:
        raise HTTPException(status_code=401, detail="Invalid MFA challenge")

    user_id = UUID(payload["sub"])
    tenant_id = UUID(payload["tenant_id"])
    # Tenant context comes FROM THE TOKEN so RLS does not hide the user_mfa
    # row (there is no access token / get_tenant_db here).
    set_tenant_context(db, str(tenant_id))

    mfa = _get_mfa(db, user_id)
    user = db.query(AppUser).filter(
        AppUser.id == user_id, AppUser.is_active == True  # noqa: E712
    ).first()
    if mfa is None or not mfa.enabled or user is None:
        raise HTTPException(status_code=401, detail="MFA is not set up for this user")

    if mfa_service.is_locked(mfa):
        raise HTTPException(status_code=423, detail="Account locked. Try again later.")

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
            tenant_id=tenant_id,
            actor=str(user_id),
            action="mfa.failed",
            target_type="user_mfa",
            target_id=str(user_id),
            outcome="failure",
        )
        db.commit()
        raise HTTPException(status_code=401, detail="Invalid code")

    # Success — reset throttle, advance replay guard, stamp login.
    mfa_service.register_success(mfa, step)
    user.last_login_at = datetime.now(timezone.utc)

    role_bindings = db.query(RoleBinding).filter(
        RoleBinding.user_id == user.id,
        RoleBinding.tenant_id == tenant_id,
    ).all()
    roles = [rb.role for rb in role_bindings]
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    tenant_slug = tenant.slug if tenant else ""

    subject = _build_token_subject(user, tenant_slug, roles)
    access_token = create_access_token(subject)
    refresh_token = create_refresh_token(subject)

    audit.record(
        db,
        tenant_id=tenant_id,
        actor=str(user_id),
        action="mfa.verified",
        target_type="user_mfa",
        target_id=str(user_id),
    )
    # Build the response BEFORE commit — expire_on_commit + RLS would
    # otherwise lazy-reload the user with no tenant context (mirrors the
    # admin_sftp_connections pattern).
    response = TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        must_change_password=user.must_change_password,
        user=_user_dict(user, tenant_slug, roles),
    )
    db.commit()
    return response


# ── POST /disable (access) ───────────────────────

@router.post("/disable")
def disable(
    body: DisableRequest,
    db: Session = Depends(get_tenant_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = UUID(current_user["sub"])
    tenant_id = UUID(current_user["tenant_id"])

    mfa = _get_mfa(db, user_id)
    if mfa is None or not mfa.enabled:
        raise HTTPException(status_code=400, detail="MFA is not enabled")

    user = db.query(AppUser).filter(AppUser.id == user_id).first()
    if user is None or not user.password_hash or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=400, detail="Invalid password")

    secret = crypto.decrypt_str(bytes(mfa.secret_ciphertext))
    ok, _ = mfa_service.verify_totp(secret, body.code, mfa.last_used_step)
    if not ok:
        raise HTTPException(status_code=400, detail="Invalid code")

    mfa.secret_ciphertext = None
    mfa.enabled = False
    mfa.confirmed_at = None
    mfa.last_used_step = None
    mfa.failed_attempts = 0
    mfa.locked_until = None
    db.query(MfaRecoveryCode).filter(MfaRecoveryCode.user_id == user_id).delete()

    audit.record(
        db,
        tenant_id=tenant_id,
        actor=current_user["sub"],
        action="mfa.disabled",
        target_type="user_mfa",
        target_id=str(user_id),
    )
    db.commit()
    return {"detail": "MFA disabled"}
