"""API contracts for distance-based recommendations from stored hotels."""

from pydantic import Field

from backend.models.hotel import HotelCoordinates, StoredHotel


class HotelItem(StoredHotel):
    distance_km: float = Field(
        ge=0,
        allow_inf_nan=False,
        description=(
            "Approximate straight-line distance from destination centre/reference point"
        ),
    )


class HotelsResponse(HotelCoordinates):
    destination_id: str
    city: str
    country_code: str
    attribution: str | None = None
    hotel_count: int = Field(ge=0, description="Stored entries before validation")
    returned_count: int = Field(ge=0, description="Hotels in this shortlist")
    hotels: list[HotelItem] = Field(default_factory=list)
