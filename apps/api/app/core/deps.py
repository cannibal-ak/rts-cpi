"""Shared FastAPI dependencies — tenant context, RBAC, filter hardening."""

import re
from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.database import get_db, get_db_rls, set_tenant_context


# ── Tenant context ─────────────────────────────

def get_tenant_id(x_tenant_id: str = Header(default=None)) -> str:
    """Extract tenant ID from header, fallback to default for local dev."""
    return x_tenant_id or settings.default_tenant_id


def get_tenant_db(
    db: Session = Depends(get_db_rls),
    tenant_id: str = Depends(get_tenant_id),
) -> Session:
    """Yields an RLS-enforced DB session with tenant context set."""
    set_tenant_context(db, tenant_id)
    return db


# ── RBAC enforcement ───────────────────────────

VALID_ROLES = {"TENANT_ADMIN", "DATA_ENGINEER", "ANALYST", "REVENUE_MANAGER", "AUDITOR", "AIRLINE_USER", "CRUISE_USER"}


def get_user_roles(x_user_roles: str = Header(default="ANALYST")) -> list[str]:
    """Extract user roles from X-User-Roles header (comma-separated).
    In production this would come from JWT/session; header is for dev/demo.
    """
    roles = [r.strip().upper() for r in x_user_roles.split(",") if r.strip()]
    return [r for r in roles if r in VALID_ROLES] or ["ANALYST"]


def get_user_identity(x_user_identity: str = Header(default="SHARED")) -> str:
    """Extract user identity from X-User-Identity header.
    Maps "Airline_JY" -> "JY", "Airline_PW" -> "PW", etc.
    """
    if "_" in x_user_identity:
        return x_user_identity.split("_")[1].upper()
    return x_user_identity.upper()


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
