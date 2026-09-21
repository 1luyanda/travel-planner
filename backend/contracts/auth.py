"""HTTP contracts for local account authentication."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from backend.models.user import UserResponse


class RegisterRequest(BaseModel):
    """New-account request; the password is never persisted or logged."""

    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str = Field(min_length=12, max_length=128)
    display_name: str = Field(min_length=1, max_length=100)

    @field_validator("display_name")
    @classmethod
    def normalize_display_name(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("display_name cannot be empty")
        return cleaned


class LoginRequest(BaseModel):
    """Login request with deliberately generic failure handling."""

    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class AuthResponse(BaseModel):
    """Successful authentication response."""

    user: UserResponse
