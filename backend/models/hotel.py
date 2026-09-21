"""Stored Cosmos hotel data, with individual hotel validation deferred."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class HotelCoordinates(BaseModel):
    latitude: float = Field(ge=-90, le=90, allow_inf_nan=False, strict=True)
    longitude: float = Field(ge=-180, le=180, allow_inf_nan=False, strict=True)


class StoredHotel(HotelCoordinates):
    name: str = Field(min_length=1, pattern=r"\S")
    osm_id: str | None = None
    stars: int | None = None
    address: str | None = None
    website: str | None = None
    booking_url: str | None = None


class HotelDocument(HotelCoordinates):
    id: str = Field(min_length=1)
    city: str
    country_code: str
    attribution: str | None = None
    # Validate each entry separately so one bad hotel cannot hide valid ones.
    hotels: list[Any] = Field(default_factory=list)
