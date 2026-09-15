"""Result models for travel-feedback interpretation.

This is the AI-owned overlay on a validated ``TripRequest``. It does not
import ranking or FastAPI.

Ivan's ``RankingPreferences`` on origin/main has numeric weights
(``price_weight``, ``weather_weight``, ``changeovers_weight``,
``duration_weight``). Relative meanings already implemented in ranking:

- cheaper options score higher (``price_eur``, lower is better)
- warmer max temperature scores higher
- fewer changeovers score higher

There is no named mapping from "cheaper" or "warmer" to a specific weight
value. This contract therefore returns semantic ``RankingIntent`` rows for
Ivan/Luyanda and does **not** invent weight numbers.

Hard filters on origin/main live in ``RankingConstraints``
(``max_price_eur``, ``max_changeovers``, ``max_flight_duration_minutes``).
"Direct flights only" is a proposed ``TripRequest.direct_flights_only=True``
update. Luyanda may map that to ``max_changeovers=0``. It is not a weight.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from backend.models.trip_request import TripRequest

InterpretStatus = Literal["ready", "needs_input", "error"]
IntentTarget = Literal["ranking_preferences", "ranking_constraints", "trip_request", "unsupported"]


class RankingIntent(BaseModel):
    """A ranking or filter intent. Values are meanings, not invented weights."""

    code: str
    target: IntentTarget
    meaning: str
    ranking_field: str | None = Field(
        default=None,
        description="Related ranking field name, if any. The numeric value is not set.",
    )


class FieldChange(BaseModel):
    """One explicit TripRequest field the user asked to change."""

    field: str
    previous: Any
    proposed: Any


class InterpretFeedbackResult(BaseModel):
    """Result for the backend owner (Luyanda).

    ``request`` is a snapshot of the input and is never mutated.
    ``updated_request`` is a new object when status is ready; unrelated
    fields are copied from the snapshot.
    """

    status: InterpretStatus
    request: TripRequest
    updated_request: TripRequest | None = None
    intents: list[RankingIntent] = Field(default_factory=list)
    changes: list[FieldChange] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)
    clarification_questions: list[str] = Field(default_factory=list)
