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

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session, joinedload

from app.core.database import get_db
from app.core.deps import (
    RequirePlatformAdmin,
    get_current_user,
    get_tenant_db,
)
from app.ingestion.exceptions import IngestionError
from app.ingestion.service import IngestionService
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
from app.services import audit
from app.tasks.sftp_pull import reingest_ingested_file


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


@router.post(
    "/{run_id}/cancel",
    response_model=IngestionRunRead,
)
def cancel_run(
    run_id: UUID,
    db: Session = Depends(get_tenant_db),
    current_user: dict = Depends(get_current_user),
):
    """Signal cooperative cancellation of an in-progress run.

    Atomically transitions ``status='RUNNING'`` to
    ``status='CANCELLING'`` via a conditional UPDATE — only currently
    running runs are cancellable; the request 400s for any other
    state (already-terminal SUCCESS/PARTIAL/FAILED/CANCELLED, or
    already-CANCELLING). The worker observes CANCELLING at the next
    file boundary and writes ``status='CANCELLED'`` along with the
    counters of work it had completed up to that point. Already-
    committed files are NOT rolled back.

    Returns the row in its post-update state (status=CANCELLING).
    Clients should poll the GET detail endpoint — or rely on the
    runs-page auto-refresh — to observe the terminal CANCELLED
    transition.
    """
    row = db.get(IngestionRun, run_id)
    if row is None:
        raise HTTPException(status_code=404, detail="ingestion run not found")

    # Conditional UPDATE — atomic. ``rowcount`` is 1 iff status was
    # RUNNING; otherwise 0 and the run is in a non-cancellable state.
    result = db.execute(
        text(
            "UPDATE ingestion_run SET status = 'CANCELLING' "
            "WHERE id = :id AND status = 'RUNNING'"
        ),
        {"id": str(run_id)},
    )
    if result.rowcount == 0:
        # Re-read to report the actual current status to the caller.
        current = db.execute(
            text("SELECT status FROM ingestion_run WHERE id = :id"),
            {"id": str(run_id)},
        ).scalar()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"run is not cancellable: current status is {current!r}; "
                "only RUNNING runs can be cancelled"
            ),
        )

    audit.record(
        db,
        tenant_id=UUID(current_user["tenant_id"]),
        actor=current_user["sub"],
        action="CANCEL",
        target_type="ingestion_run",
        target_id=str(run_id),
    )

    # Resolve tenant_code while still in the tenant-context tx (RLS
    # would filter post-commit reads — same pattern as the schedules
    # router). The raw UPDATE bypassed the ORM, so ``row.status`` is
    # still 'RUNNING'; build the response with the known new value.
    tenant_code: Optional[str] = None
    if row.schedule_id is not None:
        tenant_code = db.scalar(
            select(IngestionSchedule.tenant_code).where(
                IngestionSchedule.id == row.schedule_id
            )
        )
    response = IngestionRunRead(
        id=row.id,
        schedule_id=row.schedule_id,
        tenant_code=tenant_code,
        triggered_by=row.triggered_by,
        started_at=row.started_at,
        finished_at=row.finished_at,
        status="CANCELLING",
        files_seen=row.files_seen,
        files_pulled=row.files_pulled,
        jobs_created=row.jobs_created,
        jobs_committed=row.jobs_committed,
        error_summary=row.error_summary,
        detail_log=row.detail_log,
    )
    db.commit()
    return response


# -- per-file data operations (delete / re-ingest) --------------------
#
# These act on a single ingested file (one tenant+domain+day). Delete
# uses the OWNER db session (``get_db``) — NOT ``get_tenant_db`` — because
# the fact-row DELETE must cross RLS to remove another tenant's day
# (rts-admin deleting jy/pw/fjl data). Re-ingest hands off to a celery
# task that re-pulls the file from SFTP and re-commits with replace
# forced.


def _http_error_from_ingestion(exc: IngestionError) -> HTTPException:
    """Map an IngestionError to a structured HTTPException, mirroring the
    v1 ingestion router's error shape."""
    return HTTPException(
        status_code=exc.http_status,
        detail={
            "error_code": exc.error_code,
            "message": str(exc),
            "details": None,
        },
    )


@router.delete("/files/{ingested_file_id}/data")
def delete_file_data(
    ingested_file_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Delete the fact rows a single ingested file loaded, and free it
    for re-pull.

    Resolves the file's committed ``ingestion_job_id`` and hands off to
    ``IngestionService.delete_committed_file``. Runs on the owner DB
    session so the cross-tenant DELETE is not filtered by RLS. Only files
    that produced a COMMITTED job can be deleted (409 otherwise).
    """
    ing_file = db.get(IngestedFile, ingested_file_id)
    if ing_file is None:
        raise HTTPException(status_code=404, detail="ingested file not found")
    # Capture the job id while ing_file is still live. delete_committed_file
    # commits and DELETEs this ingested_file row, which expires the ORM
    # object — any later ing_file.* read would fire a reload of a now-gone
    # row and raise. Use this local for the rest of the handler.
    job_id = ing_file.ingestion_job_id
    if job_id is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "this file did not commit any data (no ingestion job); "
                "nothing to delete"
            ),
        )

    actor_ip = request.client.host if request.client else None
    try:
        result = IngestionService(db).delete_committed_file(
            job_id,
            user_payload=current_user,
            actor_ip=actor_ip,
        )
    except IngestionError as exc:
        raise _http_error_from_ingestion(exc)

    audit.record(
        db,
        tenant_id=UUID(current_user["tenant_id"]),
        actor=current_user["sub"],
        action="DELETE",
        target_type="ingestion_data",
        target_id=str(job_id),
    )
    db.commit()
    return result


@router.post(
    "/files/{ingested_file_id}/reingest",
    status_code=status.HTTP_202_ACCEPTED,
)
def reingest_file(
    ingested_file_id: UUID,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Queue a single-file re-pull from SFTP, replacing that day's data.

    The worker re-downloads the file and re-commits with replace forced,
    so an updated file (new content) overwrites the committed day. The
    run materialises asynchronously — poll the runs list to observe it.
    """
    ing_file = db.get(IngestedFile, ingested_file_id)
    if ing_file is None:
        raise HTTPException(status_code=404, detail="ingested file not found")
    if ing_file.schedule_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "source schedule was deleted; cannot re-pull this file "
                "from SFTP"
            ),
        )

    result = reingest_ingested_file.delay(str(ingested_file_id))

    audit.record(
        db,
        tenant_id=UUID(current_user["tenant_id"]),
        actor=current_user["sub"],
        action="REINGEST",
        target_type="ingested_file",
        target_id=str(ingested_file_id),
    )
    db.commit()
    return {"task_id": result.id, "run_id": None}
