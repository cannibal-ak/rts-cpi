"""Security helpers shared across auth flows.

hash_token: one-way SHA-256 used to store password-reset codes and invite
tokens hashed at rest. The raw value is emailed to the user; only the hash
is persisted, so a DB read cannot recover a usable code/token.
"""

import hashlib


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()
