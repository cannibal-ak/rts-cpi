"""Application-layer encryption-at-rest helpers (Fernet symmetric auth).

Import-safe: no DB, no network, no I/O on import. The Fernet instance is
built lazily on first use via ``_fernet()``; settings.cpi_kek is only
read when the first encrypt/decrypt happens, so tests can patch
settings before importing this module if needed.
"""
from __future__ import annotations

from functools import lru_cache

from cryptography.fernet import Fernet

from app.core.config import settings


@lru_cache(maxsize=1)
def _fernet() -> Fernet:
    return Fernet(settings.cpi_kek.encode())


def encrypt(plaintext: bytes) -> bytes:
    return _fernet().encrypt(plaintext)


def decrypt(ciphertext: bytes) -> bytes:
    return _fernet().decrypt(ciphertext)


def encrypt_str(s: str) -> bytes:
    return encrypt(s.encode("utf-8"))


def decrypt_str(b: bytes) -> str:
    return decrypt(b).decode("utf-8")
