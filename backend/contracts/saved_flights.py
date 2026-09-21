"""HTTP contracts for authenticated saved-flight IDs."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.contracts.candidates import FlightItem


class SaveFlightRequest(BaseModel):
    """The only persisted value is flight_id. Other fields are ignored."""

    model_config = ConfigDict(extra="ignore")

    flight_id: str = Field(min_length=1, max_length=200)

    @field_validator("flight_id")
    @classmethod
    def strip_flight_id(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("flight_id cannot be empty")
        return cleaned


class SavedFlightItem(BaseModel):
    """A saved flight ID plus current or snapshotted allowlisted flight data."""

    flight_id: str
    availability: Literal["available", "unavailable"]
    flight: FlightItem | None = None


class SavedFlightsResponse(BaseModel):
    items: list[SavedFlightItem]
