"""Shared FastAPI dependencies — JWT auth, tenant context, RBAC, filter hardening."""

import re
from fastapi import Depends, Header, HTTPException, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db, get_db_rls, set_tenant_context
from app.models.user import AppUser, RoleBinding
from app.services.auth_service import decode_token, TokenError, TokenExpiredError

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)

# Paths that bypass the forced-password-change gate
PASSWORD_CHANGE_EXEMPT_PATHS = {
    "/api/v1/auth/change-password",
    "/api/v1/auth/me",
    "/api/v1/auth/logout",
    "/api/v1/auth/refresh",
}


# ── JWT-based current user ───────────────────────

def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> dict:
    """Decode JWT, verify user exists and is active.
    Returns the decoded token payload augmented with must_change_password.
    """
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        payload = decode_token(token)
    except TokenExpiredError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except TokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

    if payload.get("token_type") != "access":
        raise HTTPException(status_code=401, detail="Not an access token")

    user = db.query(AppUser).filter(AppUser.id == payload["sub"]).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")

    payload["must_change_password"] = user.must_change_password
    return payload


# ── Forced password change middleware ─────────────

def enforce_password_change(request: Request, current_user: dict = Depends(get_current_user)) -> dict:
    """Blocks all endpoints except auth paths when must_change_password is True."""
    if current_user.get("must_change_password") and request.url.path not in PASSWORD_CHANGE_EXEMPT_PATHS:
        raise HTTPException(
            status_code=403,
            detail={"message": "Password change required", "code": "PASSWORD_CHANGE_REQUIRED"},
        )
    return current_user


# ── Tenant context ─────────────────────────────

def get_tenant_id(
    current_user: dict = Depends(get_current_user),
    x_tenant_id: str = Header(default=None),
) -> str:
    """Extract tenant_id from JWT. Falls back to X-Tenant-ID header only
    when legacy header auth is enabled via feature flag."""
    tenant_id = current_user.get("tenant_id")
    if tenant_id:
        return tenant_id
    if settings.allow_legacy_header_auth and x_tenant_id:
        return x_tenant_id
    return settings.default_tenant_id


def get_tenant_db(
    db: Session = Depends(get_db_rls),
    tenant_id: str = Depends(get_tenant_id),
) -> Session:
    """Yields an RLS-enforced DB session with tenant context set."""
    set_tenant_context(db, tenant_id)
    return db


# ── RBAC enforcement ───────────────────────────

VALID_ROLES = {"TENANT_ADMIN"}


def get_user_roles(current_user: dict = Depends(get_current_user)) -> list[str]:
    """Extract user roles from JWT payload."""
    roles = current_user.get("roles", [])
    return [r for r in roles if r in VALID_ROLES] or ["TENANT_ADMIN"]


def get_user_identity(current_user: dict = Depends(get_current_user)) -> str:
    """Extract user identity from JWT. Maps tenant_slug to identity."""
    tenant_slug = current_user.get("tenant_slug", "")
    if tenant_slug:
        return tenant_slug.upper()
    return "SHARED"


# ── Platform admin detection ──────────────────

PLATFORM_TENANT_SLUG = "RTS"


def is_platform_admin(user_identity: str, user_roles: list[str]) -> bool:
    """True if user belongs to RTS platform tenant AND has TENANT_ADMIN role."""
    return user_identity == PLATFORM_TENANT_SLUG and "TENANT_ADMIN" in user_roles


class RequireRoles:
    """FastAPI dependency that enforces role-based access.

    Usage:
        @router.get("/admin", dependencies=[Depends(RequireRoles("TENANT_ADMIN"))])
    """
    def __init__(self, *allowed_roles: str):
        self.allowed = set(r.upper() for r in allowed_roles)

    def __call__(self, user_roles: list[str] = Depends(get_user_roles)):
        if not self.allowed.intersection(user_roles):
            raise HTTPException(
                status_code=403,
                detail=f"Forbidden: requires one of {sorted(self.allowed)}",
            )
        return user_roles


class RequirePlatformAdmin:
    """Restricts access to RTS platform administrators only.

    Checks that the user has TENANT_ADMIN role AND belongs to the
    RTS platform tenant (slug='rts').
    """

    def __call__(
        self,
        user_roles: list[str] = Depends(get_user_roles),
        user_identity: str = Depends(get_user_identity),
    ):
        if not is_platform_admin(user_identity, user_roles):
            raise HTTPException(
                status_code=403,
                detail="Forbidden: platform administrator access required",
            )
        return user_roles


# ── Filter hardening ───────────────────────────

# Max lengths and allowed patterns for filter values
FILTER_MAX_LEN = 64
FILTER_MAX_ITEMS = 20  # max items in a multi-value filter
FILTER_ALLOWED_PATTERN = re.compile(r'^[a-zA-Z0-9\s\-_./()&]+$')
DATE_PATTERN = re.compile(r'^\d{4}-\d{2}-\d{2}$')


def sanitize_filter(value: str | None, field_name: str = "filter") -> str | None:
    """Validate and sanitize a single filter value."""
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    if len(value) > FILTER_MAX_LEN:
        raise HTTPException(400, f"Filter '{field_name}' exceeds max length ({FILTER_MAX_LEN})")
    if not FILTER_ALLOWED_PATTERN.match(value):
        raise HTTPException(400, f"Filter '{field_name}' contains invalid characters")
    return value


def sanitize_date(value: str | None, field_name: str = "date") -> str | None:
    """Validate a date filter (YYYY-MM-DD)."""
    if value is None:
        return None
    value = value.strip()
    if not value or value == "No file dates available":
        return None
    if not DATE_PATTERN.match(value):
        raise HTTPException(400, f"Filter '{field_name}' must be YYYY-MM-DD format")
    return value
