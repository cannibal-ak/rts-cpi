#!/usr/bin/env python3
"""Daily CSV auto-ingestion pipeline — one file per tenant.

Folder layout (inside the API container):
  /app/data/airline/JY/  Airline_CPI_JY_YYYY-MM-DD.csv   (or legacy JY_DDMMYY.csv)
  /app/data/airline/PW/  Airline_CPI_PW_YYYY-MM-DD.csv   (or legacy PW_DDMMYY.csv)
  /app/data/cruise/FJL/  Cruise_CPI_FJL_YYYY-MM-DD.csv   (or legacy FJL_DDMMYY.csv)

The script also supports the legacy flat layout:
  /app/data/JY/  JY_DDMMYY.csv
  /app/data/PW/  PW_DDMMYY.csv
  /app/data/FJL/ FJL_DDMMYY.csv

Behaviour:
  1. Scans each tenant folder and picks the newest CSV by filename date.
  2. Checks idempotency: skips if that file's report_date is already loaded.
  3. Loads rows into the existing tenant-partitioned snapshot table.
  4. Creates ImportJob / ImportBatch records for audit trail.
  5. Returns a summary of what was loaded.

Usage:
  python scripts/ingest_daily.py                   # ingest latest for all tenants
  python scripts/ingest_daily.py --tenant JY       # only JY
  python scripts/ingest_daily.py --tenant PW --force  # re-load even if date exists
"""

import os
import re
import csv
import sys
import uuid
import argparse
from datetime import datetime, date
from pathlib import Path
from sqlalchemy import create_engine, text

DATABASE_URL = os.getenv(
    "CPI_DATABASE_URL",
    "postgresql://cpi:cpi_secret@postgres:5432/cpi_db",
)

# ── Tenant configuration ─────────────────────────────────────────

TENANTS = {
    "JY": {
        "id": uuid.UUID("a0000000-0000-0000-0000-000000000001"),
        "code": "JY",
        "domain": "airline",
        "business_type": "AIRLINE",
        "name": "Acme Airways - JY",
        # Folders to scan (first match wins)
        "folders": ["/app/data/airline/JY", "/app/data/JY"],
        # Filename patterns: new naming + legacy naming
        "file_patterns": [
            r"Airline_CPI_JY_(\d{4}-\d{2}-\d{2})\.csv$",   # YYYY-MM-DD
            r"JY_(\d{6})\.csv$",                              # DDMMYY legacy CSV
            r"JY_(\d{6})\.xlsx$",                             # DDMMYY Excel
        ],
        # Velocity data file patterns
        "velocity_patterns": [
            r"JYVelocityData_(\d{2}\.\d{2}\.\d{4})\.csv$",  # DD.MM.YYYY
        ],
    },
    "PW": {
        "id": uuid.UUID("bb000000-0000-0000-0000-000000000001"),
        "code": "PW",
        "domain": "airline",
        "business_type": "AIRLINE",
        "name": "Skybound - PW",
        "folders": ["/app/data/airline/PW", "/app/data/PW"],
        "file_patterns": [
            r"Airline_CPI_PW_(\d{4}-\d{2}-\d{2})\.csv$",
            r"PW_(\d{6})\.csv$",
        ],
    },
    "FJL": {
        "id": uuid.UUID("cc000000-0000-0000-0000-000000000001"),
        "code": "FJL",
        "domain": "cfl",
        "business_type": "CRUISE_FERRY",
        "name": "Baltic Ferries - FJL",
        "folders": ["/app/data/cruise/FJL", "/app/data/FJL"],
        "file_patterns": [
            r"Cruise_CPI_FJL_(\d{4}-\d{2}-\d{2})\.csv$",
            r"FJL_(\d{6})\.csv$",
        ],
    },
}

# ── Parsing utilities ────────────────────────────────────────────


def parse_file_date(filename: str, patterns: list[str]) -> date | None:
    """Extract the report date from a filename using the tenant's patterns."""
    for pattern in patterns:
        m = re.search(pattern, filename)
        if not m:
            continue
        date_str = m.group(1)
        # Try ISO first, then DDMMYY
        for fmt in ("%Y-%m-%d", "%d%m%y"):
            try:
                return datetime.strptime(date_str, fmt).date()
            except ValueError:
                continue
    return None


def find_latest_csv(tenant_cfg: dict) -> tuple[str | None, date | None]:
    """Scan tenant folders and return (filepath, file_date) of the newest pricing file (.csv or .xlsx)."""
    best_path = None
    best_date: date | None = None

    for folder in tenant_cfg["folders"]:
        if not os.path.isdir(folder):
            continue
        for fname in os.listdir(folder):
            if not (fname.lower().endswith(".csv") or fname.lower().endswith(".xlsx")):
                continue
            fd = parse_file_date(fname, tenant_cfg["file_patterns"])
            if fd and (best_date is None or fd > best_date):
                best_date = fd
                best_path = os.path.join(folder, fname)

    return best_path, best_date


def is_already_loaded(conn, table: str, tenant_code: str, file_date: date) -> bool:
    """Check if data for this tenant + report_date is already in the table."""
    result = conn.execute(
        text(f"SELECT 1 FROM {table} WHERE tenant_code = :tc AND report_date = :rd LIMIT 1"),
        {"tc": tenant_code, "rd": file_date},
    ).fetchone()
    return result is not None


# ── CSV field parsers ────────────────────────────────────────────


def parse_date(date_str):
    if not date_str or date_str.strip() in ("0", ""):
        return None
    date_str = date_str.strip()
    for fmt in ("%d%b%y", "%d%B%y", "%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(date_str, fmt).date()
        except (ValueError, TypeError):
            continue
    try:
        return datetime.strptime(date_str.upper(), "%d%b%y").date()
    except (ValueError, TypeError):
        return None


def parse_time(time_str):
    if not time_str or not time_str.strip():
        return None
    time_str = time_str.strip()
    for fmt in ("%H:%M", "%H:%M:%S", "%I:%M %p", "%I:%M%p"):
        try:
            return datetime.strptime(time_str, fmt).time()
        except (ValueError, TypeError):
            continue
    return None


def safe_float(val):
    if not val:
        return 0.0
    try:
        return float(str(val).replace(",", "").strip() or 0)
    except (ValueError, TypeError):
        return 0.0


def safe_int(val):
    if not val:
        return 0
    try:
        return int(str(val).strip() or 0)
    except (ValueError, TypeError):
        return 0


# ── File readers (CSV + XLSX) ───────────────────────────────────


def read_data_file(file_path: str):
    """Read a CSV or XLSX file and yield rows as dicts. Auto-detects by extension."""
    if file_path.lower().endswith(".xlsx"):
        from openpyxl import load_workbook
        wb = load_workbook(file_path, read_only=True, data_only=True)
        ws = wb.active
        rows_iter = ws.iter_rows(values_only=True)
        headers = [str(h).strip() if h else f"col_{i}" for i, h in enumerate(next(rows_iter))]
        for row_values in rows_iter:
            row_dict = {}
            for i, val in enumerate(row_values):
                if i < len(headers):
                    row_dict[headers[i]] = str(val).strip() if val is not None else ""
            yield row_dict
        wb.close()
    else:
        with open(file_path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                yield row


# ── Airline ingestion ────────────────────────────────────────────


def ingest_airline(conn, file_path: str, tenant_cfg: dict, file_date: date) -> dict:
    """Load airline CSV/XLSX into airline_cpi_snapshot. Returns stats dict."""
    tenant_id = tenant_cfg["id"]
    tenant_code = tenant_cfg["code"]
    business_type = tenant_cfg["business_type"]
    source_name = f"daily-ingest:{tenant_code}/{os.path.basename(file_path)}"

    # Create import job
    job_id = uuid.uuid4()
    conn.execute(
        text(
            "INSERT INTO import_job (id, tenant_id, domain, status, source_name, data_owner, started_at) "
            "VALUES (:id, :tid, 'airline', 'validating', :src, :owner, now())"
        ),
        {"id": job_id, "tid": tenant_id, "src": source_name, "owner": tenant_code},
    )
    batch_id = uuid.uuid4()
    conn.execute(
        text(
            "INSERT INTO import_batch (id, tenant_id, import_job_id, batch_seq) "
            "VALUES (:id, :tid, :job_id, 1)"
        ),
        {"id": batch_id, "tid": tenant_id, "job_id": job_id},
    )

    valid = 0
    rejected = 0
    total = 0

    for row in read_data_file(file_path):
        total += 1
        try:
            cap_date = parse_date(row.get("CapDate"))
            if not cap_date:
                rejected += 1
                continue

            params = {
                "id": uuid.uuid4(),
                "tid": tenant_id,
                "bid": batch_id,
                "cd": cap_date,
                "ct": parse_time(row.get("CapTime")) or datetime.now().time(),
                "tt": row.get("TripType", "RT")[:4],
                "ra": row.get("RefAL", tenant_code)[:3],
                "rf": row.get("RefFltNum", "")[:10],
                "ro": row.get("RefOrg", "")[:4],
                "rd": row.get("RefDst", "")[:4],
                "rdd": parse_date(row.get("RefDepDate")) or cap_date,
                "rcc": row.get("RefCabCode", "Y")[:4],
                "rtf": safe_float(row.get("RefTotFare")),
                "rbf": safe_float(row.get("RefBaseFare")),
                "rtax": safe_float(row.get("RefTax")),
                "ryq": safe_float(row.get("RefYQ")),
                "rs": safe_int(row.get("RefSeats") or 9),
                "ca": row.get("CompAL", "")[:3],
                "cf": row.get("CompFltNum", "")[:10],
                "co": row.get("CompOrg", row.get("RefOrg", ""))[:4],
                "cdst": row.get("CompDst", row.get("RefDst", ""))[:4],
                "cdd": parse_date(row.get("CompDepDate")) or cap_date,
                "ccc": row.get("CompCabCode", "Y")[:4],
                "ctf": safe_float(row.get("CompTotFare")),
                "cbf": safe_float(row.get("CompBaseFare")),
                "ctax": safe_float(row.get("CompTax")),
                "cyq": safe_float(row.get("CompYQ")),
                "cs": safe_int(row.get("CompSeats") or 9),
                "owner": tenant_code,
                "tcode": tenant_code,
                "btype": business_type,
                "rdate": file_date,
                "sfile": os.path.basename(file_path),
            }

            conn.execute(
                text("""
                    INSERT INTO airline_cpi_snapshot (
                        id, tenant_id, import_batch_id, cap_date, cap_time, trip_type,
                        ref_al, ref_flt_num, ref_org, ref_dst, ref_dep_date, ref_cab_code,
                        ref_tot_fare, ref_base_fare, ref_tax, ref_yq, ref_seats,
                        comp_al, comp_flt_num, comp_org, comp_dst, comp_dep_date, comp_cab_code,
                        comp_tot_fare, comp_base_fare, comp_tax, comp_yq, comp_seats,
                        pos, poa, data_owner, tenant_code, business_type, report_date, source_file, loaded_at
                    ) VALUES (
                        :id, :tid, :bid, :cd, :ct, :tt,
                        :ra, :rf, :ro, :rd, :rdd, :rcc,
                        :rtf, :rbf, :rtax, :ryq, :rs,
                        :ca, :cf, :co, :cdst, :cdd, :ccc,
                        :ctf, :cbf, :ctax, :cyq, :cs,
                        'US', 'US', :owner, :tcode, :btype, :rdate, :sfile, now()
                    )
                """),
                params,
            )
            valid += 1
        except Exception as e:
            rejected += 1
            if rejected <= 5:
                print(f"  WARN: rejected row #{total} in {tenant_code}: {e}")

    status = "committed" if valid > 0 else "failed"
    conn.execute(
        text(
            "UPDATE import_job SET records_total=:t, records_valid=:v, "
            "records_rejected=:r, status=:s, completed_at=now() WHERE id=:id"
        ),
        {"t": total, "v": valid, "r": rejected, "s": status, "id": job_id},
    )
    conn.execute(
        text("UPDATE import_batch SET record_count=:v WHERE id=:id"),
        {"v": valid, "id": batch_id},
    )

    return {"tenant": tenant_code, "file": os.path.basename(file_path),
            "file_date": str(file_date), "total": total, "valid": valid,
            "rejected": rejected, "status": status, "job_id": str(job_id)}


# ── CFL ingestion ────────────────────────────────────────────────


def ingest_cfl(conn, file_path: str, tenant_cfg: dict, file_date: date) -> dict:
    """Load CFL CSV into cfl_cpi_snapshot. Returns stats dict."""
    tenant_id = tenant_cfg["id"]
    tenant_code = tenant_cfg["code"]
    business_type = tenant_cfg["business_type"]
    source_name = f"daily-ingest:{tenant_code}/{os.path.basename(file_path)}"

    job_id = uuid.uuid4()
    conn.execute(
        text(
            "INSERT INTO import_job (id, tenant_id, domain, status, source_name, data_owner, started_at) "
            "VALUES (:id, :tid, 'cfl', 'validating', :src, :owner, now())"
        ),
        {"id": job_id, "tid": tenant_id, "src": source_name, "owner": tenant_code},
    )
    batch_id = uuid.uuid4()
    conn.execute(
        text(
            "INSERT INTO import_batch (id, tenant_id, import_job_id, batch_seq) "
            "VALUES (:id, :tid, :job_id, 1)"
        ),
        {"id": batch_id, "tid": tenant_id, "job_id": job_id},
    )

    valid = 0
    rejected = 0
    total = 0

    with open(file_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            total += 1
            try:
                cap_date = parse_date(row.get("CapDate"))
                if not cap_date:
                    rejected += 1
                    continue

                params = {
                    "id": uuid.uuid4(),
                    "tid": tenant_id,
                    "owner": tenant_code,
                    "cd": cap_date,
                    "ct": parse_time(row.get("CapTime")) or datetime.now().time(),
                    "tt": row.get("TripType", "ONE_WAY")[:16],
                    "src": row.get("Source", tenant_code)[:64],
                    "org": row.get("Org", "")[:32],
                    "dst": row.get("Dest", "")[:32],
                    "odd": parse_date(row.get("OutDepDate")) or cap_date,
                    "odt": parse_time(row.get("OutDepTime")) or datetime.now().time(),
                    "pf": row.get("ProdFamily", "Standard")[:64],
                    "oen": row.get("OutEquipName", "")[:64],
                    "oct": row.get("OutCabType", "none")[:32],
                    "tf": safe_float(row.get("TotalFare")),
                    "oppf": safe_float(row.get("OutPerPaxFare")),
                    "ovf": safe_float(row.get("OutVehFare")),
                    "ocf": safe_float(row.get("OutCabFare")),
                    "otx": safe_float(row.get("OutTaxes")),
                    "onp": safe_int(row.get("OutNumPax") or 1),
                    "vs": row.get("VehSize", "none")[:16],
                    "cc": row.get("CurrCode", "EUR")[:4],
                    "oa": row.get("OutAvail", "Available")[:16],
                    "tcode": tenant_code,
                    "btype": business_type,
                    "rdate": file_date,
                    "sfile": os.path.basename(file_path),
                }

                conn.execute(
                    text("""
                        INSERT INTO cfl_cpi_snapshot (
                            id, tenant_id, data_owner, cap_date, cap_time, trip_type, source,
                            org, dest, out_dep_date, out_dep_time, prod_family, out_equip_name,
                            out_cab_type, total_fare, out_per_pax_fare, out_veh_fare, out_cab_fare,
                            out_taxes, out_num_pax, veh_size, curr_code, out_avail,
                            tenant_code, business_type, report_date, source_file, loaded_at
                        ) VALUES (
                            :id, :tid, :owner, :cd, :ct, :tt, :src,
                            :org, :dst, :odd, :odt, :pf, :oen,
                            :oct, :tf, :oppf, :ovf, :ocf,
                            :otx, :onp, :vs, :cc, :oa,
                            :tcode, :btype, :rdate, :sfile, now()
                        )
                    """),
                    params,
                )
                valid += 1
            except Exception as e:
                rejected += 1
                if rejected <= 5:
                    print(f"  WARN: rejected row #{total} in {tenant_code}: {e}")

    status = "committed" if valid > 0 else "failed"
    conn.execute(
        text(
            "UPDATE import_job SET records_total=:t, records_valid=:v, "
            "records_rejected=:r, status=:s, completed_at=now() WHERE id=:id"
        ),
        {"t": total, "v": valid, "r": rejected, "s": status, "id": job_id},
    )
    conn.execute(
        text("UPDATE import_batch SET record_count=:v WHERE id=:id"),
        {"v": valid, "id": batch_id},
    )

    return {"tenant": tenant_code, "file": os.path.basename(file_path),
            "file_date": str(file_date), "total": total, "valid": valid,
            "rejected": rejected, "status": status, "job_id": str(job_id)}


# ── Velocity data ingestion ─────────────────────────────────────


def parse_velocity_file_date(filename: str, patterns: list[str]) -> date | None:
    """Extract the report date from a velocity filename."""
    for pattern in patterns:
        m = re.search(pattern, filename)
        if not m:
            continue
        date_str = m.group(1)
        # DD.MM.YYYY format
        try:
            return datetime.strptime(date_str, "%d.%m.%Y").date()
        except ValueError:
            continue
    return None


def find_latest_velocity_csv(tenant_cfg: dict) -> tuple[str | None, date | None]:
    """Scan tenant folders for the newest velocity CSV file."""
    patterns = tenant_cfg.get("velocity_patterns")
    if not patterns:
        return None, None

    best_path = None
    best_date: date | None = None

    for folder in tenant_cfg["folders"]:
        if not os.path.isdir(folder):
            continue
        for fname in os.listdir(folder):
            if not fname.lower().endswith(".csv"):
                continue
            fd = parse_velocity_file_date(fname, patterns)
            if fd and (best_date is None or fd > best_date):
                best_date = fd
                best_path = os.path.join(folder, fname)

    return best_path, best_date


def parse_velocity_date(date_str):
    """Parse dates in M/D/YYYY format from velocity CSV."""
    if not date_str or date_str.strip() in ("0", ""):
        return None
    date_str = date_str.strip()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(date_str, fmt).date()
        except (ValueError, TypeError):
            continue
    return None


def ingest_velocity(conn, file_path: str, tenant_cfg: dict, file_date: date) -> dict:
    """Load velocity CSV into jy_velocity_snapshot. Returns stats dict."""
    tenant_id = tenant_cfg["id"]
    tenant_code = tenant_cfg["code"]
    business_type = tenant_cfg["business_type"]
    source_name = f"daily-ingest:{tenant_code}/velocity/{os.path.basename(file_path)}"

    # Create import job for velocity data
    job_id = uuid.uuid4()
    conn.execute(
        text(
            "INSERT INTO import_job (id, tenant_id, domain, status, source_name, data_owner, started_at) "
            "VALUES (:id, :tid, 'velocity', 'validating', :src, :owner, now())"
        ),
        {"id": job_id, "tid": tenant_id, "src": source_name, "owner": tenant_code},
    )
    batch_id = uuid.uuid4()
    conn.execute(
        text(
            "INSERT INTO import_batch (id, tenant_id, import_job_id, batch_seq) "
            "VALUES (:id, :tid, :job_id, 1)"
        ),
        {"id": batch_id, "tid": tenant_id, "job_id": job_id},
    )

    valid = 0
    rejected = 0
    total = 0

    with open(file_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            total += 1
            try:
                dep_date = parse_velocity_date(row.get("DepDate"))
                if not dep_date:
                    rejected += 1
                    continue

                city_pair = row.get("CityPair", "").strip()
                origin = city_pair[:3] if len(city_pair) >= 6 else ""
                destination = city_pair[3:] if len(city_pair) >= 6 else ""
                dep_code_raw = row.get("DepCode", "").strip()

                params = {
                    "id": uuid.uuid4(),
                    "tid": tenant_id,
                    "bid": batch_id,
                    "dd": dep_date,
                    "dt": row.get("DepTime", "").strip()[:8],
                    "dc": dep_code_raw[:10],
                    "cp": city_pair[:8],
                    "org": origin[:4],
                    "dst": destination[:4],
                    "eqp": row.get("Eqp", "").strip()[:8],
                    "lst": row.get("LegsegType", "").strip()[:10],
                    "lso": safe_int(row.get("LegSegOrder") or 1),
                    "dl": safe_int(row.get("Days_Left") or 0),
                    "comp": row.get("Compartment", "Y").strip()[:4],
                    "cb": safe_int(row.get("Current_Booking") or 0),
                    "cap": safe_int(row.get("Capacity") or 0),
                    "asf": safe_int(row.get("Actual_Seat_Factor") or 0),
                    "fsf": safe_int(row.get("Forecasted_Seat_Factor") or 0),
                    "owner": tenant_code,
                    "tcode": tenant_code,
                    "btype": business_type,
                    "rdate": file_date,
                    "sfile": os.path.basename(file_path),
                }

                conn.execute(
                    text("""
                        INSERT INTO jy_velocity_snapshot (
                            id, tenant_id, import_batch_id,
                            dep_date, dep_time, dep_code, city_pair, origin, destination, eqp,
                            legseg_type, leg_seg_order, days_left, compartment,
                            current_booking, capacity, actual_seat_factor, forecasted_seat_factor,
                            data_owner, tenant_code, business_type, report_date, source_file, loaded_at
                        ) VALUES (
                            :id, :tid, :bid,
                            :dd, :dt, :dc, :cp, :org, :dst, :eqp,
                            :lst, :lso, :dl, :comp,
                            :cb, :cap, :asf, :fsf,
                            :owner, :tcode, :btype, :rdate, :sfile, now()
                        )
                    """),
                    params,
                )
                valid += 1
            except Exception as e:
                rejected += 1
                if rejected <= 5:
                    print(f"  WARN: rejected velocity row #{total} in {tenant_code}: {e}")

    status = "committed" if valid > 0 else "failed"
    conn.execute(
        text(
            "UPDATE import_job SET records_total=:t, records_valid=:v, "
            "records_rejected=:r, status=:s, completed_at=now() WHERE id=:id"
        ),
        {"t": total, "v": valid, "r": rejected, "s": status, "id": job_id},
    )
    conn.execute(
        text("UPDATE import_batch SET record_count=:v WHERE id=:id"),
        {"v": valid, "id": batch_id},
    )

    return {"tenant": tenant_code, "file": os.path.basename(file_path),
            "file_date": str(file_date), "total": total, "valid": valid,
            "rejected": rejected, "status": status, "job_id": str(job_id),
            "type": "velocity"}


# ── Main entry point ─────────────────────────────────────────────


def find_all_pricing_files(tenant_cfg: dict) -> list[tuple[str, date]]:
    """Return all (filepath, file_date) pairs for pricing files (.csv or .xlsx), sorted newest-first."""
    found = []
    for folder in tenant_cfg["folders"]:
        if not os.path.isdir(folder):
            continue
        for fname in os.listdir(folder):
            if not (fname.lower().endswith(".csv") or fname.lower().endswith(".xlsx")):
                continue
            fd = parse_file_date(fname, tenant_cfg["file_patterns"])
            if fd:
                found.append((os.path.join(folder, fname), fd))
    found.sort(key=lambda x: x[1], reverse=True)
    return found


def find_all_velocity_files(tenant_cfg: dict) -> list[tuple[str, date]]:
    """Return all (filepath, file_date) pairs for velocity CSVs, sorted newest-first."""
    patterns = tenant_cfg.get("velocity_patterns")
    if not patterns:
        return []
    found = []
    for folder in tenant_cfg["folders"]:
        if not os.path.isdir(folder):
            continue
        for fname in os.listdir(folder):
            if not fname.lower().endswith(".csv"):
                continue
            fd = parse_velocity_file_date(fname, patterns)
            if fd:
                found.append((os.path.join(folder, fname), fd))
    found.sort(key=lambda x: x[1], reverse=True)
    return found


def ingest_tenant(conn, tenant_code: str, force: bool = False) -> list[dict]:
    """Ingest the latest CSV(s) for one tenant. Returns list of stats dicts."""
    cfg = TENANTS.get(tenant_code)
    if not cfg:
        print(f"ERROR: Unknown tenant '{tenant_code}'")
        return []

    # ══════════════════════════════════════════════════════
    # JY: Paired-file validation — both files required,
    #     dates must match, pick latest matching pair.
    # ══════════════════════════════════════════════════════
    if cfg.get("velocity_patterns"):
        pricing_files = find_all_pricing_files(cfg)
        velocity_files = find_all_velocity_files(cfg)

        pricing_dates = {fd for _, fd in pricing_files}
        velocity_dates = {fd for _, fd in velocity_files}

        has_pricing = len(pricing_files) > 0
        has_velocity = len(velocity_files) > 0

        # ── Validation: both file types must be present ──
        if not has_pricing and not has_velocity:
            msg = f"VALIDATION_ERROR: [{tenant_code}] No files found. Both pricing and JYVelocityData files are required for JY ingestion."
            print(msg)
            sys.exit(1)
        if has_pricing and not has_velocity:
            p_date = pricing_files[0][1]
            msg = f"VALIDATION_ERROR: [{tenant_code}] Both files (pricing + JYVelocityData) are required for JY ingestion. Found pricing file dated {p_date} but no JYVelocityData file."
            print(msg)
            sys.exit(1)
        if has_velocity and not has_pricing:
            v_date = velocity_files[0][1]
            msg = f"VALIDATION_ERROR: [{tenant_code}] Both files (pricing + JYVelocityData) are required for JY ingestion. Found JYVelocityData file dated {v_date} but no pricing file."
            print(msg)
            sys.exit(1)

        # ── Validation: find matching date pair ──
        matching_dates = sorted(pricing_dates & velocity_dates, reverse=True)
        if not matching_dates:
            p_date = pricing_files[0][1]
            v_date = velocity_files[0][1]
            msg = f"VALIDATION_ERROR: [{tenant_code}] File date mismatch — pricing file is dated {p_date} and JYVelocityData file is dated {v_date}. Both must be for the same date."
            print(msg)
            sys.exit(1)

        # ── Pick the latest matching pair ──
        target_date = matching_dates[0]
        pricing_path = next(p for p, d in pricing_files if d == target_date)
        velocity_path = next(p for p, d in velocity_files if d == target_date)

        print(f"  [{tenant_code}] Matched file pair for date {target_date}:")
        print(f"    Pricing:  {os.path.basename(pricing_path)}")
        print(f"    Velocity: {os.path.basename(velocity_path)}")

        # ── Idempotency: check if BOTH files are already ingested ──
        pricing_loaded = is_already_loaded(conn, "airline_cpi_snapshot", tenant_code, target_date)
        velocity_loaded = is_already_loaded(conn, "jy_velocity_snapshot", tenant_code, target_date)

        if not force and pricing_loaded and velocity_loaded:
            # Both already ingested — get the last ingestion timestamp for the message
            last_ingest = conn.execute(
                text(
                    "SELECT MAX(completed_at) FROM import_job "
                    "WHERE data_owner = :tc AND status = 'committed' "
                    "AND source_name LIKE :pattern"
                ),
                {"tc": tenant_code, "pattern": f"%{os.path.basename(pricing_path)}%"},
            ).scalar()
            ts_str = last_ingest.strftime("%Y-%m-%d at %H:%M:%S") if last_ingest else "unknown"
            msg = (
                f"ALREADY_INGESTED: [{tenant_code}] Data already ingested. "
                f"Files {os.path.basename(pricing_path)} and {os.path.basename(velocity_path)} "
                f"were ingested on {ts_str}. No new data to process."
            )
            print(msg)
            return []

        results = []

        # ── Force mode: delete snapshot data first, then clean up job records ──
        if force:
            # 1. Delete snapshot data for this date (must happen BEFORE batch cleanup due to FK)
            conn.execute(
                text("DELETE FROM airline_cpi_snapshot WHERE tenant_code = :tc AND report_date = :rd"),
                {"tc": tenant_code, "rd": target_date},
            )
            conn.execute(
                text("DELETE FROM jy_velocity_snapshot WHERE tenant_code = :tc AND report_date = :rd"),
                {"tc": tenant_code, "rd": target_date},
            )
            print(f"  [{tenant_code}] Cleared existing data for report_date={target_date}")

            # 2. Delete old import_batch and import_job records for these specific files
            p_source = f"daily-ingest:{tenant_code}/{os.path.basename(pricing_path)}"
            v_source = f"daily-ingest:{tenant_code}/velocity/{os.path.basename(velocity_path)}"
            old_job_ids = conn.execute(
                text(
                    "SELECT j.id FROM import_job j "
                    "WHERE j.data_owner = :tc "
                    "AND (j.source_name = :p_src OR j.source_name = :v_src)"
                ),
                {"tc": tenant_code, "p_src": p_source, "v_src": v_source},
            ).fetchall()
            old_ids = [str(r[0]) for r in old_job_ids]
            if old_ids:
                for oid in old_ids:
                    conn.execute(text("DELETE FROM import_batch WHERE import_job_id = :jid"), {"jid": oid})
                    conn.execute(text("DELETE FROM import_job WHERE id = :jid"), {"jid": oid})
                print(f"  [{tenant_code}] Cleaned up {len(old_ids)} old job record(s)")

        # ── Ingest pricing file (data already cleared above in force mode) ──
        if not force and pricing_loaded:
            print(f"  [{tenant_code}] SKIP pricing — report_date={target_date} already loaded.")
        else:
            result = ingest_airline(conn, pricing_path, cfg, target_date)
            if result:
                results.append(result)

        # ── Ingest velocity file (data already cleared above in force mode) ──
        if not force and velocity_loaded:
            print(f"  [{tenant_code}] SKIP velocity — report_date={target_date} already loaded.")
        else:
            vel_result = ingest_velocity(conn, velocity_path, cfg, target_date)
            if vel_result:
                results.append(vel_result)

        if results:
            p_count = next((r["valid"] for r in results if r.get("type") != "velocity"), 0)
            v_count = next((r["valid"] for r in results if r.get("type") == "velocity"), 0)
            print(
                f"  [{tenant_code}] SUCCESS — ingested {len(results)} file(s) for date {target_date} "
                f"({p_count} pricing + {v_count} velocity records)"
            )

        return results

    # ══════════════════════════════════════════════════════
    # PW / FJL: Single-file flow (unchanged)
    # ══════════════════════════════════════════════════════
    file_path, file_date = find_latest_csv(cfg)
    if not file_path:
        print(f"  [{tenant_code}] No CSV files found in {cfg['folders']}")
        return []

    print(f"  [{tenant_code}] Latest file: {os.path.basename(file_path)} (date={file_date})")

    table = "airline_cpi_snapshot" if cfg["domain"] == "airline" else "cfl_cpi_snapshot"
    if not force and is_already_loaded(conn, table, tenant_code, file_date):
        print(f"  [{tenant_code}] SKIP — report_date={file_date} already loaded. Use --force to reload.")
        return []

    if force:
        conn.execute(
            text(f"DELETE FROM {table} WHERE tenant_code = :tc AND report_date = :rd"),
            {"tc": tenant_code, "rd": file_date},
        )
        print(f"  [{tenant_code}] Cleared existing data for report_date={file_date}")

    if cfg["domain"] == "airline":
        result = ingest_airline(conn, file_path, cfg, file_date)
    else:
        result = ingest_cfl(conn, file_path, cfg, file_date)

    return [result] if result else []


def main():
    parser = argparse.ArgumentParser(description="Daily CSV auto-ingestion")
    parser.add_argument("--tenant", help="Ingest only this tenant (JY/PW/FJL)")
    parser.add_argument("--force", action="store_true", help="Re-load even if date exists")
    args = parser.parse_args()

    tenants_to_run = [args.tenant] if args.tenant else list(TENANTS.keys())

    engine = create_engine(DATABASE_URL)
    results = []

    with engine.connect() as conn:
        with conn.begin():
            # Ensure tenants exist
            for code in tenants_to_run:
                cfg = TENANTS.get(code)
                if not cfg:
                    continue
                res = conn.execute(
                    text("SELECT 1 FROM tenant WHERE id = :tid"),
                    {"tid": cfg["id"]},
                ).fetchone()
                if not res:
                    conn.execute(
                        text("INSERT INTO tenant (id, slug, display_name) VALUES (:tid, :slug, :name)"),
                        {"tid": cfg["id"], "slug": cfg["code"].lower(), "name": cfg["name"]},
                    )

            print(f"=== Daily Ingestion — {datetime.now().isoformat()} ===")
            for code in tenants_to_run:
                tenant_results = ingest_tenant(conn, code, force=args.force)
                results.extend(tenant_results)

    # Summary
    print("\n=== Ingestion Summary ===")
    if not results:
        print("  No new data ingested (all tenants up-to-date or no files found).")
    else:
        for r in results:
            rtype = r.get('type', 'pricing')
            print(f"  [{r['tenant']}] ({rtype}) {r['file']} → {r['valid']}/{r['total']} rows ({r['status']})")

    return results


if __name__ == "__main__":
    main()
