"""Integration tests for app.tasks.sftp_pull.run_pull (the testable core).

We exercise ``run_pull`` directly rather than dispatching through the
Celery wrapper so we don't need a broker. The wrapper is trivial — it
just opens/closes a session — and is asserted at the end via attribute
checks on the task object.

Each test inserts its own sftp_connection + ingestion_schedule rows
inside the savepoint-rollback ``db_session`` fixture (tests/conftest.py),
so all DB writes are undone at test end. The IngestionService side
effects (staged files on disk) are routed at a pytest tmp_path.
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta
from io import BytesIO
from pathlib import Path

import pytest
from openpyxl import Workbook
from sqlalchemy import text

from app.core.crypto import encrypt_str
from app.ingestion.sftp_client import SFTPClientError
from app.tasks.sftp_pull import run_pull, sftp_pull_for_schedule


# ── fixtures + helpers ──────────────────────────────────────────────


def _admin_user_id(db_session):
    row = db_session.execute(
        text("SELECT id FROM app_user WHERE email = 'admin@rts.com'")
    ).first()
    assert row, (
        "test prerequisite: admin@rts.com must exist (migration 016)"
    )
    return row[0]


def _safe_jy_date(db_session, *, days_back_start=120) -> date:
    """Pick a YYMMDD that has no JY airline ingestion_jobs row in the DB.

    Dates within the smoke-test window may collide with previously
    committed jobs, so we walk back from ~4 months to find a clear date.
    """
    used = set(
        db_session.execute(
            text(
                "SELECT file_date FROM ingestion_jobs "
                "WHERE tenant_code = 'JY' AND domain = 'AIRLINE'"
            )
        ).scalars().all()
    )
    for offset in range(days_back_start, days_back_start + 200):
        d = date.today() - timedelta(days=offset)
        if d not in used:
            return d
    raise RuntimeError("no safe JY airline date found in 200-day window")


def _insert_connection(
    db_session,
    sftpserver,
    *,
    password_ct: bytes | None = None,
    host: str | None = None,
    port: int | None = None,
    username: str = "testuser",
):
    """Insert a sftp_connection row pointing at the pytest-sftpserver."""
    if password_ct is None:
        password_ct = encrypt_str("testpass")
    cid = str(uuid.uuid4())
    db_session.execute(
        text(
            "INSERT INTO sftp_connection "
            "(id, tenant_code, name, host, port, username, "
            " password_ciphertext, remote_base_path, is_active, "
            " created_by_user_id) "
            "VALUES (:id, 'jy', :name, :host, :port, :user, "
            "        :pw, '/upload', true, :uid)"
        ),
        {
            "id": cid,
            "name": "test-conn-" + cid[:8],
            "host": host or sftpserver.host,
            "port": port or sftpserver.port,
            "user": username,
            "pw": password_ct,
            "uid": _admin_user_id(db_session),
        },
    )
    return cid


def _insert_schedule(
    db_session,
    conn_id,
    *,
    regex: str = r"^JY_(\d{6})\.xlsx$",
    replace_existing: bool = False,
):
    sid = str(uuid.uuid4())
    db_session.execute(
        text(
            "INSERT INTO ingestion_schedule "
            "(id, sftp_connection_id, tenant_code, domain, "
            " cron_expression, timezone, filename_regex, "
            " replace_existing, is_enabled, created_by_user_id) "
            "VALUES (:id, :cid, 'jy', 'AIRLINE', '* * * * *', 'UTC', "
            "        :rx, :replace, true, :uid)"
        ),
        {
            "id": sid,
            "cid": conn_id,
            "rx": regex,
            "replace": replace_existing,
            "uid": _admin_user_id(db_session),
        },
    )
    db_session.commit()
    return sid


def _build_minimal_xlsx_bytes(file_date: date) -> bytes:
    """Build a tiny xlsx with the columns IngestionService._insert_airline_rows
    expects. ``file_date`` is the CapDate / RefDepDate / CompDepDate."""
    wb = Workbook()
    ws = wb.active
    ws.append([
        "CapDate", "CapTime", "TripType",
        "RefAL", "RefFltNum", "RefOrg", "RefDst", "RefDepDate",
        "RefCabCode", "RefTotFare", "RefBaseFare", "RefTax",
        "RefYQ", "RefSeats",
        "CompAL", "CompFltNum", "CompOrg", "CompDst", "CompDepDate",
        "CompCabCode", "CompTotFare", "CompBaseFare", "CompTax",
        "CompYQ", "CompSeats",
    ])
    iso = file_date.isoformat()
    for i in range(3):
        ws.append([
            iso, "08:00", "OW",
            "JY", f"JY10{i}", "DEL", "BOM", iso,
            "Y", 250.0 + i, 200.0, 50.0, 0.0, 9,
            "AI", f"AI10{i}", "DEL", "BOM", iso,
            "Y", 240.0, 190.0, 50.0, 0.0, 9,
        ])
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _filename_for(file_date: date) -> str:
    return f"JY_{file_date.strftime('%d%m%y')}.xlsx"


# ── tests ────────────────────────────────────────────────────────────


def test_happy_path(db_session, sftpserver, tmp_path: Path):
    """JY xlsx in fixture SFTP -> committed to airline_cpi_snapshot."""
    fd = _safe_jy_date(db_session, days_back_start=120)
    fname = _filename_for(fd)
    payload = _build_minimal_xlsx_bytes(fd)

    with sftpserver.serve_content({"upload": {fname: payload}}):
        cid = _insert_connection(db_session, sftpserver)
        sid = _insert_schedule(db_session, cid)
        result = run_pull(db_session, sid, scope="all", staging_root=tmp_path)

    assert result["status"] == "SUCCESS"
    assert result["files_seen"] == 1
    assert result["files_pulled"] == 1
    assert result["jobs_committed"] == 1

    row = db_session.execute(
        text(
            "SELECT outcome, ingestion_job_id FROM ingested_file "
            "WHERE remote_filename = :n"
        ),
        {"n": fname},
    ).first()
    assert row is not None
    assert row[0] == "COMMITTED"
    assert row[1] is not None  # has an ingestion_jobs reference

    n_snap = db_session.execute(
        text(
            "SELECT COUNT(*) FROM airline_cpi_snapshot "
            "WHERE source_file = :f"
        ),
        {"f": fname},
    ).scalar()
    assert n_snap == 3  # 3 dummy rows in the xlsx


def test_idempotency_second_run_skips(db_session, sftpserver, tmp_path: Path):
    """Same file twice: first run COMMITS, second run records DUPLICATE
    in detail_log; airline_cpi_snapshot row count unchanged."""
    fd = _safe_jy_date(db_session, days_back_start=180)
    fname = _filename_for(fd)
    payload = _build_minimal_xlsx_bytes(fd)

    with sftpserver.serve_content({"upload": {fname: payload}}):
        cid = _insert_connection(db_session, sftpserver)
        sid = _insert_schedule(db_session, cid)

        result1 = run_pull(db_session, sid, scope="all", staging_root=tmp_path)
        assert result1["jobs_committed"] == 1

        snap_after_1 = db_session.execute(
            text(
                "SELECT COUNT(*) FROM airline_cpi_snapshot "
                "WHERE source_file = :f"
            ),
            {"f": fname},
        ).scalar()

        result2 = run_pull(db_session, sid, scope="all", staging_root=tmp_path)

    assert result2["status"] == "SUCCESS"
    assert result2["files_seen"] == 1
    assert result2["files_pulled"] == 0
    assert result2["jobs_committed"] == 0

    n_files = db_session.execute(
        text("SELECT COUNT(*) FROM ingested_file WHERE remote_filename = :f"),
        {"f": fname},
    ).scalar()
    assert n_files == 1  # UNIQUE (sha256, remote_filename) — no second row

    snap_after_2 = db_session.execute(
        text(
            "SELECT COUNT(*) FROM airline_cpi_snapshot "
            "WHERE source_file = :f"
        ),
        {"f": fname},
    ).scalar()
    assert snap_after_2 == snap_after_1

    detail = db_session.execute(
        text("SELECT detail_log FROM ingestion_run WHERE id = :id"),
        {"id": result2["run_id"]},
    ).scalar()
    assert detail and any(e.get("outcome") == "DUPLICATE" for e in detail)


def test_empty_sftp(db_session, sftpserver, tmp_path: Path):
    """No matching files -> SUCCESS with zero counts."""
    with sftpserver.serve_content({"upload": {"some_other.txt": "ignore"}}):
        cid = _insert_connection(db_session, sftpserver)
        sid = _insert_schedule(db_session, cid)
        result = run_pull(db_session, sid, staging_root=tmp_path)

    assert result["status"] == "SUCCESS"
    assert result["files_seen"] == 0
    assert result["files_pulled"] == 0
    assert result["jobs_committed"] == 0


def test_sftp_connection_failure_raises_for_retry(
    db_session, sftpserver, tmp_path: Path
):
    """Bogus SFTP host -> SFTPClientError raised so celery autoretry kicks in.
    Run row finalised to FAILED before the raise propagates."""
    cid = _insert_connection(
        db_session, sftpserver, host="127.0.0.1", port=1, username="x"
    )
    sid = _insert_schedule(db_session, cid)

    with pytest.raises(SFTPClientError):
        run_pull(db_session, sid, staging_root=tmp_path)

    status = db_session.execute(
        text(
            "SELECT status FROM ingestion_run "
            "WHERE schedule_id = :sid ORDER BY started_at DESC LIMIT 1"
        ),
        {"sid": sid},
    ).scalar()
    assert status == "FAILED"

    # Confirm SFTPClientError IS in the task's autoretry list
    assert SFTPClientError in (sftp_pull_for_schedule.autoretry_for or ())


def test_decryption_failure_no_retry(db_session, sftpserver, tmp_path: Path):
    """Corrupted password ciphertext -> InvalidToken raised. NOT in
    autoretry_for, so celery would not retry. Run row marked FAILED."""
    from cryptography.fernet import InvalidToken

    cid = _insert_connection(
        db_session,
        sftpserver,
        password_ct=b"not-a-valid-fernet-token-just-random-bytes",
    )
    sid = _insert_schedule(db_session, cid)

    with pytest.raises(InvalidToken):
        run_pull(db_session, sid, staging_root=tmp_path)

    status = db_session.execute(
        text(
            "SELECT status FROM ingestion_run "
            "WHERE schedule_id = :sid ORDER BY started_at DESC LIMIT 1"
        ),
        {"sid": sid},
    ).scalar()
    assert status == "FAILED"

    # Confirm InvalidToken is NOT in autoretry_for (celery wouldn't retry)
    assert InvalidToken not in (sftp_pull_for_schedule.autoretry_for or ())

# ── velocity batch isolation (added after run 5e041969) ─────────────
# Self-contained helpers: the module-level _admin_user_id() above still
# hardcodes the pre-rename admin@skywave.com (migration 026 renamed the
# platform tenant skywave -> rts), so it skips. These resolve the admin
# tolerantly so this regression test for the run_pull hardening runs.


def _resolve_admin_id(db_session):
    row = db_session.execute(
        text(
            "SELECT id FROM app_user "
            "WHERE email IN ('admin@rts.com', 'admin@skywave.com') "
            "ORDER BY (email = 'admin@rts.com') DESC LIMIT 1"
        )
    ).first()
    if not row:
        pytest.skip("no platform admin user (admin@rts.com) in DB")
    return row[0]


def _insert_velocity_connection(db_session, sftpserver):
    cid = str(uuid.uuid4())
    db_session.execute(
        text(
            "INSERT INTO sftp_connection "
            "(id, tenant_code, name, host, port, username, "
            " password_ciphertext, remote_base_path, is_active, "
            " created_by_user_id) "
            "VALUES (:id, 'jy', :name, :host, :port, 'testuser', "
            "        :pw, '/upload', true, :uid)"
        ),
        {
            "id": cid,
            "name": "vel-conn-" + cid[:8],
            "host": sftpserver.host,
            "port": sftpserver.port,
            "pw": encrypt_str("testpass"),
            "uid": _resolve_admin_id(db_session),
        },
    )
    return cid


def _safe_velocity_dates(db_session, n: int, *, days_back_start=300):
    """Pick ``n`` distinct dates with no jy VELOCITY ingestion_jobs row."""
    used = set(
        db_session.execute(
            text(
                "SELECT file_date FROM ingestion_jobs "
                "WHERE tenant_code = 'jy' AND domain = 'VELOCITY'"
            )
        ).scalars().all()
    )
    out: list[date] = []
    offset = days_back_start
    while len(out) < n and offset < days_back_start + 400:
        d = date.today() - timedelta(days=offset)
        if d not in used:
            out.append(d)
        offset += 1
    assert len(out) == n, "no clear velocity date window"
    return out


def _vfname(fd: date) -> str:
    return f"JY_VL_{fd.strftime('%d%m%y')}.csv"


def _valid_velocity_csv(fd: date, *, n_rows: int = 2) -> bytes:
    """Headerless 13-col velocity rows with a parseable M/D/YYYY DepDate.

    ``n_rows`` varies the row count (and thus the content sha) so callers
    can build two same-date files with different content to force a
    CONFLICT (vs. an identical-content DUPLICATE).
    """
    dd = f"{fd.month}/{fd.day}/{fd.year}"
    rows = [
        f"{dd},{900 + i:04d},0416,DELBOM,AT4,Leg,{i + 1},0,Y,"
        f"{20 + i},48,44,85"
        for i in range(n_rows)
    ]
    return ("\r\n".join(rows) + "\r\n").encode("utf-8")


def _insert_velocity_schedule(db_session, conn_id):
    sid = str(uuid.uuid4())
    db_session.execute(
        text(
            "INSERT INTO ingestion_schedule "
            "(id, sftp_connection_id, tenant_code, domain, "
            " cron_expression, timezone, filename_regex, "
            " replace_existing, is_enabled, created_by_user_id) "
            "VALUES (:id, :cid, 'jy', 'VELOCITY', '* * * * *', 'UTC', "
            "        :rx, false, true, :uid)"
        ),
        {
            "id": sid,
            "cid": conn_id,
            "rx": r"^JY_VL_(\d{6})\.csv$",
            "uid": _resolve_admin_id(db_session),
        },
    )
    db_session.commit()
    return sid


def test_batch_valid_empty_valid_isolates_and_persists(
    db_session, sftpserver, tmp_path: Path
):
    """(f) Batch [valid, empty, valid]: both valids COMMIT, empty is
    SKIPPED (no abort), run finalises PARTIAL with persisted telemetry."""
    d1, d2, d3 = _safe_velocity_dates(db_session, 3)
    f1, f2, f3 = _vfname(d1), _vfname(d2), _vfname(d3)
    content = {
        f1: _valid_velocity_csv(d1),
        f2: b"\r\n\r\n\r\n\r\n",  # all-blank -> SKIPPED
        f3: _valid_velocity_csv(d3),
    }

    with sftpserver.serve_content({"upload": content}):
        cid = _insert_velocity_connection(db_session, sftpserver)
        sid = _insert_velocity_schedule(db_session, cid)
        result = run_pull(
            db_session, sid, scope="all", staging_root=tmp_path
        )

    assert result["status"] == "PARTIAL"
    assert result["files_seen"] == 3
    assert result["files_pulled"] == 3
    assert result["jobs_committed"] == 2

    rows = dict(
        db_session.execute(
            text(
                "SELECT remote_filename, outcome FROM ingested_file "
                "WHERE schedule_id = :sid"
            ),
            {"sid": sid},
        ).all()
    )
    assert rows[f1] == "COMMITTED"
    assert rows[f2] == "SKIPPED"
    assert rows[f3] == "COMMITTED"

    # the empty file must NOT have produced velocity facts
    assert db_session.execute(
        text("SELECT COUNT(*) FROM velocity_snapshot WHERE source_file = :f"),
        {"f": f2},
    ).scalar() == 0

    # run-level telemetry persisted (NOT all-zeros) on a non-SUCCESS run
    run_row = db_session.execute(
        text(
            "SELECT files_seen, files_pulled, jobs_committed, status, "
            "detail_log FROM ingestion_run WHERE id = :id"
        ),
        {"id": result["run_id"]},
    ).first()
    assert run_row[0] == 3
    assert run_row[1] == 3
    assert run_row[2] == 2
    assert run_row[3] == "PARTIAL"
    detail = run_row[4]
    assert any(
        e.get("event") == "RUN_SUMMARY" and e.get("jobs_skipped") == 1
        for e in detail
    )
    assert any(e.get("outcome") == "SKIPPED" for e in detail)


def test_batch_conflict_is_success_not_partial(
    db_session, sftpserver, tmp_path: Path
):
    """A benign CONFLICT (file_date already committed) must NOT downgrade
    the run to PARTIAL: [valid, same-date-different-content, valid] ->
    SUCCESS, with 2 COMMITTED + 1 CONFLICT + 0 skipped/errored."""
    d1, dmid, d3 = _safe_velocity_dates(db_session, 3, days_back_start=520)
    cid = _insert_velocity_connection(db_session, sftpserver)
    sid = _insert_velocity_schedule(db_session, cid)

    # Seed: commit dmid first (separate run).
    with sftpserver.serve_content(
        {"upload": {_vfname(dmid): _valid_velocity_csv(dmid, n_rows=2)}}
    ):
        seed = run_pull(db_session, sid, scope="all", staging_root=tmp_path)
    assert seed["jobs_committed"] == 1

    # Measured run: dmid reappears with DIFFERENT content (different sha,
    # same file_date) -> not a sha-duplicate -> commit -> CONFLICT.
    batch = {
        _vfname(d1): _valid_velocity_csv(d1, n_rows=2),
        _vfname(dmid): _valid_velocity_csv(dmid, n_rows=3),
        _vfname(d3): _valid_velocity_csv(d3, n_rows=2),
    }
    with sftpserver.serve_content({"upload": batch}):
        result = run_pull(db_session, sid, scope="all", staging_root=tmp_path)

    assert result["status"] == "SUCCESS"
    assert result["jobs_committed"] == 2

    outcomes = dict(
        db_session.execute(
            text(
                "SELECT remote_filename, outcome FROM ingested_file "
                "WHERE run_id = :rid"
            ),
            {"rid": result["run_id"]},
        ).all()
    )
    assert outcomes[_vfname(d1)] == "COMMITTED"
    assert outcomes[_vfname(dmid)] == "CONFLICT"
    assert outcomes[_vfname(d3)] == "COMMITTED"

    run_row = db_session.execute(
        text(
            "SELECT status, detail_log FROM ingestion_run WHERE id = :id"
        ),
        {"id": result["run_id"]},
    ).first()
    assert run_row[0] == "SUCCESS"
    assert any(
        e.get("event") == "RUN_SUMMARY"
        and e.get("jobs_conflict") == 1
        and e.get("jobs_rejected") == 0
        for e in run_row[1]
    )
