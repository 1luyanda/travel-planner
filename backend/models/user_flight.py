"""Cosmos document for one user's saved flight snapshots."""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.contracts.candidates import FlightItem
from backend.contracts.saved_flights import SavedExplanationBody


class SavedFlightSnapshot(FlightItem):
    """Allowlisted flight fields captured at save time."""

    flight_id: str = Field(min_length=1, max_length=200)
    saved_at: datetime
    explanation: SavedExplanationBody | None = None

    @classmethod
    def from_flight(
        cls,
        raw: dict,
        *,
        saved_at: datetime | None = None,
        explanation: SavedExplanationBody | None = None,
    ) -> "SavedFlightSnapshot":
        cosmos_id = raw.get("id")
        if not isinstance(cosmos_id, str) or cosmos_id == "":
            raise ValueError("Flight document is missing id")
        flight = FlightItem.model_validate(raw)
        payload = flight.model_dump()
        payload["id"] = cosmos_id
        return cls(
            flight_id=cosmos_id,
            saved_at=saved_at or datetime.now(timezone.utc),
            explanation=explanation,
            **payload,
        )

    def to_flight_item(self) -> FlightItem:
        return FlightItem.model_validate(
            self.model_dump(exclude={"flight_id", "saved_at", "explanation"})
        )

    def differs_from_flight(self, raw: dict) -> bool:
        current = FlightItem.model_validate(raw)
        return self.to_flight_item().model_dump() != current.model_dump()


class UserSavedFlightsDocument(BaseModel):
    """One user-flights item. Snapshots keep a copy of the flight at save time."""

    model_config = ConfigDict(extra="ignore")

    id: str = Field(min_length=1, max_length=200)
    flights: list[SavedFlightSnapshot] = Field(default_factory=list)
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
    def keep_exact_flight_ids(cls, values: list[str]) -> list[str]:
        seen: set[str] = set()
        kept: list[str] = []
        for value in values:
            if not isinstance(value, str) or value == "" or value in seen:
                continue
            seen.add(value)
            kept.append(value)
        return kept

    @model_validator(mode="after")
    def keep_legacy_ids(self) -> "UserSavedFlightsDocument":
        snapshot_ids = [item.flight_id for item in self.flights]
        leftover = [
            flight_id
            for flight_id in self.flight_ids
            if flight_id not in set(snapshot_ids)
        ]
        self.flight_ids = [*snapshot_ids, *leftover]
        return self

    def all_flight_ids(self) -> list[str]:
        return list(self.flight_ids)
