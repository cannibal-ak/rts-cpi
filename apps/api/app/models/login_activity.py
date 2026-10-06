"""Per-user, per-day sign-in activity (migration 048)."""

import uuid
from sqlalchemy import Column, Date, DateTime, Integer, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from app.core.database import Base


class UserLoginDay(Base):
    __tablename__ = "user_login_day"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Indexes (ix_user_login_day_date / _tenant) are created by migration 048.
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("app_user.id", ondelete="CASCADE"), nullable=False)
    activity_date = Column(Date, nullable=False)   # IST calendar day
    first_login_at = Column(DateTime(timezone=True), nullable=False)
    last_login_at = Column(DateTime(timezone=True), nullable=False)
    login_count = Column(Integer, nullable=False, default=1, server_default="1")
    last_logout_at = Column(DateTime(timezone=True), nullable=True)
    last_seen_at = Column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("user_id", "activity_date", name="uq_user_login_day_user_date"),
    )
