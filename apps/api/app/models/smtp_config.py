"""SMTP config ORM model — backs the smtp_config table from migration 027.

Singleton table (a unique expression-index on ``(true)`` enforces at
most one row). The ``password_encrypted`` column holds Fernet
ciphertext only; the plaintext password is never persisted and never
returned by the read endpoint.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SmtpConfig(Base):
    __tablename__ = "smtp_config"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    host = Column(String(255), nullable=False)
    port = Column(Integer, nullable=False, default=587)
    # 'NONE' | 'STARTTLS' | 'SSL_TLS' — validated in the Pydantic layer.
    encryption = Column(String(20), nullable=False, default="STARTTLS")
    username = Column(String(255), nullable=False)
    password_encrypted = Column(Text, nullable=False)
    from_email = Column(String(255), nullable=False)
    from_name = Column(String(255), nullable=False)
    # NULL ⇒ never tested. Otherwise 'success' | 'failed'.
    last_test_at = Column(DateTime(timezone=True), nullable=True)
    last_test_status = Column(String(20), nullable=True)
    last_test_error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )
    # Bare UUID (no FK). Self-heals on every save.
    updated_by_user_id = Column(UUID(as_uuid=True), nullable=True)
