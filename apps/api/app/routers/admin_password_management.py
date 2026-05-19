"""Admin Password Management — list users, reset queue, generate code, force reset.

All endpoints require RTS platform admin (RequirePlatformAdmin) at the
router level; main.py also stacks the password-change gate via _protected,
matching every other admin router.

Code generation is reused from app.routers.password_reset to keep a single
source of truth; same goes for password hashing and strength validation.
"""

import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import RequirePlatformAdmin
from app.models.user import AppUser, RoleBinding
from app.models.tenant import Tenant
from app.models.password_reset_token import PasswordResetToken
from app.routers.password_reset import _generate_code, CODE_TTL_MINUTES
from app.schemas.admin_password import (
    AdminUserListItem,
    AdminUserListResponse,
    AdminResetTokenItem,
    AdminResetTokenListResponse,
    AdminGenerateResetCodeRequest,
    AdminGenerateResetCodeResponse,
    AdminForceResetRequest,
    AdminForceResetResponse,
)
from app.services.auth_service import hash_password, validate_password_strength

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/admin/password-management",
    tags=["Admin - Password Management"],
    dependencies=[Depends(RequirePlatformAdmin())],
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _token_status(token: PasswordResetToken) -> str:
    if token.used:
        return "used"
    if token.expires_at < _now():
        return "expired"
    return "pending"


def _is_locked(user: AppUser) -> bool:
    return user.locked_until is not None and user.locked_until > _now()


# ── GET /users ────────────────────────────────────

@router.get("/users", response_model=AdminUserListResponse)
def list_users(db: Session = Depends(get_db)):
    rows = (
        db.query(AppUser, Tenant)
        .join(Tenant, Tenant.id == AppUser.tenant_id)
        .order_by(Tenant.display_name, AppUser.email)
        .all()
    )

    # Single round-trip for roles, then group in Python — avoids N+1.
    user_ids = [u.id for (u, _t) in rows]
    role_rows = (
        db.query(RoleBinding.user_id, RoleBinding.role)
        .filter(RoleBinding.user_id.in_(user_ids))
        .all()
        if user_ids else []
    )
    roles_by_user: dict = {}
    for uid, role in role_rows:
        roles_by_user.setdefault(uid, []).append(role)

    items: list[AdminUserListItem] = []
    for user, tenant in rows:
        roles = roles_by_user.get(user.id, [])
        items.append(
            AdminUserListItem(
                id=user.id,
                email=user.email,
                tenant_name=tenant.display_name,
                role=roles[0] if roles else "",
                is_active=bool(user.is_active),
                is_locked=_is_locked(user),
                force_password_change=bool(user.must_change_password),
                last_login=user.last_login_at,
                created_at=user.created_at,
            )
        )

    return AdminUserListResponse(users=items, total=len(items))


# ── GET /reset-codes ──────────────────────────────

@router.get("/reset-codes", response_model=AdminResetTokenListResponse)
def list_reset_codes(
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
):
    tokens = (
        db.query(PasswordResetToken)
        .order_by(PasswordResetToken.created_at.desc())
        .limit(limit)
        .all()
    )
    items = [
        AdminResetTokenItem(
            id=t.id,
            email=t.email,
            code=t.code,
            status=_token_status(t),
            created_at=t.created_at,
            expires_at=t.expires_at,
            attempts=t.attempts,
        )
        for t in tokens
    ]
    return AdminResetTokenListResponse(tokens=items, total=len(items))


# ── POST /generate-code ───────────────────────────

@router.post("/generate-code", response_model=AdminGenerateResetCodeResponse)
def generate_code(body: AdminGenerateResetCodeRequest, db: Session = Depends(get_db)):
    email = body.email.lower()
    user = (
        db.query(AppUser)
        .filter(AppUser.email == email, AppUser.is_active == True)  # noqa: E712
        .first()
    )
    if not user:
        raise HTTPException(status_code=404, detail=f"No active user found with email '{email}'.")

    # Invalidate any previously unused tokens for this email (same as forgot-password).
    db.query(PasswordResetToken).filter(
        PasswordResetToken.email == email,
        PasswordResetToken.used == False,  # noqa: E712
    ).update({PasswordResetToken.used: True})

    code = _generate_code()
    expires_at = _now() + timedelta(minutes=CODE_TTL_MINUTES)
    token = PasswordResetToken(
        user_id=user.id,
        email=email,
        code=code,
        expires_at=expires_at,
        ip_address=None,  # admin-initiated; no requester IP captured
    )
    db.add(token)
    db.commit()

    logger.info("Admin generated reset code for %s (expires in %d min)", email, CODE_TTL_MINUTES)

    return AdminGenerateResetCodeResponse(
        success=True,
        message=f"Reset code generated. Valid for {CODE_TTL_MINUTES} minutes.",
        code=code,
        expires_at=expires_at,
    )


# ── POST /force-reset ─────────────────────────────

@router.post("/force-reset", response_model=AdminForceResetResponse)
def force_reset(body: AdminForceResetRequest, db: Session = Depends(get_db)):
    email = body.email.lower()
    user = db.query(AppUser).filter(AppUser.email == email).first()
    if not user:
        raise HTTPException(status_code=404, detail=f"No user found with email '{email}'.")

    is_valid, error_msg = validate_password_strength(body.new_password)
    if not is_valid:
        raise HTTPException(status_code=400, detail=error_msg)

    user.password_hash = hash_password(body.new_password)
    user.must_change_password = bool(body.force_change_on_login)
    user.password_changed_at = _now()
    # Clear lockout state (admins use this to recover locked accounts too).
    user.locked_until = None
    user.failed_login_count = 0

    # Invalidate any pending reset tokens — they're no longer needed.
    db.query(PasswordResetToken).filter(
        PasswordResetToken.email == email,
        PasswordResetToken.used == False,  # noqa: E712
    ).update({PasswordResetToken.used: True})

    db.commit()

    logger.info(
        "Admin force-reset password for %s (force_change=%s)",
        email,
        body.force_change_on_login,
    )

    return AdminForceResetResponse(
        success=True,
        message=(
            "Password reset successfully. User will be required to change it on next login."
            if body.force_change_on_login
            else "Password reset successfully."
        ),
    )
