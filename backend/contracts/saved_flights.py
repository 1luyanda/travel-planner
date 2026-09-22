"""HTTP contracts for authenticated saved-flight IDs."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.contracts.candidates import FlightItem


class SavedEvidenceBody(BaseModel):
    """One stored explanation fact. Unknown extra keys are ignored."""

    model_config = ConfigDict(extra="ignore")

    id: str | None = Field(default=None, max_length=200)
    code: str | None = Field(default=None, max_length=80)
    statement: str = Field(default="", max_length=500)


class SavedExplanationBody(BaseModel):
    """LLM summary captured when the user saved the flight."""

    model_config = ConfigDict(extra="ignore")

    summary: str = Field(default="", max_length=2000)
    evidence: list[SavedEvidenceBody] = Field(default_factory=list, max_length=12)


class SaveFlightRequest(BaseModel):
    """Persists flight_id and an optional explanation snapshot."""

    model_config = ConfigDict(extra="ignore")

    flight_id: str = Field(min_length=1, max_length=200)
    explanation: SavedExplanationBody | None = None

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
    explanation: SavedExplanationBody | None = None


class SavedFlightsResponse(BaseModel):
    items: list[SavedFlightItem]
