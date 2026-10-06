"""Pydantic schemas for the admin Login Activity page.

Backs apps/api/app/routers/admin_login_activity.py.
"""

from datetime import date as Date, datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel

SessionStatus = Literal["online", "logged_out", "session_ended", "not_signed_in"]


class LoginActivityItem(BaseModel):
    user_id: UUID
    email: str
    tenant_name: str
    tenant_slug: str
    role: str
    is_active: bool
    first_login_at: Optional[datetime] = None
    last_login_at: Optional[datetime] = None
    login_count: int = 0
    last_logout_at: Optional[datetime] = None
    last_seen_at: Optional[datetime] = None
    status: SessionStatus


class LoginActivityResponse(BaseModel):
    date: Date
    retention_days: int
    oldest_date: Date
    items: list[LoginActivityItem]
    signed_in_count: int
    total_users: int
