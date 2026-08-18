"""Focused tests for the guarded hard-delete + last-active-admin guard (D1).

Handlers are called directly against the transactional ``db_session`` fixture
(all writes rolled back at test end), mirroring tests/test_user_deactivate.py.

SAFETY: every test operates ONLY on throwaway tenants/users it creates itself.
No real account (jy@, pw@, fjl@, wm@, skyair@, admin@rts.com, ...) is ever
deleted or mutated — the fixture's outer-transaction rollback discards all of
it, and the `delete_user` handler's commit only releases a savepoint.

Run ONLY this file:
    pytest tests/test_user_delete.py -q
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import text

from app.core import crypto
from app.models.user import AppUser, RoleBinding
from app.models.user_mfa import UserMfa
from app.models.mfa_recovery_code import MfaRecoveryCode
from app.models.password_reset_token import PasswordResetToken
from app.routers.admin_password_management import delete_user, deactivate_user

from app.services.auth_service import hash_password

PW = "TempPass2026!xy"


def _future():
    return datetime.now(timezone.utc) + timedelta(hours=1)


def _mk_tenant(db):
    """Create a throwaway tenant (rolled back at test end)."""
    slug = f"ztd-{uuid.uuid4().hex[:8]}"
    db.execute(
        text(
            "INSERT INTO tenant (slug, display_name, is_active) "
            "VALUES (:s, :n, true)"
        ),
        {"s": slug, "n": f"Throwaway {slug}"},
    )
    tid = db.execute(
        text("SELECT id FROM tenant WHERE slug = :s"), {"s": slug}
    ).scalar()
    return tid, slug


def _mk_user(db, tenant_id, *, active=True, admin=False, email=None):
    """Create a throwaway user; optionally grant the TENANT_ADMIN binding."""
    email = email or f"ztu-{uuid.uuid4().hex[:8]}@throwaway.test"
    db.query(AppUser).filter(AppUser.email == email).delete()
    u = AppUser(
        tenant_id=tenant_id,
        email=email,
        display_name="Throwaway User",
        is_active=active,
        password_hash=hash_password(PW),
        must_change_password=False,
    )
    db.add(u)
    db.flush()
    if admin:
        db.add(RoleBinding(tenant_id=tenant_id, user_id=u.id, role="TENANT_ADMIN"))
        db.flush()
    return u


def _reload(db, user_id):
    return db.query(AppUser).filter(AppUser.id == user_id).first()


# 1) clean delete -> 204, row + set-(A) rows gone, audit row written ----------
def test_clean_delete(db_session, admin_jwt_payload):
    tid, _ = _mk_tenant(db_session)
    u = _mk_user(db_session, tid, active=True, admin=False)
    uid = u.id
    # Seed every set-(A) user-owned auth artifact so the cascade is observable.
    db_session.add(UserMfa(
        tenant_id=tid, user_id=uid, enabled=True,
        secret_ciphertext=crypto.encrypt_str("JBSWY3DPEHPK3PXP"),
    ))
    db_session.add(MfaRecoveryCode(tenant_id=tid, user_id=uid, code_hash="x"))
    db_session.add(PasswordResetToken(
        user_id=uid, email=u.email, token_hash="h",
        purpose="reset", expires_at=_future(), used=False, ip_address=None,
    ))
    db_session.flush()

    resp = delete_user(uid, db=db_session, current_user=admin_jwt_payload)
    assert resp.status_code == 204

    assert _reload(db_session, uid) is None
    assert db_session.query(RoleBinding).filter(RoleBinding.user_id == uid).count() == 0
    assert db_session.query(UserMfa).filter(UserMfa.user_id == uid).count() == 0
    assert db_session.query(MfaRecoveryCode).filter(MfaRecoveryCode.user_id == uid).count() == 0
    assert db_session.query(PasswordResetToken).filter(PasswordResetToken.user_id == uid).count() == 0

    n = db_session.execute(
        text(
            "SELECT count(*) FROM audit_event "
            "WHERE action = 'user.deleted' AND target_id LIKE :p"
        ),
        {"p": f"{uid}%"},
    ).scalar()
    assert n >= 1


# 2) delete with history -> 409 has_history, user still present ---------------
def test_delete_with_history_blocked(db_session, admin_jwt_payload):
    tid, _ = _mk_tenant(db_session)
    u = _mk_user(db_session, tid, active=True, admin=False)
    # audit_event.actor reference == real history (the no-FK set-(B) source).
    db_session.execute(
        text(
            "INSERT INTO audit_event "
            "(tenant_id, actor, action, target_type, target_id, outcome) "
            "VALUES (:t, :a, 'TEST', 'thing', :tid, 'success')"
        ),
        {"t": str(tid), "a": str(u.id), "tid": str(u.id)},
    )
    db_session.flush()

    with pytest.raises(HTTPException) as ei:
        delete_user(u.id, db=db_session, current_user=admin_jwt_payload)
    assert ei.value.status_code == 409
    assert ei.value.detail["code"] == "has_history"
    assert _reload(db_session, u.id) is not None


# 3) delete self -> 400 -------------------------------------------------------
def test_delete_self_blocked(db_session, admin_jwt_payload):
    with pytest.raises(HTTPException) as ei:
        delete_user(
            uuid.UUID(admin_jwt_payload["sub"]),
            db=db_session, current_user=admin_jwt_payload,
        )
    assert ei.value.status_code == 400


# 4) delete a platform admin (by a DIFFERENT actor) -> 400 -------------------
def test_delete_platform_admin_blocked(db_session, admin_user):
    actor = {"sub": str(uuid.uuid4()), "tenant_id": str(admin_user["tenant_id"])}
    with pytest.raises(HTTPException) as ei:
        delete_user(admin_user["id"], db=db_session, current_user=actor)
    assert ei.value.status_code == 400
    assert "super" in str(ei.value.detail).lower()


# 5) delete sole active admin of a tenant -> 409 last_active_admin -----------
def test_delete_sole_active_admin_blocked(db_session, admin_jwt_payload):
    tid, _ = _mk_tenant(db_session)
    u = _mk_user(db_session, tid, active=True, admin=True)
    with pytest.raises(HTTPException) as ei:
        delete_user(u.id, db=db_session, current_user=admin_jwt_payload)
    assert ei.value.status_code == 409
    assert ei.value.detail["code"] == "last_active_admin"
    assert _reload(db_session, u.id) is not None


# 6) deactivate sole active admin -> 409 (new guard on existing endpoint) -----
def test_deactivate_sole_active_admin_blocked(db_session, admin_jwt_payload):
    tid, _ = _mk_tenant(db_session)
    u = _mk_user(db_session, tid, active=True, admin=True)
    with pytest.raises(HTTPException) as ei:
        deactivate_user(u.id, db=db_session, current_user=admin_jwt_payload)
    assert ei.value.status_code == 409
    assert ei.value.detail["code"] == "last_active_admin"
    assert _reload(db_session, u.id).is_active is True


# 7) guard correctness: an admin WITH an active peer can be deleted (204) -----
# Proves the last-active-admin guard does not over-block.
def test_delete_admin_with_active_peer_allowed(db_session, admin_jwt_payload):
    tid, _ = _mk_tenant(db_session)
    u1 = _mk_user(db_session, tid, active=True, admin=True)
    u2 = _mk_user(db_session, tid, active=True, admin=True)
    resp = delete_user(u1.id, db=db_session, current_user=admin_jwt_payload)
    assert resp.status_code == 204
    assert _reload(db_session, u1.id) is None
    assert _reload(db_session, u2.id) is not None


# 8) an already-inactive (sole) admin can be deleted -> 204 ------------------
# The last-active-admin guard only protects ACTIVE admins.
def test_delete_inactive_admin_allowed(db_session, admin_jwt_payload):
    tid, _ = _mk_tenant(db_session)
    u = _mk_user(db_session, tid, active=False, admin=True)
    resp = delete_user(u.id, db=db_session, current_user=admin_jwt_payload)
    assert resp.status_code == 204
    assert _reload(db_session, u.id) is None


# 9) tenant user is forbidden by the router-level RBAC guard -----------------
def test_tenant_user_forbidden_rbac(jy_jwt_payload):
    from app.core.deps import RequirePlatformAdmin, get_user_roles, get_user_identity
    roles = get_user_roles(jy_jwt_payload)
    identity = get_user_identity(jy_jwt_payload)
    with pytest.raises(HTTPException) as ei:
        RequirePlatformAdmin()(user_roles=roles, user_identity=identity)
    assert ei.value.status_code == 403


# 10) unauthenticated -> 401 -------------------------------------------------
def test_unauth_401():
    from app.core.deps import get_current_user
    with pytest.raises(HTTPException) as ei:
        get_current_user(token=None, db=None)
    assert ei.value.status_code == 401
