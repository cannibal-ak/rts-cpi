"""Admin endpoints for SFTP ingestion-run history (Phase 3, Step 4d).

Read-only router exposing two endpoints under
``/api/v1/admin/ingestion-runs``:

* ``GET /``           — paginated, filterable list of runs
* ``GET /{run_id}``   — full detail including the per-run
                        ingested-file rows

Reads aren't audit-logged (matches Phase A's ``/api/v1/audit/events``
read pattern).

Migration 020 declares ``ingestion_run.schedule_id`` with
``ondelete=SET NULL``, so orphan runs are possible once a schedule
is deleted. The list endpoint INNER-joins on schedule (orphans
excluded; tenant filtering would be undefined for them anyway). The
detail endpoint resolves tenant_code via a separate scalar lookup
that returns ``None`` for orphans — the schema's
``tenant_code: Optional[str]`` accommodates that.

Module is import-safe but is NOT wired into ``main.py`` until
Step 4e — landing it inert keeps the diff focused.
"""

import logging
from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.core.deps import (
    RequirePlatformAdmin,
    get_current_user,
    get_tenant_db,
)
from app.models.sftp import (
    IngestedFile,
    IngestionRun,
    IngestionSchedule,
)
from app.schemas.common import PageInfo, PaginatedResponse
from app.schemas.sftp import (
    IngestedFileRead,
    IngestionRunDetail,
    IngestionRunRead,
)


logger = logging.getLogger("uvicorn.error")


router = APIRouter(
    prefix="/api/v1/admin/ingestion-runs",
    tags=["admin / runs"],
    dependencies=[Depends(RequirePlatformAdmin())],
)


# -- helpers ----------------------------------------------------------


def _run_to_read(
    row: IngestionRun, tenant_code: Optional[str]
) -> IngestionRunRead:
    """Build IngestionRunRead. ``tenant_code`` is sourced from the
    joined IngestionSchedule by the caller (run rows don't carry
    tenant_code directly). May be ``None`` for orphan runs whose
    parent schedule has been deleted."""
    return IngestionRunRead(
        id=row.id,
        schedule_id=row.schedule_id,
        tenant_code=tenant_code,
        triggered_by=row.triggered_by,
        started_at=row.started_at,
        finished_at=row.finished_at,
        status=row.status,
        files_seen=row.files_seen,
        files_pulled=row.files_pulled,
        jobs_created=row.jobs_created,
        jobs_committed=row.jobs_committed,
        error_summary=row.error_summary,
        detail_log=row.detail_log,
    )


def _file_to_read(row: IngestedFile) -> IngestedFileRead:
    return IngestedFileRead(
        id=row.id,
        run_id=row.run_id,
        schedule_id=row.schedule_id,
        remote_filename=row.remote_filename,
        sha256=row.sha256,
        remote_size_bytes=row.remote_size_bytes,
        remote_mtime_utc=row.remote_mtime_utc,
        outcome=row.outcome,
        ingestion_job_id=row.ingestion_job_id,
        error_message=row.error_message,
        created_at=row.created_at,
    )


# -- routes -----------------------------------------------------------


@router.get(
    "/",
    response_model=PaginatedResponse[IngestionRunRead],
)
def list_runs(
    db: Session = Depends(get_tenant_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    tenant_code: Optional[str] = Query(default=None),
    schedule_id: Optional[UUID] = Query(default=None),
    status: Optional[str] = Query(default=None),
    started_after: Optional[datetime] = Query(default=None),
    started_before: Optional[datetime] = Query(default=None),
):
    """List ingestion runs with optional filters.

    INNER-joins ``ingestion_schedule`` to surface ``tenant_code``;
    orphan runs (whose schedule was deleted) are excluded — they can
    only be reached via ``GET /{run_id}``.
    """
    q = (
        db.query(IngestionRun, IngestionSchedule.tenant_code)
        .join(
            IngestionSchedule,
            IngestionRun.schedule_id == IngestionSchedule.id,
        )
    )
    if tenant_code is not None:
        q = q.filter(IngestionSchedule.tenant_code == tenant_code)
    if schedule_id is not None:
        q = q.filter(IngestionRun.schedule_id == schedule_id)
    if status is not None:
        q = q.filter(IngestionRun.status == status)
    if started_after is not None:
        q = q.filter(IngestionRun.started_at >= started_after)
    if started_before is not None:
        q = q.filter(IngestionRun.started_at < started_before)

    total = q.count()
    offset = (page - 1) * page_size
    rows = (
        q.order_by(IngestionRun.started_at.desc())
        .offset(offset)
        .limit(page_size)
        .all()
    )

    items = [_run_to_read(run, tc) for (run, tc) in rows]
    return PaginatedResponse(
        items=items,
        page_info=PageInfo(
            total=total,
            page=page,
            page_size=page_size,
            has_next=offset + page_size < total,
        ),
    )


@router.get(
    "/{run_id}",
    response_model=IngestionRunDetail,
)
def get_run(
    run_id: UUID,
    db: Session = Depends(get_tenant_db),
):
    """Return a single run with its ingested-file rows.

    Eager-loads ``ingested_files`` via ``joinedload`` to avoid an
    N+1 select. ``tenant_code`` is resolved via a separate scalar
    lookup that yields ``None`` for orphan runs (schedule deleted
    after the run completed).
    """
    row = (
        db.query(IngestionRun)
        .options(joinedload(IngestionRun.ingested_files))
        .filter(IngestionRun.id == run_id)
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="ingestion run not found")

    tenant_code: Optional[str] = None
    if row.schedule_id is not None:
        tenant_code = db.scalar(
            select(IngestionSchedule.tenant_code).where(
                IngestionSchedule.id == row.schedule_id
            )
        )
        if tenant_code is None:
            logger.info(
                "run %s has schedule_id=%s but no matching schedule "
                "row (orphan via FK SET NULL); tenant_code unresolvable",
                run_id,
                row.schedule_id,
            )

    files_sorted = sorted(row.ingested_files, key=lambda f: f.created_at)
    return IngestionRunDetail(
        id=row.id,
        schedule_id=row.schedule_id,
        tenant_code=tenant_code,
        triggered_by=row.triggered_by,
        started_at=row.started_at,
        finished_at=row.finished_at,
        status=row.status,
        files_seen=row.files_seen,
        files_pulled=row.files_pulled,
        jobs_created=row.jobs_created,
        jobs_committed=row.jobs_committed,
        error_summary=row.error_summary,
        detail_log=row.detail_log,
        ingested_files=[_file_to_read(f) for f in files_sorted],
    )
