"""TOTP MFA enrollment state per user (migration 033).

One row per ``app_user`` (UNIQUE ``user_id``). The TOTP shared secret is
stored as Fernet ciphertext (``bytea``) via ``app.core.crypto`` — the same
KEK (``CPI_KEK``) already used for SFTP credentials — so a DB read alone
cannot recover a usable secret. Mirrors the column idioms in
``app/models/user.py`` / ``app/models/sftp.py``: ``Column()`` style,
``postgresql.UUID(as_uuid=True)``, ``DateTime(timezone=True)`` and
``LargeBinary`` for ciphertext.

``last_used_step`` holds the last accepted TOTP time-step counter
(``unix_time // period``) and is the replay guard — a code for a step
``<= last_used_step`` is rejected even if still inside its validity
window. ``failed_attempts`` / ``locked_until`` throttle brute-force
verification (Phase 2 wires the enforcement).
"""

import uuid

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.core.database import Base


class UserMfa(Base):
    __tablename__ = "user_mfa"

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
    )
    # Fernet ciphertext of the base32 TOTP secret; NULL until enrollment
    # begins. Encrypt/decrypt via app.core.crypto.encrypt_str / decrypt_str.
    secret_ciphertext = Column(LargeBinary, nullable=True)
    enabled = Column(Boolean, nullable=False, default=False, server_default="false")
    confirmed_at = Column(DateTime(timezone=True), nullable=True)
    # Last accepted TOTP step counter — replay guard (see module docstring).
    last_used_step = Column(BigInteger, nullable=True)
    failed_attempts = Column(Integer, nullable=False, default=0, server_default="0")
    locked_until = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("user_id", name="uq_user_mfa_user"),
    )
