"""Recommend stored hotels by distance, independently of destination ranking."""

from __future__ import annotations

from math import asin, cos, radians, sin, sqrt

from pydantic import ValidationError

from backend.contracts.candidates import FlightItem
from backend.contracts.hotels import HotelItem, HotelsResponse
from backend.models.hotel import StoredHotel
from backend.repositories import CosmosDestinationRepository


def haversine_km(
    latitude: float,
    longitude: float,
    hotel_latitude: float,
    hotel_longitude: float,
) -> float:
    """Return unrounded great-circle distance between valid coordinates."""

    lat1, lat2 = radians(latitude), radians(hotel_latitude)
    delta_lat = lat2 - lat1
    delta_lon = radians(hotel_longitude - longitude)
    a = sin(delta_lat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(delta_lon / 2) ** 2
    # Clamp floating-point drift at identical/antipodal points.
    return 2 * 6371.0 * asin(sqrt(max(0.0, min(1.0, a))))


class HotelService:
    def __init__(self, repository: CosmosDestinationRepository) -> None:
        self._repository = repository

    async def resolve_destination_ids(self, flights: list[FlightItem]) -> dict[str, str | None]:
        """Map flight IDs to actual hotel IDs, sharing lookups within this request."""

        resolved: dict[str, str | None] = {}
        cache: dict[tuple[str, str, tuple[str, ...]], str | None] = {}
        for flight in flights:
            city = (flight.destination_city or "").strip().casefold()
            country = (flight.destination_country_code or "").strip().upper()
            codes = tuple(sorted({
                code.strip().upper()
                for code in (flight.destination_iata, flight.destination_airport)
                if code and code.strip()
            }))
            key = (city, country, codes)
            if key not in cache:
                cache[key] = await self._repository.resolve_hotel_destination_id(
                    city=city, country_code=country, iata_codes=codes,
                )
            resolved[flight.id] = cache[key]
        return resolved

    async def recommend(self, destination_id: str, limit: int = 5) -> HotelsResponse:
        document = await self._repository.get_hotel_document(destination_id)
        hotels: list[HotelItem] = []
        for raw_hotel in document.hotels:
            try:
                hotel = StoredHotel.model_validate(raw_hotel)
            except ValidationError:
                # Missing/out-of-range/non-finite coordinates and malformed
                # records cannot provide reliable distance-based recommendations.
                continue
            hotels.append(
                HotelItem(
                    **hotel.model_dump(),
                    distance_km=haversine_km(
                        document.latitude,
                        document.longitude,
                        hotel.latitude,
                        hotel.longitude,
                    ),
                )
            )

        hotels.sort(
            key=lambda hotel: (
                hotel.distance_km,
                hotel.name.casefold(),
                hotel.name,
                hotel.osm_id or "",
                hotel.latitude,
                hotel.longitude,
            )
        )
        shortlist = hotels[:limit]
        return HotelsResponse(
            destination_id=document.id,
            city=document.city,
            country_code=document.country_code,
            latitude=document.latitude,
            longitude=document.longitude,
            attribution=document.attribution,
            hotel_count=len(document.hotels),
            returned_count=len(shortlist),
            hotels=shortlist,
        )
