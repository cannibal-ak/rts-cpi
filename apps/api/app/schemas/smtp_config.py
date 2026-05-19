"""Pydantic schemas for the admin SMTP Config endpoint.

Shapes:
  * SmtpConfigBase    — fields shared by read and write.
  * SmtpConfigUpdate  — PUT body. Password is optional: omit it to
                        keep the existing encrypted value (so the form
                        does not need to re-prompt for a password
                        whenever the admin edits an unrelated field).
  * SmtpConfigRead    — GET body. The encrypted password is never
                        exposed; the boolean ``password_set`` tells
                        the UI whether one is currently stored.
  * SmtpTestRequest   — POST /test body. ``config_override`` lets the
                        admin test BEFORE saving (form values), and
                        omitting it tests the saved row.
  * SmtpTestResponse  — POST /test response: success flag, message,
                        latency_ms.
"""

from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, SecretStr


EncryptionMode = Literal["NONE", "STARTTLS", "SSL_TLS"]


class SmtpConfigBase(BaseModel):
    host: str = Field(min_length=1, max_length=255)
    port: int = Field(default=587, ge=1, le=65535)
    encryption: EncryptionMode = "STARTTLS"
    username: str = Field(min_length=1, max_length=255)
    from_email: EmailStr
    from_name: str = Field(min_length=1, max_length=255)


class SmtpConfigUpdate(SmtpConfigBase):
    """PUT body. Required password on first save, optional on edits."""
    password: Optional[SecretStr] = None


class SmtpConfigCreate(SmtpConfigBase):
    """Inline config supplied to /test before any row is saved.

    Password is required here because the test runs against the
    supplied values directly — there is no encrypted blob to fall
    back on.
    """
    password: SecretStr


class SmtpConfigRead(SmtpConfigBase):
    id: UUID
    last_test_at: Optional[datetime] = None
    last_test_status: Optional[str] = None
    last_test_error: Optional[str] = None
    updated_at: datetime
    # Lets the UI render a "password stored" indicator and decide
    # whether the field can be left blank on edit.
    password_set: bool = True

    model_config = ConfigDict(from_attributes=True)


class SmtpTestRequest(BaseModel):
    to_email: EmailStr
    # Provide config_override to test in-flight form values before
    # saving; omit to test the saved row.
    config_override: Optional[SmtpConfigCreate] = None


class SmtpTestResponse(BaseModel):
    success: bool
    message: str
    latency_ms: Optional[int] = None
