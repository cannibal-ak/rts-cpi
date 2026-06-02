"""Shared pytest fixtures for the api test suite.

The DB fixture uses the standard SQLAlchemy "outer transaction with
savepoints" pattern so service-internal ``session.commit()`` calls become
nested savepoints that are rolled back at end of test, leaving the database
clean. Tests run against the real cpi_db (no SQLite — the schema relies on
JSONB / INET / native enums).
"""
from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from sqlalchemy import event, text
from sqlalchemy.orm import Session


@pytest.fixture
def db_session():
    """Yield a session whose work is fully rolled back on test exit."""
    from app.core.database import engine

    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, autoflush=False, autocommit=False)

    # Outer SAVEPOINT — every service-internal commit becomes a nested
    # savepoint. We restart the savepoint after each end so the test never
    # actually escapes the outer transaction.
    nested = connection.begin_nested()

    @event.listens_for(session, "after_transaction_end")
    def restart_savepoint(_session, _trans):
        nonlocal nested
        if not nested.is_active:
            nested = connection.begin_nested()

    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def admin_user(db_session):
    """The canonical RTS platform admin app_user row (UUID + email)."""
    row = db_session.execute(
        text(
            "SELECT id, email, tenant_id FROM app_user "
            "WHERE email = 'admin@rts.com'"
        )
    ).first()
    if not row:
        pytest.skip("Canonical admin@rts.com user not found in DB")
    return {"id": row[0], "email": row[1], "tenant_id": row[2]}


@pytest.fixture
def admin_jwt_payload(admin_user):
    """A JWT payload shape that passes is_platform_admin()."""
    return {
        "sub": str(admin_user["id"]),
        "tenant_id": str(admin_user["tenant_id"]),
        "tenant_slug": "rts",
        "roles": ["TENANT_ADMIN"],
        "token_type": "access",
    }


@pytest.fixture
def jy_jwt_payload(db_session):
    """A JWT payload for jy@airline.com (NOT a platform admin)."""
    row = db_session.execute(
        text(
            "SELECT id, tenant_id FROM app_user "
            "WHERE email = 'jy@airline.com'"
        )
    ).first()
    if not row:
        pytest.skip("Canonical jy@airline.com user not found in DB")
    return {
        "sub": str(row[0]),
        "tenant_id": str(row[1]),
        "tenant_slug": "jy",
        "roles": ["TENANT_ADMIN"],
        "token_type": "access",
    }


@pytest.fixture
def staging_dir(tmp_path: Path) -> Path:
    """Per-test staging root inside pytest's tmp_path."""
    d = tmp_path / "staging"
    d.mkdir(parents=True, exist_ok=True)
    return d
