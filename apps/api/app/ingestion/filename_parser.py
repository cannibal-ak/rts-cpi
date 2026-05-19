"""Filename parser for the ingestion overhaul.

Recognises filenames for the supported tenant/domain combinations and extracts
``tenant_code``, ``domain``, and ``file_date``. Patterns are configured in
``filename_patterns.yaml`` beside this module so new tenant/domain pairs can
be added without code changes.

A future date in the filename is rejected (filenames must refer to past or
present data). Empty or unrecognised filenames return a ``ParsedFilename``
with ``is_valid=False`` and a human-readable ``error_reason``.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import yaml


DEFAULT_PATTERNS_FILE = Path(__file__).parent / "filename_patterns.yaml"

VALID_DOMAINS = frozenset({"AIRLINE", "VELOCITY", "CFL"})

SUPPORTED_DATE_FORMATS: dict[str, str] = {
    "DDMMYY": "%d%m%y",
    "DD.MM.YYYY": "%d.%m.%Y",
    "YYYY-MM-DD": "%Y-%m-%d",
}

# Recognised tenant prefixes — used for diagnostic error messages when a
# filename does not match any tight pattern but the user clearly intended one.
KNOWN_PREFIXES = frozenset(
    {"jy", "jyvelocitydata", "pw", "pwvelocitydata", "fjl"}
)
SUPPORTED_EXTENSIONS = frozenset({"csv", "xlsx"})


@dataclass(frozen=True)
class ParsedFilename:
    tenant_code: Optional[str]
    domain: Optional[str]
    file_date: Optional[date]
    is_valid: bool
    error_reason: Optional[str] = None


@dataclass(frozen=True)
class _PatternRule:
    regex: re.Pattern[str]
    tenant_code: str
    domain: str
    date_format: str
    example: str


def _load_patterns(path: Optional[Path] = None) -> list[_PatternRule]:
    """Load pattern rules from a YAML config file."""
    target = path or DEFAULT_PATTERNS_FILE
    with open(target, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}

    rules: list[_PatternRule] = []
    for entry in data.get("patterns", []):
        flags = re.IGNORECASE if entry.get("case_insensitive", True) else 0
        domain = entry["domain"].upper()
        if domain not in VALID_DOMAINS:
            raise ValueError(
                f"Invalid domain '{domain}' in pattern config; "
                f"expected one of {sorted(VALID_DOMAINS)}"
            )
        date_format = entry["date_format"]
        if date_format not in SUPPORTED_DATE_FORMATS:
            raise ValueError(
                f"Unsupported date_format '{date_format}' in pattern config; "
                f"expected one of {sorted(SUPPORTED_DATE_FORMATS)}"
            )
        rules.append(
            _PatternRule(
                regex=re.compile(entry["regex"], flags),
                tenant_code=entry["tenant_code"].upper(),
                domain=domain,
                date_format=date_format,
                example=entry.get("example", ""),
            )
        )
    return rules


_PATTERN_CACHE: Optional[list[_PatternRule]] = None


def _patterns() -> list[_PatternRule]:
    global _PATTERN_CACHE
    if _PATTERN_CACHE is None:
        _PATTERN_CACHE = _load_patterns()
    return _PATTERN_CACHE


def reload_patterns(path: Optional[Path] = None) -> None:
    """Reload pattern config — useful for tests with a custom YAML."""
    global _PATTERN_CACHE
    _PATTERN_CACHE = _load_patterns(path)


def parse_filename(
    name: str, *, today: Optional[date] = None
) -> ParsedFilename:
    """Parse a filename and return a :class:`ParsedFilename`.

    ``today`` is injectable to make the future-date check deterministic in
    tests; defaults to :func:`date.today` when omitted.
    """
    today = today or date.today()
    name = os.path.basename(name).strip()

    if not name:
        return ParsedFilename(None, None, None, False, "empty filename")

    for rule in _patterns():
        m = rule.regex.match(name)
        if not m:
            continue

        date_str = m.group(1)
        fmt = SUPPORTED_DATE_FORMATS[rule.date_format]
        try:
            parsed = datetime.strptime(date_str, fmt).date()
        except ValueError:
            return ParsedFilename(
                rule.tenant_code,
                rule.domain,
                None,
                False,
                f"malformed date '{date_str}' (expected {rule.date_format})",
            )

        if parsed > today:
            return ParsedFilename(
                rule.tenant_code,
                rule.domain,
                parsed,
                False,
                f"file date {parsed.isoformat()} is in the future "
                f"(today is {today.isoformat()})",
            )

        return ParsedFilename(
            rule.tenant_code, rule.domain, parsed, True, None
        )

    return _diagnose_no_match(name)


def _diagnose_no_match(name: str) -> ParsedFilename:
    """Produce an actionable error reason when no tight pattern matched."""
    shape = re.match(
        r"^([A-Za-z]+(?:VelocityData)?)_(.*)\.([A-Za-z0-9]+)$", name
    )
    if not shape:
        return ParsedFilename(
            None,
            None,
            None,
            False,
            f"unknown filename pattern: '{name}'",
        )

    prefix, date_part, ext = (
        shape.group(1),
        shape.group(2),
        shape.group(3).lower(),
    )

    if prefix.lower() in {"jyvelocitydata", "pwvelocitydata"}:
        return ParsedFilename(
            None,
            None,
            None,
            False,
            "Old velocity format detected. Use JY_VL_DDMMYY.csv "
            "or JY_VL_DDMMYY.xlsx instead.",
        )

    if prefix.lower() not in KNOWN_PREFIXES:
        return ParsedFilename(
            None,
            None,
            None,
            False,
            f"unknown tenant prefix '{prefix}'",
        )

    if ext not in SUPPORTED_EXTENSIONS:
        return ParsedFilename(
            None,
            None,
            None,
            False,
            f"unsupported file extension '.{ext}' "
            f"(expected one of {sorted(SUPPORTED_EXTENSIONS)})",
        )

    if not date_part:
        return ParsedFilename(
            None, None, None, False, "missing date in filename"
        )

    for fmt in SUPPORTED_DATE_FORMATS.values():
        try:
            datetime.strptime(date_part, fmt)
            return ParsedFilename(
                None,
                None,
                None,
                False,
                f"file extension '.{ext}' not supported for prefix "
                f"'{prefix}' (check expected extension for this "
                "tenant/domain combination)",
            )
        except ValueError:
            continue

    return ParsedFilename(
        None,
        None,
        None,
        False,
        f"malformed date '{date_part}' in filename",
    )
