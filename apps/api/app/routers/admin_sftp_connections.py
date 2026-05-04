"""Admin endpoints for SFTP connection records (Phase 3, Step 4b).

All routes:
  - mounted under ``/api/v1/admin/sftp-connections``
  - guarded by :class:`RequirePlatformAdmin` at the router level
    (Skywave tenant + ``TENANT_ADMIN`` role)
  - audit-logged via :func:`app.services.audit.record` to the
    ``audit_event`` table

This module is import-safe but is NOT wired into ``main.py`` until
Step 4e — landing it inert keeps the diff focused.
"""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.crypto import decrypt_str, encrypt_str
from app.core.deps import RequirePlatformAdmin, get_current_user, get_tenant_db
from app.ingestion.sftp_client import SFTPClientError, SFTPSourceClient
from app.models.sftp import IngestionSchedule, SftpConnection
from app.schemas.common import PageInfo, PaginatedResponse
from app.schemas.sftp import (
    SftpConnectionCreate,
    SftpConnectionRead,
    SftpConnectionUpdate,
)
from app.services import audit


router = APIRouter(
    prefix="/api/v1/admin/sftp-connections",
    tags=["admin / sftp"],
    dependencies=[Depends(RequirePlatformAdmin())],
)


# -- helpers ----------------------------------------------------------


def _to_read(row: SftpConnection) -> SftpConnectionRead:
    """Build a ``SftpConnectionRead`` with masked credential.

    Plaintext credentials are NEVER read off the row here — only the
    presence of ciphertext is reported.
    """
    if row.password_ciphertext is not None:
        masked = "****"
    elif row.private_key_ciphertext is not None:
        masked = "pkey: <encrypted>"
    else:
        masked = "<none>"
    return SftpConnectionRead(
        id=row.id,
        tenant_code=row.tenant_code,
        name=row.name,
        host=row.host,
        port=row.port,
        username=row.username,
        # auth_method is derived — migration 020 enforces XOR on
        # password_ciphertext vs private_key_ciphertext via DB CHECK
        # constraint rather than storing a discriminator column.
        # The CHECK guarantees exactly one is non-NULL, so the
        # ternary is total.
        auth_method=(
            "password" if row.password_ciphertext is not None
            else "private_key"
        ),
        remote_base_path=row.remote_base_path,
        host_key_fingerprint=row.host_key_fingerprint,
        is_active=row.is_active,
        created_at=row.created_at,
        updated_at=row.updated_at,
        masked_credential=masked,
    )


# -- routes -----------------------------------------------------------


@router.post(
    "/",
    response_model=SftpConnectionRead,
    status_code=status.HTTP_201_CREATED,
)
def create_connection(
    body: SftpConnectionCreate,
    db: Session = Depends(get_tenant_db),
    current_user: dict = Depends(get_current_user),
):
    pwd_ct = encrypt_str(body.password) if body.password else None
    pk_ct = (
        encrypt_str(body.private_key_pem) if body.private_key_pem else None
    )

    row = SftpConnection(
        tenant_code=body.tenant_code,
        name=body.name,
        host=body.host,
        port=body.port,
        username=body.username,
        password_ciphertext=pwd_ct,
        private_key_ciphertext=pk_ct,
        host_key_fingerprint=None,
        remote_base_path=body.remote_base_path,
        is_active=body.is_active,
        created_by_user_id=UUID(current_user["sub"]),
    )
    db.add(row)
    db.flush()

    audit.record(
        db,
        tenant_id=UUID(current_user["tenant_id"]),
        actor=current_user["sub"],
        action="CREATE",
        target_type="sftp_connection",
        target_id=str(row.id),
    )
    # Refresh BEFORE commit. set_tenant_context()'s `SET LOCAL
    # app.current_tenant` is transaction-scoped and is reset by the
    # commit; refreshing afterwards would run in a fresh transaction
    # with no tenant context, and the RLS policy on sftp_connection
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
    response_model=PaginatedResponse[SftpConnectionRead],
)
def list_connections(
    db: Session = Depends(get_tenant_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    tenant_code: Optional[str] = Query(default=None),
    is_active: Optional[bool] = Query(default=None),
):
    q = select(SftpConnection)
    if tenant_code is not None:
        q = q.where(SftpConnection.tenant_code == tenant_code)
    if is_active is not None:
        q = q.where(SftpConnection.is_active.is_(is_active))

    total = db.scalar(select(func.count()).select_from(q.subquery()))
    offset = (page - 1) * page_size
    q = q.order_by(SftpConnection.created_at.desc()).offset(offset).limit(page_size)
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
    "/{connection_id}",
    response_model=SftpConnectionRead,
)
def get_connection(
    connection_id: UUID,
    db: Session = Depends(get_tenant_db),
):
    row = db.scalars(
        select(SftpConnection).where(SftpConnection.id == connection_id)
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="SFTP connection not found")
    return _to_read(row)


@router.put(
    "/{connection_id}",
    response_model=SftpConnectionRead,
)
def update_connection(
    connection_id: UUID,
    body: SftpConnectionUpdate,
    db: Session = Depends(get_tenant_db),
    current_user: dict = Depends(get_current_user),
):
    """Update an SFTP connection.

    Credential-field semantics: a missing field, an explicit ``None``,
    or an empty string for ``password`` / ``private_key_pem`` all mean
    "leave the encrypted credential unchanged." The only way to rotate
    a credential is to send a new non-empty value. There is no API
    path to clear a credential without setting a replacement; tenants
    who need to rotate from password to key (or vice versa) should
    DELETE and recreate the connection so the ``auth_method`` change
    is explicit.
    """
    row = db.scalars(
        select(SftpConnection).where(SftpConnection.id == connection_id)
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="SFTP connection not found")

    data = body.model_dump(exclude_unset=True)
    for field, value in data.items():
        if field == "password":
            if value is None or value == "":
                continue
            row.password_ciphertext = encrypt_str(value)
        elif field == "private_key_pem":
            if value is None or value == "":
                continue
            row.private_key_ciphertext = encrypt_str(value)
        else:
            setattr(row, field, value)

    db.flush()
    audit.record(
        db,
        tenant_id=UUID(current_user["tenant_id"]),
        actor=current_user["sub"],
        action="UPDATE",
        target_type="sftp_connection",
        target_id=str(row.id),
    )
    # Refresh BEFORE commit. set_tenant_context()'s `SET LOCAL
    # app.current_tenant` is transaction-scoped and is reset by the
    # commit; refreshing afterwards would run in a fresh transaction
    # with no tenant context, and the RLS policy on sftp_connection
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
    "/{connection_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_connection(
    connection_id: UUID,
    db: Session = Depends(get_tenant_db),
    current_user: dict = Depends(get_current_user),
):
    row = db.scalars(
        select(SftpConnection).where(SftpConnection.id == connection_id)
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="SFTP connection not found")

    ref_count = db.scalar(
        select(func.count())
        .select_from(IngestionSchedule)
        .where(IngestionSchedule.sftp_connection_id == connection_id)
    )
    if ref_count and ref_count > 0:
        audit.record(
            db,
            tenant_id=UUID(current_user["tenant_id"]),
            actor=current_user["sub"],
            action="DELETE",
            target_type="sftp_connection",
            target_id=str(connection_id),
            outcome="failure",
        )
        db.commit()
        raise HTTPException(
            status_code=409,
            detail=(
                f"Cannot delete: {ref_count} schedule(s) still reference "
                "this connection."
            ),
        )

    db.delete(row)
    db.flush()
    audit.record(
        db,
        tenant_id=UUID(current_user["tenant_id"]),
        actor=current_user["sub"],
        action="DELETE",
        target_type="sftp_connection",
        target_id=str(connection_id),
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{connection_id}/test",
)
def test_connection(
    connection_id: UUID,
    db: Session = Depends(get_tenant_db),
    current_user: dict = Depends(get_current_user),
):
    row = db.scalars(
        select(SftpConnection).where(SftpConnection.id == connection_id)
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="SFTP connection not found")

    pw = decrypt_str(bytes(row.password_ciphertext)) if row.password_ciphertext else None
    pk = decrypt_str(bytes(row.private_key_ciphertext)) if row.private_key_ciphertext else None

    try:
        client = SFTPSourceClient(
            host=row.host,
            port=row.port,
            username=row.username,
            password=pw,
            private_key_pem=pk,
            host_key_fingerprint=row.host_key_fingerprint,
            connect_timeout=10,
        )
    except (ValueError, SFTPClientError) as exc:
        audit.record(
            db,
            tenant_id=UUID(current_user["tenant_id"]),
            actor=current_user["sub"],
            action="TEST",
            target_type="sftp_connection",
            target_id=str(connection_id),
            outcome="failure",
        )
        db.commit()
        return {"ok": False, "detail": f"Client construction failed: {exc}"}

    result = client.test_connection(row.remote_base_path)
    ok = bool(result.get("ok"))
    detail = (
        "Connection successful"
        if ok
        else (result.get("error") or "unknown error")
    )

    audit.record(
        db,
        tenant_id=UUID(current_user["tenant_id"]),
        actor=current_user["sub"],
        action="TEST",
        target_type="sftp_connection",
        target_id=str(connection_id),
        outcome="success" if ok else "failure",
    )
    db.commit()
    return {"ok": ok, "detail": detail}
