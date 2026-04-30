"""Typed exceptions raised by the ingestion service.

Routers map these to HTTP status codes (see app/api/v1/ingestion.py in
Phase 5). Keeping them as a separate module lets tests assert on exception
types without importing FastAPI.
"""
from __future__ import annotations


class IngestionError(Exception):
    """Base for all ingestion service errors."""

    http_status: int = 500
    error_code: str = "ingestion_error"


class IngestionAuthError(IngestionError):
    """Caller is not authorised to perform the requested action."""

    http_status = 403
    error_code = "ingestion_forbidden"


class IngestionFilenameError(IngestionError):
    """Filename did not match a known pattern, or the date is invalid."""

    http_status = 400
    error_code = "ingestion_filename_invalid"


class IngestionConflictError(IngestionError):
    """Same (tenant_code, domain, file_date) already committed with a
    different file hash. Caller can retry with replace_existing=True."""

    http_status = 409
    error_code = "ingestion_conflict"

    def __init__(self, message: str, existing_job_id: str | None = None):
        super().__init__(message)
        self.existing_job_id = existing_job_id


class IngestionNotFoundError(IngestionError):
    """No ingestion_jobs row with the given id."""

    http_status = 404
    error_code = "ingestion_not_found"


class IngestionStateError(IngestionError):
    """Job is in a status that does not permit the requested transition
    (e.g. trying to commit a STAGED job that has not been validated)."""

    http_status = 409
    error_code = "ingestion_invalid_state"


class IngestionValidationError(IngestionError):
    """Validation pass produced zero valid rows or otherwise failed."""

    http_status = 400
    error_code = "ingestion_validation_failed"


class IngestionConfigError(IngestionError):
    """Unexpected misconfiguration (unknown tenant slug, missing tenant
    row, etc.). Indicates a bug or data drift, not a user error."""

    http_status = 500
    error_code = "ingestion_config_error"
