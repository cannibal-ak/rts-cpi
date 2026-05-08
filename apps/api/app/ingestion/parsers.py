"""Shared CSV/XLSX row parsing helpers used by the ingestion service.

These helpers were previously inlined in ``scripts/ingest_daily.py``; they
are kept here so the working logic survives the Phase 6 removal of that
script. The helpers are intentionally lenient: bad rows return safe
defaults (``0``, ``None``) and the caller decides whether the row is
valid based on critical fields.
"""
from __future__ import annotations

import csv
from datetime import date, datetime, time
from typing import Iterator


def parse_date(value: str | None) -> date | None:
    """Parse a date string in any of the formats produced by the source files.

    Returns ``None`` if the value is missing, blank, or unparseable.
    """
    if not value:
        return None
    s = str(value).strip()
    if not s or s == "0":
        return None
    for fmt in ("%d%b%y", "%d%B%y", "%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except (ValueError, TypeError):
            continue
    try:
        return datetime.strptime(s.upper(), "%d%b%y").date()
    except (ValueError, TypeError):
        return None


def parse_velocity_date(value: str | None) -> date | None:
    """Parse a date string from a velocity CSV (M/D/YYYY or ISO)."""
    if not value:
        return None
    s = str(value).strip()
    if not s or s == "0":
        return None
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except (ValueError, TypeError):
            continue
    return None


def parse_time(value: str | None) -> time | None:
    """Parse a time string. Returns ``None`` if missing or unparseable."""
    if not value:
        return None
    s = str(value).strip()
    if not s:
        return None
    for fmt in ("%H:%M", "%H:%M:%S", "%I:%M %p", "%I:%M%p"):
        try:
            return datetime.strptime(s, fmt).time()
        except (ValueError, TypeError):
            continue
    return None


def safe_float(value: object) -> float:
    if not value:
        return 0.0
    try:
        return float(str(value).replace(",", "").strip() or 0)
    except (ValueError, TypeError):
        return 0.0


def safe_int(value: object) -> int:
    if not value:
        return 0
    try:
        return int(str(value).strip() or 0)
    except (ValueError, TypeError):
        return 0


def safe_int_nullable(value: object) -> int | None:
    """Like ``safe_int``, but returns ``None`` for missing/blank/unparseable input.

    Use this for nullable integer DB columns where 0 would be a valid
    semantic value (e.g. ``ref_stops = 0`` is "nonstop"; we don't want
    a missing value to silently look like a nonstop flight).
    """
    if value is None:
        return None
    s = str(value).strip()
    if not s or s.upper() == "NULL":
        return None
    try:
        return int(s)
    except (ValueError, TypeError):
        return None


def read_data_file(file_path: str) -> Iterator[dict]:
    """Yield rows from a CSV or XLSX file as ``dict``s keyed by header.

    Auto-detects format by extension. The XLSX path uses openpyxl in
    read-only mode so memory stays bounded for large workbooks.
    """
    if file_path.lower().endswith(".xlsx"):
        from openpyxl import load_workbook

        wb = load_workbook(file_path, read_only=True, data_only=True)
        try:
            ws = wb.active
            rows_iter = ws.iter_rows(values_only=True)
            try:
                header_row = next(rows_iter)
            except StopIteration:
                return
            headers = [
                str(h).strip() if h is not None else f"col_{i}"
                for i, h in enumerate(header_row)
            ]
            for row_values in rows_iter:
                row_dict: dict[str, str] = {}
                for i, val in enumerate(row_values):
                    if i < len(headers):
                        row_dict[headers[i]] = (
                            str(val).strip() if val is not None else ""
                        )
                yield row_dict
        finally:
            wb.close()
        return

    with open(file_path, "r", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            yield row
