"""HTTP contracts for authenticated saved (liked) activities."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.contracts.activities import ActivityItem


class SaveActivityRequest(BaseModel):
    """The activity plus the destination context to persist alongside it.

    Unlike saved flights, there is no activities container to re-read later,
    so the full activity payload is captured at save time, not just an id.
    """

    model_config = ConfigDict(extra="ignore")

    activity: ActivityItem
    city: str = Field(min_length=1, max_length=100)
    country_code: str | None = None
    destination_id: str | None = Field(default=None, max_length=150)

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


class SavedActivityItem(BaseModel):
    """A liked activity as stored. Always a snapshot; Places is never re-queried."""

    place_id: str
    destination_id: str | None = None
    city: str
    country_code: str | None = None
    activity: ActivityItem


class SavedActivitiesResponse(BaseModel):
    items: list[SavedActivityItem]
