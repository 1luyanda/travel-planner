"""Cosmos document for one user's liked activities."""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.contracts.activities import ActivityItem


class SavedActivitySnapshot(ActivityItem):
    """A liked activity plus the destination context Google Places does not carry."""

    destination_id: str | None = Field(default=None, max_length=150)
    city: str = Field(min_length=1, max_length=100)
    country_code: str | None = None
    saved_at: datetime

    @classmethod
    def from_activity(
        cls,
        activity: ActivityItem,
        *,
        city: str,
        country_code: str | None = None,
        destination_id: str | None = None,
        saved_at: datetime | None = None,
    ) -> "SavedActivitySnapshot":
        payload = activity.model_dump()
        return cls(
            city=city,
            country_code=country_code,
            destination_id=destination_id,
            saved_at=saved_at or datetime.now(timezone.utc),
            **payload,
        )

    def to_activity_item(self) -> ActivityItem:
        return ActivityItem.model_validate(
            self.model_dump(
                exclude={"destination_id", "city", "country_code", "saved_at"}
            )
        )


class UserSavedActivitiesDocument(BaseModel):
    """One user-activities item. Every entry is a permanent snapshot: there is
    no activities container to re-read, unlike saved flights."""

    model_config = ConfigDict(extra="ignore")

    id: str = Field(min_length=1, max_length=200)
    activities: list[SavedActivitySnapshot] = Field(default_factory=list)

    @field_validator("id")
    @classmethod
    def strip_user_id(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("id cannot be empty")
        return cleaned

    def all_place_ids(self) -> list[str]:
        return [item.place_id for item in self.activities]
