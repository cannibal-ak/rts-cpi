"""Login Activity — per-user daily login/logout tracking (migration 048).

Handlers and services are called directly against the transactional
``db_session`` fixture (all writes rolled back at test end), mirroring
tests/test_user_deactivate.py. Every test works on a throwaway tenant and
users it creates itself; no real account is touched.

The service clock is frozen (``clock`` fixture) at 06:00 UTC — 11:30 IST,
far from the IST midnight — so no test can straddle a day boundary.

Run ONLY this file:
    pytest tests/test_login_activity.py -q
"""

import uuid
from datetime import datetime, timedelta, timezone

import pyotp
import pytest
from fastapi import HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.core import crypto
from app.core.config import settings
from app.models.login_activity import UserLoginDay
from app.models.user import AppUser, RoleBinding
from app.models.user_mfa import UserMfa
from app.routers.admin_login_activity import list_login_activity, router as admin_router
from app.routers.admin_password_management import delete_user
from app.routers.auth import (
    LoginRequest, RefreshRequest, heartbeat, login, logout, refresh,
)
from app.routers.mfa import VerifyRequest, verify
from app.services import login_activity
from app.services.auth_service import (
    create_access_token, create_mfa_challenge_token, create_refresh_token, hash_password,
)

PW = "TempPass2026!xy"
TOTP_SECRET = "JBSWY3DPEHPK3PXP"


IST_OFFSET = timedelta(hours=5, minutes=30)   # Asia/Kolkata has no DST


class _Clock:
    def __init__(self):
        self.now = datetime.now(timezone.utc).replace(hour=6, minute=0, second=0, microsecond=0)

    def ist_date(self):
        """The IST calendar day of `now`, computed independently of the service."""
        return (self.now + IST_OFFSET).date()

    def advance(self, **kw):
        self.now += timedelta(**kw)
        return self.now


@pytest.fixture
def clock(monkeypatch):
    c = _Clock()
    monkeypatch.setattr(login_activity, "_utcnow", lambda: c.now)
    return c


def _mk_tenant(db):
    slug = f"zla-{uuid.uuid4().hex[:8]}"
    db.execute(
        text("INSERT INTO tenant (slug, display_name, is_active) VALUES (:s, :n, true)"),
        {"s": slug, "n": f"Throwaway {slug}"},
    )
    return db.execute(text("SELECT id FROM tenant WHERE slug = :s"), {"s": slug}).scalar()


def _mk_user(db, tenant_id, *, active=True, role="TENANT_USER"):
    u = AppUser(
        tenant_id=tenant_id,
        email=f"zla-{uuid.uuid4().hex[:8]}@zla-throwaway.com",
        display_name="Login Activity Test",
        is_active=active,
        password_hash=hash_password(PW),
        must_change_password=False,
    )
    db.add(u)
    db.flush()
    if role:
        db.add(RoleBinding(tenant_id=tenant_id, user_id=u.id, role=role))
        db.flush()
    return u


@pytest.fixture
def user(db_session):
    return _mk_user(db_session, _mk_tenant(db_session))


def _rows(db, user_id):
    db.expire_all()
    return (
        db.query(UserLoginDay)
        .filter(UserLoginDay.user_id == user_id)
        .order_by(UserLoginDay.activity_date)
        .all()
    )


def _seed(db, u, day, at, **kw):
    """A day row as if the user logged in at `at` (and was last seen then)."""
    db.add(UserLoginDay(
        tenant_id=u.tenant_id, user_id=u.id, activity_date=day,
        first_login_at=at, last_login_at=at, last_seen_at=at, **kw,
    ))
    db.flush()


def _access_token(u):
    return create_access_token({
        "sub": str(u.id), "tenant_id": str(u.tenant_id), "email": u.email,
        "roles": ["TENANT_USER"], "tenant_slug": "zla",
    })


# ── login ───────────────────────────────────────────────────────────────────

def test_days_are_ist_calendar_days(db_session, user, clock):
    # 20:00 UTC is 01:30 IST the NEXT day — a UTC-dated bucket would differ.
    clock.now = clock.now.replace(hour=20)
    assert clock.ist_date() == clock.now.date() + timedelta(days=1)

    login(LoginRequest(email=user.email, password=PW), db=db_session)
    assert [r.activity_date for r in _rows(db_session, user.id)] == [clock.ist_date()]
    assert list_login_activity(day=None, db=db_session).date == clock.ist_date()

    # A heartbeat 5 hours later (01:00 UTC, 06:30 IST) is still the same IST day.
    clock.advance(hours=5)
    login_activity.touch(db_session, user.id)
    assert [r.activity_date for r in _rows(db_session, user.id)] == [clock.ist_date()]

    # 19:00 UTC that day is 00:30 IST the day after: carried into a new row.
    clock.advance(hours=18)
    login_activity.touch(db_session, user.id)
    rows = _rows(db_session, user.id)
    assert [r.activity_date for r in rows] == [clock.ist_date() - timedelta(days=1), clock.ist_date()]


def test_first_login_creates_row(db_session, user, clock):
    login(LoginRequest(email=user.email, password=PW), db=db_session)
    rows = _rows(db_session, user.id)
    assert len(rows) == 1
    r = rows[0]
    assert r.activity_date == login_activity.ist_today()
    assert r.login_count == 1
    assert r.first_login_at == r.last_login_at == r.last_seen_at == clock.now
    assert r.last_logout_at is None
    assert r.tenant_id == user.tenant_id


def test_second_login_same_day_increments(db_session, user, clock):
    t0 = clock.now
    login(LoginRequest(email=user.email, password=PW), db=db_session)
    t1 = clock.advance(minutes=10)
    login(LoginRequest(email=user.email, password=PW), db=db_session)
    rows = _rows(db_session, user.id)
    assert len(rows) == 1
    assert rows[0].login_count == 2
    assert rows[0].first_login_at == t0
    assert rows[0].last_login_at == rows[0].last_seen_at == t1


def test_failed_login_records_nothing(db_session, user, clock):
    with pytest.raises(HTTPException):
        login(LoginRequest(email=user.email, password="WrongPass!123"), db=db_session)
    assert _rows(db_session, user.id) == []


def test_mfa_challenge_not_counted_until_verify(db_session, user, clock, monkeypatch):
    db_session.add(UserMfa(
        tenant_id=user.tenant_id, user_id=user.id, enabled=True,
        secret_ciphertext=crypto.encrypt_str(TOTP_SECRET),
    ))
    db_session.flush()
    monkeypatch.setattr(settings, "mfa_enforced", True)

    resp = login(LoginRequest(email=user.email, password=PW), db=db_session)
    assert isinstance(resp, JSONResponse)          # challenge, not tokens
    assert _rows(db_session, user.id) == []

    tok = create_mfa_challenge_token(str(user.id), str(user.tenant_id))
    out = verify(VerifyRequest(mfa_token=tok, code=pyotp.TOTP(TOTP_SECRET).now()), db=db_session)
    assert out.access_token
    rows = _rows(db_session, user.id)
    assert len(rows) == 1 and rows[0].login_count == 1


def test_prune_drops_rows_outside_window(db_session, user, clock):
    today = login_activity.ist_today()
    old = today - timedelta(days=settings.login_activity_retention_days)      # just outside
    edge = login_activity.oldest_kept_day(today)                              # last kept day
    for d in (old, edge):
        _seed(db_session, user, d, clock.now - timedelta(days=40))

    login(LoginRequest(email=user.email, password=PW), db=db_session)
    days = [r.activity_date for r in _rows(db_session, user.id)]
    assert old not in days
    assert edge in days and today in days


# ── logout / refresh / heartbeat ────────────────────────────────────────────

def test_logout_stamps_todays_row(db_session, user, clock):
    login(LoginRequest(email=user.email, password=PW), db=db_session)
    t1 = clock.advance(minutes=45)
    logout(token=_access_token(user), db=db_session)
    r = _rows(db_session, user.id)[0]
    assert r.last_logout_at == r.last_seen_at == t1
    assert login_activity.session_status(r) == "logged_out"


def test_logout_after_midnight_carries_session_into_today(db_session, user, clock):
    today = login_activity.ist_today()
    started = clock.now - timedelta(hours=14)                   # 21:30 IST yesterday
    _seed(db_session, user, today - timedelta(days=1), started)

    logout(token=_access_token(user), db=db_session)
    prev, cur = _rows(db_session, user.id)
    # Yesterday's row is left as it was ...
    assert prev.last_logout_at is None and prev.last_seen_at == started
    # ... and today's row records the continued session and its logout.
    assert cur.activity_date == today
    assert cur.login_count == 0
    assert cur.first_login_at == cur.last_login_at == started
    assert cur.last_logout_at == cur.last_seen_at == clock.now
    assert login_activity.session_status(cur) == "logged_out"


def test_touch_carries_over_from_the_latest_earlier_row(db_session, user, clock):
    today = clock.ist_date()
    older = clock.now - timedelta(days=3)
    morning = clock.now - timedelta(days=1, hours=2)
    evening = clock.now - timedelta(days=1) + timedelta(hours=9)
    _seed(db_session, user, today - timedelta(days=3), older)
    # Yesterday: two logins — the session left open overnight is the LATER one.
    _seed(db_session, user, today - timedelta(days=1), morning)
    prev = _rows(db_session, user.id)[1]
    prev.last_login_at = prev.last_seen_at = evening
    prev.login_count = 2
    db_session.flush()

    login_activity.touch(db_session, user.id)
    rows = _rows(db_session, user.id)
    assert [r.activity_date for r in rows] == [today - timedelta(days=3), today - timedelta(days=1), today]
    assert rows[0].last_seen_at == older and rows[1].last_seen_at == evening   # untouched
    carried = rows[2]
    assert carried.first_login_at == carried.last_login_at == evening   # the session that carried over
    assert carried.last_seen_at == clock.now and carried.login_count == 0


def test_refresh_and_heartbeat_bump_last_seen(db_session, user, clock):
    t0 = clock.now
    login_activity.record_login(db_session, user)
    db_session.flush()

    t1 = clock.advance(minutes=5)
    refresh(RefreshRequest(refresh_token=create_refresh_token({
        "sub": str(user.id), "tenant_id": str(user.tenant_id), "email": user.email,
        "roles": [], "tenant_slug": "zla",
    })), db=db_session)
    assert _rows(db_session, user.id)[0].last_seen_at == t1

    t2 = clock.advance(minutes=5)
    resp = heartbeat(current_user={"sub": str(user.id)}, db=db_session)
    assert resp.status_code == 204
    rows = _rows(db_session, user.id)
    assert len(rows) == 1
    assert rows[0].last_seen_at == t2
    assert rows[0].last_login_at == t0              # heartbeat is not a login
    assert rows[0].login_count == 1


def test_heartbeat_never_moves_last_seen_backwards(db_session, user, clock):
    login_activity.record_login(db_session, user)
    login_activity.touch(db_session, user.id, now=clock.now - timedelta(minutes=30))
    assert _rows(db_session, user.id)[0].last_seen_at == clock.now
    earlier = clock.now - timedelta(minutes=20)
    login_activity.record_logout(db_session, user.id, now=earlier)
    r = _rows(db_session, user.id)[0]
    assert r.last_logout_at == earlier and r.last_seen_at == clock.now


def test_touch_and_logout_without_any_row_are_noops(db_session, user, clock):
    login_activity.touch(db_session, user.id)
    login_activity.record_logout(db_session, user.id)
    assert _rows(db_session, user.id) == []


# ── status derivation ───────────────────────────────────────────────────────

def test_session_status_values():
    now = datetime.now(timezone.utc)
    login_at = now - timedelta(hours=1)

    def row(**kw):
        base = dict(first_login_at=login_at, last_login_at=login_at,
                    last_seen_at=login_at, last_logout_at=None)
        base.update(kw)
        return UserLoginDay(**base)

    assert login_activity.session_status(None, now) == "not_signed_in"
    assert login_activity.session_status(row(last_logout_at=now), now) == "logged_out"
    assert login_activity.session_status(row(last_seen_at=now - timedelta(minutes=3)), now) == "online"
    assert login_activity.session_status(row(last_seen_at=now - timedelta(minutes=40)), now) == "session_ended"
    # Logged out, then logged in again later -> the newer login is what counts.
    again = row(last_logout_at=login_at, last_login_at=now - timedelta(minutes=5),
                last_seen_at=now - timedelta(minutes=5))
    assert login_activity.session_status(again, now) == "online"


# ── admin list endpoint ─────────────────────────────────────────────────────

def test_list_includes_signed_in_and_not_signed_in(db_session, clock):
    tid = _mk_tenant(db_session)
    signed = _mk_user(db_session, tid)
    idle = _mk_user(db_session, tid)
    gone = _mk_user(db_session, tid, active=False)        # inactive, no activity -> hidden
    left = _mk_user(db_session, tid, active=False)        # inactive, active today -> shown
    login(LoginRequest(email=signed.email, password=PW), db=db_session)
    _seed(db_session, left, login_activity.ist_today(), clock.now)

    resp = list_login_activity(day=None, db=db_session)
    assert resp.date == login_activity.ist_today()
    by_id = {i.user_id: i for i in resp.items}
    assert by_id[signed.id].status == "online"
    assert by_id[signed.id].login_count == 1
    assert by_id[signed.id].role == "TENANT_USER"
    assert by_id[idle.id].status == "not_signed_in"
    assert by_id[idle.id].first_login_at is None
    assert gone.id not in by_id
    assert by_id[left.id].is_active is False and by_id[left.id].status == "online"
    assert resp.signed_in_count == sum(1 for i in resp.items if i.status != "not_signed_in")
    assert resp.total_users == len(resp.items)


def test_list_shows_carried_over_session_on_both_days(db_session, user, clock):
    today = login_activity.ist_today()
    yesterday = today - timedelta(days=1)
    _seed(db_session, user, yesterday, clock.now - timedelta(hours=14))
    heartbeat(current_user={"sub": str(user.id)}, db=db_session)

    now_view = {i.user_id: i for i in list_login_activity(day=today, db=db_session).items}
    assert now_view[user.id].status == "online"
    assert now_view[user.id].login_count == 0
    old_view = {i.user_id: i for i in list_login_activity(day=yesterday, db=db_session).items}
    assert old_view[user.id].status == "session_ended"


def test_list_window_boundaries(db_session, clock):
    today = login_activity.ist_today()
    oldest = login_activity.oldest_kept_day(today)
    assert list_login_activity(day=oldest, db=db_session).date == oldest
    assert list_login_activity(day=today, db=db_session).oldest_date == oldest
    for bad in (today + timedelta(days=1), oldest - timedelta(days=1)):
        with pytest.raises(HTTPException) as ei:
            list_login_activity(day=bad, db=db_session)
        assert ei.value.status_code == 400


def test_router_is_platform_admin_only(jy_jwt_payload):
    from app.core.deps import RequirePlatformAdmin, get_user_roles, get_user_identity
    assert any(isinstance(d.dependency, RequirePlatformAdmin) for d in admin_router.dependencies)
    with pytest.raises(HTTPException) as ei:
        RequirePlatformAdmin()(
            user_roles=get_user_roles(jy_jwt_payload),
            user_identity=get_user_identity(jy_jwt_payload),
        )
    assert ei.value.status_code == 403


# ── hard delete still works ─────────────────────────────────────────────────

def test_delete_user_cascades_login_rows(db_session, admin_jwt_payload, user, clock):
    login(LoginRequest(email=user.email, password=PW), db=db_session)
    assert len(_rows(db_session, user.id)) == 1
    resp = delete_user(user.id, db=db_session, current_user=admin_jwt_payload)
    assert resp.status_code == 204
    assert _rows(db_session, user.id) == []
