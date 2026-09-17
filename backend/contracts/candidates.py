"""FastAPI contracts for retrieving validated ranking candidates."""

from __future__ import annotations

from datetime import date, datetime
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class FlightQuery(BaseModel):
    """Partition-scoped flight query produced after resolving an origin."""

    origin_id: str = Field(min_length=3, max_length=150)
    departure_date: date | None = None
    return_date: date | None = None
    max_price_eur: float | None = Field(default=None, gt=0, le=1_000_000)
    min_temperature_c: float | None = Field(default=None, ge=-100, le=100)
    destination_country_code: str | None = Field(
        default=None, min_length=2, max_length=2
    )
    max_changeovers: int | None = Field(default=None, ge=0, le=20)
    max_flight_duration_minutes: int | None = Field(
        default=None,
        gt=0,
        le=10_080,
    )
    limit: int = Field(default=100, ge=1, le=200)

    @field_validator("origin_id")
    @classmethod
    def normalize_origin_id(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not normalized:
            raise ValueError("origin_id cannot be empty")
        return normalized

    @field_validator("destination_country_code")
    @classmethod
    def normalize_country_code(cls, value: str | None) -> str | None:
        return value.strip().upper() if value else None

    @model_validator(mode="after")
    def validate_dates(self) -> "FlightQuery":
        if (
            self.departure_date is not None
            and self.return_date is not None
            and self.return_date < self.departure_date
        ):
            raise ValueError("return_date cannot be before departure_date")
        return self


class OriginItem(BaseModel):
    """Public origin fields returned to the frontend."""

    model_config = ConfigDict(extra="ignore")

    id: str
    city: str
    country: str
    country_code: str
    airports: list[str] = Field(default_factory=list)
    city_iata: list[str] = Field(default_factory=list)
    flight_count: int = 0
    photo_url: str | None = None
    photo_url_small: str | None = None


class FlightItem(BaseModel):
    """Allowlisted flight fields safe for frontend display and map joins."""

    model_config = ConfigDict(extra="ignore")

    id: str
    origin_id: str | None = None
    origin_iata: str | None = None
    origin_airport: str | None = None
    destination_iata: str | None = None
    destination_airport: str | None = None
    destination_city: str | None = None
    destination_country: str | None = None
    destination_country_code: str | None = None
    airport_name: str | None = None
    price_eur: float | None = None
    currency: str | None = None
    departure_at: datetime | None = None
    return_at: datetime | None = None
    outbound_stops: int | None = None
    return_stops: int | None = None
    duration_minutes: int | None = None
    airline_code: str | None = None
    airline_name: str | None = None
    flight_number: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    photo_url: str | None = None
    photo_url_small: str | None = None


class CandidateItem(BaseModel):
    """Validated data that the ranking algorithm can consume."""

    destination_id: str
    destination_iata: str
    city: str
    price_eur: float
    changeover_count: int
    flight_duration_minutes: int
    trip_duration_days: int
    average_max_temperature_c: float
    average_min_temperature_c: float | None
    precipitation_probability_percent: float
    sunshine_hours: float | None
    max_wind_speed_kmh: float | None
    airport_distance_km: float | None
    # These are optional because the current flattened Cosmos schema does not
    # preserve source retrieval timestamps yet.
    flight_retrieved_at: datetime | None
    weather_retrieved_at: datetime | None


class RejectionItem(BaseModel):
    code: str
    message: str


class RejectedCandidateItem(BaseModel):
    destination_id: str | None
    destination_iata: str | None
    reasons: list[RejectionItem]


class CandidateResponse(BaseModel):
    origin_id: str
    candidates: list[CandidateItem]
    rejected: list[RejectedCandidateItem]
    data_source: str


class FlightListResponse(BaseModel):
    """Bounded, allowlisted flight data for one origin partition."""

    origin_id: str
    flights: list[FlightItem]
    count: int
    data_source: str
