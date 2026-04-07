"""Utilities for extracting file dates from CSV filenames.

Supports both naming conventions:
  New:    Airline_CPI_JY_2026-02-20.csv  (YYYY-MM-DD)
  Legacy: JY_200226.csv                  (DDMMYY)
"""

import os
import re
from datetime import datetime, date


# Patterns ordered by preference (new format first)
_DATE_PATTERNS = [
    (r"_(\d{4}-\d{2}-\d{2})\.csv$", "%Y-%m-%d"),   # YYYY-MM-DD
    (r"_(\d{6})\.csv$",             "%d%m%y"),       # DDMMYY (legacy)
]


def parse_date_from_filename(filename: str) -> date | None:
    """Extract a date from a CSV filename.

    Tries ISO (YYYY-MM-DD) first, then legacy DDMMYY.
    Returns None if no date pattern is found.
    """
    for pattern, fmt in _DATE_PATTERNS:
        match = re.search(pattern, filename)
        if match:
            try:
                return datetime.strptime(match.group(1), fmt).date()
            except ValueError:
                continue
    return None


def get_available_file_dates(data_path: str, subfolders: list[str]) -> list[str]:
    """Scan subfolders for CSV files and return unique sorted dates (latest first).

    Supports both flat layout (/data/JY/) and nested layout (/data/airline/JY/).
    """
    dates: set[str] = set()

    for sub in subfolders:
        folder = os.path.join(data_path, sub)
        if not os.path.isdir(folder):
            continue

        for filename in os.listdir(folder):
            if filename.lower().endswith(".csv"):
                dt = parse_date_from_filename(filename)
                if dt:
                    dates.add(dt.isoformat())

    sorted_dates = sorted(dates, reverse=True)
    return sorted_dates if sorted_dates else ["No file dates available"]


def get_latest_file_date_for_tenant(
    data_path: str, tenant_code: str
) -> date | None:
    """Find the most recent file date across all folders for a given tenant.

    Searches both new (/data/airline/JY, /data/cruise/FJL) and legacy (/data/JY) layouts.
    """
    tenant_folders = {
        "JY":  ["airline/JY", "JY"],
        "PW":  ["airline/PW", "PW"],
        "FJL": ["cruise/FJL", "FJL"],
    }

    folders = tenant_folders.get(tenant_code, [tenant_code])
    best: date | None = None

    for sub in folders:
        folder = os.path.join(data_path, sub)
        if not os.path.isdir(folder):
            continue
        for fname in os.listdir(folder):
            if fname.lower().endswith(".csv"):
                fd = parse_date_from_filename(fname)
                if fd and (best is None or fd > best):
                    best = fd

    return best
