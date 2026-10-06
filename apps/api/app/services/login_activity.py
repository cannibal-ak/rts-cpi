"""Per-user daily sign-in tracking for the admin Login Activity page.

One user_login_day row per IST calendar day on which the user was active.
Login upserts today's row. Logout, /auth/refresh and the browser heartbeat
stamp today's row too: when the session began on an earlier day (tabs are
often left open overnight — refresh tokens live 7 days), the first such
signal carries it over into a row for today with login_count = 0 and
first/last login copied from the day it started. So every day's list shows
everyone who was active that day, not only those who logged in afresh.

Nothing here commits — the caller's commit carries the write. Every write
runs inside a SAVEPOINT and swallows its own errors, so tracking can never
fail (or poison the transaction of) a login, refresh or logout.
"""

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.login_activity import UserLoginDay
from app.models.user import AppUser

logger = logging.getLogger("uvicorn.error")

IST = ZoneInfo("Asia/Kolkata")

# A session with no logout counts as "online" while its last heartbeat is this
# recent: 2x the 5-minute browser heartbeat, plus slack for throttled tabs.
ONLINE_WINDOW = timedelta(minutes=12)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def ist_day(at: datetime) -> date:
    return at.astimezone(IST).date()


def ist_today() -> date:
    return ist_day(_utcnow())


def oldest_kept_day(today: Optional[date] = None) -> date:
    """First day still inside the retention window (today counts as day 1)."""
    days = max(int(settings.login_activity_retention_days), 1)
    return (today or ist_today()) - timedelta(days=days - 1)


def record_login(db: Session, user: AppUser, now: Optional[datetime] = None) -> None:
    """Upsert today's row for a login that issued tokens, then prune old days."""
    now = now or _utcnow()
    try:
        with db.begin_nested():
            stmt = pg_insert(UserLoginDay).values(
                tenant_id=user.tenant_id,
                user_id=user.id,
                activity_date=ist_day(now),
                first_login_at=now,
                last_login_at=now,
                login_count=1,
                last_seen_at=now,
            ).on_conflict_do_update(
                index_elements=[UserLoginDay.user_id, UserLoginDay.activity_date],
                set_={
                    "last_login_at": now,
                    "last_seen_at": now,
                    "login_count": UserLoginDay.login_count + 1,
                },
            )
            db.execute(stmt)
            db.execute(
                text("DELETE FROM user_login_day WHERE activity_date < :cutoff"),
                {"cutoff": oldest_kept_day(ist_day(now))},
            )
    except Exception:
        logger.exception("login_activity: record_login failed for user %s", user.id)


# Bump last_seen on today's row, creating it from the user's latest earlier
# row when the session started on a previous day. No row at all (a session
# from before this feature) -> nothing to carry over, nothing written.
_TOUCH_SQL = text("""
    INSERT INTO user_login_day
           (tenant_id, user_id, activity_date,
            first_login_at, last_login_at, login_count, last_seen_at)
    SELECT tenant_id, user_id, :today,
           last_login_at, last_login_at, 0, :now
      FROM user_login_day
     WHERE user_id = :uid
     ORDER BY activity_date DESC
     LIMIT 1
    ON CONFLICT (user_id, activity_date) DO UPDATE
       SET last_seen_at = GREATEST(user_login_day.last_seen_at, EXCLUDED.last_seen_at)
""")

_LOGOUT_SQL = text("""
    UPDATE user_login_day
       SET last_logout_at = :now,
           last_seen_at = GREATEST(last_seen_at, :now)
     WHERE user_id = :uid AND activity_date = :today
""")


def _touch_today(db: Session, user_id, now: datetime) -> None:
    db.execute(_TOUCH_SQL, {"uid": str(user_id), "today": ist_day(now), "now": now})


def record_logout(db: Session, user_id, now: Optional[datetime] = None) -> None:
    """Explicit logout: stamp last_logout_at on today's row (carried over if needed)."""
    now = now or _utcnow()
    try:
        with db.begin_nested():
            _touch_today(db, user_id, now)
            db.execute(_LOGOUT_SQL, {"uid": str(user_id), "today": ist_day(now), "now": now})
    except Exception:
        logger.exception("login_activity: record_logout failed for user %s", user_id)


def touch(db: Session, user_id, now: Optional[datetime] = None) -> None:
    """Still-signed-in signal (refresh / heartbeat): bump today's last_seen_at."""
    now = now or _utcnow()
    try:
        with db.begin_nested():
            _touch_today(db, user_id, now)
    except Exception:
        logger.exception("login_activity: touch failed for user %s", user_id)


def session_status(row: Optional[UserLoginDay], now: Optional[datetime] = None) -> str:
    """logged_out | online | session_ended | not_signed_in."""
    if row is None:
        return "not_signed_in"
    if row.last_logout_at is not None and row.last_logout_at >= row.last_login_at:
        return "logged_out"
    now = now or _utcnow()
    if now - row.last_seen_at <= ONLINE_WINDOW:
        return "online"
    return "session_ended"
