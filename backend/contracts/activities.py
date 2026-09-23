"""HTTP contracts for destination activities from Google Places."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class ActivitiesRequest(BaseModel):
    city: str = Field(min_length=1, max_length=100)
    country_code: str | None = None
    destination_id: str | None = None
    moods: list[str] = Field(default_factory=list)
    limit: int = Field(default=8, ge=1, le=20)

    @field_validator("city")
    @classmethod
    def _strip_city(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("city is required")
        return cleaned

    @field_validator("country_code", "destination_id")
    @classmethod
    def _strip_optional(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @field_validator("moods")
    @classmethod
    def _clean_moods(cls, value: list[str]) -> list[str]:
        return [str(item).strip() for item in value if item and str(item).strip()]


class ActivityItem(BaseModel):
    place_id: str
    name: str
    types: list[str] = Field(default_factory=list)
    address: str | None = None
    rating: float | None = None
    user_ratings_total: int | None = None
    business_status: str | None = None
    price_level: str | None = None
    description: str | None = None
    description_language_code: str | None = None


class ActivitiesResponse(BaseModel):
    status: Literal["ready", "error"]
    city: str
    destination_id: str | None = None
    activities: list[ActivityItem] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)


# Nearby Search (New) Table A types used for activities and attractions.
DEFAULT_NEARBY_TYPES: tuple[str, ...] = (
    "tourist_attraction",
    "museum",
    "park",
    "art_gallery",
    "historical_landmark",
)
ALLOWED_NEARBY_TYPES = frozenset(DEFAULT_NEARBY_TYPES)
DEFAULT_NEARBY_RADIUS_METERS = 5000
DEFAULT_NEARBY_LIMIT = 10
_COUNTRY_CODE = re.compile(r"^[A-Z]{2}$")


class NearbyActivitiesRequest(BaseModel):
    """Explicit nearby search. Coordinates are not logged or stored."""

    city: str | None = Field(default=None, max_length=100)
    country_code: str | None = None
    latitude: float | None = Field(default=None, ge=-90, le=90, allow_inf_nan=False)
    longitude: float | None = Field(default=None, ge=-180, le=180, allow_inf_nan=False)
    radius_meters: int = Field(default=DEFAULT_NEARBY_RADIUS_METERS, ge=1, le=50_000)
    limit: int = Field(default=DEFAULT_NEARBY_LIMIT, ge=1, le=20)
    included_types: list[str] = Field(default_factory=list, max_length=5, validate_default=True)

    @field_validator("city")
    @classmethod
    def _strip_city(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @field_validator("country_code")
    @classmethod
    def _country_code(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip().upper()
        if not cleaned:
            return None
        if not _COUNTRY_CODE.fullmatch(cleaned):
            raise ValueError("country_code must be a 2-letter code")
        return cleaned

    @field_validator("included_types")
    @classmethod
    def _types(cls, value: list[str]) -> list[str]:
        cleaned: list[str] = []
        seen: set[str] = set()
        for item in value:
            key = str(item).strip()
            if not key:
                continue
            if key not in ALLOWED_NEARBY_TYPES:
                raise ValueError(f"unsupported activity type: {key}")
            if key in seen:
                continue
            seen.add(key)
            cleaned.append(key)
        return cleaned or list(DEFAULT_NEARBY_TYPES)

    @model_validator(mode="after")
    def _require_center(self) -> "NearbyActivitiesRequest":
        has_latitude = self.latitude is not None
        has_longitude = self.longitude is not None
        if has_latitude != has_longitude:
            raise ValueError("latitude and longitude must be provided together")
        if not has_latitude and not self.city:
            raise ValueError("A city or location is required")
        return self


class PhotoAttribution(BaseModel):
    display_name: str | None = None
    uri: str | None = None
    photo_uri: str | None = None


class ActivityPhoto(BaseModel):
    name: str
    author_attributions: list[PhotoAttribution] = Field(default_factory=list)
    google_maps_uri: str | None = None


class NearbyActivityItem(BaseModel):
    place_id: str
    name: str
    types: list[str] = Field(default_factory=list)
    address: str | None = None
    rating: float | None = None
    user_ratings_total: int | None = None
    business_status: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    google_maps_uri: str | None = None
    photo: ActivityPhoto | None = None


class SearchCenter(BaseModel):
    latitude: float
    longitude: float


class NearbyActivitiesResponse(BaseModel):
    status: Literal["ready", "error"]
    city: str | None = None
    radius_meters: int
    search_center: SearchCenter | None = None
    activities: list[NearbyActivityItem] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)
    attribution: Literal["Google Maps"] = "Google Maps"
