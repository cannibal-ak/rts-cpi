#!/usr/bin/env python3
"""Ingest the relabelled DreamAir files through the normal ingestion pipeline.

Companion to relabel_pw_files_as_da.py. Runs each DA_* file through the exact
path the admin upload UI uses -- upload_file -> validate_job -> commit_job --
rather than INSERTing rows directly, so the DreamAir data is produced by the
same parser, the same column widths and the same validation as any real feed.

Runs as the RTS platform admin, which is what IngestionService._require_admin
demands. Idempotent: a file already COMMITTED for DA is skipped, so the script
can be re-run after a partial failure.

Usage (inside the api container):
    python3 scripts/ingest_dreamair_demo.py --dir /tmp/da_files
    python3 scripts/ingest_dreamair_demo.py --dir /tmp/da_files --limit 2
    python3 scripts/ingest_dreamair_demo.py --dir /tmp/da_files --domain VELOCITY
"""
from __future__ import annotations

import argparse
import os
import sys
import traceback
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, "/app")

from app.ingestion.service import IngestionService  # noqa: E402

# The canonical RTS platform-admin user (migration 016). Ingestion is
# admin-only, and _identity_from_payload upper-cases tenant_slug to derive the
# identity, so this must be the platform tenant, not the DA tenant.
ADMIN_PAYLOAD = {
    "sub": "11111111-0000-0000-0000-000000000001",
    "tenant_slug": "rts",
    "roles": ["TENANT_ADMIN"],
}

TENANT = "DA"


def already_committed(session) -> set[str]:
    rows = session.execute(sa.text(
        "SELECT filename FROM ingestion_jobs "
        "WHERE tenant_code = :tc AND status = 'COMMITTED'"
    ), {"tc": TENANT})
    return {r[0] for r in rows}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--domain", choices=["AIRLINE", "VELOCITY"], default=None,
                    help="restrict to one domain (default: both)")
    args = ap.parse_args()

    url = os.environ.get("CPI_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("CPI_DATABASE_URL not set")
    engine = sa.create_engine(url)
    Session = sessionmaker(bind=engine)

    src = Path(args.dir)
    files = sorted(p for p in src.iterdir() if p.is_file() and p.name.startswith("DA_"))
    if args.domain == "AIRLINE":
        files = [p for p in files if not p.name.startswith("DA_VL_")]
    elif args.domain == "VELOCITY":
        files = [p for p in files if p.name.startswith("DA_VL_")]
    if args.limit:
        files = files[: args.limit]

    with Session() as probe:
        done = already_committed(probe)
    todo = [p for p in files if p.name not in done]
    print(f"{len(files)} candidate files, {len(done)} already COMMITTED for {TENANT}, "
          f"{len(todo)} to do", flush=True)

    ok = skipped = failed = 0
    total_rows = 0
    for i, path in enumerate(todo, 1):
        content = path.read_bytes()
        session = Session()
        try:
            svc = IngestionService(session)
            up = svc.upload_file(content, path.name, ADMIN_PAYLOAD)
            job_id = up.job.id
            val = svc.validate_job(job_id, ADMIN_PAYLOAD)
            if val.job.status != "VALIDATED":
                print(f"  [{i}/{len(todo)}] {path.name}: NOT VALIDATED "
                      f"({val.job.status}) valid={val.row_count_valid} "
                      f"rejected={val.row_count_rejected} -- {val.summary}", flush=True)
                failed += 1
                session.close()
                continue
            if val.row_count_rejected:
                print(f"  [{i}/{len(todo)}] {path.name}: "
                      f"{val.row_count_rejected} of {val.row_count_total} rows rejected",
                      flush=True)
            com = svc.commit_job(job_id, ADMIN_PAYLOAD, replace_existing=True)
            rows = com.rows_inserted
            total_rows += rows
            ok += 1
            if i % 10 == 0 or i == len(todo):
                print(f"  [{i}/{len(todo)}] {path.name} committed ({rows} rows); "
                      f"running total {total_rows}", flush=True)
        except Exception as exc:  # noqa: BLE001 - report and continue
            msg = str(exc)
            if "Duplicate file" in msg:
                skipped += 1
            else:
                failed += 1
                print(f"  [{i}/{len(todo)}] {path.name}: FAILED {type(exc).__name__}: {msg}",
                      flush=True)
                traceback.print_exc()
            session.rollback()
        finally:
            session.close()

    print(f"\ncommitted={ok} skipped_duplicate={skipped} failed={failed} rows={total_rows}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
