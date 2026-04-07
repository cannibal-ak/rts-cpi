"""Admin schemas — tenant features, provider contracts, and source config."""

from pydantic import BaseModel
from typing import Optional, Any
from datetime import datetime
from uuid import UUID


class TenantFeatureOut(BaseModel):
    code: str
    label: str
    category: str
    enabled: bool

    model_config = {"from_attributes": True}


class TenantFeatureUpdate(BaseModel):
    enabled: bool


class TenantUserRoles(BaseModel):
    roles: list[str]


class ProviderContractOut(BaseModel):
    id: UUID
    name: str
    provider: str
    domain: str
    status: str
    validation_mode: str
    field_mappings: Any = {}
    required_fields: list[str] = []
    optional_fields: list[str] = []
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class ProviderContractCreate(BaseModel):
    name: str
    provider: str
    domain: str
    status: str = "draft"
    validation_mode: str = "STRICT"
    field_mappings: dict = {}
    required_fields: list[str] = []
    optional_fields: list[str] = []
