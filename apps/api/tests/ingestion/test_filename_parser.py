"""Unit tests for app.ingestion.filename_parser."""
from datetime import date

import pytest

from app.ingestion.filename_parser import ParsedFilename, parse_filename


# Reference "today" used in tests for deterministic future-date detection.
# Picked well after the latest canonical sample-data date (May 19, 2026 — the
# velocity-format-change cutover) so the valid filenames are always in the past.
TEST_TODAY = date(2026, 5, 31)


# ── Valid filenames ────────────────────────────────────────────────


@pytest.mark.parametrize(
    "filename,expected_tenant,expected_domain,expected_date",
    [
        ("JY_010426.xlsx", "JY", "AIRLINE", date(2026, 4, 1)),
        # Velocity: new JY_VL_DDMMYY.{csv|CSV|xlsx|XLSX} format, all 4 ext variants.
        ("JY_VL_190526.CSV", "JY", "VELOCITY", date(2026, 5, 19)),
        ("JY_VL_190526.csv", "JY", "VELOCITY", date(2026, 5, 19)),
        ("JY_VL_190526.XLSX", "JY", "VELOCITY", date(2026, 5, 19)),
        ("JY_VL_190526.xlsx", "JY", "VELOCITY", date(2026, 5, 19)),
        ("PW_010426.xlsx", "PW", "AIRLINE", date(2026, 4, 1)),
        # Velocity: new PW_VL_DDMMYY.{csv|CSV|xlsx|XLSX} format, all 4 ext variants.
        ("PW_VL_190526.CSV", "PW", "VELOCITY", date(2026, 5, 19)),
        ("PW_VL_190526.csv", "PW", "VELOCITY", date(2026, 5, 19)),
        ("PW_VL_190526.XLSX", "PW", "VELOCITY", date(2026, 5, 19)),
        ("PW_VL_190526.xlsx", "PW", "VELOCITY", date(2026, 5, 19)),
        ("FJL_010426.csv", "FJL", "CFL", date(2026, 4, 1)),
    ],
)
def test_valid_patterns(
    filename: str,
    expected_tenant: str,
    expected_domain: str,
    expected_date: date,
) -> None:
    result = parse_filename(filename, today=TEST_TODAY)
    assert result.is_valid, f"expected valid, got error: {result.error_reason}"
    assert result.tenant_code == expected_tenant
    assert result.domain == expected_domain
    assert result.file_date == expected_date
    assert result.error_reason is None


def test_case_insensitive_match() -> None:
    """Lowercase filename should still match (case_insensitive=true in YAML)."""
    result = parse_filename("jy_010426.XLSX", today=TEST_TODAY)
    assert result.is_valid
    assert result.tenant_code == "JY"
    assert result.domain == "AIRLINE"
    assert result.file_date == date(2026, 4, 1)


def test_basename_extraction() -> None:
    """parse_filename should accept full paths and use the basename only."""
    result = parse_filename(
        "/tmp/uploads/PW_010426.xlsx", today=TEST_TODAY
    )
    assert result.is_valid
    assert result.tenant_code == "PW"


# ── Invalid filenames (the 6 required edge cases) ─────────────────


def test_empty_filename() -> None:
    result = parse_filename("", today=TEST_TODAY)
    assert not result.is_valid
    assert result.error_reason == "empty filename"
    assert result.tenant_code is None
    assert result.file_date is None


def test_whitespace_only_filename() -> None:
    result = parse_filename("   ", today=TEST_TODAY)
    assert not result.is_valid
    assert result.error_reason == "empty filename"


def test_unknown_prefix() -> None:
    result = parse_filename("XYZ_010426.csv", today=TEST_TODAY)
    assert not result.is_valid
    assert "unknown tenant prefix" in result.error_reason
    assert "XYZ" in result.error_reason


def test_wrong_extension() -> None:
    """Known prefix + valid date but unsupported extension."""
    result = parse_filename("PW_010426.txt", today=TEST_TODAY)
    assert not result.is_valid
    assert "unsupported file extension" in result.error_reason
    assert ".txt" in result.error_reason


def test_malformed_date() -> None:
    """Right shape but the date portion is not parseable."""
    result = parse_filename("PW_XXXXXX.xlsx", today=TEST_TODAY)
    assert not result.is_valid
    assert "malformed date" in result.error_reason


def test_missing_date() -> None:
    """Right shape but the date portion is empty."""
    result = parse_filename("PW_.xlsx", today=TEST_TODAY)
    assert not result.is_valid
    assert result.error_reason == "missing date in filename"


def test_future_date() -> None:
    """A correctly-formed filename whose date is after today is rejected."""
    # 011230 in DDMMYY = 2030-12-01, comfortably after TEST_TODAY (2026-04-30).
    result = parse_filename("PW_011230.xlsx", today=TEST_TODAY)
    assert not result.is_valid
    assert result.tenant_code == "PW"  # tenant identified
    assert result.domain == "AIRLINE"
    assert result.file_date == date(2030, 12, 1)
    assert "future" in result.error_reason


# ── Additional coverage ────────────────────────────────────────────


def test_extension_mismatch_for_tenant() -> None:
    """JY pricing requires .xlsx; .csv with a JY prefix should be rejected
    with a clear hint about the wrong extension."""
    result = parse_filename("JY_010426.csv", today=TEST_TODAY)
    assert not result.is_valid
    assert "extension" in result.error_reason.lower()


def test_pw_extension_mismatch() -> None:
    """PW pricing requires .xlsx (mirrors JY); .csv should be rejected."""
    result = parse_filename("PW_010426.csv", today=TEST_TODAY)
    assert not result.is_valid
    assert "extension" in result.error_reason.lower()


def test_garbage_filename() -> None:
    """A filename that doesn't even match the prefix_DATE.ext shape."""
    result = parse_filename("not-a-real-filename", today=TEST_TODAY)
    assert not result.is_valid
    assert "unknown filename pattern" in result.error_reason


def test_parsed_filename_is_frozen_dataclass() -> None:
    """ParsedFilename should be immutable so callers can't mutate it."""
    result = parse_filename("PW_010426.xlsx", today=TEST_TODAY)
    assert isinstance(result, ParsedFilename)
    with pytest.raises(Exception):
        result.is_valid = False  # type: ignore[misc]


# ── Velocity filename-format-change cutover (2026-05-19) ──────────


def test_old_velocity_format_rejected_jy() -> None:
    """Pre-2026-05-19 JYVelocityData_DD.MM.YYYY format is dead and must be
    rejected with a hint pointing at the new JY_VL_DDMMYY format."""
    result = parse_filename(
        "JYVelocityData_19.05.2026.csv", today=TEST_TODAY
    )
    assert not result.is_valid
    assert "Old velocity format detected" in result.error_reason
    assert "JY_VL_DDMMYY" in result.error_reason


def test_old_velocity_format_rejected_pw() -> None:
    result = parse_filename(
        "PWVelocityData_19.05.2026.csv", today=TEST_TODAY
    )
    assert not result.is_valid
    assert "Old velocity format detected" in result.error_reason


def test_velocity_wrong_extension_txt() -> None:
    result = parse_filename("JY_VL_190526.txt", today=TEST_TODAY)
    assert not result.is_valid
    assert "unsupported file extension" in result.error_reason


def test_velocity_wrong_extension_pdf() -> None:
    result = parse_filename("JY_VL_190526.pdf", today=TEST_TODAY)
    assert not result.is_valid
    assert "unsupported file extension" in result.error_reason


def test_velocity_eight_digit_date_rejected() -> None:
    """The new format is DDMMYY (6 digits), not DDMMYYYY (8 digits)."""
    result = parse_filename("JY_VL_19052026.csv", today=TEST_TODAY)
    assert not result.is_valid


def test_velocity_missing_date_rejected() -> None:
    result = parse_filename("JY_VL_.csv", today=TEST_TODAY)
    assert not result.is_valid


def test_velocity_invalid_day_rejected() -> None:
    """Day 32 is impossible; strptime must reject it."""
    result = parse_filename("JY_VL_320526.csv", today=TEST_TODAY)
    assert not result.is_valid
    assert "malformed date" in result.error_reason


def test_velocity_lowercase_prefix_rejected() -> None:
    """Velocity prefix must be UPPERCASE (JY_VL_, PW_VL_) — unlike pricing,
    velocity is case-sensitive on the prefix. Extension stays case-insensitive."""
    result = parse_filename("jy_vl_190526.csv", today=TEST_TODAY)
    assert not result.is_valid
