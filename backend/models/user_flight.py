"""Cosmos document for one user's saved flight snapshots."""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.contracts.candidates import FlightItem
from backend.contracts.saved_flights import SavedExplanationBody


class SavedFlightSnapshot(FlightItem):
    """Allowlisted flight fields captured at save time, plus its AI explanation."""

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

    def without_explanation(self) -> "SavedFlightSnapshot":
        """The stored form of this snapshot in the ``flights`` map, where
        the explanation is deliberately absent (it lives in its own map)."""

        if self.explanation is None:
            return self
        return self.model_copy(update={"explanation": None})


class UserSavedFlightsDocument(BaseModel):
    """One user-flights item. Flight fields and their AI explanation are
    stored in two separate top-level maps, both keyed by ``flight_id``, so
    that liking, unliking, or resaving-with-an-explanation can each be
    written as a single targeted Cosmos patch operation — without reading
    or rewriting any of the user's other saved flights, and without ever
    clobbering an existing explanation when a resave doesn't include a new
    one.
    """

    model_config = ConfigDict(extra="ignore")

    id: str = Field(min_length=1, max_length=200)
    flights: dict[str, SavedFlightSnapshot] = Field(default_factory=dict)
    explanations: dict[str, SavedExplanationBody] = Field(default_factory=dict)

    @field_validator("id")
    @classmethod
    def strip_user_id(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("id cannot be empty")
        return cleaned

    def all_flight_ids(self) -> list[str]:
        """Most-recently saved or resaved first."""

        return [
            flight_id
            for flight_id, _ in sorted(
                self.flights.items(),
                key=lambda pair: pair[1].saved_at,
                reverse=True,
            )
        ]

    def combined_snapshots(self) -> dict[str, SavedFlightSnapshot]:
        """Flight fields merged with their explanation, keyed by flight_id."""

        return {
            flight_id: (
                snapshot.model_copy(
                    update={"explanation": self.explanations[flight_id]}
                )
                if flight_id in self.explanations
                else snapshot
            )
            for flight_id, snapshot in self.flights.items()
        }
