"""SQLAlchemy engine, session factory, Base class, and tenant context."""

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker, Session

from app.core.config import settings

# ── Superuser engine (migrations, admin ops — bypasses RLS) ──
engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# ── RLS-enforced engine (cpi_app role — subject to RLS policies) ──
engine_rls = create_engine(settings.database_url_rls, pool_pre_ping=True)
SessionLocalRLS = sessionmaker(autocommit=False, autoflush=False, bind=engine_rls)


class Base(DeclarativeBase):
    """Base class for all ORM models."""
    pass


def get_db():
    """FastAPI dependency — superuser session (no RLS). Use for admin/migration tasks."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_db_rls():
    """FastAPI dependency — RLS-enforced session via cpi_app role."""
    db = SessionLocalRLS()
    try:
        yield db
    finally:
        db.close()


def set_tenant_context(db: Session, tenant_id: str) -> None:
    """Set the RLS tenant context on an existing session.

    Call this at the start of any tenant-scoped route handler:
        set_tenant_context(db, tenant_id)
    All subsequent queries in the same transaction are filtered by RLS.
    """
    db.execute(text("SET LOCAL app.current_tenant = :tid"), {"tid": tenant_id})
