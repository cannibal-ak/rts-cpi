"""Unit tests for the VELOCITY branch of ``read_data_file``.

These cover the empty-file / leading-blank-line hardening added after
run 5e041969 aborted on PW_VL_030326.csv (2,390 all-blank CRLF lines).
Pure parser-level tests — no DB, no SFTP.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.ingestion.parsers import read_data_file

HEADER = (
    "DepDate,DepTime,DepCode,CityPair,Eqp,LegsegType,LegSegOrder,"
    "Days_Left,Compartment,Current_Booking,Capacity,"
    "Actual_Seat_Factor,Forecasted_Seat_Factor"
)
ROW = "4/1/2026,0900,0416,DELBOM,AT4,Leg,1,0,Y,21,48,44,85"


def _write(tmp_path: Path, name: str, content) -> str:
    p = tmp_path / name
    if isinstance(content, str):
        content = content.encode("utf-8")
    p.write_bytes(content)
    return str(p)


def test_all_blank_crlf_file_is_skipped(tmp_path):
    """(a) Reproduce PW_VL_030326.csv: nothing but blank CRLF lines.

    Must yield zero rows and NOT raise — the empty-skip.
    """
    path = _write(tmp_path, "PW_VL_030326.csv", "\r\n" * 2390)
    rows = list(read_data_file(path, domain="VELOCITY"))
    assert rows == []


def test_leading_blanks_then_headerless_data(tmp_path):
    """(b) Leading blank lines before valid 13-col headerless data."""
    path = _write(tmp_path, "v.csv", "\r\n\r\n" + ROW + "\r\n" + ROW + "\r\n")
    rows = list(read_data_file(path, domain="VELOCITY"))
    assert len(rows) == 2
    assert rows[0]["DepDate"] == "4/1/2026"
    assert rows[0]["Forecasted_Seat_Factor"] == "85"


def test_valid_headerless_unchanged(tmp_path):
    """(c) Valid headerless 13-col file: canonical header injected."""
    path = _write(tmp_path, "v.csv", ROW + "\n" + ROW + "\n")
    rows = list(read_data_file(path, domain="VELOCITY"))
    assert len(rows) == 2
    assert rows[0]["DepCode"] == "0416"
    assert rows[0]["CityPair"] == "DELBOM"


def test_headered_file_unchanged(tmp_path):
    """(d) File starting with the DepDate header: header drives keys."""
    path = _write(tmp_path, "v.csv", HEADER + "\n" + ROW + "\n")
    rows = list(read_data_file(path, domain="VELOCITY"))
    assert len(rows) == 1
    assert rows[0]["DepDate"] == "4/1/2026"
    assert rows[0]["Capacity"] == "48"


def test_content_with_wrong_column_count_still_raises(tmp_path):
    """(e) Headerless content with != 13 columns must still raise loudly."""
    path = _write(tmp_path, "v.csv", "4/1/2026,0900,0416,DELBOM,AT4\n")
    with pytest.raises(ValueError, match="expected 13"):
        list(read_data_file(path, domain="VELOCITY"))


def test_trailing_blank_line_tolerated(tmp_path):
    """A valid headerless file with a trailing blank line parses cleanly
    (the blank row is skipped, no junk row, no raise)."""
    path = _write(tmp_path, "v.csv", ROW + "\r\n" + ROW + "\r\n\r\n")
    rows = list(read_data_file(path, domain="VELOCITY"))
    assert len(rows) == 2
    assert rows[-1]["DepCode"] == "0416"
