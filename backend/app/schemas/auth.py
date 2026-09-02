"""Pydantic contracts for account verification and session flows."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field

from app.models.entities import AccountStatus, Role


class SignupRequest(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)


class SignupResponse(BaseModel):
    user_id: str
    email: EmailStr
    status: AccountStatus
    message: str


class VerifyRequest(BaseModel):
    email: EmailStr
    otp: str = Field(pattern=r"^\d{6}$")


class OtpRequest(BaseModel):
    email: EmailStr


class GoogleSignInRequest(BaseModel):
    credential: str = Field(min_length=100, max_length=12000)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_seconds: int


class CurrentUserResponse(BaseModel):
    id: str
    name: str
    email: EmailStr
    role: Role
    status: AccountStatus
    auth_provider: str
    email_verified_at: datetime | None
    created_at: datetime


class AccountProfileResponse(CurrentUserResponse):
    phone: str | None = None
    last_active_at: datetime | None = None


class AccountProfileUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=160)
    phone: str | None = Field(default=None, min_length=3, max_length=40)


class AccountPreferencesResponse(BaseModel):
    language: str | None = None
    timezone: str | None = None
    date_format: str | None = None
    time_format: str | None = None
    items_per_page: int | None = None
    theme: str | None = None
    updated_at: datetime | None = None


class AccountPreferencesUpdateRequest(BaseModel):
    language: str | None = Field(default=None, max_length=80)
    timezone: str | None = Field(default=None, max_length=80)
    date_format: str | None = Field(default=None, max_length=40)
    time_format: str | None = Field(default=None, max_length=40)
    items_per_page: int | None = Field(default=None, ge=5, le=200)
    theme: Literal["light"] | None = None


class AccountSecurityResponse(BaseModel):
    password_configured: bool
    email_verification_status: Literal["verified", "pending"]
    two_factor_supported: bool
    session_management_supported: bool
    active_session_count: int


class AccountSessionResponse(BaseModel):
    id: str
    device_label: str
    created_at: datetime
    last_active_at: datetime
    expires_at: datetime
    revoked_at: datetime | None
    status: Literal["active", "revoked"]
    is_current: bool


class AccountActivityResponse(BaseModel):
    id: str
    action: str
    object_type: str
    object_id: str | None
    outcome: str
    created_at: datetime
