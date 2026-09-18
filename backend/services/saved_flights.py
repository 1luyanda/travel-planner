"""Authenticated saved-flight IDs. Flight facts stay in the flights container."""

from __future__ import annotations

from backend.contracts import FlightItem, SaveFlightRequest, SavedFlightItem
from backend.repositories import (
    CosmosDestinationRepository,
    RepositoryNotFoundError,
)


class SavedFlightNotFoundError(RuntimeError):
    """Raised when a referenced flight cannot be saved."""


class SavedFlightsService:
    """Stores only flight IDs per user and hydrates them from flights."""

    def __init__(self, repository: CosmosDestinationRepository) -> None:
        self._repository = repository

    async def save(self, user_id: str, body: SaveFlightRequest) -> SavedFlightItem:
        try:
            raw_flight = await self._repository.get_flight_by_id(body.flight_id)
        except RepositoryNotFoundError as error:
            raise SavedFlightNotFoundError(
                "That stored flight was not found."
            ) from error

        await self._repository.add_user_saved_flight(user_id, body.flight_id)
        return SavedFlightItem(
            flight_id=body.flight_id,
            availability="available",
            flight=FlightItem.model_validate(raw_flight),
        )

    async def delete(self, user_id: str, flight_id: str) -> None:
        await self._repository.remove_user_saved_flight(user_id, flight_id)

    async def list_for_user(self, user_id: str) -> list[SavedFlightItem]:
        flight_ids = await self._repository.list_user_saved_flight_ids(user_id)
        flights = {
            str(item.get("id")): item
            for item in await self._repository.get_flights_by_ids(flight_ids)
            if item.get("id")
        }
        items: list[SavedFlightItem] = []
        for flight_id in flight_ids:
            raw_flight = flights.get(flight_id)
            if raw_flight is None:
                items.append(
                    SavedFlightItem(
                        flight_id=flight_id,
                        availability="unavailable",
                        flight=None,
                    )
                )
                continue
            items.append(
                SavedFlightItem(
                    flight_id=flight_id,
                    availability="available",
                    flight=FlightItem.model_validate(raw_flight),
                )
            )
        return items
