#!/usr/bin/env python3
"""Auto-ingest CPI data files dropped into a local inbox folder.

Walks the inbox folder for files matching one of the five known filename
patterns (JY/PW airline + JY/PW velocity + FJL CFL), then drives the
existing IngestionService through upload -> validate -> commit by
shelling into cpi-api-1 via `docker exec`.

This script bypasses the HTTP layer because the deployed API does not
expose the upload router; the underlying IngestionService class is
identical to what the (latent) HTTP route would call. See
`_ingest_worker.py` for the in-container half of the pipeline.

Successfully processed files are moved to processed/ with a timestamp
prefix; anything rejected (bad filename, validation failure, commit
failure) lands in failed/ alongside a .reason sidecar describing why.

Usage:
    python3 auto_ingest.py [--inbox PATH]
"""
from __future__ import annotations

import argparse
import fcntl
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional


# ---- Configuration ------------------------------------------------------

CONTAINER = "cpi-api-1"
DEFAULT_INBOX = "/home/ankitprajapati/CPI/apps/api/data/inbox"
PROCESSED_DIR = "/home/ankitprajapati/CPI/apps/api/data/processed"
FAILED_DIR = "/home/ankitprajapati/CPI/apps/api/data/failed"
TMP_PREPROCESS_DIR = "/home/ankitprajapati/CPI/apps/api/data/_tmp_preprocess"
LOCK_PATH = "/tmp/cpi_auto_ingest.lock"

# Bind-mount path translation (host -> container view).
HOST_TO_CONTAINER_PATHS = {
    "/home/ankitprajapati/CPI/apps/api/data/inbox": "/app/data/inbox",
    "/home/ankitprajapati/CPI/apps/api/data/_tmp_preprocess": "/app/data/_tmp_preprocess",
}
WORKER_IN_CONTAINER = "/app/scripts/_ingest_worker.py"

# Canonical velocity CSV header. Some source files arrive without a
# header row (positional CSV). The column ORDER below matches the
# fixed source-file column order; if first line of a velocity file
# does not start with "DepDate", we prepend this line to a temp copy
# before handing it to the worker.
VELOCITY_HEADER = (
    "DepDate,DepTime,DepCode,CityPair,Eqp,LegsegType,LegSegOrder,"
    "Days_Left,Compartment,Current_Booking,Capacity,"
    "Actual_Seat_Factor,Forecasted_Seat_Factor"
)

WORKER_TIMEOUT_SEC = 600  # generous: a 50 MB xlsx insert can take a while

# Mirror of apps/api/app/ingestion/filename_patterns.yaml. PW airline
# accepts both .xlsx and .csv per the live regex patched on 2026-05-08.
FILENAME_PATTERNS = [
    (re.compile(r"^JY_(\d{6})\.xlsx$", re.IGNORECASE),
     "JY", "AIRLINE", "airline_cpi_snapshot"),
    (re.compile(r"^JYVelocityData_(\d{2}\.\d{2}\.\d{4})\.csv$", re.IGNORECASE),
     "JY", "VELOCITY", "velocity_snapshot"),
    (re.compile(r"^PW_(\d{6})\.(xlsx|csv)$", re.IGNORECASE),
     "PW", "AIRLINE", "airline_cpi_snapshot"),
    (re.compile(r"^PWVelocityData_(\d{2}\.\d{2}\.\d{4})\.csv$", re.IGNORECASE),
     "PW", "VELOCITY", "velocity_snapshot"),
    (re.compile(r"^FJL_(\d{6})\.csv$", re.IGNORECASE),
     "FJL", "CFL", "cfl_cpi_snapshot"),
]


# ---- Logging ------------------------------------------------------------

def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)


# ---- Helpers ------------------------------------------------------------

def match_pattern(name: str):
    for pat, tenant, domain, table in FILENAME_PATTERNS:
        if pat.match(name):
            return tenant, domain, table
    return None


def host_to_container_path(host_path: Path) -> Optional[str]:
    """Translate a host-side path to the container view, for any of
    our known bind-mounted locations."""
    for host_root, container_root in HOST_TO_CONTAINER_PATHS.items():
        try:
            rel = host_path.relative_to(host_root)
        except ValueError:
            continue
        return f"{container_root}/{rel.as_posix()}"
    return None


def maybe_preprocess_velocity(domain: str, src: Path) -> tuple[Path, Optional[Path]]:
    """Detect header-less velocity CSVs and prepend the canonical
    header line to a temp copy. Returns (path_to_use_for_worker,
    cleanup_path_or_None). If the file already has a header, the
    original path is returned and cleanup is None."""
    if domain != "VELOCITY":
        return src, None
    try:
        with src.open("rb") as fh:
            first_line = fh.readline().decode("utf-8", errors="replace").strip()
    except OSError:
        return src, None
    if first_line.startswith("DepDate"):
        return src, None
    # Header missing -- write a fixed copy to TMP_PREPROCESS_DIR.
    Path(TMP_PREPROCESS_DIR).mkdir(parents=True, exist_ok=True)
    tmp = Path(TMP_PREPROCESS_DIR) / src.name
    with src.open("rb") as fin, tmp.open("wb") as fout:
        fout.write((VELOCITY_HEADER + "\n").encode("utf-8"))
        shutil.copyfileobj(fin, fout)
    log(f"  prepended canonical header (file had no header row)")
    return tmp, tmp


def write_failure(path: Path, reason: str) -> Path:
    stamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    dest = Path(FAILED_DIR) / f"{stamp}_{path.name}"
    shutil.move(str(path), str(dest))
    sidecar = dest.with_suffix(dest.suffix + ".reason")
    sidecar.write_text(reason + "\n")
    return dest


def move_to_processed(path: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    dest = Path(PROCESSED_DIR) / f"{stamp}_{path.name}"
    shutil.move(str(path), str(dest))
    return dest


# ---- Worker invocation --------------------------------------------------

def run_worker(container_file_path: str) -> dict:
    """Invoke the in-container worker. Returns the parsed JSON result.

    Raises subprocess.TimeoutExpired or ValueError on transport-level
    issues (we treat those as failures upstream)."""
    cmd = [
        "docker", "exec",
        "-w", "/app",
        "-e", "PYTHONPATH=/app",
        CONTAINER,
        "python", WORKER_IN_CONTAINER, container_file_path,
    ]
    proc = subprocess.run(
        cmd, capture_output=True, text=True,
        timeout=WORKER_TIMEOUT_SEC,
    )
    out = (proc.stdout or "").strip()
    if not out:
        raise ValueError(
            f"worker produced no stdout (exit={proc.returncode}); "
            f"stderr={proc.stderr.strip()[:1000]}"
        )
    # Worker emits a single JSON line; tolerate trailing noise just in case.
    last_line = out.splitlines()[-1]
    try:
        result = json.loads(last_line)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"worker stdout was not JSON: {exc}; raw={out[:500]!r}; "
            f"stderr={proc.stderr.strip()[:500]}"
        ) from exc
    return result


# ---- Per-file pipeline --------------------------------------------------

def process_file(path: Path) -> bool:
    """Returns True on success, False on any failure."""
    name = path.name

    matched = match_pattern(name)
    if not matched:
        moved = write_failure(path, "unrecognized filename pattern")
        log(f"  skip {name} -> {moved.name} (unrecognized filename)")
        return False
    tenant, domain, target_table = matched

    log(f"Ingesting {name} ({tenant} {domain}) -> {target_table} ...")

    # Velocity preprocessing: if file has no header row, prepend the
    # canonical one to a temp copy. The worker reads from the temp.
    working_path, cleanup_path = maybe_preprocess_velocity(domain, path)

    container_path = host_to_container_path(working_path)
    if container_path is None:
        moved = write_failure(
            path,
            f"host path {working_path} is not under any known bind-mount",
        )
        log(f"  skip {name} -> {moved.name} (no container path mapping)")
        if cleanup_path is not None:
            cleanup_path.unlink(missing_ok=True)
        return False

    try:
        try:
            result = run_worker(container_path)
        except subprocess.TimeoutExpired:
            write_failure(path, f"worker timed out after {WORKER_TIMEOUT_SEC}s")
            log(f"  FAIL {name}: worker timeout")
            return False
        except ValueError as exc:
            write_failure(path, f"worker transport error: {exc}")
            log(f"  FAIL {name}: {exc}")
            return False
        except Exception as exc:
            write_failure(path, f"unhandled subprocess error: {exc!r}")
            log(f"  FAIL {name}: {exc!r}")
            return False
    finally:
        if cleanup_path is not None:
            try:
                cleanup_path.unlink(missing_ok=True)
            except OSError:
                pass

    if not result.get("ok"):
        reason = (
            f"phase={result.get('phase')} "
            f"error_code={result.get('error_code')} "
            f"error_message={result.get('error_message')} "
            f"detail={json.dumps({k: v for k, v in result.items() if k not in {'phase', 'error_code', 'error_message', 'ok'}})[:1500]}"
        )
        write_failure(path, reason)
        log(f"  FAIL {name}: {result.get('phase')} / {result.get('error_code')} / {result.get('error_message')}")
        return False

    if result.get("duplicate"):
        moved = move_to_processed(path)
        log(f"  duplicate {name} -> existing job {result.get('existing_job_id', '')[:8]} (archived as {moved.name})")
        return True

    rows_inserted = result.get("rows_inserted", 0)
    valid = result.get("row_count_valid", 0)
    rejected = result.get("row_count_rejected", 0)
    replaced = result.get("replaced_job_id")
    log(f"  validated {valid:,} rows ({rejected} rejected)")
    log(f"  ✓ committed {name} -> {target_table} ({rows_inserted:,} rows" +
        (f", replaced {replaced[:8]}" if replaced else "") + ")")
    moved = move_to_processed(path)
    log(f"  archived as {moved.name}")
    return True


# ---- Driver -------------------------------------------------------------

def acquire_lock():
    fd = open(LOCK_PATH, "w")
    try:
        fcntl.flock(fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        log("Another auto_ingest run is in progress; exiting.")
        sys.exit(0)
    return fd


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--inbox", default=DEFAULT_INBOX)
    args = parser.parse_args()

    inbox = Path(args.inbox)
    if not inbox.is_dir():
        log(f"Inbox dir does not exist: {inbox}")
        return 1

    Path(PROCESSED_DIR).mkdir(parents=True, exist_ok=True)
    Path(FAILED_DIR).mkdir(parents=True, exist_ok=True)

    lock_fd = acquire_lock()  # noqa: F841 -- keep lock alive

    log(f"Scanning inbox {inbox} ...")
    files = sorted(
        p for p in inbox.iterdir()
        if p.is_file() and not p.name.startswith(".")
    )
    log(f"Found {len(files)} file(s)")
    if not files:
        return 0

    success_count = 0
    fail_count = 0
    for f in files:
        try:
            ok = process_file(f)
        except Exception as exc:
            try:
                write_failure(f, f"unhandled exception: {exc!r}")
            except Exception:
                pass
            log(f"  FAIL {f.name}: unhandled exception {exc!r}")
            ok = False
        if ok:
            success_count += 1
        else:
            fail_count += 1

    log(f"Done. success={success_count} failed={fail_count}")
    return 0 if fail_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
