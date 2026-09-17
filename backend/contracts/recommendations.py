"""HTTP contracts for recommend and refine orchestration."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from backend.contracts.candidates import OriginItem, RejectedCandidateItem
from backend.models.explanation import DestinationExplanation
from backend.models.feedback import FieldChange, RankingIntent
from backend.models.trip_request import ExtractedPreferences, TripRequest

RecommendStatus = Literal["ready", "needs_input", "error"]


class RankingPreferencesBody(BaseModel):
    """Optional ranking weights supplied by the ranking owner or frontend.

    Omitted fields keep Ivan's RankingPreferences defaults. On refine,
    recognized intents such as cheaper or warmer replace these via
    ``preferences_from_intents``.
    """

    price_weight: float | None = Field(default=None, ge=0, le=1)
    weather_weight: float | None = Field(default=None, ge=0, le=1)
    changeovers_weight: float | None = Field(default=None, ge=0, le=1)
    duration_weight: float | None = Field(default=None, ge=0, le=1)


class RecommendRequest(BaseModel):
    """First-search body: free text plus optional form fields."""

    text: str = Field(default="", max_length=4000)
    form_fields: dict[str, Any] | None = Field(default=None, max_length=20)
    ranking_preferences: RankingPreferencesBody | None = None


class RefineRequest(BaseModel):
    """Feedback body against a previously validated trip request."""

    text: str = Field(min_length=1, max_length=2000)
    request: TripRequest
    ranking_preferences: RankingPreferencesBody | None = None


class RecommendationResponse(BaseModel):
    """Shared recommend/refine result for the React client."""

    status: RecommendStatus
    request: TripRequest | None = None
    updated_request: TripRequest | None = None
    preferences: ExtractedPreferences | None = None
    origin: OriginItem | None = None
    origin_id: str | None = None
    recommendations: list[DestinationExplanation] = Field(default_factory=list)
    rejected: list[RejectedCandidateItem] = Field(default_factory=list)
    intents: list[RankingIntent] = Field(default_factory=list)
    changes: list[FieldChange] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)
    clarification_questions: list[str] = Field(default_factory=list)
    data_source: str | None = None
