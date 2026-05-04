"""SFTP pull task — fetch files from a configured SFTP source per schedule.

Workflow per task invocation:
  1. Load ingestion_schedule + sftp_connection from DB
  2. Resolve system user (Skywave admin) — fail fast if missing
  3. Insert ingestion_run row with status=RUNNING
  4. Decrypt SFTP credentials via app.core.crypto
  5. List remote files matching schedule's filename_regex
  6. For each file:
       - Compute SHA-256 of remote bytes
       - Pre-check ingested_file (sha256, remote_filename) — skip
         if already present, record DUPLICATE in detail_log
       - Otherwise: download, hand to IngestionService
         (upload -> validate -> commit), insert ingested_file row
  7. Finalise ingestion_run with totals + status
  8. Update ingestion_schedule.last_run_at

Idempotency: the (sha256, remote_filename) UNIQUE constraint on
ingested_file (migration 020) is enforced by an explicit pre-check.
Duplicate occurrences do NOT insert a second row; they are recorded
in ingestion_run.detail_log only.

Retry policy:
  - SFTPClientError + sqlalchemy OperationalError: autoretry (max 3,
    exponential backoff up to 600s with jitter)
  - All other errors (decryption failure, missing schedule, missing
    system user, IngestionError subclasses): NOT in autoretry_for —
    task fails permanently after marking the run FAILED
"""
from __future__ import annotations

import hashlib
import json
import logging
import uuid
from pathlib import Path
from typing import Optional

from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.core.crypto import decrypt_str
from app.core.database import SessionLocal
from app.ingestion.exceptions import IngestionConflictError, IngestionError
from app.ingestion.service import IngestionService
from app.ingestion.sftp_client import SFTPClientError, SFTPSourceClient
from app.worker import celery_app


logger = logging.getLogger(__name__)


SYSTEM_USER_EMAIL = "admin@skywave.com"


# ── helpers (testable independently of celery) ──────────────────────


def _system_user_payload(db: Session) -> dict:
    """Resolve the Skywave super-admin user as the actor for ingestion.

    Raises RuntimeError if the canonical user row is missing — this is
    a configuration invariant, NOT a transient failure, so no retry.
    """
    row = db.execute(
        text("SELECT id FROM app_user WHERE email = :email"),
        {"email": SYSTEM_USER_EMAIL},
    ).first()
    if not row:
        raise RuntimeError(
            f"system user {SYSTEM_USER_EMAIL} not found in app_user — "
            "configuration invariant violated"
        )
    return {
        "sub": str(row[0]),
        "tenant_slug": "skywave",
        "roles": ["TENANT_ADMIN"],
    }


def _load_schedule(db: Session, schedule_id: str) -> dict:
    row = db.execute(
        text(
            "SELECT id, sftp_connection_id, tenant_code, domain, "
            "filename_regex, replace_existing "
            "FROM ingestion_schedule WHERE id = :id"
        ),
        {"id": schedule_id},
    ).mappings().first()
    if not row:
        raise RuntimeError(f"ingestion_schedule {schedule_id} not found")
    return dict(row)


def _load_connection(db: Session, conn_id) -> dict:
    row = db.execute(
        text(
            "SELECT id, host, port, username, password_ciphertext, "
            "private_key_ciphertext, host_key_fingerprint, "
            "remote_base_path "
            "FROM sftp_connection WHERE id = :id"
        ),
        {"id": str(conn_id)},
    ).mappings().first()
    if not row:
        raise RuntimeError(f"sftp_connection {conn_id} not found")
    return dict(row)


def _build_sftp_client(connection: dict) -> SFTPSourceClient:
    """Decrypt creds and build an SFTP client. Raises InvalidToken on
    bad ciphertext (permanent, no retry)."""
    pwd_ct = connection["password_ciphertext"]
    pk_ct = connection["private_key_ciphertext"]
    password = decrypt_str(bytes(pwd_ct)) if pwd_ct else None
    private_key_pem = decrypt_str(bytes(pk_ct)) if pk_ct else None
    return SFTPSourceClient(
        host=connection["host"],
        port=connection["port"],
        username=connection["username"],
        password=password,
        private_key_pem=private_key_pem,
        host_key_fingerprint=connection["host_key_fingerprint"],
    )


def _create_run(db: Session, schedule_id: str) -> str:
    run_id = str(uuid.uuid4())
    db.execute(
        text(
            "INSERT INTO ingestion_run "
            "(id, schedule_id, triggered_by, status) "
            "VALUES (:id, :sched, 'SCHEDULED', 'RUNNING')"
        ),
        {"id": run_id, "sched": schedule_id},
    )
    db.commit()
    return run_id


def _finalize_run(
    db: Session,
    run_id: str,
    status: str,
    *,
    files_seen: int = 0,
    files_pulled: int = 0,
    jobs_created: int = 0,
    jobs_committed: int = 0,
    error_summary: Optional[str] = None,
    detail_log: Optional[list[dict]] = None,
) -> None:
    db.execute(
        text(
            "UPDATE ingestion_run SET "
            "  finished_at = now(), "
            "  status = :status, "
            "  files_seen = :seen, "
            "  files_pulled = :pulled, "
            "  jobs_created = :created, "
            "  jobs_committed = :committed, "
            "  error_summary = :err, "
            "  detail_log = CAST(:detail AS JSONB) "
            "WHERE id = :id"
        ),
        {
            "id": run_id,
            "status": status,
            "seen": files_seen,
            "pulled": files_pulled,
            "created": jobs_created,
            "committed": jobs_committed,
            "err": (error_summary or "")[:2000] or None,
            "detail": json.dumps(detail_log or [], default=str),
        },
    )
    db.commit()


def _process_one_file(
    db: Session,
    svc: IngestionService,
    client: SFTPSourceClient,
    connection: dict,
    schedule: dict,
    run_id: str,
    entry: dict,
    system_payload: dict,
) -> dict:
    """Process a single remote file. Returns a dict for detail_log."""
    filename = entry["filename"]
    remote_path = connection["remote_base_path"]

    content = client.download_bytes(remote_path, filename)
    sha = hashlib.sha256(content).hexdigest()

    # ── Duplicate handling — design decision (approved 2026-05-04) ──
    #
    # Migration 020 declares ``UNIQUE (sha256, remote_filename)`` on
    # ingested_file, so a file with the same content + same name can
    # only ever produce one row. When the same file reappears on a
    # later run, we deliberately DO NOT insert a second ingested_file
    # row (which the constraint would block anyway) and DO NOT update
    # the existing row's outcome (which would lose the original
    # COMMITTED state). Instead we record the duplicate in
    # ingestion_run.detail_log JSONB — the per-run forensic surface.
    #
    # ingested_file is therefore a tight table-of-truth ("this file
    # was ingested once, here is its job"); detail_log is the per-run
    # audit ("on this run we observed N files, M were duplicates").
    # Operators querying "was this file processed?" check ingested_file;
    # operators querying "what happened during run X?" check detail_log.
    dup = db.execute(
        text(
            "SELECT id FROM ingested_file "
            "WHERE sha256 = :sha AND remote_filename = :name"
        ),
        {"sha": sha, "name": filename},
    ).first()
    if dup:
        return {
            "filename": filename,
            "sha256": sha,
            "outcome": "DUPLICATE",
            "ingested_file_id": str(dup[0]),
            "note": "skipped — already present in ingested_file",
        }

    job_id: Optional[str] = None
    outcome = "ERROR"
    error_msg: Optional[str] = None
    try:
        up_result = svc.upload_file(content, filename, system_payload)
        job_id = str(up_result.job.id)
        if up_result.duplicate:
            outcome = "DUPLICATE"
        else:
            svc.validate_job(up_result.job.id, system_payload)
            try:
                svc.commit_job(
                    up_result.job.id,
                    system_payload,
                    replace_existing=schedule["replace_existing"],
                )
                outcome = "COMMITTED"
            except IngestionConflictError as exc:
                outcome = "CONFLICT"
                error_msg = str(exc)
    except IngestionError as exc:
        outcome = "REJECTED"
        error_msg = str(exc)

    db.execute(
        text(
            "INSERT INTO ingested_file "
            "(id, run_id, schedule_id, remote_filename, "
            " remote_size_bytes, remote_mtime_utc, sha256, "
            " ingestion_job_id, outcome, error_message) "
            "VALUES (:id, :rid, :sid, :name, :size, :mtime, :sha, "
            "        :jid, :outcome, :err)"
        ),
        {
            "id": str(uuid.uuid4()),
            "rid": run_id,
            "sid": str(schedule["id"]),
            "name": filename,
            "size": entry["size"],
            "mtime": entry["mtime_utc"],
            "sha": sha,
            "jid": job_id,
            "outcome": outcome,
            "err": (error_msg or "")[:2000] or None,
        },
    )
    db.commit()
    return {
        "filename": filename,
        "sha256": sha,
        "outcome": outcome,
        "ingestion_job_id": job_id,
        "error": error_msg,
    }


def run_pull(
    db: Session,
    schedule_id: str,
    *,
    staging_root: Optional[Path] = None,
) -> dict:
    """Core SFTP-pull logic — testable without celery.

    The ``staging_root`` override exists so tests can route IngestionService
    file-staging at a tmp_path; production callers leave it None and the
    service uses its DEFAULT_STAGING_ROOT.

    Returns ``{run_id, files_seen, files_pulled, jobs_committed, status}``.
    Always finalises the ingestion_run row before returning or re-raising.
    """
    run_id: Optional[str] = None
    try:
        schedule = _load_schedule(db, schedule_id)
        connection = _load_connection(db, schedule["sftp_connection_id"])
        system_payload = _system_user_payload(db)

        run_id = _create_run(db, schedule_id)

        client = _build_sftp_client(connection)

        entries = client.list_matching(
            connection["remote_base_path"], schedule["filename_regex"]
        )

        files_seen = len(entries)
        files_pulled = 0
        jobs_created = 0
        jobs_committed = 0
        detail_log: list[dict] = []

        svc = IngestionService(db, staging_root=staging_root)
        for entry in entries:
            result = _process_one_file(
                db, svc, client, connection, schedule,
                run_id, entry, system_payload,
            )
            detail_log.append(result)
            if result["outcome"] != "DUPLICATE":
                files_pulled += 1
                jobs_created += 1
            if result["outcome"] == "COMMITTED":
                jobs_committed += 1

        if jobs_created == 0:
            final_status = "SUCCESS"
        elif jobs_committed == jobs_created:
            final_status = "SUCCESS"
        elif jobs_committed > 0:
            final_status = "PARTIAL"
        else:
            final_status = "FAILED"

        _finalize_run(
            db, run_id, final_status,
            files_seen=files_seen,
            files_pulled=files_pulled,
            jobs_created=jobs_created,
            jobs_committed=jobs_committed,
            detail_log=detail_log,
        )

        db.execute(
            text(
                "UPDATE ingestion_schedule SET last_run_at = now() "
                "WHERE id = :id"
            ),
            {"id": schedule_id},
        )
        db.commit()

        return {
            "run_id": run_id,
            "files_seen": files_seen,
            "files_pulled": files_pulled,
            "jobs_committed": jobs_committed,
            "status": final_status,
        }
    except Exception as exc:
        if run_id is not None:
            try:
                _finalize_run(db, run_id, "FAILED", error_summary=str(exc)[:1000])
            except Exception:
                logger.exception("failed to finalise run %s after error", run_id)
        raise


@celery_app.task(
    bind=True,
    name="app.tasks.sftp_pull.sftp_pull_for_schedule",
    autoretry_for=(SFTPClientError, OperationalError),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
    max_retries=3,
    acks_late=True,
)
def sftp_pull_for_schedule(self, schedule_id: str) -> dict:
    """Celery wrapper around ``run_pull``. See module docstring for details."""
    db = SessionLocal()
    try:
        return run_pull(db, schedule_id)
    finally:
        try:
            db.close()
        except Exception:
            pass
