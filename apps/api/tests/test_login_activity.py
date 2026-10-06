"""Login Activity — per-user daily login/logout tracking (migration 048).

Handlers and services are called directly against the transactional
``db_session`` fixture (all writes rolled back at test end), mirroring
tests/test_user_deactivate.py. Every test works on a throwaway tenant and
users it creates itself; no real account is touched.

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


def _access_token(u):
    return create_access_token({
        "sub": str(u.id), "tenant_id": str(u.tenant_id), "email": u.email,
        "roles": ["TENANT_USER"], "tenant_slug": "zla",
    })


# ── login ───────────────────────────────────────────────────────────────────

def test_first_login_creates_row(db_session, user):
    login(LoginRequest(email=user.email, password=PW), db=db_session)
    rows = _rows(db_session, user.id)
    assert len(rows) == 1
    r = rows[0]
    assert r.activity_date == login_activity.ist_today()
    assert r.login_count == 1
    assert r.first_login_at == r.last_login_at == r.last_seen_at
    assert r.last_logout_at is None
    assert r.tenant_id == user.tenant_id


def test_second_login_same_day_increments(db_session, user):
    login(LoginRequest(email=user.email, password=PW), db=db_session)
    first = _rows(db_session, user.id)[0].first_login_at
    login(LoginRequest(email=user.email, password=PW), db=db_session)
    rows = _rows(db_session, user.id)
    assert len(rows) == 1
    assert rows[0].login_count == 2
    assert rows[0].first_login_at == first
    assert rows[0].last_login_at >= first


def test_failed_login_records_nothing(db_session, user):
    with pytest.raises(HTTPException):
        login(LoginRequest(email=user.email, password="WrongPass!123"), db=db_session)
    assert _rows(db_session, user.id) == []


def test_mfa_challenge_not_counted_until_verify(db_session, user, monkeypatch):
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


def test_prune_drops_rows_outside_window(db_session, user):
    today = login_activity.ist_today()
    old = today - timedelta(days=settings.login_activity_retention_days)      # just outside
    edge = login_activity.oldest_kept_day(today)                              # last kept day
    now = datetime.now(timezone.utc)
    for d in (old, edge):
        db_session.add(UserLoginDay(
            tenant_id=user.tenant_id, user_id=user.id, activity_date=d,
            first_login_at=now, last_login_at=now, last_seen_at=now,
        ))
    db_session.flush()

    login(LoginRequest(email=user.email, password=PW), db=db_session)
    days = [r.activity_date for r in _rows(db_session, user.id)]
    assert old not in days
    assert edge in days and today in days


# ── logout / refresh / heartbeat ────────────────────────────────────────────

def test_logout_stamps_latest_row(db_session, user):
    login(LoginRequest(email=user.email, password=PW), db=db_session)
    logout(token=_access_token(user), db=db_session)
    r = _rows(db_session, user.id)[0]
    assert r.last_logout_at is not None
    assert r.last_logout_at >= r.last_login_at
    assert login_activity.session_status(r) == "logged_out"


def test_logout_after_midnight_closes_previous_day(db_session, user):
    yesterday = login_activity.ist_today() - timedelta(days=1)
    t = datetime.now(timezone.utc) - timedelta(hours=2)
    db_session.add(UserLoginDay(
        tenant_id=user.tenant_id, user_id=user.id, activity_date=yesterday,
        first_login_at=t, last_login_at=t, last_seen_at=t,
    ))
    db_session.flush()
    logout(token=_access_token(user), db=db_session)
    rows = _rows(db_session, user.id)
    assert len(rows) == 1                          # no new row for today
    assert rows[0].activity_date == yesterday
    assert rows[0].last_logout_at is not None


def test_refresh_and_heartbeat_bump_last_seen(db_session, user):
    t = datetime.now(timezone.utc) - timedelta(minutes=30)
    login_activity.record_login(db_session, user, now=t)
    db_session.flush()

    refresh(RefreshRequest(refresh_token=create_refresh_token({
        "sub": str(user.id), "tenant_id": str(user.tenant_id), "email": user.email,
        "roles": [], "tenant_slug": "zla",
    })), db=db_session)
    after_refresh = _rows(db_session, user.id)[0].last_seen_at
    assert after_refresh > t

    resp = heartbeat(current_user={"sub": str(user.id)}, db=db_session)
    assert resp.status_code == 204
    r = _rows(db_session, user.id)[0]
    assert r.last_seen_at >= after_refresh
    assert r.last_login_at == t                    # heartbeat is not a login
    assert r.login_count == 1


def test_touch_without_any_row_is_a_noop(db_session, user):
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

def test_list_includes_signed_in_and_not_signed_in(db_session):
    tid = _mk_tenant(db_session)
    signed = _mk_user(db_session, tid)
    idle = _mk_user(db_session, tid)
    gone = _mk_user(db_session, tid, active=False)   # inactive, no activity -> hidden
    login(LoginRequest(email=signed.email, password=PW), db=db_session)

    resp = list_login_activity(day=None, db=db_session)
    assert resp.date == login_activity.ist_today()
    by_id = {i.user_id: i for i in resp.items}
    assert by_id[signed.id].status == "online"
    assert by_id[signed.id].login_count == 1
    assert by_id[signed.id].role == "TENANT_USER"
    assert by_id[idle.id].status == "not_signed_in"
    assert by_id[idle.id].first_login_at is None
    assert gone.id not in by_id
    assert resp.signed_in_count == sum(1 for i in resp.items if i.status != "not_signed_in")
    assert resp.total_users == len(resp.items)


def test_list_rejects_dates_outside_window():
    today = login_activity.ist_today()
    for bad in (today + timedelta(days=1),
                today - timedelta(days=settings.login_activity_retention_days)):
        with pytest.raises(HTTPException) as ei:
            list_login_activity(day=bad, db=None)
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

def test_delete_user_cascades_login_rows(db_session, admin_jwt_payload, user):
    login(LoginRequest(email=user.email, password=PW), db=db_session)
    assert len(_rows(db_session, user.id)) == 1
    resp = delete_user(user.id, db=db_session, current_user=admin_jwt_payload)
    assert resp.status_code == 204
    assert _rows(db_session, user.id) == []
