"""Pydantic schemas for the SFTP-driven ingestion REST API (Phase 3).

These back ``/admin/sftp-connections``, ``/admin/ingestion-schedules``,
and ``/admin/ingestion-runs``. Field names align with the SQL columns
from migration 020 (``name``, ``remote_base_path``, ``filename_regex``,
``domain``, ``replace_existing``, ...) so the routers in
``app/routers/admin_*.py`` can map straight through.

Plaintext credentials (``password``, ``private_key_pem``) are accepted on
Create / Update only; they are encrypted at the router boundary via
:mod:`app.core.crypto` and never appear on any ``*Read`` schema, which
exposes ``masked_credential`` instead.

Both the cron parser and the YAML-pattern lookup are imported lazily
inside their validator functions so this module stays importable in
environments that have not yet bootstrapped Celery or the
ingestion-pattern cache (OpenAPI generation, isolated unit tests).
"""

from datetime import datetime
from typing import Any, List, Literal, Optional, Set, Tuple
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


# Domain casing convention (locked):
# Phase A's filename_parser emits domain values uppercased (AIRLINE,
# VELOCITY, CFL — derived via ``.upper()`` in
# ``app/ingestion/filename_parser.py`` from the YAML source). These
# schemas accept and return uppercase values verbatim; there is no
# API-side lowercase translation. Clients (including the Phase 4
# admin UI) must submit uppercase domain strings matching Phase A's
# YAML source of truth.


def _known_pattern_pairs() -> List[Tuple[str, str]]:
    """Return [(domain, filename_regex), ...] from the Phase A YAML.

    Imported lazily — Phase 3 hard rule forbids modifying Phase A code,
    so we read the cached rules directly via the underscore-prefixed
    accessor.
    """
    from app.ingestion.filename_parser import _patterns

    return [(rule.domain, rule.regex.pattern) for rule in _patterns()]


def _known_domains() -> Set[str]:
    """Return the set of domains declared by the Phase A pattern YAML."""
    return {domain for domain, _ in _known_pattern_pairs()}


def _known_regexes() -> Set[str]:
    """Return the set of filename regexes declared by the Phase A YAML."""
    return {regex for _, regex in _known_pattern_pairs()}


def _validate_cron(value: str) -> str:
    """Validate a 5-field cron expression via celery's parser.

    Imported inside the function so importing this schema module never
    requires a celery-configured runtime.
    """
    from celery.schedules import crontab

    parts = value.split()
    if len(parts) != 5:
        raise ValueError(
            "cron_expression must have 5 fields "
            "(minute hour day-of-month month day-of-week); "
            f"got {len(parts)} fields"
        )
    minute, hour, dom, month, dow = parts
    try:
        crontab(
            minute=minute,
            hour=hour,
            day_of_month=dom,
            month_of_year=month,
            day_of_week=dow,
        )
    except Exception as exc:
        raise ValueError(f"invalid cron_expression: {exc}") from exc
    return value


# -- SFTP connection ---------------------------------------------------


class SftpConnectionCreate(BaseModel):
    tenant_code: str = Field(..., min_length=1, max_length=16)
    name: str = Field(..., min_length=1, max_length=64)
    host: str = Field(..., min_length=1)
    port: int = Field(default=22, ge=1, le=65535)
    username: str = Field(..., min_length=1)
    auth_method: Literal["password", "private_key"]
    password: Optional[str] = None
    private_key_pem: Optional[str] = None
    remote_base_path: str = Field(..., min_length=1)
    is_active: bool = True

    @model_validator(mode="after")
    def _check_credentials(self) -> "SftpConnectionCreate":
        has_pwd = self.password is not None
        has_pk = self.private_key_pem is not None
        if has_pwd == has_pk:
            raise ValueError(
                "exactly one of password / private_key_pem must be set"
            )
        if self.auth_method == "password" and not has_pwd:
            raise ValueError(
                "auth_method='password' requires password to be set"
            )
        if self.auth_method == "private_key" and not has_pk:
            raise ValueError(
                "auth_method='private_key' requires private_key_pem"
            )
        return self


class SftpConnectionUpdate(BaseModel):
    tenant_code: Optional[str] = Field(
        default=None, min_length=1, max_length=16
    )
    name: Optional[str] = Field(default=None, min_length=1, max_length=64)
    host: Optional[str] = Field(default=None, min_length=1)
    port: Optional[int] = Field(default=None, ge=1, le=65535)
    username: Optional[str] = Field(default=None, min_length=1)
    auth_method: Optional[Literal["password", "private_key"]] = None
    password: Optional[str] = None
    private_key_pem: Optional[str] = None
    remote_base_path: Optional[str] = Field(default=None, min_length=1)
    is_active: Optional[bool] = None

    @model_validator(mode="after")
    def _check_credentials(self) -> "SftpConnectionUpdate":
        has_pwd = self.password is not None
        has_pk = self.private_key_pem is not None
        if has_pwd and has_pk:
            raise ValueError(
                "at most one of password / private_key_pem may be set on update"
            )
        if self.auth_method == "password" and has_pk and not has_pwd:
            raise ValueError(
                "auth_method='password' is incompatible with private_key_pem"
            )
        if self.auth_method == "private_key" and has_pwd and not has_pk:
            raise ValueError(
                "auth_method='private_key' is incompatible with password"
            )
        return self


class SftpConnectionRead(BaseModel):
    id: UUID
    tenant_code: str
    name: str
    host: str
    port: int
    username: str
    auth_method: Literal["password", "private_key"]
    remote_base_path: str
    host_key_fingerprint: Optional[str] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime
    masked_credential: str

    model_config = ConfigDict(from_attributes=True)


# -- ingestion schedule ------------------------------------------------


class IngestionScheduleCreate(BaseModel):
    tenant_code: str = Field(..., min_length=1, max_length=16)
    sftp_connection_id: UUID
    cron_expression: str = Field(..., min_length=1, max_length=64)
    timezone: str = "UTC"
    is_enabled: bool = True
    domain: str = Field(..., min_length=1, max_length=16)
    filename_regex: str = Field(..., min_length=1)
    replace_existing: bool = False

    @field_validator("cron_expression")
    @classmethod
    def _check_cron(cls, value: str) -> str:
        return _validate_cron(value)

    @field_validator("domain")
    @classmethod
    def _domain_known(cls, value: str) -> str:
        known = _known_domains()
        if value not in known:
            raise ValueError(
                "domain must be one of the YAML-driven known domains "
                f"(got '{value}'; known: {sorted(known)})"
            )
        return value

    @field_validator("filename_regex")
    @classmethod
    def _regex_known(cls, value: str) -> str:
        known = _known_regexes()
        if value not in known:
            raise ValueError(
                "filename_regex must be one of the YAML-driven known patterns "
                f"(got '{value}')"
            )
        return value

    @model_validator(mode="after")
    def _check_pair(self) -> "IngestionScheduleCreate":
        pairs = _known_pattern_pairs()
        if (self.domain, self.filename_regex) not in pairs:
            raise ValueError(
                "(domain, filename_regex) pair not declared in Phase A YAML "
                f"(got ('{self.domain}', '{self.filename_regex}'))"
            )
        return self


class IngestionScheduleUpdate(BaseModel):
    tenant_code: Optional[str] = Field(
        default=None, min_length=1, max_length=16
    )
    sftp_connection_id: Optional[UUID] = None
    cron_expression: Optional[str] = Field(
        default=None, min_length=1, max_length=64
    )
    timezone: Optional[str] = None
    is_enabled: Optional[bool] = None
    domain: Optional[str] = Field(default=None, min_length=1, max_length=16)
    filename_regex: Optional[str] = Field(default=None, min_length=1)
    replace_existing: Optional[bool] = None

    @field_validator("cron_expression")
    @classmethod
    def _check_cron(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        return _validate_cron(value)

    @field_validator("domain")
    @classmethod
    def _domain_known(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        known = _known_domains()
        if value not in known:
            raise ValueError(
                "domain must be one of the YAML-driven known domains "
                f"(got '{value}'; known: {sorted(known)})"
            )
        return value

    @field_validator("filename_regex")
    @classmethod
    def _regex_known(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        known = _known_regexes()
        if value not in known:
            raise ValueError(
                "filename_regex must be one of the YAML-driven known patterns "
                f"(got '{value}')"
            )
        return value

    @model_validator(mode="after")
    def _check_pair(self) -> "IngestionScheduleUpdate":
        if self.domain is not None and self.filename_regex is None:
            raise ValueError(
                "filename_regex must be supplied alongside domain on update"
            )
        if self.filename_regex is not None and self.domain is None:
            raise ValueError(
                "domain must be supplied alongside filename_regex on update"
            )
        if self.domain is not None and self.filename_regex is not None:
            pairs = _known_pattern_pairs()
            if (self.domain, self.filename_regex) not in pairs:
                raise ValueError(
                    "(domain, filename_regex) pair not declared in Phase A "
                    f"YAML (got ('{self.domain}', '{self.filename_regex}'))"
                )
        return self


class IngestionScheduleRead(BaseModel):
    id: UUID
    tenant_code: str
    sftp_connection_id: UUID
    cron_expression: str
    timezone: str
    is_enabled: bool
    domain: str
    filename_regex: str
    replace_existing: bool
    last_run_at: Optional[datetime] = None
    next_run_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    redbeat_registered: bool = False

    model_config = ConfigDict(from_attributes=True)


# -- ingestion run / ingested file -------------------------------------


class IngestedFileRead(BaseModel):
    id: UUID
    run_id: UUID
    schedule_id: Optional[UUID] = None
    remote_filename: str
    sha256: str
    remote_size_bytes: int
    remote_mtime_utc: Optional[datetime] = None
    outcome: str
    ingestion_job_id: Optional[UUID] = None
    error_message: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class IngestionRunRead(BaseModel):
    id: UUID
    schedule_id: Optional[UUID] = None
    tenant_code: Optional[str] = None
    triggered_by: Optional[str] = None
    started_at: datetime
    finished_at: Optional[datetime] = None
    status: str
    files_seen: int
    files_pulled: int
    jobs_created: int
    jobs_committed: int
    error_summary: Optional[str] = None
    # detail_log is a free-form JSONB observability field. Phase 2's
    # _finalize_run writes a list[dict] of per-file outcomes; future
    # workers may write arbitrary shapes (dicts of structured
    # diagnostics, nested lists, etc.). Typed as Optional[Any] so
    # the schema reflects this — clients should treat the value as
    # opaque structured JSON and inspect keys defensively.
    detail_log: Optional[Any] = None

    model_config = ConfigDict(from_attributes=True)


class IngestionRunDetail(IngestionRunRead):
    ingested_files: List[IngestedFileRead] = []
