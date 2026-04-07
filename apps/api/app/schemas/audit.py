"""Audit event schemas."""

from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from uuid import UUID


class AuditEventOut(BaseModel):
    id: UUID
    actor: str
    action: str
    target_type: str
    target_id: str
    outcome: str
    event_time: Optional[datetime] = None

    model_config = {"from_attributes": True}
