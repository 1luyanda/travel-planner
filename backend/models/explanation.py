"""Result models for grounded destination explanations.

Integration with `ranking.RankedDestination` is pending. This module does not
copy that package. The explanation service accepts any object with the
documented RankedDestination fields.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

ExplainStatus = Literal["ok", "error"]


class EvidenceReference(BaseModel):
    """One allowed, destination-scoped fact used in an explanation."""

    id: str
    code: str
    destination_id: str
    statement: str


class DestinationExplanation(BaseModel):
    """Explanation for one ranked destination, in the supplied ranking order."""

    destination_id: str
    destination_iata: str
    city: str
    rank: int = Field(ge=1, description="1-based position in the supplied ranking list.")
    price_eur: float
    changeover_count: int
    flight_duration_minutes: int
    average_max_temperature_c: float
    price_score: float
    weather_score: float
    stops_score: float
    duration_score: float
    final_score: float
    summary: str
    evidence: list[EvidenceReference] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)
    precipitation_score: float = 0.0
    sunshine_score: float = 0.0
    temperature_direction: Literal["lower_is_better", "higher_is_better"] = "higher_is_better"


class ExplainRankedTripsResult(BaseModel):
    """Validated explanation result for the backend owner (Luyanda)."""

    status: ExplainStatus
    explanations: list[DestinationExplanation] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)
