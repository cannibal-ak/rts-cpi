"""Unit / integration tests for app.ingestion.service.IngestionService.

These tests run against the real cpi_db and rely on the savepoint-based
``db_session`` fixture in conftest.py to roll back changes after each test.
"""
from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from sqlalchemy import text

from app.ingestion.exceptions import (
    IngestionAuthError,
    IngestionConflictError,
    IngestionFilenameError,
    IngestionNotFoundError,
    IngestionStateError,
)
from app.ingestion.service import IngestionService
from app.models.ingestion import IngestionAuditLog, IngestionJob


# Canonical UUIDs used to verify the Phase 1 fix.
JY_TENANT_UUID = uuid.UUID("dd000000-0000-0000-0000-000000000001")
SKYWAVE_TENANT_UUID = uuid.UUID("a0000000-0000-0000-0000-000000000001")


# Minimal but realistic file fixtures.
PRICING_CSV_HEADER = (
    "CapDate,CapTime,TripType,RefAL,RefFltNum,RefOrg,RefDst,RefDepDate,"
    "RefCabCode,RefTotFare,RefBaseFare,RefTax,RefYQ,RefSeats,"
    "CompAL,CompFltNum,CompOrg,CompDst,CompDepDate,CompCabCode,"
    "CompTotFare,CompBaseFare,CompTax,CompYQ,CompSeats\n"
)
PRICING_CSV_ROW = (
    "01Apr26,09:00,RT,PW,123,LHR,JFK,01Apr26,Y,500,400,50,50,9,"
    "BA,456,LHR,JFK,01Apr26,Y,520,420,50,50,9\n"
)


def _xlsx_bytes_from_csv_strings(header: str, row: str, rows: int) -> bytes:
    """Render a CSV-shaped header + row into a real XLSX byte stream.

    The airline parser dispatches on file extension (.xlsx -> openpyxl),
    so test fixtures must produce real XLSX bytes once PW airline
    follows JY's .xlsx pattern (Phase 3 of the PW-parity work).
    """
    from io import BytesIO
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.append(header.strip().split(","))
    row_values = row.strip().split(",")
    for _ in range(rows):
        ws.append(row_values)
    bio = BytesIO()
    wb.save(bio)
    return bio.getvalue()


def _pricing_pw_bytes(rows: int = 3) -> bytes:
    return _xlsx_bytes_from_csv_strings(PRICING_CSV_HEADER, PRICING_CSV_ROW, rows)


def _pricing_pw_bytes_v2(rows: int = 3) -> bytes:
    """Slightly different content (different fares) for replace tests."""
    row = PRICING_CSV_ROW.replace("500", "999").replace("400", "888")
    return _xlsx_bytes_from_csv_strings(PRICING_CSV_HEADER, row, rows)


def _make_service(db_session, staging_dir: Path) -> IngestionService:
    return IngestionService(db_session, staging_root=staging_dir)


# ── upload_file ────────────────────────────────────────────────


def test_upload_file_happy_path(db_session, admin_jwt_payload, staging_dir):
    svc = _make_service(db_session, staging_dir)
    payload = _pricing_pw_bytes()

    result = svc.upload_file(payload, "PW_010426.xlsx", admin_jwt_payload)

    assert not result.duplicate
    assert not result.conflict
    assert result.job.status == "STAGED"
    assert result.job.tenant_code == "PW"
    assert result.job.domain == "AIRLINE"
    assert result.job.file_size_bytes == len(payload)
    assert (staging_dir / str(result.job.id) / "PW_010426.xlsx").exists()

    # Audit row created
    audit = (
        db_session.query(IngestionAuditLog)
        .filter(IngestionAuditLog.job_id == result.job.id)
        .all()
    )
    assert len(audit) == 1
    assert audit[0].action == "UPLOADED"


def test_upload_file_resolves_jy_uuid_correctly(
    db_session, admin_jwt_payload, staging_dir
):
    """The Phase 1 fix: JY uploads must use JY's UUID, not Skywave's."""
    svc = _make_service(db_session, staging_dir)
    # Build a minimal JY pricing xlsx is awkward; use velocity csv instead
    velocity = (
        "DepDate,DepTime,CityPair,CapDate\n"
        "4/1/2026,09:00,LHRJFK,4/1/2026\n"
    ).encode("utf-8")
    result = svc.upload_file(
        velocity, "JY_VL_010426.csv", admin_jwt_payload
    )
    assert result.job.tenant_id == JY_TENANT_UUID
    assert result.job.tenant_id != SKYWAVE_TENANT_UUID


def test_upload_file_rejects_non_admin(
    db_session, jy_jwt_payload, staging_dir
):
    svc = _make_service(db_session, staging_dir)
    with pytest.raises(IngestionAuthError):
        svc.upload_file(_pricing_pw_bytes(), "PW_010426.xlsx", jy_jwt_payload)


def test_upload_file_rejects_invalid_filename(
    db_session, admin_jwt_payload, staging_dir
):
    svc = _make_service(db_session, staging_dir)
    with pytest.raises(IngestionFilenameError):
        svc.upload_file(b"junk", "totally-bogus.txt", admin_jwt_payload)


def test_upload_file_returns_duplicate_for_committed_hash(
    db_session, admin_jwt_payload, staging_dir
):
    """Re-uploading a file whose hash is already COMMITTED is a no-op."""
    svc = _make_service(db_session, staging_dir)
    payload = _pricing_pw_bytes()

    # Upload + validate + commit once
    r1 = svc.upload_file(payload, "PW_010426.xlsx", admin_jwt_payload)
    svc.validate_job(r1.job.id, admin_jwt_payload)
    svc.commit_job(r1.job.id, admin_jwt_payload)

    # Same bytes again — should detect as duplicate
    r2 = svc.upload_file(payload, "PW_010426.xlsx", admin_jwt_payload)
    assert r2.duplicate is True
    assert r2.job.id == r1.job.id


def test_upload_file_flags_conflict_for_same_date_different_hash(
    db_session, admin_jwt_payload, staging_dir
):
    svc = _make_service(db_session, staging_dir)

    r1 = svc.upload_file(
        _pricing_pw_bytes(), "PW_010426.xlsx", admin_jwt_payload
    )
    svc.validate_job(r1.job.id, admin_jwt_payload)
    svc.commit_job(r1.job.id, admin_jwt_payload)

    r2 = svc.upload_file(
        _pricing_pw_bytes_v2(), "PW_010426.xlsx", admin_jwt_payload
    )
    assert r2.duplicate is False
    assert r2.conflict is True
    assert r2.existing_job_id == r1.job.id


# ── validate_job ───────────────────────────────────────────────


def test_validate_job_happy_path(db_session, admin_jwt_payload, staging_dir):
    svc = _make_service(db_session, staging_dir)
    r = svc.upload_file(
        _pricing_pw_bytes(rows=5), "PW_010426.xlsx", admin_jwt_payload
    )

    vr = svc.validate_job(r.job.id, admin_jwt_payload)

    assert vr.row_count_total == 5
    assert vr.row_count_valid == 5
    assert vr.row_count_rejected == 0
    assert vr.job.status == "VALIDATED"
    assert vr.job.validated_at is not None


def test_validate_job_records_rejected_rows(
    db_session, admin_jwt_payload, staging_dir
):
    svc = _make_service(db_session, staging_dir)
    # Build a 2-row XLSX where row 1 is valid and row 2 has an empty cap_date.
    from io import BytesIO
    from openpyxl import Workbook
    bad_row = ",,RT,PW,1,LHR,JFK,01Apr26,Y,1,1,1,1,1,BA,1,LHR,JFK,01Apr26,Y,1,1,1,1,1"
    wb = Workbook(); ws = wb.active
    ws.append(PRICING_CSV_HEADER.strip().split(","))
    ws.append(PRICING_CSV_ROW.strip().split(","))
    ws.append(bad_row.split(","))
    bio = BytesIO(); wb.save(bio); bad_xlsx = bio.getvalue()
    r = svc.upload_file(bad_xlsx, "PW_010426.xlsx", admin_jwt_payload)
    vr = svc.validate_job(r.job.id, admin_jwt_payload)
    assert vr.row_count_total == 2
    assert vr.row_count_valid == 1
    assert vr.row_count_rejected == 1
    assert vr.summary["rejection_reasons_sample"]


def test_validate_job_not_found(db_session, admin_jwt_payload, staging_dir):
    svc = _make_service(db_session, staging_dir)
    with pytest.raises(IngestionNotFoundError):
        svc.validate_job(uuid.uuid4(), admin_jwt_payload)


# ── commit_job ─────────────────────────────────────────────────


def test_commit_job_happy_path_inserts_facts_with_correct_tenant_id(
    db_session, admin_jwt_payload, staging_dir
):
    """Verifies the Phase 1 fix end-to-end: PW data is inserted under
    PW's tenant_id, not Skywave's."""
    svc = _make_service(db_session, staging_dir)
    r = svc.upload_file(
        _pricing_pw_bytes(rows=3), "PW_010426.xlsx", admin_jwt_payload
    )
    svc.validate_job(r.job.id, admin_jwt_payload)
    cr = svc.commit_job(r.job.id, admin_jwt_payload)

    assert cr.rows_inserted == 3
    assert cr.job.status == "COMMITTED"
    assert cr.job.committed_at is not None
    assert cr.replaced_job_id is None

    # Verify the rows ended up under the right tenant_id
    rows = db_session.execute(
        text(
            "SELECT tenant_id, tenant_code, COUNT(*) FROM airline_cpi_snapshot "
            "WHERE source_file = :sf AND report_date = :rd "
            "GROUP BY tenant_id, tenant_code"
        ),
        {"sf": "PW_010426.xlsx", "rd": cr.job.file_date},
    ).all()
    assert len(rows) == 1
    tenant_id_used, tenant_code_used, n = rows[0]
    assert n == 3
    assert tenant_code_used == "PW"
    assert str(tenant_id_used) == "bb000000-0000-0000-0000-000000000001"


def test_commit_job_blocked_by_conflict(
    db_session, admin_jwt_payload, staging_dir
):
    svc = _make_service(db_session, staging_dir)

    # First commit succeeds
    r1 = svc.upload_file(
        _pricing_pw_bytes(), "PW_010426.xlsx", admin_jwt_payload
    )
    svc.validate_job(r1.job.id, admin_jwt_payload)
    svc.commit_job(r1.job.id, admin_jwt_payload)

    # Second commit on different content for same date should require replace
    r2 = svc.upload_file(
        _pricing_pw_bytes_v2(), "PW_010426.xlsx", admin_jwt_payload
    )
    svc.validate_job(r2.job.id, admin_jwt_payload)
    with pytest.raises(IngestionConflictError) as exc_info:
        svc.commit_job(r2.job.id, admin_jwt_payload)
    assert exc_info.value.existing_job_id == str(r1.job.id)


def test_commit_job_replace_existing_marks_old_replaced_and_swaps_data(
    db_session, admin_jwt_payload, staging_dir
):
    svc = _make_service(db_session, staging_dir)

    r1 = svc.upload_file(
        _pricing_pw_bytes(rows=3), "PW_010426.xlsx", admin_jwt_payload
    )
    svc.validate_job(r1.job.id, admin_jwt_payload)
    svc.commit_job(r1.job.id, admin_jwt_payload)

    r2 = svc.upload_file(
        _pricing_pw_bytes_v2(rows=4), "PW_010426.xlsx", admin_jwt_payload
    )
    svc.validate_job(r2.job.id, admin_jwt_payload)
    cr2 = svc.commit_job(
        r2.job.id, admin_jwt_payload, replace_existing=True
    )

    assert cr2.replaced_job_id == r1.job.id
    assert cr2.rows_inserted == 4
    assert cr2.job.status == "COMMITTED"

    # Old job marked REPLACED
    db_session.refresh(r1.job)
    assert r1.job.status == "REPLACED"
    assert r1.job.replaced_by_job_id == r2.job.id

    # Total rows for that date now equal r2 only
    n = db_session.execute(
        text(
            "SELECT COUNT(*) FROM airline_cpi_snapshot "
            "WHERE tenant_code = 'PW' AND report_date = :rd"
        ),
        {"rd": r2.job.file_date},
    ).scalar()
    assert n == 4


def test_commit_job_wrong_state_raises(
    db_session, admin_jwt_payload, staging_dir
):
    """Commit on a STAGED (not yet validated) job must error."""
    svc = _make_service(db_session, staging_dir)
    r = svc.upload_file(
        _pricing_pw_bytes(), "PW_010426.xlsx", admin_jwt_payload
    )
    with pytest.raises(IngestionStateError):
        svc.commit_job(r.job.id, admin_jwt_payload)


# ── cancel_job ─────────────────────────────────────────────────


def test_cancel_job_happy_path(db_session, admin_jwt_payload, staging_dir):
    svc = _make_service(db_session, staging_dir)
    r = svc.upload_file(
        _pricing_pw_bytes(), "PW_010426.xlsx", admin_jwt_payload
    )
    job_dir = staging_dir / str(r.job.id)
    assert job_dir.exists()

    svc.cancel_job(r.job.id, admin_jwt_payload)

    db_session.refresh(r.job)
    assert r.job.status == "REJECTED"
    assert not job_dir.exists()


def test_cancel_job_rejects_committed_job(
    db_session, admin_jwt_payload, staging_dir
):
    svc = _make_service(db_session, staging_dir)
    r = svc.upload_file(
        _pricing_pw_bytes(), "PW_010426.xlsx", admin_jwt_payload
    )
    svc.validate_job(r.job.id, admin_jwt_payload)
    svc.commit_job(r.job.id, admin_jwt_payload)
    with pytest.raises(IngestionStateError):
        svc.cancel_job(r.job.id, admin_jwt_payload)


def test_cancel_job_rejects_non_admin(
    db_session, admin_jwt_payload, jy_jwt_payload, staging_dir
):
    svc = _make_service(db_session, staging_dir)
    r = svc.upload_file(
        _pricing_pw_bytes(), "PW_010426.xlsx", admin_jwt_payload
    )
    with pytest.raises(IngestionAuthError):
        svc.cancel_job(r.job.id, jy_jwt_payload)


# ── cap_date sourced from the filename (mis-stamped CapDate guard) ──────


def test_commit_stamps_cap_date_from_filename_not_in_file_capdate(
    db_session, admin_jwt_payload, staging_dir
):
    """Regression guard for the WM_290726 incident: the recorded ``cap_date``
    must come from the FILENAME, never the spreadsheet's in-file ``CapDate``
    column. ``PRICING_CSV_ROW`` carries an in-file CapDate of ``01Apr26``; if
    we name the file for the 2nd (``PW_020426.xlsx``) the rows must land under
    ``cap_date = 2026-04-02`` (the filename), not ``2026-04-01`` (the cell)."""
    import datetime as dt

    svc = _make_service(db_session, staging_dir)
    r = svc.upload_file(
        _pricing_pw_bytes(rows=3), "PW_020426.xlsx", admin_jwt_payload
    )
    assert r.job.file_date == dt.date(2026, 4, 2)

    vr = svc.validate_job(r.job.id, admin_jwt_payload)
    assert vr.row_count_valid == 3

    cr = svc.commit_job(r.job.id, admin_jwt_payload, replace_existing=True)
    assert cr.rows_inserted == 3

    rows = db_session.execute(
        text(
            "SELECT DISTINCT cap_date, report_date FROM airline_cpi_snapshot "
            "WHERE source_file = :sf AND report_date = :rd"
        ),
        {"sf": "PW_020426.xlsx", "rd": cr.job.file_date},
    ).all()
    assert len(rows) == 1
    cap_date, report_date = rows[0]
    assert cap_date == dt.date(2026, 4, 2)
    assert report_date == dt.date(2026, 4, 2)
    assert cap_date == report_date


def test_commit_velocity_dep_date_is_not_overridden_by_filename(
    db_session, admin_jwt_payload, staging_dir
):
    """The filename-sourced capture-date change must NOT touch VELOCITY, which
    keys on ``DepDate`` — a future departure date that legitimately differs
    from the filename. File named for 01Apr26 but DepDate 15Apr26 -> the stored
    ``dep_date`` must stay 2026-04-15."""
    import datetime as dt

    velocity = (
        "DepDate,DepTime,CityPair,CapDate\n"
        "4/15/2026,09:00,LHRJFK,4/1/2026\n"
    ).encode("utf-8")
    svc = _make_service(db_session, staging_dir)
    r = svc.upload_file(velocity, "JY_VL_010426.csv", admin_jwt_payload)
    assert r.job.file_date == dt.date(2026, 4, 1)

    svc.validate_job(r.job.id, admin_jwt_payload)
    cr = svc.commit_job(r.job.id, admin_jwt_payload)
    assert cr.rows_inserted == 1

    rows = db_session.execute(
        text(
            "SELECT DISTINCT dep_date, report_date FROM velocity_snapshot "
            "WHERE source_file = :sf"
        ),
        {"sf": "JY_VL_010426.csv"},
    ).all()
    assert len(rows) == 1
    dep_date, report_date = rows[0]
    assert dep_date == dt.date(2026, 4, 15)
    assert report_date == dt.date(2026, 4, 1)


# ── delete_committed_file ──────────────────────────────────────


def test_delete_committed_file_removes_facts_and_marks_deleted(
    db_session, admin_jwt_payload, staging_dir
):
    """A manually-uploaded COMMITTED job's fact rows are hard-deleted, the
    job flips to DELETED, and a DELETED audit entry is written."""
    svc = _make_service(db_session, staging_dir)
    r = svc.upload_file(
        _pricing_pw_bytes(rows=3), "PW_150120.xlsx", admin_jwt_payload
    )
    svc.validate_job(r.job.id, admin_jwt_payload)
    cr = svc.commit_job(r.job.id, admin_jwt_payload)

    before = db_session.execute(
        text(
            "SELECT COUNT(*) FROM airline_cpi_snapshot "
            "WHERE source_file = :sf AND report_date = :rd"
        ),
        {"sf": "PW_150120.xlsx", "rd": cr.job.file_date},
    ).scalar()
    assert before == 3

    result = svc.delete_committed_file(r.job.id, admin_jwt_payload)
    assert result["rows_deleted"] == 3

    after = db_session.execute(
        text(
            "SELECT COUNT(*) FROM airline_cpi_snapshot "
            "WHERE source_file = :sf AND report_date = :rd"
        ),
        {"sf": "PW_150120.xlsx", "rd": cr.job.file_date},
    ).scalar()
    assert after == 0

    db_session.refresh(r.job)
    assert r.job.status == "DELETED"
    deleted_audits = (
        db_session.query(IngestionAuditLog)
        .filter(
            IngestionAuditLog.job_id == r.job.id,
            IngestionAuditLog.action == "DELETED",
        )
        .count()
    )
    assert deleted_audits == 1


def test_delete_committed_file_rejects_non_committed_job(
    db_session, admin_jwt_payload, staging_dir
):
    """Only COMMITTED jobs are deletable; a STAGED job raises."""
    svc = _make_service(db_session, staging_dir)
    r = svc.upload_file(
        _pricing_pw_bytes(), "PW_150120.xlsx", admin_jwt_payload
    )
    with pytest.raises(IngestionStateError):
        svc.delete_committed_file(r.job.id, admin_jwt_payload)


def test_delete_committed_file_rejects_non_admin(
    db_session, admin_jwt_payload, jy_jwt_payload, staging_dir
):
    svc = _make_service(db_session, staging_dir)
    r = svc.upload_file(
        _pricing_pw_bytes(), "PW_150120.xlsx", admin_jwt_payload
    )
    svc.validate_job(r.job.id, admin_jwt_payload)
    svc.commit_job(r.job.id, admin_jwt_payload)
    with pytest.raises(IngestionAuthError):
        svc.delete_committed_file(r.job.id, jy_jwt_payload)
