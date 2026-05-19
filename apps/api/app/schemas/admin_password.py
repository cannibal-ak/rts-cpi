"""Pydantic schemas for the admin Password Management feature.

Backs apps/api/app/routers/admin_password_management.py.
Field naming uses the public-facing contract (`is_locked`,
`force_password_change`) rather than the raw column names
(`locked_until`, `must_change_password`); the router translates
between the two.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr


# ── User listing ──────────────────────────────────

class AdminUserListItem(BaseModel):
    id: UUID
    email: str
    tenant_name: str
    tenant_slug: str               # canonical key into the frontend TENANT_CONFIG map
    role: str
    is_active: bool
    is_locked: bool                # computed: locked_until > now()
    force_password_change: bool    # renamed from must_change_password
    last_login: Optional[datetime] = None
    created_at: datetime


class AdminUserListResponse(BaseModel):
    users: list[AdminUserListItem]
    total: int


# ── Reset code queue ──────────────────────────────

class AdminResetTokenItem(BaseModel):
    id: UUID
    email: str
    code: str
    status: str                    # "pending" | "used" | "expired"
    created_at: datetime
    expires_at: datetime
    attempts: int


class AdminResetTokenListResponse(BaseModel):
    tokens: list[AdminResetTokenItem]
    total: int


# ── Generate code on behalf of a user ─────────────

class AdminGenerateResetCodeRequest(BaseModel):
    email: EmailStr


class AdminGenerateResetCodeResponse(BaseModel):
    success: bool
    message: str
    code: str
    expires_at: datetime


# ── Force reset (admin sets password directly) ────

class AdminForceResetRequest(BaseModel):
    email: EmailStr
    new_password: str
    force_change_on_login: bool = True


class AdminForceResetResponse(BaseModel):
    success: bool
    message: str
