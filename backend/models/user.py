"""Local-authentication user models."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserDocument(BaseModel):
    """The Cosmos representation of a local user account."""

    model_config = ConfigDict(extra="ignore")

    id: str
    email: str = Field(min_length=1, max_length=128)
    email_normalized: str = Field(min_length=1, max_length=128)
    display_name: str = Field(min_length=1, max_length=128)
    password_hash: str
    created_at: datetime
    updated_at: datetime


class UserResponse(BaseModel):
    """Safe user data returned to the frontend."""

    id: str
    email: EmailStr
    display_name: str
    created_at: datetime
