"""Alert rule, event and per-user read-state ORM models — tenant-owned.

All three tables carry RLS keyed on `app.current_tenant`, so any session that
touches them must either be the cpi superuser (which bypasses RLS entirely) or
have had set_tenant_context() called on it. The evaluator deliberately uses the
RLS-enforced session: see app/services/alerts/evaluator.py.
"""

import uuid
from sqlalchemy import (
    Column, String, Boolean, DateTime, Date, Text, ForeignKey, Index,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
from app.core.database import Base


class AlertRule(Base):
    __tablename__ = "alert_rule"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False, index=True)
    # Stable per-tenant handle ('comp_price_move'). Code and URLs reference
    # this, never `name`, which is display text a user may edit.
    rule_key = Column(String(64), nullable=False)
    name = Column(String(128), nullable=False)
    description = Column(Text)
    domain = Column(String(16), nullable=False)
    rule_type = Column(String(16), nullable=False)
    condition_json = Column(JSONB, nullable=False, server_default="{}")
    is_active = Column(Boolean, nullable=False, server_default="true")
    # False for user-created rows: catalogue-preset INSTANCES (preset_key set)
    # and the old free-form POST /rules rules (preset_key NULL).
    is_preset = Column(Boolean, nullable=False, server_default="true")
    # Which catalogue family this rule evaluates as. Equal to rule_key on
    # preset rows, the family key on instances. NULL = evaluator-invisible.
    preset_key = Column(String(64), nullable=True)
    # Tombstone for deleted BUILT-IN rules. The row must survive so
    # _ensure_presets does not resurrect the rule with defaults; restore
    # clears it. Instances are hard-deleted instead (keys never reused).
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    severity_default = Column(String(16), nullable=False, server_default="warning")
    owner = Column(String(128), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True))
    updated_by_user_id = Column(UUID(as_uuid=True), ForeignKey("app_user.id", ondelete="SET NULL"))

    __table_args__ = (
        UniqueConstraint("tenant_id", "rule_key", name="uq_alert_rule_tenant_key"),
    )


class AlertEvent(Base):
    __tablename__ = "alert_event"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False, index=True)
    rule_id = Column(UUID(as_uuid=True), ForeignKey("alert_rule.id", ondelete="CASCADE"), nullable=False)
    rule_key = Column(String(64), nullable=False)
    rule_name = Column(String(128), nullable=False)

    # What this alert is ABOUT, stable across captures: 'rank|ZNZ-NBO|00-07'.
    # Used to find the last state emitted for this subject.
    scope_key = Column(Text, nullable=False)
    # THIS EXACT FIRING. Unique per tenant — the engine's idempotency guarantee.
    dedupe_key = Column(Text, nullable=False)

    # When we say it happened. For backfilled events this is the capture date's
    # own business time, not the moment we computed it — see payload.evaluated_at.
    triggered_at = Column(DateTime(timezone=True), server_default=func.now())
    # The capture this fact is about, and the baseline it was compared against.
    # Separate from triggered_at so the UI can sort by business date.
    observed_at = Column(Date)
    prev_observed_at = Column(Date)

    severity = Column(String(16), nullable=False, server_default="info")
    message = Column(Text, nullable=False)
    payload = Column(JSONB, nullable=False, server_default="{}")
    evaluation_mode = Column(String(16), nullable=False, server_default="live")
    # Set by nothing in phase 1. Reserved so a future "overtaken by a newer
    # alert" sweep is not another migration against a table the bell polls.
    superseded_at = Column(DateTime(timezone=True))
    # Vestigial while delivery is in-app only; this is the seam email plugs
    # into without a migration.
    delivery_status = Column(String(16), nullable=False, server_default="pending")

    __table_args__ = (
        UniqueConstraint("tenant_id", "dedupe_key", name="uq_alert_event_dedupe"),
        Index("ix_alert_event_tenant_time", "tenant_id",
              triggered_at.desc(), id.desc()),
        Index("ix_alert_event_tenant_rule_time", "tenant_id", "rule_key",
              triggered_at.desc()),
        Index("ix_alert_event_scope_observed", "tenant_id", "scope_key",
              observed_at.desc()),
    )


class AlertEventRead(Base):
    """Per-user read receipt. Read == a row exists for (event, user).

    Per-user rather than a read_at column on alert_event: an unread badge that
    one colleague clears for everybody is a bug users report on day one, and
    retrofitting per-user later costs a data migration and an API break.
    """

    __tablename__ = "alert_event_read"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False, index=True)
    event_id = Column(UUID(as_uuid=True), ForeignKey("alert_event.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("app_user.id", ondelete="CASCADE"), nullable=False)
    read_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("event_id", "user_id", name="uq_alert_event_read"),
        Index("ix_alert_event_read_user", "user_id", "event_id"),
    )
