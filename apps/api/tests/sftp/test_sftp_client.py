"""Tests for app.ingestion.sftp_client (Phase 1 SFTP foundation)."""
from __future__ import annotations

import pytest

from app.ingestion.sftp_client import SFTPClientError, SFTPSourceClient


def _make_client(sftpserver, **kw) -> SFTPSourceClient:
    """Build a client pointed at the pytest-sftpserver fixture."""
    return SFTPSourceClient(
        host=sftpserver.host,
        port=sftpserver.port,
        username="testuser",
        password="testpass",
        connect_timeout=5,
        **kw,
    )


def test_test_connection_ok(sftpserver):
    with sftpserver.serve_content({"data": {}}):
        client = _make_client(sftpserver)
        result = client.test_connection("/data")
    assert result["ok"] is True
    assert result["server_banner"]
    assert isinstance(result["latency_ms"], int)
    assert result["latency_ms"] >= 0
    assert result["error"] is None


def test_list_matching_jy_regex(sftpserver):
    contents = {
        "jy": {
            "JY_010426.xlsx": b"x" * 100,
            "JY_020426.xlsx": b"x" * 200,
            "PW_010426.csv": b"ignore",
            "JYVelocityData_01.04.2026.csv": b"velocity",
            "README.txt": b"docs",
        }
    }
    with sftpserver.serve_content(contents):
        client = _make_client(sftpserver)
        matches = client.list_matching("/jy", r"^JY_(\d{6})\.xlsx$")

    names = sorted(m["filename"] for m in matches)
    assert names == ["JY_010426.xlsx", "JY_020426.xlsx"]
    sizes = sorted(m["size"] for m in matches)
    assert sizes == [100, 200]
    for m in matches:
        assert m["mtime_utc"].tzinfo is not None


def test_list_matching_no_matches(sftpserver):
    with sftpserver.serve_content({"empty": {"nothing.txt": "x"}}):
        client = _make_client(sftpserver)
        matches = client.list_matching("/empty", r"^DOES_NOT_MATCH_.*$")
    assert matches == []


def test_download_bytes(sftpserver):
    payload = b"hello sftp world \x00\xff\x42"
    with sftpserver.serve_content({"d": {"f.dat": payload}}):
        client = _make_client(sftpserver)
        got = client.download_bytes("/d", "f.dat")
    assert got == payload


def test_test_connection_bogus_host_returns_ok_false():
    client = SFTPSourceClient(
        host="127.0.0.1",
        port=1,
        username="x",
        password="y",
        connect_timeout=2,
    )
    result = client.test_connection()
    assert result["ok"] is False
    assert result["error"]
    assert isinstance(result["latency_ms"], int)


def test_init_mutex_password_pkey_raises():
    fake_pem = (
        "-----BEGIN OPENSSH PRIVATE KEY-----\n"
        "AAAAfake==\n"
        "-----END OPENSSH PRIVATE KEY-----\n"
    )
    with pytest.raises(ValueError, match="mutually exclusive"):
        SFTPSourceClient(
            host="example.com",
            port=22,
            username="u",
            password="p",
            private_key_pem=fake_pem,
        )
