"""Cosmos document for one user's saved flight IDs."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


class UserSavedFlightsDocument(BaseModel):
    """One user-flights item. Flight facts stay in the flights container."""

    model_config = ConfigDict(extra="ignore")

    id: str = Field(min_length=1, max_length=200)
    flight_ids: list[str] = Field(default_factory=list)

    @field_validator("id")
    @classmethod
    def strip_user_id(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("id cannot be empty")
        return cleaned

    @field_validator("flight_ids")
    @classmethod
    def normalize_flight_ids(cls, values: list[str]) -> list[str]:
        seen: set[str] = set()
        normalized: list[str] = []
        for value in values:
            flight_id = str(value).strip()
            if not flight_id or flight_id in seen:
                continue
            seen.add(flight_id)
            normalized.append(flight_id)
        return normalized
