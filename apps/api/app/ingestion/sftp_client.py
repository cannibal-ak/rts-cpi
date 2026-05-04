"""Paramiko-based SFTP client for SFTP-driven ingestion (Phase 1 foundation).

Import-safe: paramiko is imported but no SSH session is opened until a
SFTPSourceClient instance method runs.

Design: each public method opens its own connection, performs one
read-only operation, and closes - trading a small per-call setup cost
for simple, predictable error semantics. No long-lived sessions.
"""
from __future__ import annotations

import base64
import hashlib
import io
import logging
import posixpath
import re
import time
from datetime import datetime, timezone
from typing import Any, Optional

import paramiko

logger = logging.getLogger(__name__)


class SFTPClientError(Exception):
    """Operational failure inside SFTPSourceClient.

    Attributes:
        code:    short machine-readable identifier (e.g. ``connect_failed``).
        message: human-readable description (may be empty).
        detail:  free-form structured context (host, path, original error).
    """

    def __init__(self, code: str, message: str = "", **detail: Any) -> None:
        self.code = code
        self.message = message
        self.detail = detail
        super().__init__(f"{code}: {message}" if message else code)


def _load_private_key(pem: str) -> paramiko.PKey:
    """Parse a PEM-encoded private key by trying each supported type."""
    last_err: Optional[Exception] = None
    for key_class in (
        paramiko.Ed25519Key,
        paramiko.RSAKey,
        paramiko.ECDSAKey,
        paramiko.DSSKey,
    ):
        try:
            return key_class.from_private_key(io.StringIO(pem))
        except paramiko.SSHException as exc:
            last_err = exc
    raise SFTPClientError(
        "private_key_unparseable",
        message=f"Could not parse private key as any supported type: {last_err}",
    )


def _fingerprint(key: paramiko.PKey) -> str:
    """Return sha256:<base64-no-padding> matching ssh's host-key format."""
    digest = hashlib.sha256(key.asbytes()).digest()
    return "sha256:" + base64.b64encode(digest).decode("ascii").rstrip("=")


class SFTPSourceClient:
    """Read-only SFTP client for scheduled ingestion pulls.

    Phase 1 scope: connect, stat, listdir-with-regex, read-bytes. Mutually
    exclusive password / private_key_pem auth. Optional host-key
    fingerprint verification (SHA-256 base64). All failures surface as
    SFTPClientError; only ``test_connection`` swallows them and returns a
    diagnostic dict.
    """

    def __init__(
        self,
        host: str,
        port: int,
        username: str,
        password: Optional[str] = None,
        private_key_pem: Optional[str] = None,
        host_key_fingerprint: Optional[str] = None,
        connect_timeout: int = 10,
    ) -> None:
        if password is not None and private_key_pem is not None:
            raise ValueError(
                "password and private_key_pem are mutually exclusive - "
                "pass exactly one"
            )
        if password is None and private_key_pem is None:
            raise ValueError("must provide one of password or private_key_pem")

        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.host_key_fingerprint = host_key_fingerprint
        self.connect_timeout = connect_timeout
        self._pkey: Optional[paramiko.PKey] = (
            _load_private_key(private_key_pem) if private_key_pem else None
        )

    def _open(self) -> tuple[paramiko.SSHClient, paramiko.SFTPClient]:
        client = paramiko.SSHClient()
        if not self.host_key_fingerprint:
            logger.warning(
                "SFTP connection to %s:%s has no host_key_fingerprint - "
                "using AutoAddPolicy. Phase 5 will tighten this.",
                self.host,
                self.port,
            )
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        try:
            client.connect(
                hostname=self.host,
                port=self.port,
                username=self.username,
                password=self.password,
                pkey=self._pkey,
                timeout=self.connect_timeout,
                allow_agent=False,
                look_for_keys=False,
            )
        except Exception as exc:
            raise SFTPClientError(
                "connect_failed",
                message=str(exc),
                host=self.host,
                port=self.port,
                username=self.username,
            ) from exc

        if self.host_key_fingerprint:
            transport = client.get_transport()
            assert transport is not None
            actual = _fingerprint(transport.get_remote_server_key())
            if actual != self.host_key_fingerprint:
                client.close()
                raise SFTPClientError(
                    "host_key_mismatch",
                    message="Server host key does not match expected fingerprint",
                    expected=self.host_key_fingerprint,
                    actual=actual,
                    host=self.host,
                )

        try:
            sftp = client.open_sftp()
        except Exception as exc:
            client.close()
            raise SFTPClientError(
                "sftp_subsystem_failed", message=str(exc), host=self.host
            ) from exc

        return client, sftp

    @staticmethod
    def _safe_close(*objs: Any) -> None:
        for o in objs:
            if o is None:
                continue
            try:
                o.close()
            except Exception:
                pass

    def test_connection(self, remote_path: str = ".") -> dict:
        """Open, stat ``remote_path``, close. Always returns a dict.

        Returns ``{ok, server_banner, latency_ms, error}``. Never raises.
        """
        start = time.monotonic()
        client: Optional[paramiko.SSHClient] = None
        sftp: Optional[paramiko.SFTPClient] = None
        try:
            client, sftp = self._open()
            transport = client.get_transport()
            banner = transport.remote_version if transport else ""
            sftp.stat(remote_path)
            return {
                "ok": True,
                "server_banner": banner,
                "latency_ms": int((time.monotonic() - start) * 1000),
                "error": None,
            }
        except SFTPClientError as exc:
            return {
                "ok": False,
                "server_banner": "",
                "latency_ms": int((time.monotonic() - start) * 1000),
                "error": (
                    f"{exc.code}: {exc.message}" if exc.message else exc.code
                ),
            }
        except Exception as exc:
            return {
                "ok": False,
                "server_banner": "",
                "latency_ms": int((time.monotonic() - start) * 1000),
                "error": str(exc),
            }
        finally:
            self._safe_close(sftp, client)

    def list_matching(self, remote_path: str, regex: str) -> list[dict]:
        """List entries under ``remote_path`` matching ``regex``.

        Regex is compiled with re.ASCII to avoid Unicode-class surprises.
        Returns ``[{filename, size, mtime_utc}, ...]``. Raises
        SFTPClientError on any failure.
        """
        try:
            pattern = re.compile(regex, re.ASCII)
        except re.error as exc:
            raise SFTPClientError(
                "invalid_regex",
                message=f"Failed to compile regex {regex!r}: {exc}",
                regex=regex,
            ) from exc

        client, sftp = self._open()
        try:
            try:
                entries = sftp.listdir_attr(remote_path)
            except Exception as exc:
                raise SFTPClientError(
                    "listdir_failed",
                    message=str(exc),
                    host=self.host,
                    remote_path=remote_path,
                ) from exc
        finally:
            self._safe_close(sftp, client)

        matches: list[dict] = []
        for attr in entries:
            name = attr.filename
            if not name or not pattern.match(name):
                continue
            mtime = attr.st_mtime if attr.st_mtime is not None else 0
            matches.append(
                {
                    "filename": name,
                    "size": int(attr.st_size or 0),
                    "mtime_utc": datetime.fromtimestamp(mtime, tz=timezone.utc),
                }
            )
        return matches

    def download_bytes(self, remote_path: str, filename: str) -> bytes:
        """Read ``remote_path/filename`` fully into memory."""
        full = posixpath.join(remote_path, filename)
        client, sftp = self._open()
        try:
            try:
                with sftp.open(full, "rb") as fh:
                    return fh.read()
            except Exception as exc:
                raise SFTPClientError(
                    "download_failed",
                    message=str(exc),
                    host=self.host,
                    remote_path=remote_path,
                    filename=filename,
                ) from exc
        finally:
            self._safe_close(sftp, client)
