"""Data-layer boundary used by the recommendation workflow."""

from __future__ import annotations

from typing import Any

from backend.contracts import FlightQuery, OriginItem
from backend.repositories import CosmosDestinationRepository


class DestinationDataService:
    """Returns complete normalized destination records.

    Currently this reads previously normalized searches from Cosmos DB.

    TODO(data team): when a matching search is missing or stale:
      1. fetch origin-wide flight candidates,
      2. enrich shortlisted destinations with weather and country metadata,
      3. normalize and persist the result,
      4. return the normalized destination records.
    """

    def __init__(self, repository: CosmosDestinationRepository) -> None:
        self._repository = repository

    @property
    def source_name(self) -> str:
        return self._repository.source_name

    async def get_destination_records(
        self,
        request: FlightQuery,
    ) -> list[dict[str, Any]]:
        return await self._repository.get_candidates(request)

    async def search_origins(
        self,
        city_query: str,
        country: str | None = None,
    ) -> list[OriginItem]:
        return await self._repository.search_origins(city_query, country)

    async def get_origin(self, origin_id: str) -> OriginItem:
        return await self._repository.get_origin(origin_id)

    async def find_origins_by_iata(self, iata: str) -> list[OriginItem]:
        return await self._repository.find_origins_by_iata(iata)
