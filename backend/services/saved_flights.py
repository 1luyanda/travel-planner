"""Authenticated saved-flight snapshots. Current flights stay in the flights container."""

from __future__ import annotations

from backend.contracts import FlightItem, SaveFlightRequest, SavedFlightItem
from backend.models.user_flight import SavedFlightSnapshot
from backend.repositories import (
    CosmosDestinationRepository,
    RepositoryNotFoundError,
)


class SavedFlightNotFoundError(RuntimeError):
    """Raised when a referenced flight cannot be saved."""


class SavedFlightsService:
    """Stores a snapshot per saved flight and hydrates availability from flights."""

    def __init__(self, repository: CosmosDestinationRepository) -> None:
        self._repository = repository

    async def save(self, user_id: str, body: SaveFlightRequest) -> SavedFlightItem:
        try:
            raw_flight = await self._repository.get_flight_by_id(body.flight_id)
        except RepositoryNotFoundError as error:
            raise SavedFlightNotFoundError(
                "That stored flight was not found."
            ) from error

        snapshot = SavedFlightSnapshot.from_flight(raw_flight)
        await self._repository.add_user_saved_flight(user_id, snapshot)
        return SavedFlightItem(
            flight_id=snapshot.flight_id,
            availability="available",
            flight=snapshot.to_flight_item(),
        )

    async def delete(self, user_id: str, flight_id: str) -> None:
        await self._repository.remove_user_saved_flight(user_id, flight_id)

    async def list_for_user(self, user_id: str) -> list[SavedFlightItem]:
        document = await self._repository.list_user_saved_flights(user_id)
        if document is None:
            return []

        flight_ids = document.all_flight_ids()
        current_flights = {
            str(item.get("id")): item
            for item in await self._repository.get_flights_by_ids(flight_ids)
            if item.get("id")
        }
        snapshots = {item.flight_id: item for item in document.flights}
        items: list[SavedFlightItem] = []
        for flight_id in flight_ids:
            current = current_flights.get(flight_id)
            snapshot = snapshots.get(flight_id)
            if current is not None:
                items.append(
                    SavedFlightItem(
                        flight_id=flight_id,
                        availability="available",
                        flight=FlightItem.model_validate(current),
                    )
                )
                continue
            if snapshot is not None:
                items.append(
                    SavedFlightItem(
                        flight_id=flight_id,
                        availability="unavailable",
                        flight=snapshot.to_flight_item(),
                    )
                )
                continue
            items.append(
                SavedFlightItem(
                    flight_id=flight_id,
                    availability="unavailable",
                    flight=None,
                )
            )
        return items
