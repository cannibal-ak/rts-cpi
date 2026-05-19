"""Admin SMTP Config router — /api/v1/admin/settings/smtp.

GET     → SmtpConfigRead | null  (current config; null when unset)
PUT     → SmtpConfigRead          (create or update; password optional on edit)
POST /test → SmtpTestResponse     (test saved row OR in-flight form values)
DELETE  → 204                     (clear config)

All endpoints require RTS platform admin via RequirePlatformAdmin at
the router level; main.py also stacks the password-change gate via
_protected. Mirrors the other admin routers.

Audit events SMTP_CONFIG_UPDATED and SMTP_CONFIG_TESTED are emitted
through the uvicorn.error logger per the project's logging
convention — a real audit_log table is a deferred follow-up.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import RequirePlatformAdmin, get_current_user
from app.core.encryption import decrypt_secret, encrypt_secret
from app.models.smtp_config import SmtpConfig
from app.schemas.smtp_config import (
    SmtpConfigRead,
    SmtpConfigUpdate,
    SmtpTestRequest,
    SmtpTestResponse,
)
from app.services import smtp_service

logger = logging.getLogger("uvicorn.error")

router = APIRouter(
    prefix="/api/v1/admin/settings/smtp",
    tags=["Admin - Settings - Email"],
    dependencies=[Depends(RequirePlatformAdmin())],
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _to_read(row: SmtpConfig) -> SmtpConfigRead:
    return SmtpConfigRead.model_validate({
        "id": row.id,
        "host": row.host,
        "port": row.port,
        "encryption": row.encryption,
        "username": row.username,
        "from_email": row.from_email,
        "from_name": row.from_name,
        "last_test_at": row.last_test_at,
        "last_test_status": row.last_test_status,
        "last_test_error": row.last_test_error,
        "updated_at": row.updated_at,
        "password_set": bool(row.password_encrypted),
    })


def _coerce_actor_uuid(current_user: dict) -> Optional[uuid.UUID]:
    raw = current_user.get("sub")
    if not raw:
        return None
    try:
        return uuid.UUID(str(raw))
    except (ValueError, TypeError):
        return None


@router.get("", response_model=Optional[SmtpConfigRead])
def read_smtp_config(db: Session = Depends(get_db)):
    row = smtp_service.get_smtp_config(db)
    if row is None:
        return None
    return _to_read(row)


@router.put("", response_model=SmtpConfigRead)
def upsert_smtp_config(
    body: SmtpConfigUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    row = smtp_service.get_smtp_config(db)
    is_new = row is None

    if is_new:
        if body.password is None:
            raise HTTPException(
                status_code=422,
                detail="password is required when no SMTP config exists yet.",
            )
        row = SmtpConfig(
            id=uuid.uuid4(),
            host=body.host,
            port=body.port,
            encryption=body.encryption,
            username=body.username,
            password_encrypted=encrypt_secret(body.password.get_secret_value()),
            from_email=str(body.from_email),
            from_name=body.from_name,
        )
        db.add(row)
        changed = [
            "host", "port", "encryption", "username",
            "password", "from_email", "from_name",
        ]
    else:
        changed: list[str] = []

        def _set(attr: str, new_value):
            if getattr(row, attr) != new_value:
                setattr(row, attr, new_value)
                changed.append(attr)

        _set("host", body.host)
        _set("port", body.port)
        _set("encryption", body.encryption)
        _set("username", body.username)
        _set("from_email", str(body.from_email))
        _set("from_name", body.from_name)

        if body.password is not None:
            row.password_encrypted = encrypt_secret(body.password.get_secret_value())
            changed.append("password")

    row.updated_at = _now()
    row.updated_by_user_id = _coerce_actor_uuid(current_user)

    db.commit()
    db.refresh(row)

    logger.info(
        "SMTP_CONFIG_UPDATED actor=%s changed=%s host=%s port=%s encryption=%s",
        current_user.get("sub"),
        changed,
        row.host,
        row.port,
        row.encryption,
    )

    return _to_read(row)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
def delete_smtp_config(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    row = smtp_service.get_smtp_config(db)
    if row is None:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    db.delete(row)
    db.commit()
    logger.info(
        "SMTP_CONFIG_UPDATED actor=%s changed=['deleted']",
        current_user.get("sub"),
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/test", response_model=SmtpTestResponse)
def test_smtp(
    body: SmtpTestRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    override = body.config_override
    using_saved = override is None

    if override is None:
        row = smtp_service.get_smtp_config(db)
        if row is None:
            raise HTTPException(
                status_code=422,
                detail=(
                    "No saved SMTP config — provide config_override to test "
                    "before saving."
                ),
            )
        try:
            password = decrypt_secret(row.password_encrypted)
        except Exception as e:
            logger.error(
                "SMTP_CONFIG_TESTED actor=%s saved-config decrypt failed: %s",
                current_user.get("sub"), e,
            )
            raise HTTPException(
                status_code=500,
                detail=(
                    "Stored SMTP password could not be decrypted. "
                    "Check CPI_SMTP_ENCRYPTION_KEY."
                ),
            )
        result = smtp_service.test_smtp_connection(
            host=row.host,
            port=row.port,
            encryption=row.encryption,
            username=row.username,
            password=password,
            from_email=row.from_email,
            from_name=row.from_name,
            to_email=str(body.to_email),
        )
        # Persist the last-test outcome on the saved row.
        row.last_test_at = _now()
        row.last_test_status = "success" if result["success"] else "failed"
        row.last_test_error = None if result["success"] else result["message"]
        db.commit()
    else:
        result = smtp_service.test_smtp_connection(
            host=override.host,
            port=override.port,
            encryption=override.encryption,
            username=override.username,
            password=override.password.get_secret_value(),
            from_email=str(override.from_email),
            from_name=override.from_name,
            to_email=str(body.to_email),
        )

    logger.info(
        "SMTP_CONFIG_TESTED actor=%s using_saved=%s success=%s latency_ms=%s",
        current_user.get("sub"),
        using_saved,
        result["success"],
        result.get("latency_ms"),
    )

    return SmtpTestResponse(**result)
