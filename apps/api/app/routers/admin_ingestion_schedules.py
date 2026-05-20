"""Admin endpoints for SFTP-driven ingestion schedules (Phase 3, Step 4c).

All routes:
  - mounted under ``/api/v1/admin/ingestion-schedules``
  - guarded by :class:`RequirePlatformAdmin` at the router level
    (Skywave tenant + ``TENANT_ADMIN`` role)
  - audit-logged via :func:`app.services.audit.record` to the
    ``audit_event`` table

Transactional contract with redbeat:
  Postgres is the source of truth; redbeat caches the cron entries
  the worker reads. On every state-changing route the DB write and
  the redbeat call are sequenced so an early redbeat failure rolls
  back the SQL change; a late SQL failure leaves a redbeat key that
  the next ``reconcile_all`` (FastAPI lifespan) sweeps. This module
  never tries to roll back redbeat after a successful save — that
  inversion is reserved for the lifespan reconcile.

This module is import-safe but is NOT wired into ``main.py`` until
Step 4e — landing it inert keeps the diff focused.
"""

import logging
from typing import Optional
from uuid import UUID

from fastapi import (
    APIRouter,
    Body,
    Depends,
    HTTPException,
    Query,
    Response,
    status,
)
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.deps import (
    RequirePlatformAdmin,
    get_current_user,
    get_tenant_db,
)
from app.models.sftp import IngestionSchedule, SftpConnection
from app.schemas.common import PageInfo, PaginatedResponse
from app.schemas.sftp import (
    IngestionScheduleCreate,
    IngestionScheduleRead,
    IngestionScheduleUpdate,
    RunNowRequest,
)
from app.services import audit, redbeat_sync
from app.services.redbeat_sync import RedbeatSyncError
from app.tasks.sftp_pull import sftp_pull_for_schedule


logger = logging.getLogger("uvicorn.error")


router = APIRouter(
    prefix="/api/v1/admin/ingestion-schedules",
    tags=["admin / schedules"],
    dependencies=[Depends(RequirePlatformAdmin())],
)


# -- helpers ----------------------------------------------------------


def _to_read(row: IngestionSchedule) -> IngestionScheduleRead:
    """Build an ``IngestionScheduleRead`` with ``redbeat_registered``
    computed live against the running redbeat store.

    ``is_registered`` is already best-effort + logging-internally;
    the defensive try/except here only catches truly-unexpected
    surface (e.g. import failure) and falls through to ``False`` so
    a list endpoint never 500s on a single bad row.
    """
    try:
        rb = redbeat_sync.is_registered(row.id)
    except Exception:
        rb = False
    return IngestionScheduleRead(
        id=row.id,
        tenant_code=row.tenant_code,
        sftp_connection_id=row.sftp_connection_id,
        cron_expression=row.cron_expression,
        timezone=row.timezone,
        is_enabled=row.is_enabled,
        domain=row.domain,
        filename_regex=row.filename_regex,
        replace_existing=row.replace_existing,
        last_run_at=row.last_run_at,
        next_run_at=row.next_run_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
        redbeat_registered=rb,
    )


# -- routes -----------------------------------------------------------


@router.post(
    "/",
    response_model=IngestionScheduleRead,
    status_code=status.HTTP_201_CREATED,
)
def create_schedule(
    body: IngestionScheduleCreate,
    db: Session = Depends(get_tenant_db),
    current_user: dict = Depends(get_current_user),
):
    conn = db.get(SftpConnection, body.sftp_connection_id)
    if conn is None:
        raise HTTPException(
            status_code=404,
            detail=f"sftp_connection {body.sftp_connection_id} not found",
        )

    row = IngestionSchedule(
        tenant_code=body.tenant_code,
        sftp_connection_id=body.sftp_connection_id,
        cron_expression=body.cron_expression,
        timezone=body.timezone,
        is_enabled=body.is_enabled,
        domain=body.domain,
        filename_regex=body.filename_regex,
        replace_existing=body.replace_existing,
        created_by_user_id=UUID(current_user["sub"]),
    )
    db.add(row)
    db.flush()

    if row.is_enabled:
        try:
            redbeat_sync.register(row)
        except RedbeatSyncError as e:
            db.rollback()
            raise HTTPException(
                status_code=502,
                detail=(
                    "Schedule created in DB but redbeat registration "
                    f"failed: {e}"
                ),
            )

    audit.record(
        db,
        tenant_id=UUID(current_user["tenant_id"]),
        actor=current_user["sub"],
        action="CREATE",
        target_type="ingestion_schedule",
        target_id=str(row.id),
    )
    # Refresh BEFORE commit. set_tenant_context()'s `SET LOCAL
    # app.current_tenant` is transaction-scoped and is reset by the
    # commit; refreshing afterwards would run in a fresh transaction
    # with no tenant context, and the RLS policy on ingestion_schedule
    # would filter the row out (raising InvalidRequestError).
    db.refresh(row)
    # Capture the response BEFORE commit. SQLAlchemy's
    # expire_on_commit=True (default) marks all attrs expired on
    # commit; accessing them post-commit triggers a lazy reload
    # in a fresh transaction with no tenant context, which RLS
    # filters out (ObjectDeletedError).
    response = _to_read(row)
    db.commit()
    return response


@router.get(
    "/",
    response_model=PaginatedResponse[IngestionScheduleRead],
)
def list_schedules(
    db: Session = Depends(get_tenant_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    tenant_code: Optional[str] = Query(default=None),
    is_enabled: Optional[bool] = Query(default=None),
    sftp_connection_id: Optional[UUID] = Query(default=None),
):
    q = select(IngestionSchedule)
    if tenant_code is not None:
        q = q.where(IngestionSchedule.tenant_code == tenant_code)
    if is_enabled is not None:
        q = q.where(IngestionSchedule.is_enabled.is_(is_enabled))
    if sftp_connection_id is not None:
        q = q.where(IngestionSchedule.sftp_connection_id == sftp_connection_id)

    total = db.scalar(select(func.count()).select_from(q.subquery()))
    offset = (page - 1) * page_size
    q = q.order_by(IngestionSchedule.created_at.desc()).offset(offset).limit(page_size)
    rows = db.scalars(q).all()

    return PaginatedResponse(
        items=[_to_read(r) for r in rows],
        page_info=PageInfo(
            total=total,
            page=page,
            page_size=page_size,
            has_next=offset + page_size < total,
        ),
    )


@router.get(
    "/{schedule_id}",
    response_model=IngestionScheduleRead,
)
def get_schedule(
    schedule_id: UUID,
    db: Session = Depends(get_tenant_db),
):
    row = db.get(IngestionSchedule, schedule_id)
    if row is None:
        raise HTTPException(status_code=404, detail="schedule not found")
    return _to_read(row)


@router.put(
    "/{schedule_id}",
    response_model=IngestionScheduleRead,
)
def update_schedule(
    schedule_id: UUID,
    body: IngestionScheduleUpdate,
    db: Session = Depends(get_tenant_db),
    current_user: dict = Depends(get_current_user),
):
    """Update an ingestion schedule with transactional redbeat sync.

    is_enabled transitions and any change to the schedule's runtime
    semantics (cron, domain, filename_regex, replace_existing,
    tenant_code) all force a redbeat re-sync inside the same
    transaction. A redbeat failure rolls back the DB change so
    callers never observe partial state.
    """
    row = db.get(IngestionSchedule, schedule_id)
    if row is None:
        raise HTTPException(status_code=404, detail="schedule not found")

    was_enabled = row.is_enabled
    data = body.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(row, field, value)
    db.flush()

    schedule_changed = any(
        k in data
        for k in (
            "cron_expression",
            "domain",
            "filename_regex",
            "replace_existing",
            "is_enabled",
            "tenant_code",
        )
    )

    if row.is_enabled and (was_enabled != row.is_enabled or schedule_changed):
        try:
            redbeat_sync.update(row)
        except RedbeatSyncError as e:
            db.rollback()
            raise HTTPException(
                status_code=502,
                detail=(
                    "Schedule updated in DB but redbeat sync failed: "
                    f"{e}"
                ),
            )
    elif was_enabled and not row.is_enabled:
        try:
            redbeat_sync.unregister(row.id)
        except RedbeatSyncError as e:
            db.rollback()
            raise HTTPException(
                status_code=502,
                detail=(
                    "Schedule disabled in DB but redbeat unregister "
                    f"failed: {e}"
                ),
            )

    audit.record(
        db,
        tenant_id=UUID(current_user["tenant_id"]),
        actor=current_user["sub"],
        action="UPDATE",
        target_type="ingestion_schedule",
        target_id=str(row.id),
    )
    # Refresh BEFORE commit. set_tenant_context()'s `SET LOCAL
    # app.current_tenant` is transaction-scoped and is reset by the
    # commit; refreshing afterwards would run in a fresh transaction
    # with no tenant context, and the RLS policy on ingestion_schedule
    # would filter the row out (raising InvalidRequestError).
    db.refresh(row)
    # Capture the response BEFORE commit. SQLAlchemy's
    # expire_on_commit=True (default) marks all attrs expired on
    # commit; accessing them post-commit triggers a lazy reload
    # in a fresh transaction with no tenant context, which RLS
    # filters out (ObjectDeletedError).
    response = _to_read(row)
    db.commit()
    return response


@router.delete(
    "/{schedule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_schedule(
    schedule_id: UUID,
    db: Session = Depends(get_tenant_db),
    current_user: dict = Depends(get_current_user),
):
    row = db.get(IngestionSchedule, schedule_id)
    if row is None:
        raise HTTPException(status_code=404, detail="schedule not found")

    # Best-effort redbeat cleanup before the DB delete. The DB is
    # source of truth — any orphan redbeat key is swept by the next
    # lifespan reconcile.
    try:
        redbeat_sync.unregister(schedule_id)
    except RedbeatSyncError as e:
        logger.warning(
            "redbeat unregister failed during DELETE of schedule %s: %s "
            "(will be cleaned up by next reconcile)",
            schedule_id,
            e,
        )

    db.delete(row)
    db.flush()
    audit.record(
        db,
        tenant_id=UUID(current_user["tenant_id"]),
        actor=current_user["sub"],
        action="DELETE",
        target_type="ingestion_schedule",
        target_id=str(schedule_id),
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{schedule_id}/enable",
    response_model=IngestionScheduleRead,
)
def enable_schedule(
    schedule_id: UUID,
    db: Session = Depends(get_tenant_db),
    current_user: dict = Depends(get_current_user),
):
    row = db.get(IngestionSchedule, schedule_id)
    if row is None:
        raise HTTPException(status_code=404, detail="schedule not found")

    if row.is_enabled:
        # Idempotent: already enabled. No state change, no audit.
        return _to_read(row)

    row.is_enabled = True
    db.flush()
    try:
        redbeat_sync.register(row)
    except RedbeatSyncError as e:
        db.rollback()
        raise HTTPException(
            status_code=502,
            detail=(
                "Schedule enabled in DB but redbeat register failed: "
                f"{e}"
            ),
        )

    audit.record(
        db,
        tenant_id=UUID(current_user["tenant_id"]),
        actor=current_user["sub"],
        action="ENABLE",
        target_type="ingestion_schedule",
        target_id=str(row.id),
    )
    # Refresh BEFORE commit. set_tenant_context()'s `SET LOCAL
    # app.current_tenant` is transaction-scoped and is reset by the
    # commit; refreshing afterwards would run in a fresh transaction
    # with no tenant context, and the RLS policy on ingestion_schedule
    # would filter the row out (raising InvalidRequestError).
    db.refresh(row)
    # Capture the response BEFORE commit. SQLAlchemy's
    # expire_on_commit=True (default) marks all attrs expired on
    # commit; accessing them post-commit triggers a lazy reload
    # in a fresh transaction with no tenant context, which RLS
    # filters out (ObjectDeletedError).
    response = _to_read(row)
    db.commit()
    return response


@router.post(
    "/{schedule_id}/disable",
    response_model=IngestionScheduleRead,
)
def disable_schedule(
    schedule_id: UUID,
    db: Session = Depends(get_tenant_db),
    current_user: dict = Depends(get_current_user),
):
    row = db.get(IngestionSchedule, schedule_id)
    if row is None:
        raise HTTPException(status_code=404, detail="schedule not found")

    if not row.is_enabled:
        # Idempotent: already disabled. No state change, no audit.
        return _to_read(row)

    row.is_enabled = False
    db.flush()
    try:
        redbeat_sync.unregister(row.id)
    except RedbeatSyncError as e:
        db.rollback()
        raise HTTPException(
            status_code=502,
            detail=(
                "Schedule disabled in DB but redbeat unregister failed: "
                f"{e}"
            ),
        )

    audit.record(
        db,
        tenant_id=UUID(current_user["tenant_id"]),
        actor=current_user["sub"],
        action="DISABLE",
        target_type="ingestion_schedule",
        target_id=str(row.id),
    )
    # Refresh BEFORE commit. set_tenant_context()'s `SET LOCAL
    # app.current_tenant` is transaction-scoped and is reset by the
    # commit; refreshing afterwards would run in a fresh transaction
    # with no tenant context, and the RLS policy on ingestion_schedule
    # would filter the row out (raising InvalidRequestError).
    db.refresh(row)
    # Capture the response BEFORE commit. SQLAlchemy's
    # expire_on_commit=True (default) marks all attrs expired on
    # commit; accessing them post-commit triggers a lazy reload
    # in a fresh transaction with no tenant context, which RLS
    # filters out (ObjectDeletedError).
    response = _to_read(row)
    db.commit()
    return response


@router.post(
    "/{schedule_id}/run-now",
    status_code=status.HTTP_202_ACCEPTED,
)
def run_schedule_now(
    schedule_id: UUID,
    body: RunNowRequest = Body(default_factory=RunNowRequest),
    db: Session = Depends(get_tenant_db),
    current_user: dict = Depends(get_current_user),
):
    """Publish the SFTP-pull task immediately, bypassing cron.

    The worker creates the ``ingestion_run`` row when it picks up the
    task, so ``run_id`` is null in the response. Callers poll
    ``/api/v1/admin/ingestion-runs?schedule_id=<id>`` to find the
    new run once it materialises.

    Body is optional; when omitted defaults to ``{"scope": "today"}``.
    The scope is stored in ``ingestion_run.detail_log[0]`` (the
    DATE_FILTER event) by the worker, so it is durably auditable.
    """
    row = db.get(IngestionSchedule, schedule_id)
    if row is None:
        raise HTTPException(status_code=404, detail="schedule not found")

    result = sftp_pull_for_schedule.delay(str(row.id), scope=body.scope)

    audit.record(
        db,
        tenant_id=UUID(current_user["tenant_id"]),
        actor=current_user["sub"],
        action="RUN_NOW",
        target_type="ingestion_schedule",
        target_id=str(row.id),
    )
    db.commit()
    return {"task_id": result.id, "run_id": None, "scope": body.scope}
