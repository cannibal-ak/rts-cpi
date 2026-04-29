"""Authentication endpoints — login, refresh, logout, change-password, me."""

import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.models.user import AppUser, RoleBinding
from app.models.tenant import Tenant
from app.services.auth_service import (
    verify_password,
    hash_password,
    validate_password_strength,
    create_access_token,
    create_refresh_token,
    decode_token,
    TokenError,
    TokenExpiredError,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)

LOCKOUT_MINUTES = 15
MAX_FAILED_ATTEMPTS = 5


# ── Request / Response schemas ────────────────────

class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    must_change_password: bool
    user: dict


class RefreshRequest(BaseModel):
    refresh_token: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


# ── Helpers ───────────────────────────────────────

def _build_token_subject(user: AppUser, tenant_slug: str, roles: list[str]) -> dict:
    return {
        "sub": str(user.id),
        "tenant_id": str(user.tenant_id),
        "email": user.email,
        "roles": roles,
        "tenant_slug": tenant_slug,
    }


def _user_dict(user: AppUser, tenant_slug: str, roles: list[str]) -> dict:
    return {
        "id": str(user.id),
        "email": user.email,
        "display_name": user.display_name,
        "tenant_id": str(user.tenant_id),
        "tenant_slug": tenant_slug,
        "roles": roles,
        "is_active": user.is_active,
        "must_change_password": user.must_change_password,
    }


# ── POST /login ──────────────────────────────────

@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)):
    # Find user by email
    user = db.query(AppUser).filter(
        AppUser.email == body.email.lower(),
        AppUser.is_active == True,
    ).first()

    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    # Resolve tenant
    tenant = db.query(Tenant).filter(Tenant.id == user.tenant_id, Tenant.is_active == True).first()
    if not tenant:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    # Check lockout
    if user.locked_until and user.locked_until > datetime.now(timezone.utc):
        remaining = int((user.locked_until - datetime.now(timezone.utc)).total_seconds() / 60) + 1
        raise HTTPException(
            status_code=423,
            detail=f"Account locked. Try again in {remaining} minute(s).",
        )

    # Verify password
    if not user.password_hash or not verify_password(body.password, user.password_hash):
        user.failed_login_count = (user.failed_login_count or 0) + 1
        if user.failed_login_count >= MAX_FAILED_ATTEMPTS:
            user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=LOCKOUT_MINUTES)
            logger.warning("Account locked: %s (tenant: %s)", user.email, tenant.slug)
        db.commit()
        raise HTTPException(status_code=401, detail="Invalid email or password")

    # Success — reset counters
    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = datetime.now(timezone.utc)
    db.commit()

    # Get roles
    role_bindings = db.query(RoleBinding).filter(
        RoleBinding.user_id == user.id,
        RoleBinding.tenant_id == tenant.id,
    ).all()
    roles = [rb.role for rb in role_bindings]

    subject = _build_token_subject(user, tenant.slug, roles)
    access_token = create_access_token(subject)
    refresh_token = create_refresh_token(subject)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        must_change_password=user.must_change_password,
        user=_user_dict(user, tenant.slug, roles),
    )


# ── POST /refresh ────────────────────────────────

@router.post("/refresh")
def refresh(body: RefreshRequest, db: Session = Depends(get_db)):
    try:
        payload = decode_token(body.refresh_token)
    except TokenExpiredError:
        raise HTTPException(status_code=401, detail="Refresh token expired")
    except TokenError:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    if payload.get("token_type") != "refresh":
        raise HTTPException(status_code=401, detail="Not a refresh token")

    # Verify user still exists and is active
    user = db.query(AppUser).filter(AppUser.id == payload["sub"]).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User no longer active")

    # Rebuild subject with current roles
    role_bindings = db.query(RoleBinding).filter(
        RoleBinding.user_id == user.id,
        RoleBinding.tenant_id == user.tenant_id,
    ).all()
    roles = [rb.role for rb in role_bindings]
    tenant = db.query(Tenant).filter(Tenant.id == user.tenant_id).first()

    subject = _build_token_subject(user, tenant.slug if tenant else "", roles)
    new_access_token = create_access_token(subject)

    return {"access_token": new_access_token, "token_type": "bearer"}


# ── POST /logout ─────────────────────────────────

@router.post("/logout")
def logout(token: str = Depends(oauth2_scheme)):
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = decode_token(token)
        logger.info("User %s logged out (jti: %s)", payload.get("email"), payload.get("jti"))
    except TokenError:
        pass
    return {"detail": "Logged out"}


# ── POST /change-password ────────────────────────

@router.post("/change-password")
def change_password(body: ChangePasswordRequest, token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        payload = decode_token(token)
    except TokenError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    user = db.query(AppUser).filter(AppUser.id == payload["sub"]).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found")

    # Verify current password
    if not user.password_hash or not verify_password(body.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect")

    # Validate new password strength
    is_valid, error_msg = validate_password_strength(body.new_password)
    if not is_valid:
        raise HTTPException(status_code=400, detail=error_msg)

    # Prevent reuse of current password
    if verify_password(body.new_password, user.password_hash):
        raise HTTPException(status_code=400, detail="New password must differ from current password")

    user.password_hash = hash_password(body.new_password)
    user.must_change_password = False
    user.password_changed_at = datetime.now(timezone.utc)
    db.commit()

    return {"detail": "Password changed successfully"}


# ── GET /me ──────────────────────────────────────

@router.get("/me")
def me(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        payload = decode_token(token)
    except TokenError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    user = db.query(AppUser).filter(AppUser.id == payload["sub"]).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found")

    role_bindings = db.query(RoleBinding).filter(
        RoleBinding.user_id == user.id,
        RoleBinding.tenant_id == user.tenant_id,
    ).all()
    roles = [rb.role for rb in role_bindings]
    tenant = db.query(Tenant).filter(Tenant.id == user.tenant_id).first()

    return _user_dict(user, tenant.slug if tenant else "", roles)
