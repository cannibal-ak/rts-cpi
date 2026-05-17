"""Password reset token ORM model — backs the forgot-password flow."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, Boolean, Integer, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class PasswordResetToken(Base):
    __tablename__ = "password_reset_token"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("app_user.id", ondelete="CASCADE"), nullable=False)
    email = Column(String(256), nullable=False, index=True)
    code = Column(String(6), nullable=False, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    used = Column(Boolean, nullable=False, default=False, server_default="false")
    attempts = Column(Integer, nullable=False, default=0, server_default="0")
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    ip_address = Column(String(45), nullable=True)
