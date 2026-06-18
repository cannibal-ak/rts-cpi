"""One-time MFA recovery codes (migration 033).

Many rows per ``app_user``. Only the hash of each code is persisted
(``code_hash`` — SHA-256 hex via ``app.core.security.hash_token``, the
same one-way scheme already used for password-reset / invite tokens), so
a DB read cannot recover a usable code. A code is spent when ``used_at``
is set. Mirrors the column idioms in ``app/models/user.py``.
"""

import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.core.database import Base


class MfaRecoveryCode(Base):
    __tablename__ = "mfa_recovery_code"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(
        UUID(as_uuid=True),
        ForeignKey("tenant.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("app_user.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    code_hash = Column(Text, nullable=False)
    used_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
