from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.enums import UserRole


class PatientProfileIn(BaseModel):
    full_name: str = Field(min_length=1, max_length=200)
    dob: date | None = None
    country: str | None = Field(default=None, min_length=2, max_length=2)
    phone: str | None = Field(default=None, max_length=32)
    preferred_language: str | None = Field(default=None, max_length=16)


class PatientProfileOut(PatientProfileIn):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID


class RegisterRequest(BaseModel):
    email: EmailStr
    # bcrypt truncates past 72 bytes; hash_password rejects longer, so cap here too.
    password: str = Field(min_length=8, max_length=72)
    # Self-registration is patient-only; coordinator/admin accounts are provisioned
    # by an admin through POST /users, never by this endpoint.
    profile: PatientProfileIn


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_at: datetime


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    role: UserRole
    is_active: bool
    created_at: datetime


class MeOut(UserOut):
    profile: PatientProfileOut | None = None


class CreateUserRequest(BaseModel):
    """Admin-only user provisioning (coordinators, other admins)."""

    email: EmailStr
    password: str = Field(min_length=8, max_length=72)
    role: UserRole
