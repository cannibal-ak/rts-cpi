"""REST router for the ingestion overhaul (Phase A).

Endpoints:
* POST   /api/v1/ingestion/upload                  multi-file upload
* GET    /api/v1/ingestion/jobs                    list with filters
* GET    /api/v1/ingestion/jobs/{id}               job detail
* POST   /api/v1/ingestion/jobs/{id}/validate      run validation
* GET    /api/v1/ingestion/jobs/{id}/preview       sample rows
* POST   /api/v1/ingestion/jobs/{id}/commit        commit (replace_existing)
* DELETE /api/v1/ingestion/jobs/{id}               cancel staged
* DELETE /api/v1/ingestion/jobs/{id}/data          delete committed data
* GET    /api/v1/ingestion/jobs/{id}/audit         audit log

All endpoints require a valid JWT (handled by ``enforce_password_change``
in main.py) and Skywave platform-admin identity (enforced inside the
``IngestionService`` for upload/validate/commit/cancel; route-level for
read-only endpoints via the ``RequirePlatformAdmin`` dependency).
"""
from __future__ import annotations

import csv
import io
import os
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from fastapi import (
    APIRouter,
    Body,
    Depends,
    File,
    HTTPException,
    Query,
    Request,
    UploadFile,
)
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import desc, exists
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import RequirePlatformAdmin, get_current_user
from app.ingestion.exceptions import (
    IngestionConflictError,
    IngestionError,
)
from app.ingestion.parsers import read_data_file
from app.ingestion.service import (
    DEFAULT_STAGING_ROOT,
    IngestionService,
)
from app.models.ingestion import IngestionAuditLog, IngestionJob
from app.models.sftp import IngestedFile


# ── Configuration (env-overridable) ───────────────────────────────

MAX_FILE_SIZE_BYTES = int(
    os.environ.get("INGESTION_MAX_FILE_SIZE_BYTES", str(50 * 1024 * 1024))
)
MAX_FILES_PER_REQUEST = int(
    os.environ.get("INGESTION_MAX_FILES_PER_REQUEST", "20")
)
PREVIEW_SAMPLE_SIZE = int(
    os.environ.get("INGESTION_PREVIEW_SAMPLE_SIZE", "10")
)


router = APIRouter(prefix="/api/v1/ingestion", tags=["ingestion"])


# ── Pydantic schemas ──────────────────────────────────────────────


class IngestionJobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    tenant_code: str
    domain: str
    filename: str
    file_hash: str
    file_size_bytes: int
    file_date: date
    status: str
    mode: str
    row_count_total: Optional[int] = None
    row_count_valid: Optional[int] = None
    row_count_rejected: Optional[int] = None
    validation_summary: Optional[dict] = None
    uploaded_by_user_id: uuid.UUID
    uploaded_at: datetime
    validated_at: Optional[datetime] = None
    committed_at: Optional[datetime] = None
    replaced_by_job_id: Optional[uuid.UUID] = None
    error_message: Optional[str] = None
    # True only for a COMMITTED job that was uploaded manually (no SFTP
    # ``ingested_file`` bridge row). Such a job's inserted fact rows can be
    # deleted from this page via ``DELETE /jobs/{id}/data``. SFTP-pulled jobs
    # are managed from the Admin → Ingestion Runs page instead. Computed by
    # the route (not an ORM column), so it defaults to False.
    deletable: bool = False


class UploadFileResult(BaseModel):
    """Result for a single file inside a multi-file upload request."""

    filename: str
    job: Optional[IngestionJobOut] = None
    duplicate: bool = False
    conflict: bool = False
    existing_job_id: Optional[uuid.UUID] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None


class UploadResponse(BaseModel):
    files: list[UploadFileResult]
    summary: dict = Field(
        default_factory=lambda: {"accepted": 0, "duplicate": 0, "conflict": 0, "rejected": 0}
    )


class PageInfo(BaseModel):
    total: int
    page: int
    page_size: int
    pages: int


class PaginatedJobs(BaseModel):
    items: list[IngestionJobOut]
    page_info: PageInfo


class CommitRequest(BaseModel):
    replace_existing: bool = False


class CommitResponse(BaseModel):
    job: IngestionJobOut
    rows_inserted: int
    replaced_job_id: Optional[uuid.UUID] = None


class DeleteDataResponse(BaseModel):
    job: IngestionJobOut
    rows_deleted: int


class ValidationResponse(BaseModel):
    job: IngestionJobOut
    row_count_total: int
    row_count_valid: int
    row_count_rejected: int
    summary: dict


class AuditEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    job_id: uuid.UUID
    actor_user_id: uuid.UUID
    action: str
    actor_ip: Optional[str] = None
    timestamp: datetime
    details: Optional[dict] = None


class AuditLogResponse(BaseModel):
    job_id: uuid.UUID
    entries: list[AuditEntryOut]


class PreviewRow(BaseModel):
    row_num: int
    data: dict


class PreviewRejection(BaseModel):
    row_num: int
    reason: str


class PreviewResponse(BaseModel):
    job_id: uuid.UUID
    sample_valid: list[PreviewRow]
    sample_rejected: list[PreviewRejection]


class ErrorResponse(BaseModel):
    error_code: str
    message: str
    details: Optional[dict] = None


# ── Helpers ────────────────────────────────────────────────────────


def _service(db: Session) -> IngestionService:
    return IngestionService(db, staging_root=DEFAULT_STAGING_ROOT)


def _http_error_for(exc: IngestionError) -> HTTPException:
    """Convert an IngestionError into a structured HTTPException."""
    details: dict = {}
    if isinstance(exc, IngestionConflictError) and exc.existing_job_id:
        details["existing_job_id"] = exc.existing_job_id
    return HTTPException(
        status_code=exc.http_status,
        detail={
            "error_code": exc.error_code,
            "message": str(exc),
            "details": details or None,
        },
    )


def _sftp_bridged_ids(
    db: Session, job_ids: list[uuid.UUID]
) -> set[uuid.UUID]:
    """Return the subset of ``job_ids`` that have an SFTP ``ingested_file``
    bridge row (i.e. were pulled via SFTP, not uploaded manually)."""
    if not job_ids:
        return set()
    rows = (
        db.query(IngestedFile.ingestion_job_id)
        .filter(IngestedFile.ingestion_job_id.in_(job_ids))
        .distinct()
        .all()
    )
    return {r[0] for r in rows if r[0] is not None}


def _job_out(job: IngestionJob, *, deletable: bool = False) -> IngestionJobOut:
    """Serialise a job, stamping the computed ``deletable`` flag."""
    out = IngestionJobOut.model_validate(job)
    out.deletable = deletable
    return out


def _jobs_out(db: Session, jobs: list[IngestionJob]) -> list[IngestionJobOut]:
    """Serialise a list of jobs, computing ``deletable`` for each.

    A job is deletable when it is COMMITTED and has no SFTP bridge row —
    resolved with a single bulk query over the COMMITTED ids.
    """
    committed_ids = [j.id for j in jobs if j.status == "COMMITTED"]
    bridged = _sftp_bridged_ids(db, committed_ids)
    return [
        _job_out(
            j,
            deletable=(j.status == "COMMITTED" and j.id not in bridged),
        )
        for j in jobs
    ]


def _client_ip(request: Request) -> Optional[str]:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client and request.client.host:
        return request.client.host
    return None


# ── Endpoints ──────────────────────────────────────────────────────


@router.post(
    "/upload",
    response_model=UploadResponse,
    responses={
        400: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        413: {"model": ErrorResponse},
    },
    dependencies=[Depends(RequirePlatformAdmin())],
    summary="Stage one or more files for ingestion",
)
async def upload_files(
    request: Request,
    files: list[UploadFile] = File(...),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UploadResponse:
    """Accept up to 20 files per request, each up to 50 MB. Each file is
    hashed, parsed for metadata, and staged. Existing committed hashes are
    flagged as duplicate (no re-stage); same-date conflicts are surfaced
    with the existing job id for the client to decide on replace."""
    if not files:
        raise HTTPException(
            status_code=400,
            detail={
                "error_code": "ingestion_no_files",
                "message": "No files provided in upload request",
            },
        )
    if len(files) > MAX_FILES_PER_REQUEST:
        raise HTTPException(
            status_code=400,
            detail={
                "error_code": "ingestion_too_many_files",
                "message": (
                    f"Too many files: {len(files)} > "
                    f"max {MAX_FILES_PER_REQUEST}"
                ),
            },
        )

    svc = _service(db)
    actor_ip = _client_ip(request)
    results: list[UploadFileResult] = []
    summary = {"accepted": 0, "duplicate": 0, "conflict": 0, "rejected": 0}

    for upload in files:
        try:
            content = await upload.read()
            if len(content) > MAX_FILE_SIZE_BYTES:
                results.append(
                    UploadFileResult(
                        filename=upload.filename or "<unnamed>",
                        error_code="ingestion_file_too_large",
                        error_message=(
                            f"File exceeds {MAX_FILE_SIZE_BYTES} bytes "
                            f"(actual: {len(content)})"
                        ),
                    )
                )
                summary["rejected"] += 1
                continue

            result = svc.upload_file(
                content,
                upload.filename or "",
                current_user,
                actor_ip=actor_ip,
            )
            results.append(
                UploadFileResult(
                    filename=upload.filename or "<unnamed>",
                    job=IngestionJobOut.model_validate(result.job),
                    duplicate=result.duplicate,
                    conflict=result.conflict,
                    existing_job_id=result.existing_job_id,
                )
            )
            if result.duplicate:
                summary["duplicate"] += 1
            elif result.conflict:
                summary["conflict"] += 1
            else:
                summary["accepted"] += 1

        except IngestionError as exc:
            results.append(
                UploadFileResult(
                    filename=upload.filename or "<unnamed>",
                    error_code=exc.error_code,
                    error_message=str(exc),
                )
            )
            summary["rejected"] += 1

    return UploadResponse(files=results, summary=summary)


@router.get(
    "/jobs",
    response_model=PaginatedJobs,
    dependencies=[Depends(RequirePlatformAdmin())],
    summary="List ingestion jobs (paginated, filterable)",
)
def list_jobs(
    db: Session = Depends(get_db),
    status: Optional[str] = Query(None),
    tenant_code: Optional[str] = Query(None),
    domain: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> PaginatedJobs:
    q = db.query(IngestionJob)
    # Ingestion Jobs tracks MANUAL uploads only; SFTP-pulled files are
    # shown in the Ingestion Runs view. A job is SFTP-originated iff an
    # ingested_file bridge row references it, so exclude those here.
    q = q.filter(
        ~exists().where(IngestedFile.ingestion_job_id == IngestionJob.id)
    )
    if status:
        q = q.filter(IngestionJob.status == status.upper())
    if tenant_code:
        q = q.filter(IngestionJob.tenant_code == tenant_code.upper())
    if domain:
        q = q.filter(IngestionJob.domain == domain.upper())

    total = q.count()
    pages = (total + page_size - 1) // page_size if total else 1
    rows = (
        q.order_by(desc(IngestionJob.uploaded_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return PaginatedJobs(
        items=_jobs_out(db, rows),
        page_info=PageInfo(
            total=total, page=page, page_size=page_size, pages=pages
        ),
    )


@router.get(
    "/jobs/{job_id}",
    response_model=IngestionJobOut,
    responses={404: {"model": ErrorResponse}},
    dependencies=[Depends(RequirePlatformAdmin())],
    summary="Fetch one ingestion job",
)
def get_job(job_id: uuid.UUID, db: Session = Depends(get_db)) -> IngestionJobOut:
    job = db.query(IngestionJob).filter(IngestionJob.id == job_id).first()
    if not job:
        raise HTTPException(
            status_code=404,
            detail={
                "error_code": "ingestion_not_found",
                "message": f"No ingestion job with id {job_id}",
            },
        )
    return _jobs_out(db, [job])[0]


@router.post(
    "/jobs/{job_id}/validate",
    response_model=ValidationResponse,
    responses={
        400: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
    },
    dependencies=[Depends(RequirePlatformAdmin())],
    summary="Run validation on a staged job",
)
def validate_job(
    job_id: uuid.UUID,
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ValidationResponse:
    svc = _service(db)
    try:
        result = svc.validate_job(
            job_id, current_user, actor_ip=_client_ip(request)
        )
    except IngestionError as exc:
        raise _http_error_for(exc)
    return ValidationResponse(
        job=IngestionJobOut.model_validate(result.job),
        row_count_total=result.row_count_total,
        row_count_valid=result.row_count_valid,
        row_count_rejected=result.row_count_rejected,
        summary=result.summary,
    )


@router.get(
    "/jobs/{job_id}/preview",
    response_model=PreviewResponse,
    responses={404: {"model": ErrorResponse}},
    dependencies=[Depends(RequirePlatformAdmin())],
    summary="Preview a sample of valid + rejected rows",
)
def preview_job(
    job_id: uuid.UUID, db: Session = Depends(get_db)
) -> PreviewResponse:
    job = db.query(IngestionJob).filter(IngestionJob.id == job_id).first()
    if not job:
        raise HTTPException(
            status_code=404,
            detail={
                "error_code": "ingestion_not_found",
                "message": f"No ingestion job with id {job_id}",
            },
        )

    staged_path = (
        Path(DEFAULT_STAGING_ROOT) / str(job.id) / job.filename
    )
    sample_valid: list[PreviewRow] = []
    sample_rejected: list[PreviewRejection] = []

    if staged_path.exists():
        for row_num, row in enumerate(read_data_file(str(staged_path)), start=1):
            if len(sample_valid) >= PREVIEW_SAMPLE_SIZE:
                break
            sample_valid.append(PreviewRow(row_num=row_num, data=row))

    summary = job.validation_summary or {}
    for rej in (summary.get("rejection_reasons_sample") or [])[
        :PREVIEW_SAMPLE_SIZE
    ]:
        try:
            rn = int(rej.get("row", 0))
        except (TypeError, ValueError):
            rn = 0
        sample_rejected.append(
            PreviewRejection(
                row_num=rn, reason=str(rej.get("reason", ""))
            )
        )

    return PreviewResponse(
        job_id=job.id,
        sample_valid=sample_valid,
        sample_rejected=sample_rejected,
    )


@router.post(
    "/jobs/{job_id}/commit",
    response_model=CommitResponse,
    responses={
        400: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
    },
    dependencies=[Depends(RequirePlatformAdmin())],
    summary="Commit a validated job (load rows into fact tables)",
)
def commit_job(
    job_id: uuid.UUID,
    request: Request,
    body: CommitRequest = Body(default_factory=CommitRequest),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CommitResponse:
    svc = _service(db)
    try:
        result = svc.commit_job(
            job_id,
            current_user,
            replace_existing=body.replace_existing,
            actor_ip=_client_ip(request),
        )
    except IngestionError as exc:
        raise _http_error_for(exc)
    return CommitResponse(
        job=IngestionJobOut.model_validate(result.job),
        rows_inserted=result.rows_inserted,
        replaced_job_id=result.replaced_job_id,
    )


@router.delete(
    "/jobs/{job_id}",
    response_model=IngestionJobOut,
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
    },
    dependencies=[Depends(RequirePlatformAdmin())],
    summary="Cancel a staged or validated job",
)
def cancel_job(
    job_id: uuid.UUID,
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> IngestionJobOut:
    svc = _service(db)
    try:
        job = svc.cancel_job(
            job_id, current_user, actor_ip=_client_ip(request)
        )
    except IngestionError as exc:
        raise _http_error_for(exc)
    return IngestionJobOut.model_validate(job)


@router.delete(
    "/jobs/{job_id}/data",
    response_model=DeleteDataResponse,
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
    },
    dependencies=[Depends(RequirePlatformAdmin())],
    summary="Delete a manually-uploaded committed job's inserted fact rows",
)
def delete_job_data(
    job_id: uuid.UUID,
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DeleteDataResponse:
    """Hard-delete the fact rows a COMMITTED, manually-uploaded file loaded.

    Only jobs uploaded through this page are deletable here. A job that was
    pulled via SFTP (has an ``ingested_file`` bridge row) is managed from the
    Admin → Ingestion Runs page instead, and is rejected with 409. The job
    row itself is kept as ``DELETED`` history with an audit entry.
    """
    # Manual-only guard: reject SFTP-pulled jobs before touching any data.
    if _sftp_bridged_ids(db, [job_id]):
        raise HTTPException(
            status_code=409,
            detail={
                "error_code": "ingestion_sftp_managed",
                "message": (
                    "This file was pulled via SFTP. Delete its data from "
                    "the Admin → Ingestion Runs page."
                ),
                "details": None,
            },
        )

    svc = _service(db)
    try:
        result = svc.delete_committed_file(
            job_id, current_user, actor_ip=_client_ip(request)
        )
    except IngestionError as exc:
        raise _http_error_for(exc)

    job = db.query(IngestionJob).filter(IngestionJob.id == job_id).first()
    return DeleteDataResponse(
        job=_job_out(job, deletable=False),
        rows_deleted=int(result.get("rows_deleted", 0)),
    )


@router.get(
    "/jobs/{job_id}/audit",
    response_model=AuditLogResponse,
    responses={404: {"model": ErrorResponse}},
    dependencies=[Depends(RequirePlatformAdmin())],
    summary="Fetch the full audit trail for a job",
)
def get_audit_log(
    job_id: uuid.UUID, db: Session = Depends(get_db)
) -> AuditLogResponse:
    job = db.query(IngestionJob).filter(IngestionJob.id == job_id).first()
    if not job:
        raise HTTPException(
            status_code=404,
            detail={
                "error_code": "ingestion_not_found",
                "message": f"No ingestion job with id {job_id}",
            },
        )
    entries = (
        db.query(IngestionAuditLog)
        .filter(IngestionAuditLog.job_id == job_id)
        .order_by(desc(IngestionAuditLog.timestamp))
        .all()
    )
    return AuditLogResponse(
        job_id=job_id,
        entries=[AuditEntryOut.model_validate(e) for e in entries],
    )
