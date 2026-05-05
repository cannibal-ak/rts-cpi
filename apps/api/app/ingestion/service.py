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
    safe_int,
)
from app.models.ingestion import IngestionAuditLog, IngestionJob


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

        existing_committed = (
            self.db.query(IngestionJob)
            .filter(
                IngestionJob.file_hash == file_hash,
                IngestionJob.status == "COMMITTED",
            )
            .first()
        )
        if existing_committed:
            return UploadResult(
                job=existing_committed,
                duplicate=True,
                conflict=False,
                existing_job_id=existing_committed.id,
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
        rejection_reasons: list[dict[str, str]] = []

        date_field = self._date_field_for(job.domain)

        for row in read_data_file(str(staged_file)):
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
            valid += 1

        summary = {
            "total": total,
            "valid": valid,
            "rejected": rejected,
            "rejection_reasons_sample": rejection_reasons,
            "date_field_checked": date_field,
        }

        if total == 0:
            job.status = "REJECTED"
            job.error_message = "Staged file contains zero data rows"
        elif valid == 0:
            job.status = "REJECTED"
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
        # itself stays, just flipped to status=REPLACED).
        if prior.domain == "AIRLINE":
            self.db.execute(
                text(
                    "DELETE FROM airline_cpi_snapshot "
                    "WHERE tenant_code = :tc AND report_date = :rd"
                ),
                {"tc": prior.tenant_code, "rd": prior.file_date},
            )
        elif prior.domain == "VELOCITY":
            self.db.execute(
                text(
                    "DELETE FROM velocity_snapshot "
                    "WHERE tenant_code = :tc AND report_date = :rd"
                ),
                {"tc": prior.tenant_code, "rd": prior.file_date},
            )
        elif prior.domain == "CFL":
            self.db.execute(
                text(
                    "DELETE FROM cfl_cpi_snapshot "
                    "WHERE tenant_code = :tc AND report_date = :rd"
                ),
                {"tc": prior.tenant_code, "rd": prior.file_date},
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
        sql = text(
            """
            INSERT INTO airline_cpi_snapshot (
                id, tenant_id, cap_date, cap_time, trip_type,
                ref_al, ref_flt_num, ref_org, ref_dst, ref_dep_date,
                ref_cab_code, ref_tot_fare, ref_base_fare, ref_tax,
                ref_yq, ref_seats,
                comp_al, comp_flt_num, comp_org, comp_dst, comp_dep_date,
                comp_cab_code, comp_tot_fare, comp_base_fare, comp_tax,
                comp_yq, comp_seats,
                pos, poa, data_owner, tenant_code, business_type,
                report_date, source_file, loaded_at
            ) VALUES (
                :id, :tid, :cd, :ct, :tt,
                :ra, :rf, :ro, :rd, :rdd,
                :rcc, :rtf, :rbf, :rtax,
                :ryq, :rs,
                :ca, :cf, :co, :cdst, :cdd,
                :ccc, :ctf, :cbf, :ctax,
                :cyq, :cs,
                'US', 'US', :owner, :tcode, :btype,
                :rdate, :sfile, now()
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
                "cd": cap_date,
                "ct": parse_time(row.get("CapTime")) or datetime.now().time(),
                "tt": (row.get("TripType") or "RT")[:4],
                "ra": (row.get("RefAL") or job.tenant_code)[:3],
                "rf": (row.get("RefFltNum") or "")[:10],
                "ro": (row.get("RefOrg") or "")[:4],
                "rd": (row.get("RefDst") or "")[:4],
                "rdd": parse_date(row.get("RefDepDate")) or cap_date,
                "rcc": (row.get("RefCabCode") or "Y")[:4],
                "rtf": safe_float(row.get("RefTotFare")),
                "rbf": safe_float(row.get("RefBaseFare")),
                "rtax": safe_float(row.get("RefTax")),
                "ryq": safe_float(row.get("RefYQ")),
                "rs": safe_int(row.get("RefSeats") or 9),
                "ca": (row.get("CompAL") or "")[:3],
                "cf": (row.get("CompFltNum") or "")[:10],
                "co": (row.get("CompOrg") or row.get("RefOrg") or "")[:4],
                "cdst": (row.get("CompDst") or row.get("RefDst") or "")[:4],
                "cdd": parse_date(row.get("CompDepDate")) or cap_date,
                "ccc": (row.get("CompCabCode") or "Y")[:4],
                "ctf": safe_float(row.get("CompTotFare")),
                "cbf": safe_float(row.get("CompBaseFare")),
                "ctax": safe_float(row.get("CompTax")),
                "cyq": safe_float(row.get("CompYQ")),
                "cs": safe_int(row.get("CompSeats") or 9),
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
                airline_code, data_owner, tenant_code, business_type,
                report_date, source_file, loaded_at
            ) VALUES (
                :id, :tid, :dd, :dt, :dc, :cp,
                :org, :dst, :eqp, :lst, :lso,
                :dl, :comp, :cb, :cap,
                :asf, :fsf,
                :acode, :owner, :tcode, :btype,
                :rdate, :sfile, now()
            )
            """
        )
        inserted = 0
        for row in read_data_file(str(staged_file)):
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
                "acode": job.tenant_code,
                "owner": job.tenant_code,
                "tcode": job.tenant_code,
                "btype": _business_type_for(job.domain),
                "rdate": job.file_date,
                "sfile": job.filename,
            }
            self.db.execute(sql, params)
            inserted += 1
        return inserted

    def _insert_cfl_rows(self, job: IngestionJob, staged_file: Path) -> int:
        sql = text(
            """
            INSERT INTO cfl_cpi_snapshot (
                id, tenant_id, data_owner, cap_date, cap_time, trip_type,
                source, org, dest, out_dep_date, out_dep_time,
                prod_family, out_equip_name, out_cab_type,
                total_fare, out_per_pax_fare, out_veh_fare, out_cab_fare,
                out_taxes, out_num_pax, veh_size, curr_code, out_avail,
                tenant_code, business_type, report_date, source_file,
                loaded_at
            ) VALUES (
                :id, :tid, :owner, :cd, :ct, :tt,
                :src, :org, :dst, :odd, :odt,
                :pf, :oen, :oct,
                :tf, :oppf, :ovf, :ocf,
                :otx, :onp, :vs, :cc, :oa,
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
            params = {
                "id": uuid.uuid4(),
                "tid": job.tenant_id,
                "owner": job.tenant_code,
                "cd": cap_date,
                "ct": parse_time(row.get("CapTime")) or datetime.now().time(),
                "tt": (row.get("TripType") or "ONE_WAY")[:16],
                "src": (row.get("Source") or job.tenant_code)[:64],
                "org": (row.get("Org") or "")[:32],
                "dst": (row.get("Dest") or "")[:32],
                "odd": parse_date(row.get("OutDepDate")) or cap_date,
                "odt": parse_time(row.get("OutDepTime")) or datetime.now().time(),
                "pf": (row.get("ProdFamily") or "Standard")[:64],
                "oen": (row.get("OutEquipName") or "")[:64],
                "oct": (row.get("OutCabType") or "none")[:32],
                "tf": safe_float(row.get("TotalFare")),
                "oppf": safe_float(row.get("OutPerPaxFare")),
                "ovf": safe_float(row.get("OutVehFare")),
                "ocf": safe_float(row.get("OutCabFare")),
                "otx": safe_float(row.get("OutTaxes")),
                "onp": safe_int(row.get("OutNumPax") or 1),
                "vs": (row.get("VehSize") or "none")[:16],
                "cc": (row.get("CurrCode") or "EUR")[:4],
                "oa": (row.get("OutAvail") or "Available")[:16],
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
