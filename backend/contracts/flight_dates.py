"""Additive date metadata for candidate and recommendation HTTP responses."""

from datetime import date

from pydantic import BaseModel


class FlightDateMetadata(BaseModel):
    is_flexible_date_option: bool = False
    requested_departure_date: date | None = None
    requested_return_date: date | None = None
    actual_departure_date: date | None = None
    actual_return_date: date | None = None


class DateFallbackSummary(BaseModel):
    # True only when at least one alternative was added, not merely searched.
    flexible_date_fallback_used: bool = False
    exact_match_count: int = 0
    fallback_count: int = 0
