"""Symmetric encryption helpers for secrets persisted in the database.

Uses Fernet (AES-128-CBC + HMAC-SHA256) keyed by
``CPI_SMTP_ENCRYPTION_KEY`` from the environment. Generate the key
once with::

    python -c "from cryptography.fernet import Fernet; \\
               print(Fernet.generate_key().decode())"

Losing the key means losing the ability to decrypt anything that was
encrypted with it — back it up to a password manager or KMS the same
way you back up database credentials.
"""

from functools import lru_cache

from cryptography.fernet import Fernet

from app.core.config import settings


class EncryptionConfigError(RuntimeError):
    """Raised when CPI_SMTP_ENCRYPTION_KEY is missing or malformed."""


@lru_cache(maxsize=1)
def _get_fernet() -> Fernet:
    key = settings.smtp_encryption_key
    if not key:
        raise EncryptionConfigError(
            "CPI_SMTP_ENCRYPTION_KEY is not set. Generate one with "
            "Fernet.generate_key() and add it to the environment "
            "before saving any SMTP credentials."
        )
    try:
        return Fernet(key.encode() if isinstance(key, str) else key)
    except Exception as e:
        raise EncryptionConfigError(
            f"CPI_SMTP_ENCRYPTION_KEY is malformed: {e}"
        ) from e


def encrypt_secret(plaintext: str) -> str:
    """Encrypt a plaintext string. Returns base64-urlsafe ciphertext."""
    if plaintext is None:
        raise ValueError("plaintext must not be None")
    return _get_fernet().encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt_secret(ciphertext: str) -> str:
    """Decrypt a Fernet ciphertext back to plaintext.

    Raises ``cryptography.fernet.InvalidToken`` if the input was not
    encrypted with the current key (e.g. the key was rotated without
    re-encrypting the row).
    """
    return _get_fernet().decrypt(ciphertext.encode("ascii")).decode("utf-8")
