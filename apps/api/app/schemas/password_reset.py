"""Pydantic schemas for the password reset flow."""

from typing import Optional

from pydantic import BaseModel, EmailStr


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetVerify(BaseModel):
    email: EmailStr
    code: str


class PasswordResetNewPassword(BaseModel):
    email: EmailStr
    code: str
    new_password: str


class PasswordResetResponse(BaseModel):
    success: bool
    message: str
    # TODO: REMOVE admin_debug_code when SMTP email delivery is implemented.
    # Exposes the 6-digit code in the API response so the admin can see and
    # relay it during the no-email phase. Drop this field once mail is wired.
    admin_debug_code: Optional[str] = None
