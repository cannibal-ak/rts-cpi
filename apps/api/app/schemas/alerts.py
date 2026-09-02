"""Alert schemas.

`AlertEventOut` grew additively — every field the original carried keeps its
name and type, so nothing that already read this shape breaks. `delivery_status`
stays even though delivery is in-app only today; it is the seam email plugs into.
"""

from datetime import date, datetime
from typing import Any, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ── Events ───────────────────────────────────────────────────

class AlertEventOut(BaseModel):
    id: UUID
    rule_id: UUID
    rule_key: str
    rule_name: str
    triggered_at: Optional[datetime] = None
    severity: str
    message: str
    delivery_status: str

    # Added by migration 040.
    scope_key: Optional[str] = None
    observed_at: Optional[date] = None
    prev_observed_at: Optional[date] = None
    evaluation_mode: str = "live"
    payload: dict[str, Any] = Field(default_factory=dict)
    # Not a column — computed per request from alert_event_read for the caller.
    is_read: bool = False

    model_config = {"from_attributes": True}


class AlertSummaryOut(BaseModel):
    """One small request that feeds both the badge and the popover."""
    unread_count: int
    capped: bool = False
    recent: list[AlertEventOut] = Field(default_factory=list)
    newest_triggered_at: Optional[datetime] = None


class MarkReadIn(BaseModel):
    event_ids: list[UUID] = Field(default_factory=list, max_length=500)


class MarkAllReadIn(BaseModel):
    before: Optional[datetime] = None


class MarkReadOut(BaseModel):
    updated: int
    unread_count: int


# ── Rules ────────────────────────────────────────────────────

class TunableFieldOut(BaseModel):
    key: str
    label: str
    type: Literal["number", "enum", "bool", "multiselect"]
    unit: Optional[str] = None
    min: Optional[float] = None
    max: Optional[float] = None
    step: Optional[float] = None
    options: Optional[list[str]] = None
    help: Optional[str] = None


class AlertRuleOut(BaseModel):
    id: UUID
    rule_key: str
    # The catalogue family this rule evaluates as: rule_key itself on preset
    # rows, the family key on user-created instances, None on legacy free-form
    # rows the evaluator ignores.
    preset_key: Optional[str] = None
    name: str
    description: Optional[str] = None
    domain: str
    rule_type: str
    is_active: bool
    is_preset: bool
    severity_default: str
    condition: dict[str, Any] = Field(default_factory=dict)
    # Straight from the preset catalogue, so the settings screen can render the
    # controls without hard-coding ranges or option lists.
    tunables: list[TunableFieldOut] = Field(default_factory=list)
    # Fields that must be filled before this rule may be switched on.
    missing_requirements: list[str] = Field(default_factory=list)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    # Tombstone: set on a deleted built-in. The settings page hides the card
    # and offers Restore instead; the evaluator skips it.
    deleted_at: Optional[datetime] = None
    updated_by: Optional[str] = None

    model_config = {"from_attributes": True}


class AlertRuleUpdate(BaseModel):
    is_active: Optional[bool] = None
    # Merge-patched over the stored condition; the MERGED WHOLE is then
    # validated against the preset's model with extra="forbid", so an unknown
    # or non-tunable key is a 422 naming the field rather than a silent no-op.
    condition: Optional[dict[str, Any]] = None
    # Instances only — renaming a preset would desync it from the catalogue
    # and the cross-env parity report, so the router refuses it with a 400.
    name: Optional[str] = Field(None, min_length=1, max_length=128)


class AlertRuleCreate(BaseModel):
    """A user-created INSTANCE of a catalogue rule type."""
    preset_key: str
    name: str = Field(min_length=1, max_length=128)
    # Partial — merged over the family's defaults, then validated whole.
    condition: Optional[dict[str, Any]] = None
    # Off by default: a new rule should be tuned (or previewed) before its
    # first sweep, not fire on whatever the defaults happen to match.
    is_active: bool = False


# ── Evaluation ───────────────────────────────────────────────

class AlertRunSummaryOut(BaseModel):
    tenant_code: str
    cap_date: Optional[str] = None
    prev_cap_date: Optional[str] = None
    cap_date_age_days: Optional[int] = None
    rules_evaluated: list[str] = Field(default_factory=list)
    groups_evaluated: int = 0
    events_created: int = 0
    events_suppressed_dedupe: int = 0
    groups_skipped_currency: int = 0
    captures_skipped_incomplete: int = 0
    duration_ms: int = 0
    mode: str = "live"
    note: Optional[str] = None


class AlertPreviewRow(BaseModel):
    severity: str
    message: str
    payload: dict[str, Any] = Field(default_factory=dict)


class AlertPreviewOut(BaseModel):
    rule_key: str
    cap_date: Optional[str] = None
    prev_cap_date: Optional[str] = None
    would_fire: int
    groups_evaluated: int
    sample: list[AlertPreviewRow] = Field(default_factory=list)
