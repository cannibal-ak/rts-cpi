"""Alert schemas."""

from pydantic import BaseModel
from typing import Optional, Union, Any
from datetime import datetime
from uuid import UUID


class AlertRuleOut(BaseModel):
    id: UUID
    name: str
    domain: str
    rule_type: str
    condition_json: Union[dict, str, Any]
    is_active: bool
    created_at: Optional[datetime] = None
    owner: str

    model_config = {"from_attributes": True}


class AlertRuleCreate(BaseModel):
    name: str
    domain: str
    rule_type: str = "threshold"
    condition_json: Union[dict, str] = {}
    is_active: bool = True
    owner: Optional[str] = "system"


class AlertEventOut(BaseModel):
    id: UUID
    rule_id: UUID
    rule_name: str
    triggered_at: Optional[datetime] = None
    severity: str
    message: str
    delivery_status: str

    model_config = {"from_attributes": True}
