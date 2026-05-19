#!/usr/bin/env python3
"""In-container worker for auto_ingest.py (Option A path).

Runs INSIDE cpi-api-1 via `docker exec`. Imports IngestionService and
drives upload -> validate -> commit for a single file. Emits a single
line of JSON on stdout describing the outcome; exits 0 unless
something catastrophic happens (in which case stderr carries the
traceback and exit code is 1 -- the host driver treats that as a
fatal failure for the file).

Usage:
    python /app/scripts/_ingest_worker.py <path-to-file-in-container>

The path is the in-container view of an inbox file; the file is read
into memory and handed to IngestionService.upload_file().

Auth is implicit: we hand-craft the same user_payload dict the JWT
auth path produces for admin@rts.com. The IngestionService still
runs its own is_platform_admin() check against tenant_slug + roles.
"""
from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path

from app.core.database import SessionLocal
from app.ingestion.exceptions import IngestionError
from app.ingestion.service import IngestionService


# admin@rts.com -- confirmed via app_user table on 2026-05-19 (renamed from
# admin@skywave.com in migration 026; same UUID, password hash unchanged).
ADMIN_USER_PAYLOAD = {
    "sub": "11111111-0000-0000-0000-000000000001",
    "tenant_id": "a0000000-0000-0000-0000-000000000001",
    "email": "admin@rts.com",
    "tenant_slug": "rts",
    "roles": ["TENANT_ADMIN"],
}
ACTOR_IP = "127.0.0.1"  # must be valid INET; column is postgres inet type


def emit(payload: dict) -> None:
    print(json.dumps(payload), flush=True)


def run(file_path: Path) -> int:
    if not file_path.is_file():
        emit({
            "ok": False,
            "phase": "preflight",
            "error_code": "file_missing",
            "error_message": f"File not found in container: {file_path}",
        })
        return 0

    content = file_path.read_bytes()
    basename = file_path.name

    db = SessionLocal()
    try:
        svc = IngestionService(db)

        # ---- upload ----
        try:
            up = svc.upload_file(
                content, basename, ADMIN_USER_PAYLOAD, actor_ip=ACTOR_IP
            )
        except IngestionError as exc:
            emit({
                "ok": False,
                "phase": "upload",
                "error_code": exc.error_code,
                "error_message": str(exc),
            })
            return 0

        job_id = str(up.job.id)
        if up.duplicate:
            emit({
                "ok": True,
                "phase": "upload",
                "duplicate": True,
                "job_id": job_id,
                "existing_job_id": str(up.existing_job_id) if up.existing_job_id else None,
                "tenant_code": up.job.tenant_code,
                "domain": up.job.domain,
                "file_date": up.job.file_date.isoformat(),
                "rows_inserted": 0,
                "message": "content hash matches an already-committed job",
            })
            return 0

        # ---- validate ----
        try:
            val = svc.validate_job(job_id, ADMIN_USER_PAYLOAD, actor_ip=ACTOR_IP)
        except IngestionError as exc:
            emit({
                "ok": False,
                "phase": "validate",
                "job_id": job_id,
                "error_code": exc.error_code,
                "error_message": str(exc),
            })
            return 0

        if val.job.status != "VALIDATED":
            emit({
                "ok": False,
                "phase": "validate",
                "job_id": job_id,
                "status": val.job.status,
                "error_code": "validation_not_passed",
                "error_message": val.job.error_message or "validation did not produce VALIDATED status",
                "row_count_total": val.row_count_total,
                "row_count_valid": val.row_count_valid,
                "row_count_rejected": val.row_count_rejected,
                "summary": val.summary,
            })
            return 0

        # ---- commit ----
        try:
            cm = svc.commit_job(
                job_id, ADMIN_USER_PAYLOAD,
                replace_existing=True, actor_ip=ACTOR_IP,
            )
        except IngestionError as exc:
            emit({
                "ok": False,
                "phase": "commit",
                "job_id": job_id,
                "error_code": exc.error_code,
                "error_message": str(exc),
            })
            return 0

        emit({
            "ok": True,
            "phase": "commit",
            "duplicate": False,
            "job_id": job_id,
            "tenant_code": cm.job.tenant_code,
            "domain": cm.job.domain,
            "file_date": cm.job.file_date.isoformat(),
            "row_count_total": val.row_count_total,
            "row_count_valid": val.row_count_valid,
            "row_count_rejected": val.row_count_rejected,
            "rows_inserted": cm.rows_inserted,
            "replaced_job_id": str(cm.replaced_job_id) if cm.replaced_job_id else None,
        })
        return 0
    finally:
        db.close()


def main() -> int:
    if len(sys.argv) != 2:
        emit({
            "ok": False,
            "phase": "preflight",
            "error_code": "usage",
            "error_message": f"expected one arg (file path), got {len(sys.argv) - 1}",
        })
        return 1
    try:
        return run(Path(sys.argv[1]))
    except Exception:
        traceback.print_exc()
        emit({
            "ok": False,
            "phase": "uncaught",
            "error_code": "uncaught_exception",
            "error_message": "see stderr for traceback",
        })
        return 1


if __name__ == "__main__":
    sys.exit(main())
