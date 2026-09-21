"""HTTP contracts for destination activities from Google Places."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class ActivitiesRequest(BaseModel):
    city: str = Field(min_length=1, max_length=100)
    country_code: str | None = None
    destination_id: str | None = None
    moods: list[str] = Field(default_factory=list)
    limit: int = Field(default=8, ge=1, le=20)

    @field_validator("city")
    @classmethod
    def _strip_city(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("city is required")
        return cleaned

    @field_validator("country_code", "destination_id")
    @classmethod
    def _strip_optional(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @field_validator("moods")
    @classmethod
    def _clean_moods(cls, value: list[str]) -> list[str]:
        return [str(item).strip() for item in value if item and str(item).strip()]


class ActivityItem(BaseModel):
    place_id: str
    name: str
    types: list[str] = Field(default_factory=list)
    address: str | None = None
    rating: float | None = None
    user_ratings_total: int | None = None
    business_status: str | None = None
    price_level: str | None = None


class ActivitiesResponse(BaseModel):
    status: Literal["ready", "error"]
    city: str
    destination_id: str | None = None
    activities: list[ActivityItem] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)
