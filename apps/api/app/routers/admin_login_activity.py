"""Admin Login Activity — who signed in on a given day, and when they left.

One row per user per IST day (user_login_day, migration 048), kept for
LOGIN_ACTIVITY_RETENTION_DAYS. RTS platform admin only (RequirePlatformAdmin
at the router level; main.py also stacks _protected), cross-tenant read on
the superuser session like admin_password_management.
"""

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.deps import RequirePlatformAdmin
from app.models.login_activity import UserLoginDay
from app.models.tenant import Tenant
from app.models.user import AppUser, RoleBinding
from app.schemas.admin_login_activity import LoginActivityItem, LoginActivityResponse
from app.services import login_activity

router = APIRouter(
    prefix="/api/v1/admin/login-activity",
    tags=["Admin - Login Activity"],
    dependencies=[Depends(RequirePlatformAdmin())],
)


@router.get("", response_model=LoginActivityResponse)
def list_login_activity(
    day: Optional[date] = Query(None, alias="date", description="IST day, YYYY-MM-DD (default: today)"),
    db: Session = Depends(get_db),
):
    today = login_activity.ist_today()
    oldest = login_activity.oldest_kept_day(today)
    day = day or today
    if day > today or day < oldest:
        raise HTTPException(
            status_code=400,
            detail=f"Login activity is kept for {settings.login_activity_retention_days} days "
                   f"({oldest.isoformat()} to {today.isoformat()}).",
        )

    # Every user, with that day's row if they signed in. Inactive users are
    # kept only when they have activity on the day.
    rows = (
        db.query(AppUser, Tenant, UserLoginDay)
        .join(Tenant, Tenant.id == AppUser.tenant_id)
        .outerjoin(
            UserLoginDay,
            and_(UserLoginDay.user_id == AppUser.id, UserLoginDay.activity_date == day),
        )
        .order_by(Tenant.display_name, AppUser.email)
        .all()
    )
    rows = [(u, t, d) for (u, t, d) in rows if u.is_active or d is not None]

    user_ids = [u.id for (u, _t, _d) in rows]
    role_rows = (
        db.query(RoleBinding.user_id, RoleBinding.role)
        .filter(RoleBinding.user_id.in_(user_ids))
        .all()
        if user_ids else []
    )
    roles_by_user: dict = {}
    for uid, role in role_rows:
        roles_by_user.setdefault(uid, []).append(role)

    items: list[LoginActivityItem] = []
    for user, tenant, act in rows:
        roles = roles_by_user.get(user.id, [])
        items.append(
            LoginActivityItem(
                user_id=user.id,
                email=user.email,
                tenant_name=tenant.display_name,
                tenant_slug=tenant.slug,
                role=roles[0] if roles else "",
                is_active=bool(user.is_active),
                first_login_at=act.first_login_at if act else None,
                last_login_at=act.last_login_at if act else None,
                login_count=act.login_count if act else 0,
                last_logout_at=act.last_logout_at if act else None,
                last_seen_at=act.last_seen_at if act else None,
                status=login_activity.session_status(act),
            )
        )

    signed_in = sum(1 for i in items if i.status != "not_signed_in")
    return LoginActivityResponse(
        date=day,
        retention_days=settings.login_activity_retention_days,
        oldest_date=oldest,
        items=items,
        signed_in_count=signed_in,
        total_users=len(items),
    )
