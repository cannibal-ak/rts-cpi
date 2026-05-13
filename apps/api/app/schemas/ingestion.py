"""Ingestion job, batch, and validation error schemas."""

from pydantic import BaseModel
from typing import Optional, Any
from datetime import datetime
from uuid import UUID


class JobTimelineEntry(BaseModel):
    status: str
    timestamp: str
    message: Optional[str] = None


class IngestionJobOut(BaseModel):
    id: UUID
    domain: str
    tenant_code: Optional[str] = None
    status: str
    source_name: Optional[str] = None
    validation_mode: str = "STRICT"
    records_total: int
    records_valid: int
    records_rejected: int
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    timeline: list[Any] = []

    model_config = {"from_attributes": True}


class ImportBatchOut(BaseModel):
    id: UUID
    import_job_id: UUID
    batch_seq: int
    record_count: int
    completeness_score: Optional[float] = None
    warning_codes: list[Any] = []
    validation_results: dict[str, Any] = {}
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class UploadRequest(BaseModel):
    domain: str  # airline | cfl
    source_name: Optional[str] = None
    source_system_id: Optional[str] = None


class PageInfo(BaseModel):
    total: int
    page: int
    page_size: int
    pages: int


class PaginatedIngestionJobs(BaseModel):
    items: list[IngestionJobOut]
    page_info: PageInfo

