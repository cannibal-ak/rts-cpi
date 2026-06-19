"""Admin Password Management — list users, reset queue, generate code, force reset.

All endpoints require RTS platform admin (RequirePlatformAdmin) at the
router level; main.py also stacks the password-change gate via _protected,
matching every other admin router.

Code generation is reused from app.routers.password_reset to keep a single
source of truth; same goes for password hashing and strength validation.
"""

import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

import secrets

from app.core.config import settings
from app.core.database import get_db
from app.core.deps import RequirePlatformAdmin, get_current_user
from app.core.security import hash_token
from app.models.user import AppUser, RoleBinding
from app.models.tenant import Tenant
from app.models.password_reset_token import PasswordResetToken
from app.routers.password_reset import (
    _create_reset_token,
    CODE_TTL_MINUTES,
    INVITE_TTL_HOURS,
)
from app.schemas.admin_password import (
    AdminUserListItem,
    AdminUserListResponse,
    AdminForceResetRequest,
    AdminForceResetResponse,
    AdminInviteUserRequest,
    AdminInviteUserResponse,
    AdminResendInviteRequest,
    AdminResendInviteResponse,
    AdminSendResetEmailRequest,
    AdminSendResetEmailResponse,
    AdminTenantOption,
)
from app.services import smtp_service, audit
from app.services.smtp_service import send_invite_email
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
                tenant_slug=tenant.slug,
                role=roles[0] if roles else "",
                is_active=bool(user.is_active),
                is_locked=_is_locked(user),
                force_password_change=bool(user.must_change_password),
                last_login=user.last_login_at,
                created_at=user.created_at,
            )
        )

    return AdminUserListResponse(users=items, total=len(items))


# ── GET /tenants (invite dropdown source) ─────────

@router.get("/tenants", response_model=list[AdminTenantOption])
def list_tenants(db: Session = Depends(get_db)):
    rows = (
        db.query(Tenant)
        .filter(Tenant.is_active == True)  # noqa: E712
        .order_by(Tenant.display_name)
        .all()
    )
    return [
        AdminTenantOption(tenant_id=t.id, slug=t.slug, name=t.display_name)
        for t in rows
    ]


# ── POST /send-reset-email ────────────────────────

@router.post("/send-reset-email", response_model=AdminSendResetEmailResponse)
def send_reset_email(body: AdminSendResetEmailRequest, db: Session = Depends(get_db)):
    """Admin-initiated password reset: issue a hashed reset code and email it.

    Reuses the same hashed issuance path as the public forgot-password flow.
    The code is NEVER returned in the response — only delivered by email.
    """
    email = body.email.lower()
    user = (
        db.query(AppUser)
        .filter(AppUser.email == email, AppUser.is_active == True)  # noqa: E712
        .first()
    )
    if not user:
        raise HTTPException(status_code=404, detail=f"No active user found with email '{email}'.")

    code = _create_reset_token(db, user_id=user.id, email=email, ip_address=None)

    sent = False
    if smtp_service.get_smtp_config(db) is None:
        logger.warning("Admin send-reset-email for %s: SMTP not configured.", email)
    else:
        sent = smtp_service.send_password_reset_email(
            db, to_email=email, code=code, expiry_minutes=CODE_TTL_MINUTES,
        )
        if not sent:
            logger.error("Admin send-reset-email for %s: SMTP delivery failed.", email)

    return AdminSendResetEmailResponse(
        sent=sent,
        message=(
            "Reset code emailed."
            if sent
            else "Could not email the reset code (SMTP not configured or delivery failed)."
        ),
    )


# ── POST /invite-user ─────────────────────────────

@router.post("/invite-user", response_model=AdminInviteUserResponse)
def invite_user(body: AdminInviteUserRequest, db: Session = Depends(get_db)):
    email = body.email.lower()

    role = body.role.upper().strip()
    if role not in {"TENANT_ADMIN"}:
        raise HTTPException(status_code=400, detail=f"Unsupported role '{body.role}'.")

    # Global uniqueness (migration 017) + per-tenant uniqueness.
    if db.query(AppUser).filter(AppUser.email == email).first():
        raise HTTPException(status_code=409, detail=f"A user with email '{email}' already exists.")

    tenant = db.query(Tenant).filter(Tenant.id == body.tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found.")

    # get_db is the superuser engine (bypasses RLS) — set tenant_id explicitly.
    user = AppUser(
        tenant_id=body.tenant_id,
        email=email,
        display_name=body.display_name,
        is_active=True,
        password_hash=None,
        must_change_password=True,
    )
    db.add(user)
    db.flush()  # assign user.id

    db.add(RoleBinding(tenant_id=body.tenant_id, user_id=user.id, role=role))

    raw_token = secrets.token_urlsafe(32)
    db.add(PasswordResetToken(
        user_id=user.id,
        email=email,
        token_hash=hash_token(raw_token),
        purpose="invite",
        expires_at=_now() + timedelta(hours=INVITE_TTL_HOURS),
        used=False,
        ip_address=None,
    ))
    db.commit()

    invite_url = f"{settings.APP_BASE_URL}/accept-invite?token={raw_token}"
    invite_sent = send_invite_email(
        db, to_email=email, invite_url=invite_url, expiry_hours=INVITE_TTL_HOURS,
    )
    if not invite_sent:
        logger.error("Invite email to %s failed to send; admin can resend.", email)

    logger.info("Invited user %s into tenant %s (invite_sent=%s)", email, tenant.slug, invite_sent)
    return AdminInviteUserResponse(user_id=user.id, email=email, invite_sent=invite_sent)


# ── POST /resend-invite ───────────────────────────

@router.post("/resend-invite", response_model=AdminResendInviteResponse)
def resend_invite(body: AdminResendInviteRequest, db: Session = Depends(get_db)):
    if not body.email and not body.user_id:
        raise HTTPException(status_code=400, detail="Provide email or user_id.")

    q = db.query(AppUser)
    if body.user_id:
        q = q.filter(AppUser.id == body.user_id)
    else:
        q = q.filter(AppUser.email == body.email.lower())
    user = q.first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    if user.password_hash is not None:
        raise HTTPException(status_code=400, detail="User has already activated their account.")

    # Invalidate prior unused invite tokens.
    db.query(PasswordResetToken).filter(
        PasswordResetToken.user_id == user.id,
        PasswordResetToken.purpose == "invite",
        PasswordResetToken.used == False,  # noqa: E712
    ).update({PasswordResetToken.used: True})

    raw_token = secrets.token_urlsafe(32)
    db.add(PasswordResetToken(
        user_id=user.id,
        email=user.email,
        token_hash=hash_token(raw_token),
        purpose="invite",
        expires_at=_now() + timedelta(hours=INVITE_TTL_HOURS),
        used=False,
        ip_address=None,
    ))
    db.commit()

    invite_url = f"{settings.APP_BASE_URL}/accept-invite?token={raw_token}"
    invite_sent = send_invite_email(
        db, to_email=user.email, invite_url=invite_url, expiry_hours=INVITE_TTL_HOURS,
    )
    return AdminResendInviteResponse(
        success=True,
        invite_sent=invite_sent,
        message="Invite re-sent." if invite_sent else "Invite generated but email failed to send.",
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
    # Phase 1a: force a password change on next login regardless of the
    # legacy toggle (A6 enforcement — admin-set passwords are temporary).
    user.must_change_password = True
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


# ── User deactivate / reactivate ──────────────────
#
# Reversible account disable. A deactivated user is blocked at /login (403
# "account disabled", enforced in app.routers.auth) and at token refresh, and
# fails get_current_user on any existing access token. No hard delete — the
# row and all its FK anchors are preserved and the action is fully reversible.

# The RTS platform super-admin must never be lockable out of the platform.
PROTECTED_SUPERADMIN_EMAIL = "admin@rts.com"


def _load_target_for_status_change(db: Session, user_id: UUID, current_user: dict) -> AppUser:
    """Fetch the target user and run the shared deactivate/reactivate guards.

    Returns 4xx (never 500) on: missing user, self-action, or the protected
    super-admin account.
    """
    user = db.query(AppUser).filter(AppUser.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    if str(user.id) == current_user["sub"]:
        raise HTTPException(status_code=400, detail="You cannot change your own account status.")
    if user.email.lower() == PROTECTED_SUPERADMIN_EMAIL:
        raise HTTPException(status_code=400, detail="The RTS super-admin account is protected.")
    return user


@router.post("/users/{user_id}/deactivate", status_code=204)
def deactivate_user(
    user_id: UUID,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Disable a user account (reversible). Blocks login + refresh immediately."""
    user = _load_target_for_status_change(db, user_id, current_user)

    user.is_active = False
    audit.record(
        db,
        tenant_id=UUID(current_user["tenant_id"]),
        actor=current_user["sub"],
        action="user.deactivated",
        target_type="app_user",
        target_id=str(user.id),
    )
    db.commit()
    logger.info("Admin %s deactivated user %s", current_user["sub"], user.email)
    return Response(status_code=204)


@router.post("/users/{user_id}/reactivate", status_code=204)
def reactivate_user(
    user_id: UUID,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Re-enable a previously deactivated user account."""
    user = _load_target_for_status_change(db, user_id, current_user)

    user.is_active = True
    audit.record(
        db,
        tenant_id=UUID(current_user["tenant_id"]),
        actor=current_user["sub"],
        action="user.reactivated",
        target_type="app_user",
        target_id=str(user.id),
    )
    db.commit()
    logger.info("Admin %s reactivated user %s", current_user["sub"], user.email)
    return Response(status_code=204)
