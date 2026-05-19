"""Pydantic schemas for the password reset flow."""

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
