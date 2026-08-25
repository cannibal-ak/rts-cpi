"""Ingestion service — staged-then-committed upload pipeline.

The service is the single source of truth for the new ingestion flow.
Routers are thin wrappers that translate exceptions into HTTP responses;
all business logic, audit trail, and DB writes live here.

Design notes:
* Each public method enforces Skywave platform-admin authorization.
* Tenant UUIDs are resolved at runtime from the ``tenant`` table by slug.
  This is the Phase 1 fix: the legacy ``ingest_daily.py`` hardcoded JY's
  UUID as Skywave's, and we want that bug to be impossible in the new
  flow by construction.
* Each method commits its own DB transaction. ``commit_job`` does this
  in two phases (mark COMMITTING, do work, mark COMMITTED-or-FAILED) so a
  crash mid-load leaves a recoverable state.
* The validate-then-commit split re-reads the staged file twice; this is
  intentional. The staged file is the source of truth on disk and we
  avoid keeping parsed rows in memory between calls.
"""
from __future__ import annotations

import hashlib
import logging
import os
import shutil
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.deps import is_platform_admin
from app.ingestion.exceptions import (
    IngestionAuthError,
    IngestionConfigError,
    IngestionConflictError,
    IngestionFilenameError,
    IngestionNotFoundError,
    IngestionStateError,
    IngestionValidationError,
)
from app.ingestion.filename_parser import parse_filename
from app.ingestion.parsers import (
    parse_date,
    parse_time,
    parse_velocity_date,
    read_data_file,
    safe_float,
    safe_float_nullable,
    safe_int,
    safe_int_nullable,
)
from app.models.ingestion import IngestionAuditLog, IngestionJob


logger = logging.getLogger(__name__)

DEFAULT_STAGING_ROOT = Path("/app/data/staging")

# Maximum rows we record validation errors for in validation_summary, to
# keep the JSON payload bounded for huge files.
MAX_REJECTION_REASONS_KEPT = 20


@dataclass
class UploadResult:
    job: IngestionJob
    duplicate: bool = False
    conflict: bool = False
    existing_job_id: Optional[uuid.UUID] = None


@dataclass
class ValidationResult:
    job: IngestionJob
    row_count_total: int
    row_count_valid: int
    row_count_rejected: int
    summary: dict[str, Any] = field(default_factory=dict)


@dataclass
class CommitResult:
    job: IngestionJob
    rows_inserted: int
    replaced_job_id: Optional[uuid.UUID] = None


# ── Helpers ──────────────────────────────────────────────────────


def _identity_from_payload(payload: dict) -> str:
    tenant_slug = payload.get("tenant_slug", "")
    return tenant_slug.upper() if tenant_slug else "SHARED"


def _roles_from_payload(payload: dict) -> list[str]:
    roles = payload.get("roles") or []
    return roles if roles else ["TENANT_ADMIN"]


def _business_type_for(domain: str) -> str:
    return "CRUISE_FERRY" if domain == "CFL" else "AIRLINE"


def _seats_or_default(value: object) -> int:
    """Seat count, falling back to 9 only when the feed omits the value.

    ``airline_cpi_snapshot.{ref,comp}_seats`` is NOT NULL, so a missing
    column needs a stand-in and 9 is the long-standing one. The previous
    form — ``safe_int(value or 9)`` — could not tell "column absent" from
    "genuinely zero", because 0 is falsy: every real 0 was rewritten to 9.
    WinAir's feed sends 0, so every WM row claimed nine seats. Routing
    through ``safe_int_nullable`` keeps a real 0 and defaults only on None
    or blank.
    """
    parsed = safe_int_nullable(value)
    return 9 if parsed is None else parsed


# Currency of last resort, per tenant, used only when the source file has no
# currency column at all. JY's pre-2026-05 25-column layout is the only such
# feed still in the archive; every current feed carries RefCur/CompCur.
# ALT is a demo clone built by direct INSERT and never ingests, but it is
# listed so the fallback stays truthful if that ever changes.
# DA is a demo tenant that DOES ingest — its files are PW's, relabelled — so
# it inherits PW's USD.
_TENANT_FALLBACK_CURRENCY = {"JY": "USD", "PW": "USD", "WM": "USD", "ALT": "EUR", "DA": "USD", "5L": "USD"}
_FALLBACK_CURRENCY = "USD"


def _currency_or_default(value: object, tenant_code: str) -> str:
    """Currency for one side of a row: the file's value wins.

    Previously this was hardcoded to ``"GBP"`` for every tenant except WM,
    which silently overrode the source: JY and PW both send ``USD`` in
    ``RefCur``/``CompCur`` and were stored — and displayed — as sterling.
    ``{ref,comp}_curr`` is varchar(4), hence the slice.
    """
    code = "" if value is None else str(value).strip()[:4]
    return code or _TENANT_FALLBACK_CURRENCY.get(tenant_code, _FALLBACK_CURRENCY)


def _ensure_actor_uuid(payload: dict) -> uuid.UUID:
    sub = payload.get("sub")
    if not sub:
        raise IngestionAuthError("JWT payload missing 'sub' (user id)")
    try:
        return uuid.UUID(str(sub))
    except (ValueError, TypeError) as exc:
        raise IngestionAuthError(f"Invalid user id in JWT: {sub}") from exc


# ── Service ──────────────────────────────────────────────────────


class IngestionService:
    def __init__(
        self, db: Session, staging_root: Optional[Path] = None
    ) -> None:
        self.db = db
        self.staging_root = Path(staging_root or DEFAULT_STAGING_ROOT)

    # ── Public methods ─────────────────────────

    def upload_file(
        self,
        file_content: bytes,
        filename: str,
        user_payload: dict,
        actor_ip: Optional[str] = None,
    ) -> UploadResult:
        actor_id = self._require_admin(user_payload)

        parsed = parse_filename(filename)
        if not parsed.is_valid:
            raise IngestionFilenameError(parsed.error_reason or "invalid filename")

        file_hash = hashlib.sha256(file_content).hexdigest()
        file_size = len(file_content)
        basename = os.path.basename(filename)

        # Dedup gate: an identical file (same SHA-256) that is already
        # COMMITTED **for this tenant** is rejected outright with HTTP 409.
        # FAILED / REJECTED prior jobs are silently allowed (the user is
        # retrying after a parser fix). STAGED / VALIDATED with the same hash
        # is allowed too but logged so operators can spot accidental duplicates.
        #
        # The tenant_code term matters for feeds that carry no airline column,
        # where the tenant is known only from the filename. Velocity CSVs are
        # exactly that: DA_VL_080126.csv and PW_VL_080126.csv are byte-identical
        # on purpose (the DreamAir demo data is PW's, re-prefixed), so a
        # tenant-blind hash check would reject the second tenant's copy as a
        # duplicate and leave that tenant with no velocity data at all.
        #
        # This strictly NARROWS the gate: a genuine re-upload within one tenant
        # is still a 409, which is the case the gate was written for.
        existing_committed = (
            self.db.query(IngestionJob)
            .filter(
                IngestionJob.file_hash == file_hash,
                IngestionJob.tenant_code == parsed.tenant_code,
                IngestionJob.status == "COMMITTED",
            )
            .first()
        )
        if existing_committed:
            committed_at = existing_committed.committed_at
            committed_label = (
                committed_at.strftime("%Y-%m-%d")
                if committed_at is not None
                else "unknown date"
            )
            raise IngestionConflictError(
                f"Duplicate file: this exact file was already committed "
                f"on {committed_label} as job {existing_committed.id}",
                existing_job_id=str(existing_committed.id),
            )

        # Tenant-scoped for the same reason as the COMMITTED gate above:
        # without it, every DreamAir velocity upload logs a spurious warning
        # about PW's byte-identical copy.
        existing_inflight = (
            self.db.query(IngestionJob)
            .filter(
                IngestionJob.file_hash == file_hash,
                IngestionJob.tenant_code == parsed.tenant_code,
                IngestionJob.status.in_(("STAGED", "VALIDATED")),
            )
            .first()
        )
        if existing_inflight:
            logger.warning(
                "ingestion.upload_file: a %s copy of file_hash=%s already "
                "exists as job %s (filename=%r). Proceeding with re-stage.",
                existing_inflight.status,
                file_hash,
                existing_inflight.id,
                basename,
            )

        conflict_job = (
            self.db.query(IngestionJob)
            .filter(
                IngestionJob.tenant_code == parsed.tenant_code,
                IngestionJob.domain == parsed.domain,
                IngestionJob.file_date == parsed.file_date,
                IngestionJob.status == "COMMITTED",
            )
            .first()
        )

        tenant_id = self._resolve_tenant_id(parsed.tenant_code)

        job_id = uuid.uuid4()
        staging_dir = self.staging_root / str(job_id)
        staging_dir.mkdir(parents=True, exist_ok=True)
        (staging_dir / basename).write_bytes(file_content)

        job = IngestionJob(
            id=job_id,
            tenant_id=tenant_id,
            tenant_code=parsed.tenant_code,
            domain=parsed.domain,
            filename=basename,
            file_hash=file_hash,
            file_size_bytes=file_size,
            file_date=parsed.file_date,
            status="STAGED",
            mode="STRICT",
            uploaded_by_user_id=actor_id,
        )
        self.db.add(job)
        self.db.flush()

        self._audit(
            job_id=job.id,
            actor_user_id=actor_id,
            action="UPLOADED",
            actor_ip=actor_ip,
            details={
                "filename": basename,
                "file_hash": file_hash,
                "file_size_bytes": file_size,
                "tenant_code": parsed.tenant_code,
                "domain": parsed.domain,
                "file_date": parsed.file_date.isoformat(),
            },
        )

        self.db.commit()
        self.db.refresh(job)

        return UploadResult(
            job=job,
            duplicate=False,
            conflict=bool(conflict_job),
            existing_job_id=conflict_job.id if conflict_job else None,
        )

    def validate_job(
        self,
        job_id: uuid.UUID | str,
        user_payload: dict,
        actor_ip: Optional[str] = None,
    ) -> ValidationResult:
        actor_id = self._require_admin(user_payload)
        job = self._get_job(job_id)

        if job.status not in {"STAGED", "VALIDATED", "REJECTED"}:
            raise IngestionStateError(
                f"job {job.id} status is {job.status}; cannot re-validate"
            )

        job.status = "VALIDATING"
        self.db.flush()

        staged_file = self._staging_path(job)
        if not staged_file.exists():
            job.status = "FAILED"
            job.error_message = f"Staged file missing: {staged_file}"
            self.db.commit()
            raise IngestionValidationError(
                f"Staged file missing for job {job.id}"
            )

        total = 0
        valid = 0
        rejected = 0
        date_mismatch = 0
        rejection_reasons: list[dict[str, str]] = []

        date_field = self._date_field_for(job.domain)
        schema_variant: Optional[str] = None
        if job.domain == "AIRLINE":
            schema_variant = self._airline_schema_variant(staged_file)
            if schema_variant == "NEW":
                date_field = "CaptureDate"
            elif schema_variant == "LEGACY":
                date_field = "CapDate"
            # UNKNOWN: leave date_field at "CapDate"; every row will fail
            # the date gate and the post-loop branch tags the job with a
            # schema-specific error_message instead of the generic one.

        for row in read_data_file(str(staged_file), domain=job.domain):
            total += 1
            raw_date = (row.get(date_field) or "").strip()
            parsed_dt = (
                parse_velocity_date(raw_date)
                if job.domain == "VELOCITY"
                else parse_date(raw_date)
            )
            if not parsed_dt:
                rejected += 1
                if len(rejection_reasons) < MAX_REJECTION_REASONS_KEPT:
                    rejection_reasons.append(
                        {
                            "row": str(total),
                            "reason": (
                                f"missing or unparseable {date_field}: "
                                f"'{raw_date}'"
                            ),
                        }
                    )
                continue
            # Non-blocking observability: the recorded capture date will be
            # taken from the filename (job.file_date) at commit; note when the
            # in-file capture date disagrees so a mis-generating upstream feed
            # can be flagged. VELOCITY's DepDate legitimately differs — skip it.
            if job.domain != "VELOCITY" and parsed_dt != job.file_date:
                date_mismatch += 1
            valid += 1

        if date_mismatch:
            logging.getLogger("uvicorn.error").warning(
                "ingestion: %s (%s) — %d of %d rows carry an in-file %s "
                "different from the filename date %s; the filename date is "
                "recorded",
                job.filename,
                job.domain,
                date_mismatch,
                total,
                date_field,
                job.file_date.isoformat(),
            )

        summary = {
            "total": total,
            "valid": valid,
            "rejected": rejected,
            "rejection_reasons_sample": rejection_reasons,
            "date_field_checked": date_field,
        }
        if schema_variant is not None:
            summary["schema_variant"] = schema_variant

        if total == 0:
            job.status = "REJECTED"
            job.error_message = "Staged file contains zero data rows"
        elif valid == 0:
            job.status = "REJECTED"
            if schema_variant == "UNKNOWN":
                job.error_message = (
                    "Unrecognized AIRLINE schema: expected a 'CapDate' "
                    "(legacy ~80-col) or 'CaptureDate' (new 45-col) header"
                )
            else:
                job.error_message = (
                    f"All {total} rows rejected during validation"
                )
        else:
            job.status = "VALIDATED"
            job.error_message = None

        job.row_count_total = total
        job.row_count_valid = valid
        job.row_count_rejected = rejected
        job.validation_summary = summary
        job.validated_at = datetime.utcnow()

        self._audit(
            job_id=job.id,
            actor_user_id=actor_id,
            action="VALIDATED",
            actor_ip=actor_ip,
            details=summary,
        )

        self.db.commit()
        self.db.refresh(job)

        return ValidationResult(
            job=job,
            row_count_total=total,
            row_count_valid=valid,
            row_count_rejected=rejected,
            summary=summary,
        )

    def commit_job(
        self,
        job_id: uuid.UUID | str,
        user_payload: dict,
        replace_existing: bool = False,
        actor_ip: Optional[str] = None,
    ) -> CommitResult:
        actor_id = self._require_admin(user_payload)
        job = self._get_job(job_id)

        if job.status != "VALIDATED":
            raise IngestionStateError(
                f"job {job.id} status is {job.status}; must be VALIDATED to commit"
            )

        prior_job = self._find_prior_committed(job)
        if prior_job and not replace_existing:
            raise IngestionConflictError(
                f"A committed job already exists for "
                f"({job.tenant_code}, {job.domain}, {job.file_date}); "
                f"set replace_existing=true to override",
                existing_job_id=str(prior_job.id),
            )

        job.status = "COMMITTING"
        self.db.commit()

        try:
            replaced_job_id: Optional[uuid.UUID] = None

            if prior_job and replace_existing:
                self._archive_prior_job(prior_job, job, actor_id, actor_ip)
                replaced_job_id = prior_job.id

            rows_inserted = self._insert_facts(job)

            job.status = "COMMITTED"
            job.committed_at = datetime.utcnow()
            job.error_message = None
            self.db.flush()

            self._audit(
                job_id=job.id,
                actor_user_id=actor_id,
                action="COMMITTED",
                actor_ip=actor_ip,
                details={
                    "rows_inserted": rows_inserted,
                    "replaced_job_id": (
                        str(replaced_job_id) if replaced_job_id else None
                    ),
                    "tenant_code": job.tenant_code,
                    "domain": job.domain,
                    "file_date": job.file_date.isoformat(),
                },
            )

            self.db.commit()
            self.db.refresh(job)

            # New fare rows have landed and are durable, so re-evaluate this
            # tenant's alert rules. Five rules, all load-bearing:
            #   * AFTER the commit, so an alert can only ever describe rows that
            #     actually exist;
            #   * dispatch only, never inline — commit_job already owns the
            #     longest transaction in the app and evaluation is not its job;
            #   * every exception swallowed, because a Redis outage must not
            #     fail an ingestion that has already succeeded;
            #   * imported lazily, to keep celery out of the ingestion import
            #     graph (same contract redbeat_sync documents);
            #   * placed here rather than in sftp_pull, so the one edit covers
            #     both the manual upload and the scheduled pull.
            # Inert for DreamAir, which never ingests in the demo — this is what
            # gives the real tenants sub-minute alerts.
            if (job.domain or "").upper() == "AIRLINE":
                try:
                    from app.tasks.alerts_eval import evaluate_tenant_task

                    evaluate_tenant_task.apply_async(
                        args=[str(job.tenant_id), job.tenant_code,
                              job.file_date.isoformat() if job.file_date else None],
                        countdown=5,
                    )
                except Exception:
                    # Not this module's `logger`: it is an app.* logger, which
                    # does not propagate in this container, so a failure here
                    # would be invisible. uvicorn.error is the convention.
                    logging.getLogger("uvicorn.error").warning(
                        "ALERT_EVAL_DISPATCH_FAILED job=%s tenant=%s",
                        job.id, job.tenant_code, exc_info=True,
                    )

            return CommitResult(
                job=job,
                rows_inserted=rows_inserted,
                replaced_job_id=replaced_job_id,
            )

        except Exception as exc:
            self.db.rollback()
            # Mark FAILED in a fresh transaction so the audit trail still
            # records what happened.
            job = self._get_job(job_id)
            job.status = "FAILED"
            job.error_message = str(exc)[:1000]
            self._audit(
                job_id=job.id,
                actor_user_id=actor_id,
                action="REJECTED",
                actor_ip=actor_ip,
                details={"phase": "commit", "error": str(exc)[:1000]},
            )
            self.db.commit()
            raise

    def cancel_job(
        self,
        job_id: uuid.UUID | str,
        user_payload: dict,
        actor_ip: Optional[str] = None,
    ) -> IngestionJob:
        actor_id = self._require_admin(user_payload)
        job = self._get_job(job_id)

        if job.status not in {"STAGED", "VALIDATED"}:
            raise IngestionStateError(
                f"job {job.id} status is {job.status}; "
                "only STAGED or VALIDATED jobs can be cancelled"
            )

        staging_dir = self.staging_root / str(job.id)
        if staging_dir.exists():
            shutil.rmtree(staging_dir, ignore_errors=True)

        job.status = "REJECTED"
        job.error_message = "Cancelled by user"

        self._audit(
            job_id=job.id,
            actor_user_id=actor_id,
            action="CANCELLED",
            actor_ip=actor_ip,
            details={"prior_status": job.status},
        )

        self.db.commit()
        self.db.refresh(job)
        return job

    # ── Internal helpers ──────────────────────────

    def _require_admin(self, user_payload: dict) -> uuid.UUID:
        identity = _identity_from_payload(user_payload)
        roles = _roles_from_payload(user_payload)
        if not is_platform_admin(identity, roles):
            raise IngestionAuthError(
                "Skywave platform admin required for ingestion operations"
            )
        return _ensure_actor_uuid(user_payload)

    def _resolve_tenant_id(self, tenant_code: str) -> uuid.UUID:
        slug = tenant_code.lower()
        row = self.db.execute(
            text("SELECT id FROM tenant WHERE slug = :slug"),
            {"slug": slug},
        ).first()
        if not row:
            raise IngestionConfigError(
                f"No tenant row found for slug '{slug}'; "
                "expected one of (jy, pw, fjl)"
            )
        return row[0]

    def _get_job(self, job_id: uuid.UUID | str) -> IngestionJob:
        try:
            jid = uuid.UUID(str(job_id))
        except (ValueError, TypeError) as exc:
            raise IngestionNotFoundError(
                f"Invalid job id: {job_id}"
            ) from exc
        job = self.db.query(IngestionJob).filter(IngestionJob.id == jid).first()
        if not job:
            raise IngestionNotFoundError(f"No ingestion job with id {jid}")
        return job

    def _staging_path(self, job: IngestionJob) -> Path:
        return self.staging_root / str(job.id) / job.filename

    @staticmethod
    def _date_field_for(domain: str) -> str:
        if domain == "VELOCITY":
            return "DepDate"
        return "CapDate"

    @staticmethod
    def _airline_schema_variant(staged_file: Path) -> str:
        # Two AIRLINE feed schemas exist in the wild: the LEGACY ~80-column
        # variant (header includes "CapDate") and the NEW 45-column variant
        # introduced post-2026-05 (header includes "CaptureDate"). We peek
        # at the first data row's keys (which mirror the header row for
        # both CSV and XLSX via read_data_file) to pick the path.
        first = next(read_data_file(str(staged_file)), None)
        if first is None:
            return "UNKNOWN"
        headers = {str(k).strip() for k in first.keys() if k is not None}
        if "CapDate" in headers:
            return "LEGACY"
        if "CaptureDate" in headers:
            return "NEW"
        return "UNKNOWN"

    def _find_prior_committed(self, job: IngestionJob) -> Optional[IngestionJob]:
        return (
            self.db.query(IngestionJob)
            .filter(
                IngestionJob.id != job.id,
                IngestionJob.tenant_code == job.tenant_code,
                IngestionJob.domain == job.domain,
                IngestionJob.file_date == job.file_date,
                IngestionJob.status == "COMMITTED",
            )
            .first()
        )

    def _archive_prior_job(
        self,
        prior: IngestionJob,
        new_job: IngestionJob,
        actor_id: uuid.UUID,
        actor_ip: Optional[str],
    ) -> None:
        # Delete prior fact rows so the new commit can re-load cleanly.
        # ``DELETE`` keeps the audit trail (the prior IngestionJob row
        # itself stays, just flipped to status=REPLACED). No source_file
        # scope here: replace-on-commit replaces the whole day.
        self._delete_facts_for_day(
            prior.domain, prior.tenant_code, prior.file_date,
        )

        prior.status = "REPLACED"
        prior.replaced_by_job_id = new_job.id

        self._audit(
            job_id=prior.id,
            actor_user_id=actor_id,
            action="REPLACED",
            actor_ip=actor_ip,
            details={
                "replaced_by_job_id": str(new_job.id),
                "new_filename": new_job.filename,
            },
        )

    # Map domain → the fact table its rows land in. Fixed allow-map so
    # the table name can be interpolated into DELETE SQL safely (never
    # from user input).
    _FACT_TABLE_BY_DOMAIN = {
        "AIRLINE": "airline_cpi_snapshot",
        "VELOCITY": "velocity_snapshot",
        "CFL": "cfl_cpi_snapshot",
    }

    def _delete_facts_for_day(
        self,
        domain: str,
        tenant_code: str,
        report_date: date,
        source_file: Optional[str] = None,
    ) -> int:
        """DELETE fact rows for one ingested day. Returns rows deleted.

        Scopes to ``(tenant_code, report_date)`` — the same key the
        replace-on-commit path (``_archive_prior_job``) uses. When
        ``source_file`` is given the delete is narrowed to that single
        file's rows, so a co-day file in the same domain is untouched
        (the explicit per-file delete passes it; the archive path passes
        None to replace the whole day, preserving prior behaviour).
        """
        table = self._FACT_TABLE_BY_DOMAIN.get(domain)
        if table is None:
            raise IngestionConfigError(f"Unknown domain: {domain}")
        sql = (
            f"DELETE FROM {table} "  # table from fixed allow-map above
            "WHERE tenant_code = :tc AND report_date = :rd"
        )
        params: dict[str, Any] = {"tc": tenant_code, "rd": report_date}
        if source_file is not None:
            sql += " AND source_file = :sf"
            params["sf"] = source_file
        result = self.db.execute(text(sql), params)
        return result.rowcount or 0

    def delete_committed_file(
        self,
        job_id: uuid.UUID | str,
        user_payload: dict,
        actor_ip: Optional[str] = None,
    ) -> dict[str, Any]:
        """Delete one committed file's fact rows and free it for re-pull.

        Removes exactly the rows this file loaded (``tenant_code`` +
        ``report_date`` + ``source_file``), clears the SFTP dedup
        marker(s) tied to the job so the same or an updated file can be
        pulled again later, flips the job to ``DELETED``, and writes an
        audit entry — all in a single transaction.

        Only ``COMMITTED`` jobs are deletable; any other status raises
        ``IngestionStateError``.
        """
        actor_id = self._require_admin(user_payload)
        job = self._get_job(job_id)

        if job.status != "COMMITTED":
            raise IngestionStateError(
                f"job {job.id} status is {job.status}; only COMMITTED "
                "files can have their data deleted"
            )

        try:
            rows_deleted = self._delete_facts_for_day(
                job.domain,
                job.tenant_code,
                job.file_date,
                source_file=job.filename,
            )

            # Keep the ingested_file marker(s) as a history record but
            # neutralise them:
            #   * flip outcome to 'DELETED' so the run's Files list shows
            #     the file was purged (and the delete button self-disables);
            #   * tombstone sha256 so a later re-pull of the SAME file is
            #     not blocked by the (sha256, remote_filename) dedup gate —
            #     a tombstone can never equal a real 64-hex digest, so the
            #     re-pull proceeds and inserts a fresh marker. The Re-ingest
            #     button stays usable because the row (schedule_id +
            #     remote_filename) survives.
            marker_rows = self.db.execute(
                text(
                    "SELECT id, run_id FROM ingested_file "
                    "WHERE ingestion_job_id = :jid"
                ),
                {"jid": job.id},
            ).mappings().all()
            affected_runs: set[uuid.UUID] = set()
            for m in marker_rows:
                self.db.execute(
                    text(
                        "UPDATE ingested_file "
                        "SET outcome = 'DELETED', sha256 = :sha "
                        "WHERE id = :id"
                    ),
                    {"sha": f"deleted-{m['id']}"[:64], "id": m["id"]},
                )
                if m["run_id"] is not None:
                    affected_runs.add(m["run_id"])

            # Refresh each affected run: recompute its committed-file count;
            # once none remain COMMITTED, mark the whole run DELETED so the
            # Ingestion Runs list reflects that its data is gone.
            for rid in affected_runs:
                committed = self.db.execute(
                    text(
                        "SELECT count(*) FROM ingested_file "
                        "WHERE run_id = :rid AND outcome = 'COMMITTED'"
                    ),
                    {"rid": rid},
                ).scalar() or 0
                if committed == 0:
                    self.db.execute(
                        text(
                            "UPDATE ingestion_run "
                            "SET status = 'DELETED', jobs_committed = 0 "
                            "WHERE id = :rid"
                        ),
                        {"rid": rid},
                    )
                else:
                    self.db.execute(
                        text(
                            "UPDATE ingestion_run SET jobs_committed = :c "
                            "WHERE id = :rid"
                        ),
                        {"c": committed, "rid": rid},
                    )

            job.status = "DELETED"
            job.error_message = None

            details: dict[str, Any] = {
                "rows_deleted": rows_deleted,
                "tenant_code": job.tenant_code,
                "domain": job.domain,
                "file_date": job.file_date.isoformat(),
                "source_file": job.filename,
            }
            self._audit(
                job_id=job.id,
                actor_user_id=actor_id,
                action="DELETED",
                actor_ip=actor_ip,
                details=details,
            )

            self.db.commit()
            self.db.refresh(job)
            return {"job_id": str(job.id), **details}
        except Exception:
            self.db.rollback()
            raise

    def _insert_facts(self, job: IngestionJob) -> int:
        staged_file = self._staging_path(job)
        if not staged_file.exists():
            raise IngestionValidationError(
                f"Staged file missing for commit: {staged_file}"
            )
        if job.domain == "AIRLINE":
            return self._insert_airline_rows(job, staged_file)
        if job.domain == "VELOCITY":
            return self._insert_velocity_rows(job, staged_file)
        if job.domain == "CFL":
            return self._insert_cfl_rows(job, staged_file)
        raise IngestionConfigError(f"Unknown domain: {job.domain}")

    def _insert_airline_rows(
        self, job: IngestionJob, staged_file: Path
    ) -> int:
        # Dispatch on header shape. Migration 023 already dropped the
        # legacy `pos`/`poa`/`pod`/`poc` columns and added `ref_pos` /
        # `comp_pos` / `ref_channel` / `comp_channel`, so both branches
        # write the post-023 column set.
        variant = self._airline_schema_variant(staged_file)
        if variant == "NEW":
            return self._insert_airline_rows_new(job, staged_file)
        if variant == "LEGACY":
            return self._insert_airline_rows_legacy(job, staged_file)
        raise IngestionValidationError(
            f"Unrecognized AIRLINE schema in {staged_file.name}: "
            "expected a 'CapDate' (legacy) or 'CaptureDate' (new) header"
        )

    def _insert_airline_rows_legacy(
        self, job: IngestionJob, staged_file: Path
    ) -> int:
        sql = text(
            """
            INSERT INTO airline_cpi_snapshot (
                id, tenant_id, cap_date, cap_time, trip_type,
                ref_al, ref_flt_num, ref_org, ref_dst, ref_dep_date,
                ref_cab_code, ref_tot_fare, ref_base_fare, ref_tax,
                ref_yq, ref_seats, ref_curr,
                comp_al, comp_flt_num, comp_org, comp_dst, comp_dep_date,
                comp_cab_code, comp_tot_fare, comp_base_fare, comp_tax,
                comp_yq, comp_seats, comp_curr,
                ref_pos, comp_pos, data_owner, tenant_code, business_type,
                report_date, source_file, loaded_at,
                -- Phase 2C: 47 new dictionary columns (migration 022)
                ref_dep_time, ref_arr_time, ref_stops, ref_via,
                ref_ff_code, ref_cab_name, ref_bkg_class, ref_yr,
                ref_anc_price, ref_anc_type, ref_equip_code,
                ref_ret_flt_num, ref_ret_dep_date, ref_ret_dep_time,
                ref_ret_arr_time, ref_ret_stops, ref_ret_via,
                ref_ret_cab_name, ref_ret_cab_code, ref_ret_bkg_class,
                ref_ret_seats, ref_ret_equip_code,
                comp_dep_time, comp_arr_time, comp_stops, comp_via,
                comp_ff_code, comp_cab_name, comp_bkg_class, comp_yr,
                comp_anc_price, comp_anc_type, comp_equip_code,
                comp_ret_flt_num, comp_ret_dep_date, comp_ret_dep_time,
                comp_ret_arr_time, comp_ret_stops, comp_ret_via,
                comp_ret_cab_name, comp_ret_cab_code, comp_ret_bkg_class,
                comp_ret_seats, comp_ret_equip_code,
                path
            ) VALUES (
                :id, :tid, :cd, :ct, :tt,
                :ra, :rf, :ro, :rd, :rdd,
                :rcc, :rtf, :rbf, :rtax,
                :ryq, :rs, :rcur,
                :ca, :cf, :co, :cdst, :cdd,
                :ccc, :ctf, :cbf, :ctax,
                :cyq, :cs, :ccur,
                :ref_pos, :comp_pos, :owner, :tcode, :btype,
                :rdate, :sfile, now(),
                :ref_dep_time, :ref_arr_time, :ref_stops, :ref_via,
                :ref_ff_code, :ref_cab_name, :ref_bkg_class, :ref_yr,
                :ref_anc_price, :ref_anc_type, :ref_equip_code,
                :ref_ret_flt_num, :ref_ret_dep_date, :ref_ret_dep_time,
                :ref_ret_arr_time, :ref_ret_stops, :ref_ret_via,
                :ref_ret_cab_name, :ref_ret_cab_code, :ref_ret_bkg_class,
                :ref_ret_seats, :ref_ret_equip_code,
                :comp_dep_time, :comp_arr_time, :comp_stops, :comp_via,
                :comp_ff_code, :comp_cab_name, :comp_bkg_class, :comp_yr,
                :comp_anc_price, :comp_anc_type, :comp_equip_code,
                :comp_ret_flt_num, :comp_ret_dep_date, :comp_ret_dep_time,
                :comp_ret_arr_time, :comp_ret_stops, :comp_ret_via,
                :comp_ret_cab_name, :comp_ret_cab_code, :comp_ret_bkg_class,
                :comp_ret_seats, :comp_ret_equip_code,
                :path
            )
            """
        )
        inserted = 0
        for row in read_data_file(str(staged_file)):
            cap_date = parse_date(row.get("CapDate"))
            if not cap_date:
                continue
            params = {
                "id": uuid.uuid4(),
                "tid": job.tenant_id,
                # cap_date recorded from the FILENAME (job.file_date),
                # never the in-file CapDate column, so a mis-stamped
                # source file cannot misfile rows under the wrong date.
                # (cap_date is still parsed above only to skip empty rows.)
                "cd": job.file_date,
                "ct": parse_time(row.get("CapTime")) or datetime.now().time(),
                "tt": (row.get("TripType") or "RT")[:4],
                "ra": (row.get("RefAL") or job.tenant_code)[:3],
                "rf": (row.get("RefFltNum") or "")[:64],
                "ro": (row.get("RefOrg") or "")[:4],
                "rd": (row.get("RefDst") or "")[:4],
                "rdd": parse_date(row.get("RefDepDate")) or cap_date,
                "rcc": (row.get("RefCabCode") or "Y")[:4],
                "rtf": safe_float(row.get("RefTotFare")),
                "rbf": safe_float(row.get("RefBaseFare")),
                "rtax": safe_float(row.get("RefTax")),
                "ryq": safe_float(row.get("RefYQ")),
                "rs": _seats_or_default(row.get("RefSeats")),
                "rcur": _currency_or_default(row.get("RefCur"), job.tenant_code),
                "ca": (row.get("CompAL") or "")[:3],
                "cf": (row.get("CompFltNum") or "")[:64],
                "co": (row.get("CompOrg") or row.get("RefOrg") or "")[:4],
                "cdst": (row.get("CompDst") or row.get("RefDst") or "")[:4],
                "cdd": parse_date(row.get("CompDepDate")) or cap_date,
                "ccc": (row.get("CompCabCode") or "Y")[:4],
                "ctf": safe_float(row.get("CompTotFare")),
                "cbf": safe_float(row.get("CompBaseFare")),
                "ctax": safe_float(row.get("CompTax")),
                "cyq": safe_float(row.get("CompYQ")),
                "cs": _seats_or_default(row.get("CompSeats")),
                "ccur": _currency_or_default(row.get("CompCur"), job.tenant_code),
                # ref_pos: post-023 nullable point-of-sale (the host carrier's
                # POS). PW source carries POS; JY legacy source does not.
                # The legacy POA field has no post-023 column; comp_pos is
                # left NULL because the legacy feed had no comp-side POS.
                "ref_pos": ((row.get("POS") or "").strip()[:4] or None),
                "comp_pos": None,
                "owner": job.tenant_code,
                "tcode": job.tenant_code,
                "btype": _business_type_for(job.domain),
                "rdate": job.file_date,
                "sfile": job.filename,
                # ── Phase 2C: 47 new dictionary columns ──
                # Reference flight — outbound additions (11)
                "ref_dep_time": ((row.get("RefDepTime") or "").strip()[:8] or None),
                "ref_arr_time": ((row.get("RefArrTime") or "").strip()[:8] or None),
                "ref_stops": safe_int_nullable(row.get("RefStops")),
                "ref_via": ((row.get("RefVia") or "").strip()[:4] or None),
                "ref_ff_code": ((row.get("RefFFCode") or "").strip()[:20] or None),
                "ref_cab_name": ((row.get("RefCabName") or "").strip()[:20] or None),
                "ref_bkg_class": ((row.get("RefBkgClass") or "").strip()[:16] or None),
                "ref_yr": safe_float(row.get("RefYR")),
                "ref_anc_price": safe_float(row.get("RefAncPrice")),
                "ref_anc_type": ((row.get("RefAncType") or "").strip()[:20] or None),
                # Equipment unification: JY's RefAircraft OR PW's RefEquipCode
                "ref_equip_code": (
                    (row.get("RefAircraft") or row.get("RefEquipCode") or "")
                    .strip()[:128] or None
                ),
                # Reference flight — return-leg (11) — JY-only in source
                "ref_ret_flt_num": ((row.get("RefRetFltNum") or "").strip()[:64] or None),
                "ref_ret_dep_date": parse_date(row.get("RefRetDepDate")),
                "ref_ret_dep_time": ((row.get("RefRetDepTime") or "").strip()[:8] or None),
                "ref_ret_arr_time": ((row.get("RefRetArrTime") or "").strip()[:8] or None),
                "ref_ret_stops": safe_int_nullable(row.get("RefRetStops")),
                "ref_ret_via": ((row.get("RefRetVia") or "").strip()[:4] or None),
                "ref_ret_cab_name": ((row.get("RefRetCabName") or "").strip()[:20] or None),
                "ref_ret_cab_code": ((row.get("RefRetCabCode") or "").strip()[:4] or None),
                "ref_ret_bkg_class": ((row.get("RefRetBkgClass") or "").strip()[:16] or None),
                "ref_ret_seats": safe_int_nullable(row.get("RefRetSeats")),
                # Same dual-name handling as the other three equipment
                # columns: the 76-column layout calls this RefRetEquipCode
                # and only the older JY sheets used RefRetAircraft. Reading
                # just the latter dropped every return equipment code.
                "ref_ret_equip_code": (
                    (row.get("RefRetAircraft") or row.get("RefRetEquipCode") or "")
                    .strip()[:128] or None
                ),
                # Competitor — outbound additions (11)
                "comp_dep_time": ((row.get("CompDepTime") or "").strip()[:8] or None),
                "comp_arr_time": ((row.get("CompArrTime") or "").strip()[:8] or None),
                "comp_stops": safe_int_nullable(row.get("CompStops")),
                "comp_via": ((row.get("CompVia") or "").strip()[:4] or None),
                "comp_ff_code": ((row.get("CompFFCode") or "").strip()[:20] or None),
                "comp_cab_name": ((row.get("CompCabName") or "").strip()[:20] or None),
                "comp_bkg_class": ((row.get("CompBkgClass") or "").strip()[:16] or None),
                "comp_yr": safe_float(row.get("CompYR")),
                "comp_anc_price": safe_float(row.get("CompAncPrice")),
                "comp_anc_type": ((row.get("CompAncType") or "").strip()[:20] or None),
                "comp_equip_code": (
                    (row.get("CompAircraft") or row.get("CompEquipCode") or "")
                    .strip()[:128] or None
                ),
                # Competitor — return-leg (11) — JY-only in source
                "comp_ret_flt_num": ((row.get("CompRetFltNum") or "").strip()[:64] or None),
                "comp_ret_dep_date": parse_date(row.get("CompRetDepDate")),
                "comp_ret_dep_time": ((row.get("CompRetDepTime") or "").strip()[:8] or None),
                "comp_ret_arr_time": ((row.get("CompRetArrTime") or "").strip()[:8] or None),
                "comp_ret_stops": safe_int_nullable(row.get("CompRetStops")),
                "comp_ret_via": ((row.get("CompRetVia") or "").strip()[:4] or None),
                "comp_ret_cab_name": ((row.get("CompRetCabName") or "").strip()[:20] or None),
                "comp_ret_cab_code": ((row.get("CompRetCabCode") or "").strip()[:4] or None),
                "comp_ret_bkg_class": ((row.get("CompRetBkgClass") or "").strip()[:16] or None),
                "comp_ret_seats": safe_int_nullable(row.get("CompRetSeats")),
                "comp_ret_equip_code": (
                    (row.get("CompRetAircraft") or row.get("CompRetEquipCode") or "")
                    .strip()[:128] or None
                ),
                # Provenance (no source carries today).
                # POD/POC dropped in migration 023 — no DB target remains.
                "path": ((row.get("Path") or "").strip()[:50] or None),
            }
            self.db.execute(sql, params)
            inserted += 1
        return inserted

    def _insert_airline_rows_new(
        self, job: IngestionJob, staged_file: Path
    ) -> int:
        # New 45-column JY airline feed (post-2026-05). Column mapping
        # from file header → airline_cpi_snapshot column:
        #
        #   CaptureDate            → cap_date             (NOT NULL)
        #   CaptureTime            → cap_time             (NOT NULL)
        #   DepCode                → ref_flt_num          (NOT NULL, [:64])
        #   Org                    → ref_org              (NOT NULL)
        #   Dest                   → ref_dst              (NOT NULL)
        #   DepDate                → ref_dep_date         (NOT NULL)
        #   DepTime                → ref_dep_time         (nullable)
        #   ArrTime                → ref_arr_time         (nullable)
        #   HostFare               → ref_tot_fare,        (NOT NULL)
        #                            ref_base_fare        (feed does not split)
        #   itinerary_type         → ref_stops            (Nonstop→0 else 1)
        #   host_marketing_carrier → ref_al               (NOT NULL)
        #   leg_sequence           → path                 (nullable, [:50])
        #   connection_points      → ref_via              (nullable)
        #   CompCode / competitor_operating_carrier
        #                          → comp_al              (NOT NULL)
        #   CompDepCode            → comp_flt_num         (NOT NULL, [:64])
        #   CompDepOrg             → comp_org             (NOT NULL)
        #   CompDepDest            → comp_dst             (NOT NULL)
        #   CompDepDate            → comp_dep_date        (NOT NULL)
        #   CompDepTime            → comp_dep_time        (nullable)
        #   CompArrTime            → comp_arr_time        (nullable)
        #   CompFare               → comp_tot_fare,       (NOT NULL)
        #                            comp_base_fare       (feed does not split)
        #   comp_itinerary_type    → comp_stops           (Nonstop→0 else 1)
        #   cabin                  → ref_cab_code/code,   (NOT NULL [:4])
        #                            ref_cab_name/name    (full string [:20])
        #   comp_connection_points → comp_via             (nullable)
        #   pos_country            → ref_pos, comp_pos    (nullable)
        #   channel                → ref_channel, comp_channel (nullable)
        #   currency               → ref_curr, comp_curr  (nullable)
        #   competitor_seats_left_hint → comp_seats       (NOT NULL int)
        #
        # Fields with no DB equivalent (intentionally skipped, not warnings
        # per row to avoid log spam): ID, num_legs, through_flight_flag,
        # comp_leg_sequence, fare_tax_included_flag, competitor_sold_out_flag,
        # days_to_departure, dow, ingest_batch_id, source_record_id,
        # data_source, created_ts, user_action_flag, action_by,
        # before_json, after_json.
        #
        # NOT NULL DB columns with no source field (defaulted): trip_type='OW'
        # (the feed compares one-way pairs per row), ref_tax=0, ref_yq=0,
        # ref_seats=9, comp_tax=0, comp_yq=0.
        sql = text(
            """
            INSERT INTO airline_cpi_snapshot (
                id, tenant_id, cap_date, cap_time, trip_type,
                ref_al, ref_flt_num, ref_org, ref_dst, ref_dep_date,
                ref_cab_code, ref_tot_fare, ref_base_fare, ref_tax,
                ref_yq, ref_seats, ref_curr,
                comp_al, comp_flt_num, comp_org, comp_dst, comp_dep_date,
                comp_cab_code, comp_tot_fare, comp_base_fare, comp_tax,
                comp_yq, comp_seats, comp_curr,
                ref_dep_time, ref_arr_time, ref_stops, ref_via,
                ref_cab_name,
                comp_dep_time, comp_arr_time, comp_stops, comp_via,
                comp_cab_name,
                ref_pos, ref_channel, comp_pos, comp_channel,
                path,
                data_owner, tenant_code, business_type,
                report_date, source_file, loaded_at
            ) VALUES (
                :id, :tid, :cd, :ct, :tt,
                :ra, :rf, :ro, :rd, :rdd,
                :rcc, :rtf, :rbf, :rtax,
                :ryq, :rs, :rcur,
                :ca, :cf, :co, :cdst, :cdd,
                :ccc, :ctf, :cbf, :ctax,
                :cyq, :cs, :ccur,
                :ref_dep_time, :ref_arr_time, :ref_stops, :ref_via,
                :ref_cab_name,
                :comp_dep_time, :comp_arr_time, :comp_stops, :comp_via,
                :comp_cab_name,
                :ref_pos, :ref_channel, :comp_pos, :comp_channel,
                :path,
                :owner, :tcode, :btype,
                :rdate, :sfile, now()
            )
            """
        )
        inserted = 0
        for row in read_data_file(str(staged_file)):
            cap_date = parse_date(row.get("CaptureDate"))
            if not cap_date:
                continue
            cabin_name = (row.get("cabin") or "").strip()
            cabin_code = (cabin_name or "Y")[:4]

            def _stops_from(itin: str) -> Optional[int]:
                t = (itin or "").strip().lower()
                if not t:
                    return None
                return 0 if t == "nonstop" else 1

            host_al = (row.get("host_marketing_carrier") or job.tenant_code or "").strip()[:3]
            comp_al_val = (
                (row.get("CompCode") or row.get("competitor_operating_carrier") or "").strip()[:3]
                or "XX"
            )
            # Never leave this None: the column DEFAULT is 'GBP', so a blank
            # currency in the feed would be stored as sterling by omission.
            currency = _currency_or_default(row.get("currency"), job.tenant_code)
            pos_country = (row.get("pos_country") or "").strip()[:4] or None
            channel = (row.get("channel") or "").strip()[:20] or None
            params = {
                "id": uuid.uuid4(),
                "tid": job.tenant_id,
                # cap_date recorded from the FILENAME (job.file_date),
                # never the in-file CaptureDate column — see legacy insert.
                "cd": job.file_date,
                "ct": parse_time(row.get("CaptureTime")) or datetime.now().time(),
                "tt": "OW",
                "ra": host_al or job.tenant_code[:3],
                "rf": (row.get("DepCode") or "").strip()[:64],
                "ro": (row.get("Org") or "").strip()[:4],
                "rd": (row.get("Dest") or "").strip()[:4],
                "rdd": parse_date(row.get("DepDate")) or cap_date,
                "rcc": cabin_code,
                "rtf": safe_float(row.get("HostFare")),
                "rbf": safe_float(row.get("HostFare")),
                "rtax": 0.0,
                "ryq": 0.0,
                "rs": 9,
                "rcur": currency,
                "ca": comp_al_val,
                "cf": (row.get("CompDepCode") or "").strip()[:64],
                "co": (row.get("CompDepOrg") or row.get("Org") or "").strip()[:4],
                "cdst": (row.get("CompDepDest") or row.get("Dest") or "").strip()[:4],
                "cdd": parse_date(row.get("CompDepDate")) or cap_date,
                "ccc": cabin_code,
                "ctf": safe_float(row.get("CompFare")),
                "cbf": safe_float(row.get("CompFare")),
                "ctax": 0.0,
                "cyq": 0.0,
                "cs": _seats_or_default(row.get("competitor_seats_left_hint")),
                "ccur": currency,
                "ref_dep_time": ((row.get("DepTime") or "").strip()[:8] or None),
                "ref_arr_time": ((row.get("ArrTime") or "").strip()[:8] or None),
                "ref_stops": _stops_from(row.get("itinerary_type") or ""),
                "ref_via": ((row.get("connection_points") or "").strip()[:4] or None),
                "ref_cab_name": (cabin_name[:20] or None),
                "comp_dep_time": ((row.get("CompDepTime") or "").strip()[:8] or None),
                "comp_arr_time": ((row.get("CompArrTime") or "").strip()[:8] or None),
                "comp_stops": _stops_from(row.get("comp_itinerary_type") or ""),
                "comp_via": ((row.get("comp_connection_points") or "").strip()[:4] or None),
                "comp_cab_name": (cabin_name[:20] or None),
                "ref_pos": pos_country,
                "ref_channel": channel,
                "comp_pos": pos_country,
                "comp_channel": channel,
                "path": ((row.get("leg_sequence") or "").strip()[:50] or None),
                "owner": job.tenant_code,
                "tcode": job.tenant_code,
                "btype": _business_type_for(job.domain),
                "rdate": job.file_date,
                "sfile": job.filename,
            }
            self.db.execute(sql, params)
            inserted += 1
        return inserted

    def _insert_velocity_rows(
        self, job: IngestionJob, staged_file: Path
    ) -> int:
        sql = text(
            """
            INSERT INTO velocity_snapshot (
                id, tenant_id, dep_date, dep_time, dep_code, city_pair,
                origin, destination, eqp, legseg_type, leg_seg_order,
                days_left, compartment, current_booking, capacity,
                actual_seat_factor, forecasted_seat_factor,
                data_owner, tenant_code, airline_code, business_type, report_date,
                source_file, loaded_at
            ) VALUES (
                :id, :tid, :dd, :dt, :dc, :cp,
                :org, :dst, :eqp, :lst, :lso,
                :dl, :comp, :cb, :cap,
                :asf, :fsf,
                :owner, :tcode, :ac, :btype, :rdate,
                :sfile, now()
            )
            """
        )
        inserted = 0
        for row in read_data_file(str(staged_file), domain=job.domain):
            dep_date = parse_velocity_date(row.get("DepDate"))
            if not dep_date:
                continue
            city_pair = (row.get("CityPair") or "").strip()
            origin = city_pair[:3] if len(city_pair) >= 6 else ""
            destination = city_pair[3:] if len(city_pair) >= 6 else ""
            params = {
                "id": uuid.uuid4(),
                "tid": job.tenant_id,
                "dd": dep_date,
                "dt": (row.get("DepTime") or "").strip()[:8],
                "dc": (row.get("DepCode") or "").strip()[:10],
                "cp": city_pair[:8],
                "org": origin[:4],
                "dst": destination[:4],
                "eqp": (row.get("Eqp") or "").strip()[:8],
                "lst": (row.get("LegsegType") or "").strip()[:10],
                "lso": safe_int(row.get("LegSegOrder") or 1),
                "dl": safe_int(row.get("Days_Left") or 0),
                "comp": (row.get("Compartment") or "Y").strip()[:4],
                "cb": safe_int(row.get("Current_Booking") or 0),
                "cap": safe_int(row.get("Capacity") or 0),
                "asf": safe_int(row.get("Actual_Seat_Factor") or 0),
                "fsf": safe_int(row.get("Forecasted_Seat_Factor") or 0),
                "owner": job.tenant_code,
                "tcode": job.tenant_code,
                "ac": job.tenant_code,
                "btype": _business_type_for(job.domain),
                "rdate": job.file_date,
                "sfile": job.filename,
            }
            self.db.execute(sql, params)
            inserted += 1
        return inserted

    def _insert_cfl_rows(self, job: IngestionJob, staged_file: Path) -> int:
        # Note: existing fare columns (total_fare, out_per_pax_fare, etc.) keep
        # safe_float() semantics (0.0 for missing) to preserve backwards
        # compatibility. The 33 new columns added in migration 024 use
        # safe_float_nullable() so a missing return-leg fare is NULL rather
        # than 0.0, which keeps averages and IS NULL filters accurate.
        sql = text(
            """
            INSERT INTO cfl_cpi_snapshot (
                id, tenant_id, data_owner, cap_date, cap_time, trip_type,
                source, org, dest, out_dep_date, out_dep_time,
                out_arr_date, out_arr_time,
                prod_family, out_equip_name, out_cab_type,
                out_cabin_desc, out_seat_type, out_num_cabs, out_seat_fare, out_num_seats,
                total_fare, out_per_pax_fare, out_veh_fare, out_cab_fare,
                out_taxes, out_num_pax, veh_size, curr_code, out_avail,
                ret_dep_date, ret_dep_time, ret_arr_date, ret_arr_time,
                ret_equip_name, ret_cab_type, ret_cab_desc, ret_seat_type, ret_avail,
                ret_per_pax_fare, ret_num_pax, ret_veh_fare, ret_cab_fare,
                ret_num_cabs, ret_seat_fare, ret_num_seats, ret_taxes,
                tot_per_pax_fare, tot_num_pax, tot_veh_fare, tot_cab_fare,
                tot_num_cabs, tot_seat_fare, tot_num_seats, tot_taxes,
                duration,
                tenant_code, business_type, report_date, source_file,
                loaded_at
            ) VALUES (
                :id, :tid, :owner, :cd, :ct, :tt,
                :src, :org, :dst, :odd, :odt,
                :oad, :oat,
                :pf, :oen, :oct,
                :ocd, :ost, :onc, :osf, :ons,
                :tf, :oppf, :ovf, :ocf,
                :otx, :onp, :vs, :cc, :oa,
                :rdd, :rdt, :rad, :rat,
                :ren, :rct, :rcd, :rst, :rav,
                :rppf, :rnp, :rvf, :rcf,
                :rnc, :rsf, :rns, :rtx,
                :tppf, :tnp, :tvf, :tcf,
                :tnc, :tsf, :tns, :ttx,
                :dur,
                :tcode, :btype, :rdate, :sfile,
                now()
            )
            """
        )
        inserted = 0
        for row in read_data_file(str(staged_file)):
            cap_date = parse_date(row.get("CapDate"))
            if not cap_date:
                continue

            def _trim(val: object, n: int) -> str | None:
                """String columns added in 024 are nullable — preserve None
                instead of coercing blank to empty string."""
                if val is None:
                    return None
                s = str(val).strip()
                if not s:
                    return None
                return s[:n]

            params = {
                "id": uuid.uuid4(),
                "tid": job.tenant_id,
                "owner": job.tenant_code,
                # cap_date recorded from the FILENAME (job.file_date),
                # never the in-file CapDate column — see legacy insert.
                "cd": job.file_date,
                "ct": parse_time(row.get("CapTime")) or datetime.now().time(),
                "tt": (row.get("TripType") or "ONE_WAY")[:16],
                "src": (row.get("Source") or job.tenant_code)[:64],
                "org": (row.get("Org") or "")[:32],
                "dst": (row.get("Dest") or "")[:32],
                "odd": parse_date(row.get("OutDepDate")) or cap_date,
                "odt": parse_time(row.get("OutDepTime")) or datetime.now().time(),
                # Outbound Arrival (024)
                "oad": parse_date(row.get("OutArrDate")),
                "oat": parse_time(row.get("OutArrTime")),
                "pf": (row.get("ProdFamily") or "Standard")[:64],
                "oen": (row.get("OutEquipName") or "")[:64],
                "oct": (row.get("OutCabType") or "none")[:32],
                # Outbound Descriptions & Seats (024)
                "ocd": _trim(row.get("OutCabinDesc"), 100),
                "ost": _trim(row.get("OutSeatType"), 50),
                "onc": safe_int_nullable(row.get("OutNumCabs")),
                "osf": safe_float_nullable(row.get("OutSeatFare")),
                "ons": safe_int_nullable(row.get("OutNumSeats")),
                # Existing outbound fares (unchanged semantics)
                "tf": safe_float(row.get("TotalFare")),
                "oppf": safe_float(row.get("OutPerPaxFare")),
                "ovf": safe_float(row.get("OutVehFare")),
                "ocf": safe_float(row.get("OutCabFare")),
                "otx": safe_float(row.get("OutTaxes")),
                "onp": safe_int(row.get("OutNumPax") or 1),
                "vs": (row.get("VehSize") or "none")[:16],
                "cc": (row.get("CurrCode") or "EUR")[:4],
                "oa": (row.get("OutAvail") or "Available")[:16],
                # Return Journey — Schedule & Product (024)
                "rdd": parse_date(row.get("RetDepDate")),
                "rdt": parse_time(row.get("RetDepTime")),
                "rad": parse_date(row.get("RetArrDate")),
                "rat": parse_time(row.get("RetArrTime")),
                "ren": _trim(row.get("RetEquipName"), 64),
                "rct": _trim(row.get("RetCabType"), 50),
                "rcd": _trim(row.get("RetCabDesc"), 100),
                "rst": _trim(row.get("RetSeatType"), 50),
                "rav": _trim(row.get("RetAvail"), 16),
                # Return Journey — Fares (024)
                "rppf": safe_float_nullable(row.get("RetPerPaxFare")),
                "rnp":  safe_int_nullable(row.get("RetNumPax")),
                "rvf":  safe_float_nullable(row.get("RetVehFare")),
                "rcf":  safe_float_nullable(row.get("RetCabFare")),
                "rnc":  safe_int_nullable(row.get("RetNumCabs")),
                "rsf":  safe_float_nullable(row.get("RetSeatFare")),
                "rns":  safe_int_nullable(row.get("RetNumSeats")),
                "rtx":  safe_float_nullable(row.get("RetTaxes")),
                # Total/Combined Fares (024)
                "tppf": safe_float_nullable(row.get("TotPerPaxFare")),
                "tnp":  safe_int_nullable(row.get("TotNumPax")),
                "tvf":  safe_float_nullable(row.get("TotVehFare")),
                "tcf":  safe_float_nullable(row.get("TotCabFare")),
                "tnc":  safe_int_nullable(row.get("TotNumCabs")),
                "tsf":  safe_float_nullable(row.get("TotSeatFare")),
                "tns":  safe_int_nullable(row.get("TotNumSeats")),
                "ttx":  safe_float_nullable(row.get("TotTaxes")),
                # Duration (024)
                "dur":  safe_int_nullable(row.get("Duration")),
                "tcode": job.tenant_code,
                "btype": _business_type_for(job.domain),
                "rdate": job.file_date,
                "sfile": job.filename,
            }
            self.db.execute(sql, params)
            inserted += 1
        return inserted

    def _audit(
        self,
        job_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        action: str,
        actor_ip: Optional[str],
        details: Optional[dict] = None,
    ) -> None:
        entry = IngestionAuditLog(
            id=uuid.uuid4(),
            job_id=job_id,
            actor_user_id=actor_user_id,
            action=action,
            actor_ip=actor_ip,
            details=details or {},
        )
        self.db.add(entry)
        self.db.flush()
