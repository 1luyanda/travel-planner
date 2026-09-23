"""Authenticated liked-activity snapshots.

Unlike saved flights, there is no activities container to re-read later —
Google Places is queried live and nothing is persisted until a user likes an
item. So every entry here is a permanent snapshot captured at save time.
"""

from __future__ import annotations

from backend.contracts.saved_activities import (
    SaveActivityRequest,
    SavedActivitiesResponse,
    SavedActivityItem,
)
from backend.models.user_activity import SavedActivitySnapshot
from backend.repositories import CosmosDestinationRepository


class SavedActivitiesService:
    """Stores a snapshot per liked activity, keyed by the authenticated user."""

    def __init__(self, repository: CosmosDestinationRepository) -> None:
        self._repository = repository

    async def save(self, user_id: str, body: SaveActivityRequest) -> SavedActivityItem:
        snapshot = SavedActivitySnapshot.from_activity(
            body.activity,
            city=body.city,
            country_code=body.country_code,
            destination_id=body.destination_id,
        )
        await self._repository.add_user_saved_activity(user_id, snapshot)
        return _to_item(snapshot)

    async def delete(self, user_id: str, place_id: str) -> None:
        await self._repository.remove_user_saved_activity(user_id, place_id)

    async def list_for_user(self, user_id: str) -> list[SavedActivityItem]:
        document = await self._repository.list_user_saved_activities(user_id)
        if document is None:
            return []
        return [_to_item(snapshot) for snapshot in document.activities.values()]


def _to_item(snapshot: SavedActivitySnapshot) -> SavedActivityItem:
    return SavedActivityItem(
        place_id=snapshot.place_id,
        destination_id=snapshot.destination_id,
        city=snapshot.city,
        country_code=snapshot.country_code,
        activity=snapshot.to_activity_item(),
    )
