"""Authenticated saved-flight snapshots. Current flights stay in the flights container."""

from __future__ import annotations

from backend.contracts import FlightItem, SaveFlightRequest, SavedExplanationBody, SavedFlightItem
from backend.contracts.saved_flights import SavedEvidenceBody
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

        snapshot = SavedFlightSnapshot.from_flight(
            raw_flight,
            explanation=_normalize_explanation(body.explanation),
        )
        await self._repository.add_user_saved_flight(user_id, snapshot)

        explanation = snapshot.explanation
        if explanation is None:
            # The save itself never reads the document (see
            # add_user_saved_flight), so a resave that omits an explanation
            # doesn't know whether an older one survives underneath it.
            # One read here, only in that case, reports it back accurately.
            document = await self._repository.list_user_saved_flights(user_id)
            if document is not None:
                explanation = document.explanations.get(snapshot.flight_id)
        return SavedFlightItem(
            flight_id=snapshot.flight_id,
            availability="available",
            flight=snapshot.to_flight_item(),
            explanation=explanation,
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
        snapshots = document.combined_snapshots()
        refreshed, items = _hydrate_saved_flights(flight_ids, current_flights, snapshots)
        if refreshed != snapshots:
            await self._repository.replace_user_saved_flights(
                document.model_copy(
                    update={
                        "flights": {
                            flight_id: snapshot.without_explanation()
                            for flight_id, snapshot in refreshed.items()
                        },
                        "explanations": {
                            flight_id: snapshot.explanation
                            for flight_id, snapshot in refreshed.items()
                            if snapshot.explanation is not None
                        },
                    }
                )
            )
        return items


def _hydrate_saved_flights(
    flight_ids: list[str],
    current_flights: dict[str, dict],
    snapshots: dict[str, SavedFlightSnapshot],
) -> tuple[dict[str, SavedFlightSnapshot], list[SavedFlightItem]]:
    refreshed: dict[str, SavedFlightSnapshot] = {}
    items: list[SavedFlightItem] = []
    for flight_id in flight_ids:
        current = current_flights.get(flight_id)
        snapshot = snapshots[flight_id]
        if current is not None:
            if _should_refresh_snapshot(snapshot, current):
                snapshot = SavedFlightSnapshot.from_flight(
                    current,
                    saved_at=snapshot.saved_at,
                    explanation=snapshot.explanation,
                )
            refreshed[flight_id] = snapshot
            items.append(
                SavedFlightItem(
                    flight_id=flight_id,
                    availability="available",
                    flight=FlightItem.model_validate(current),
                    explanation=snapshot.explanation,
                )
            )
            continue
        refreshed[flight_id] = snapshot
        items.append(
            SavedFlightItem(
                flight_id=flight_id,
                availability="unavailable",
                flight=snapshot.to_flight_item(),
                explanation=snapshot.explanation,
            )
        )
    return refreshed, items


def _should_refresh_snapshot(
    snapshot: SavedFlightSnapshot | None,
    current: dict,
) -> bool:
    """Persist a new snapshot when live flights (refreshed about every 24h) changed."""

    if snapshot is None:
        return True
    return snapshot.differs_from_flight(current)


def _normalize_explanation(
    value: SavedExplanationBody | None,
) -> SavedExplanationBody | None:
    if value is None:
        return None
    summary = (value.summary or "").strip()
    evidence: list[SavedEvidenceBody] = []
    for item in value.evidence or []:
        statement = (item.statement or "").strip()
        if not statement:
            continue
        evidence.append(
            SavedEvidenceBody(
                id=(item.id or "").strip() or None,
                code=(item.code or "").strip() or None,
                statement=statement,
            )
        )
    if not summary and not evidence:
        return None
    return SavedExplanationBody(summary=summary, evidence=evidence)
