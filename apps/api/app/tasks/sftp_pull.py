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
import re
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.core.crypto import decrypt_str
from app.core.database import SessionLocal
from app.ingestion.exceptions import IngestionConflictError, IngestionError
from app.ingestion.filename_parser import parse_filename
from app.ingestion.service import IngestionService
from app.ingestion.sftp_client import SFTPClientError, SFTPSourceClient
from app.worker import celery_app


logger = logging.getLogger(__name__)


from app.core.config import settings as _settings
SYSTEM_USER_EMAIL = _settings.system_user_email


# ── date-scoped ingestion helpers ───────────────────────────────────
#
# "Today" is always today in IST (Asia/Kolkata). The schedule row's
# timezone column is intentionally NOT consulted — IST is hard-coded
# for date-scope resolution so behaviour is identical regardless of
# how the cron entry is timezoned.
IST = ZoneInfo("Asia/Kolkata")

_SCOPE_DATE_RE = re.compile(r"^date:(\d{6})$")


def _resolve_target_date(scope: str) -> Optional[date]:
    """Resolve the date a scope filter targets.

    Returns:
        - ``date`` for ``"today"`` (today in IST) or ``"date:DDMMYY"``
        - ``None`` for ``"all"`` (caller skips the date filter)

    Raises ``ValueError`` on malformed scope strings.
    """
    if scope == "all":
        return None
    if scope == "today":
        return datetime.now(IST).date()
    m = _SCOPE_DATE_RE.match(scope)
    if m:
        try:
            return datetime.strptime(m.group(1), "%d%m%y").date()
        except ValueError as exc:
            raise ValueError(
                f"invalid date in scope {scope!r}: {exc}"
            ) from exc
    raise ValueError(
        f"invalid scope {scope!r} — must be 'today', 'all', or 'date:DDMMYY'"
    )


def _filter_by_scope(
    entries: list[dict], target_date: Optional[date]
) -> tuple[list[dict], list[str]]:
    """Keep only entries whose filename date matches ``target_date``.

    Entries whose filenames don't parse (or parse but have no date)
    are skipped — a date filter only narrows scope, and unparseable
    names would fail downstream anyway. Returns ``(kept, skipped)``
    where ``skipped`` is the list of skipped filenames for logging.

    If ``target_date`` is ``None`` (scope=all), returns
    ``(list(entries), [])`` unchanged.
    """
    if target_date is None:
        return list(entries), []
    kept: list[dict] = []
    skipped: list[str] = []
    for entry in entries:
        parsed = parse_filename(entry["filename"])
        if parsed.file_date is not None and parsed.file_date == target_date:
            kept.append(entry)
        else:
            skipped.append(entry["filename"])
    return kept, skipped


# ── helpers (testable independently of celery) ──────────────────────


def _system_user_payload(db: Session) -> dict:
    """Resolve the Skywave super-admin user as the actor for ingestion.

    Raises RuntimeError if the canonical user row is missing — this is
    a configuration invariant, NOT a transient failure, so no retry.
    """
    row = db.execute(
        text(
            "SELECT u.id AS user_id, t.slug AS tenant_slug "
            "FROM app_user u JOIN tenant t ON t.id = u.tenant_id "
            "WHERE u.email = :email"
        ),
        {"email": SYSTEM_USER_EMAIL},
    ).first()
    if not row:
        raise RuntimeError(
            f"system user {SYSTEM_USER_EMAIL} not found in app_user — "
            "configuration invariant violated"
        )
    return {
        "sub": str(row.user_id),
        "tenant_slug": row.tenant_slug,
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


def _create_run(
    db: Session,
    schedule_id: str,
    *,
    celery_task_id: Optional[str] = None,
) -> str:
    """Insert a new RUNNING ingestion_run row.

    ``celery_task_id`` is the celery message id of the task that owns
    this row (``self.request.id`` in the bound task wrapper). It is
    persisted so the periodic ``sweep_orphan_runs`` task can match
    rows against ``inspect.active/reserved/scheduled`` and distinguish
    a truly-orphaned row from one that's still being processed (or
    has been redelivered after a worker crash).
    """
    run_id = str(uuid.uuid4())
    db.execute(
        text(
            "INSERT INTO ingestion_run "
            "(id, schedule_id, triggered_by, status, celery_task_id) "
            "VALUES (:id, :sched, 'SCHEDULED', 'RUNNING', :task_id)"
        ),
        {
            "id": run_id,
            "sched": schedule_id,
            "task_id": celery_task_id,
        },
    )
    db.commit()
    return run_id


def _is_cancelling(db: Session, run_id: str) -> bool:
    """Return True iff the run row currently has ``status='CANCELLING'``.

    Called between files inside ``run_pull`` so an operator's cancel
    signal is observed at the next file boundary. Returns False on
    any DB error (cancel must not be able to crash the worker — a
    missed checkpoint just defers cancellation by one file).
    """
    try:
        cur = db.execute(
            text("SELECT status FROM ingestion_run WHERE id = :id"),
            {"id": run_id},
        ).scalar()
    except Exception:
        logger.exception("cancel-check failed for run %s", run_id)
        return False
    return cur == "CANCELLING"


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
    # Race-safe terminal write: if a cancel was signalled while the
    # worker was finishing its last file (status='CANCELLING'), the
    # CASE coerces the terminal state to CANCELLED in the same UPDATE.
    # Without this, a SUCCESS/PARTIAL/FAILED write could silently
    # overwrite the cancel signal.
    db.execute(
        text(
            "UPDATE ingestion_run SET "
            "  finished_at = now(), "
            "  status = CASE WHEN status = 'CANCELLING' "
            "                THEN 'CANCELLED' ELSE :status END, "
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
            vr = svc.validate_job(up_result.job.id, system_payload)
            if vr.row_count_total == 0:
                # Empty file (no data rows) -- e.g. an all-blank velocity
                # export. validate_job has already marked the job REJECTED;
                # we do NOT commit an empty job. Record a non-fatal SKIPPED
                # outcome so the batch carries on.
                outcome = "SKIPPED"
                error_msg = "empty file -- no data rows; skipped"
            else:
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
    celery_task_id: Optional[str] = None,
    scope: str = "today",
) -> dict:
    """Core SFTP-pull logic — testable without celery.

    The ``staging_root`` override exists so tests can route IngestionService
    file-staging at a tmp_path; production callers leave it None and the
    service uses its DEFAULT_STAGING_ROOT.

    ``scope`` controls which files are pulled:
      - ``"today"`` (default): only files whose filename DDMMYY equals
        today in IST.
      - ``"date:DDMMYY"``: only files matching the given date.
      - ``"all"``: no date filter (legacy backfill behaviour).

    A DATE_FILTER event is prepended to ``ingestion_run.detail_log``
    so the scope used is durably auditable per run.

    Returns ``{run_id, files_seen, files_pulled, jobs_committed, status}``.
    Always finalises the ingestion_run row before returning or re-raising.
    """
    # Resolve the target date OUTSIDE the run-bookkeeping try/except so
    # a malformed scope fails fast with a clean 400-equivalent ValueError
    # rather than creating a doomed ingestion_run row.
    target_date = _resolve_target_date(scope)

    run_id: Optional[str] = None
    # Pre-initialise run tallies + detail_log so the except (infra-failure)
    # path can still persist partial telemetry instead of all-zeros if we
    # fail before or during the per-file loop.
    files_seen = files_pulled = jobs_created = jobs_committed = 0
    jobs_skipped = files_errored = 0
    jobs_conflict = jobs_rejected = 0
    detail_log: list[dict] = []
    try:
        schedule = _load_schedule(db, schedule_id)
        connection = _load_connection(db, schedule["sftp_connection_id"])
        system_payload = _system_user_payload(db)

        run_id = _create_run(
            db, schedule_id, celery_task_id=celery_task_id,
        )

        client = _build_sftp_client(connection)

        entries = client.list_matching(
            connection["remote_base_path"], schedule["filename_regex"]
        )

        listed_total = len(entries)
        entries, skipped = _filter_by_scope(entries, target_date)

        files_seen = len(entries)
        files_pulled = 0
        jobs_created = 0
        jobs_committed = 0
        # Prepend the DATE_FILTER provenance event so the UI / operator
        # can see exactly which scope produced the per-file rows that
        # follow. detail_log[0] is, by convention, the run-context entry.
        detail_log: list[dict] = [
            {
                "event": "DATE_FILTER",
                "scope": scope,
                "target_date": (
                    target_date.isoformat() if target_date else None
                ),
                "timezone": "Asia/Kolkata",
                "listed_total": listed_total,
                "matched": files_seen,
                "skipped_examples": skipped[:5],
            }
        ]
        logger.info(
            "ingestion.run_pull: date filter applied — scope=%s "
            "target_date=%s listed=%d matched=%d (run_id=%s)",
            scope,
            target_date.isoformat() if target_date else "ALL",
            listed_total,
            files_seen,
            run_id,
        )

        svc = IngestionService(db, staging_root=staging_root)
        cancelled = False
        for entry in entries:
            # Cooperative cancel: an operator-initiated CANCELLING
            # state is picked up at each file boundary. Already-
            # committed files keep their COMMITTED outcome — we
            # never roll back successful work on cancel.
            if _is_cancelling(db, run_id):
                cancelled = True
                detail_log.append({
                    "event": "CANCELLED",
                    "note": "operator cancel observed before next file",
                })
                break
            try:
                result = _process_one_file(
                    db, svc, client, connection, schedule,
                    run_id, entry, system_payload,
                )
            except Exception as exc:
                # Per-file isolation: an unexpected error on one file must
                # never abort the rest of the batch. Roll back its partial
                # transaction, record an ERROR row in a fresh transaction,
                # and carry on to the next file.
                db.rollback()
                filename = entry["filename"]
                err = str(exc)[:2000]
                logger.exception(
                    "ingestion.run_pull: file %s failed; recording ERROR "
                    "and continuing (run_id=%s)", filename, run_id,
                )
                # ingested_file.sha256 is NOT NULL and we may not have
                # hashed the content, so synthesise a per-run marker hash
                # (unique within the run via the filename) for the row.
                marker_sha = hashlib.sha256(
                    f"ERROR|{run_id}|{filename}".encode("utf-8")
                ).hexdigest()
                try:
                    db.execute(
                        text(
                            "INSERT INTO ingested_file "
                            "(id, run_id, schedule_id, remote_filename, "
                            " remote_size_bytes, remote_mtime_utc, sha256, "
                            " ingestion_job_id, outcome, error_message) "
                            "VALUES (:id, :rid, :sid, :name, :size, "
                            "        :mtime, :sha, NULL, 'ERROR', :err)"
                        ),
                        {
                            "id": str(uuid.uuid4()),
                            "rid": run_id,
                            "sid": str(schedule["id"]),
                            "name": filename,
                            "size": entry.get("size", 0),
                            "mtime": entry["mtime_utc"],
                            "sha": marker_sha,
                            "err": err,
                        },
                    )
                    db.commit()
                except Exception:
                    db.rollback()
                    logger.exception(
                        "ingestion.run_pull: failed to record ERROR row "
                        "for %s (run_id=%s)", filename, run_id,
                    )
                detail_log.append(
                    {"filename": filename, "outcome": "ERROR", "error": err}
                )
                files_pulled += 1
                files_errored += 1
                continue
            detail_log.append(result)
            outcome = result["outcome"]
            if outcome == "DUPLICATE":
                pass
            elif outcome == "SKIPPED":
                files_pulled += 1
                jobs_skipped += 1
            elif outcome == "ERROR":
                files_pulled += 1
                files_errored += 1
            else:
                files_pulled += 1
                jobs_created += 1
                if outcome == "COMMITTED":
                    jobs_committed += 1
                elif outcome == "CONFLICT":
                    jobs_conflict += 1
                elif outcome == "REJECTED":
                    jobs_rejected += 1

        # Status reflects DATA outcomes only, and only GENUINE problems
        # drive PARTIAL: hard per-file errors, empty-file skips, or real
        # rejects. Benign CONFLICT (date already committed -- idempotent)
        # and DUPLICATE (same sha+name re-seen) do NOT count, so a clean
        # idempotent re-pull stays SUCCESS. FAILED is reserved for the
        # infra/connection-level except path below.
        problems = files_errored + jobs_skipped + jobs_rejected
        if cancelled:
            final_status = "CANCELLED"
        elif files_pulled == 0:
            final_status = "SUCCESS"
        elif problems == 0:
            final_status = "SUCCESS"
        else:
            final_status = "PARTIAL"

        detail_log.append({
            "event": "RUN_SUMMARY",
            "files_seen": files_seen,
            "files_pulled": files_pulled,
            "jobs_created": jobs_created,
            "jobs_committed": jobs_committed,
            "jobs_conflict": jobs_conflict,
            "jobs_rejected": jobs_rejected,
            "jobs_skipped": jobs_skipped,
            "files_errored": files_errored,
            "status": final_status,
        })
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
                # Persist whatever telemetry we accumulated before the
                # infra-level failure so the UI does not show all-zeros.
                db.rollback()
                detail_log.append({
                    "event": "RUN_ABORTED",
                    "error": str(exc)[:1000],
                    "files_seen": files_seen,
                    "files_pulled": files_pulled,
                    "jobs_created": jobs_created,
                    "jobs_committed": jobs_committed,
                    "jobs_conflict": jobs_conflict,
                    "jobs_rejected": jobs_rejected,
                    "jobs_skipped": jobs_skipped,
                    "files_errored": files_errored,
                })
                _finalize_run(
                    db, run_id, "FAILED",
                    files_seen=files_seen,
                    files_pulled=files_pulled,
                    jobs_created=jobs_created,
                    jobs_committed=jobs_committed,
                    error_summary=str(exc)[:1000],
                    detail_log=detail_log,
                )
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
def sftp_pull_for_schedule(
    self, schedule_id: str, scope: str = "today"
) -> dict:
    """Celery wrapper around ``run_pull``. See module docstring for details.

    ``scope`` defaults to ``"today"`` so cron-fired invocations (which
    pass only ``schedule_id``) get today-only filtering automatically.
    Run-Now callers can override with ``"all"`` or ``"date:DDMMYY"``.
    """
    db = SessionLocal()
    try:
        return run_pull(
            db,
            schedule_id,
            celery_task_id=self.request.id,
            scope=scope,
        )
    finally:
        try:
            db.close()
        except Exception:
            pass


# ── orphan-run sweeper ──────────────────────────────────────────────


ORPHAN_AGE_THRESHOLD = timedelta(minutes=30)
ORPHAN_ERROR_SUMMARY = (
    "Abandoned: worker died before completion (orphan sweeper)."
)


def _live_pull_task_ids(app, *, inspect_timeout: float = 2.0) -> Optional[set[str]]:
    """Return the set of celery message-ids for ``sftp_pull_for_schedule``
    tasks currently in any worker's active / reserved / scheduled queue.

    Returns ``None`` when no worker replied to ping — the sweeper MUST
    skip its scan in that case. Without confirmation that at least one
    worker is alive we cannot safely declare any row orphaned (an empty
    set would falsely match every row).
    """
    insp = app.control.inspect(timeout=inspect_timeout)
    try:
        pong = insp.ping() or {}
    except Exception:
        logger.exception("orphan-sweep: inspect.ping() failed")
        return None
    if not pong:
        logger.info(
            "orphan-sweep: no workers replied to ping; skipping this cycle"
        )
        return None

    try:
        active = insp.active() or {}
        reserved = insp.reserved() or {}
        scheduled = insp.scheduled() or {}
    except Exception:
        logger.exception("orphan-sweep: inspect.active/reserved/scheduled failed")
        return None

    task_ids: set[str] = set()
    # ``active`` and ``reserved`` return ``{worker: [task_dict, ...]}``;
    # ``scheduled`` wraps each entry as ``{'eta': ..., 'request': task_dict}``.
    for bag, wrapped in ((active, False), (reserved, False), (scheduled, True)):
        for tasks in bag.values():
            for entry in tasks or []:
                t = (entry.get("request") or {}) if wrapped else entry
                if t.get("name") != "app.tasks.sftp_pull.sftp_pull_for_schedule":
                    continue
                tid = t.get("id")
                if tid:
                    task_ids.add(str(tid))
    return task_ids


def _sweep_one(
    db: Session,
    run_id: str,
    current_status: str,
) -> Optional[str]:
    """Conditionally transition a single orphaned row.

    Returns the new status if the UPDATE moved the row, else ``None``
    (status was changed by another writer between the SELECT and the
    UPDATE — race-safe no-op).

    RUNNING → FAILED, CANCELLING → CANCELLED. ``finished_at`` is set
    only if NULL (so a coincident-but-stale finalize doesn't get
    overwritten). ``error_summary`` is preserved if already set.
    """
    if current_status == "CANCELLING":
        new_status = "CANCELLED"
    elif current_status == "RUNNING":
        new_status = "FAILED"
    else:
        return None  # caller should not pass terminal statuses

    result = db.execute(
        text(
            "UPDATE ingestion_run SET "
            "  status = :new_status, "
            "  finished_at = COALESCE(finished_at, now()), "
            "  error_summary = COALESCE(error_summary, :err) "
            "WHERE id = :id AND status = :old_status"
        ),
        {
            "id": run_id,
            "old_status": current_status,
            "new_status": new_status,
            "err": ORPHAN_ERROR_SUMMARY,
        },
    )
    return new_status if result.rowcount else None


@celery_app.task(
    name="app.tasks.sftp_pull.sweep_orphan_runs",
    ignore_result=True,
    acks_late=False,
)
def sweep_orphan_runs() -> dict:
    """Periodic sweeper: finalise ingestion_run rows whose worker died.

    Runs on the celery-beat / redbeat cadence configured in
    ``app/worker.py`` (every 5 min by default). The flow:

    1. Select RUNNING + CANCELLING rows older than ``ORPHAN_AGE_THRESHOLD``.
    2. Ask celery for ``sftp_pull_for_schedule`` task-ids that are
       currently active / reserved / scheduled. Abort the cycle if no
       worker replied (we cannot safely declare anything orphaned
       without confirmation that the inspect path is healthy).
    3. For each candidate row whose ``celery_task_id`` is NOT in the
       live set, conditionally UPDATE it to FAILED / CANCELLED with a
       fixed ``error_summary``. The UPDATE's ``WHERE status = ...``
       clause makes the operation idempotent and race-safe against the
       cancel endpoint and the worker's own ``_finalize_run``.

    Returns a small dict with counts + per-row outcomes; callers (beat,
    operators inspecting result backend) get a forensic trail without
    flooding the DB or the logs.
    """
    db = SessionLocal()
    try:
        cutoff = datetime.now(timezone.utc) - ORPHAN_AGE_THRESHOLD
        candidates = db.execute(
            text(
                "SELECT id, status, celery_task_id "
                "FROM ingestion_run "
                "WHERE status IN ('RUNNING', 'CANCELLING') "
                "  AND started_at < :cutoff"
            ),
            {"cutoff": cutoff},
        ).mappings().all()

        if not candidates:
            return {"checked": 0, "swept": 0, "skipped_live": 0}

        live_task_ids = _live_pull_task_ids(celery_app)
        if live_task_ids is None:
            logger.warning(
                "orphan-sweep: aborting cycle — inspect path unhealthy "
                "(%d candidate row(s) deferred)",
                len(candidates),
            )
            return {
                "checked": len(candidates),
                "swept": 0,
                "skipped_live": 0,
                "deferred": True,
            }

        swept: list[dict] = []
        skipped_live = 0
        for row in candidates:
            row_id = str(row["id"])
            row_status = row["status"]
            row_task_id = row["celery_task_id"]
            # A NULL task id means "no live task can claim this row"
            # (pre-migration row, or non-celery test/script writer).
            # Treat as eligible for sweep — past the age threshold, the
            # only thing that could legitimately hold it is a live
            # celery task, which by definition would have a non-NULL id
            # written by the wrapper.
            if row_task_id and row_task_id in live_task_ids:
                skipped_live += 1
                continue
            new_status = _sweep_one(db, row_id, row_status)
            if new_status:
                swept.append(
                    {
                        "run_id": row_id,
                        "from": row_status,
                        "to": new_status,
                        "celery_task_id": row_task_id,
                    }
                )
        db.commit()

        if swept:
            logger.warning(
                "orphan-sweep: finalised %d abandoned run(s): %s",
                len(swept),
                [s["run_id"] for s in swept],
            )
        else:
            logger.info(
                "orphan-sweep: %d candidate(s), %d still live, 0 swept",
                len(candidates),
                skipped_live,
            )

        return {
            "checked": len(candidates),
            "swept": len(swept),
            "skipped_live": skipped_live,
            "details": swept,
        }
    finally:
        try:
            db.close()
        except Exception:
            pass
