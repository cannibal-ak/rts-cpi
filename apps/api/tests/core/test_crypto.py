"""Unit tests for app.core.crypto (Phase 1 SFTP foundation)."""
from __future__ import annotations

import pytest
from cryptography.fernet import Fernet, InvalidToken

from app.core.crypto import decrypt, decrypt_str, encrypt, encrypt_str


def test_roundtrip_bytes():
    payload = b"hello world \x00\x01\x02"
    assert decrypt(encrypt(payload)) == payload


def test_roundtrip_str():
    s = "tëst string with unicode \U0001f389 and newline\n"
    assert decrypt_str(encrypt_str(s)) == s


def test_decrypt_with_wrong_key_raises():
    rogue = Fernet(Fernet.generate_key())
    bad_token = rogue.encrypt(b"secret payload")
    with pytest.raises(InvalidToken):
        decrypt(bad_token)


def test_empty_plaintext_roundtrips():
    assert decrypt(encrypt(b"")) == b""
