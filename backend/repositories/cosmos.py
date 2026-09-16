"""Asynchronous Cosmos DB access for normalized destination records."""

from __future__ import annotations

from typing import Any

from azure.cosmos.aio import ContainerProxy, CosmosClient
from azure.cosmos.exceptions import CosmosHttpResponseError

from backend.config import Settings
from backend.contracts import FlightQuery, OriginItem


ORIGINS_CONTAINER = "origins"
FLIGHTS_CONTAINER = "flights"


class RepositoryError(RuntimeError):
    """Raised when normalized destination data cannot be retrieved."""


class RepositoryNotFoundError(RepositoryError):
    """Raised when a requested Cosmos item does not exist."""


class CosmosDestinationRepository:
    """Reads the data team's flat ``origins`` and ``flights`` containers."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client: CosmosClient | None = None
        self._origins: ContainerProxy | None = None
        self._flights: ContainerProxy | None = None

    @property
    def source_name(self) -> str:
        return f"cosmos://{self._settings.cosmos_database_name}/{FLIGHTS_CONTAINER}"

    async def connect(self) -> None:
        """Create the Cosmos client used for the FastAPI process lifetime."""

        self._client = CosmosClient.from_connection_string(
            self._settings.cosmos_connection_string
        )
        database = self._client.get_database_client(
            self._settings.cosmos_database_name
        )
        self._origins = database.get_container_client(ORIGINS_CONTAINER)
        self._flights = database.get_container_client(FLIGHTS_CONTAINER)

    async def search_origins(
        self,
        city_query: str,
        country: str | None = None,
    ) -> list[OriginItem]:
        """Autocomplete origin cities; this small lookup may cross partitions."""

        if self._origins is None:
            raise RepositoryError("Cosmos repository has not been connected")

        query = """
            SELECT TOP 10 * FROM c
            WHERE CONTAINS(c.city, @city, true)
        """
        parameters: list[dict[str, Any]] = [
            {"name": "@city", "value": city_query.strip()}
        ]
        if country:
            query += """
                AND (
                    STRINGEQUALS(c.country, @country, true)
                    OR STRINGEQUALS(c.country_code, @country, true)
                )
            """
            parameters.append({"name": "@country", "value": country.strip()})

        try:
            # Async Cosmos treats a missing partition_key as a cross-partition
            # query. Do not pass enable_cross_partition_query; azure-cosmos 4.17
            # forwards that keyword to aiohttp and crashes.
            rows = [
                OriginItem.model_validate(item)
                async for item in self._origins.query_items(
                    query=query,
                    parameters=parameters,
                )
            ]
        except (CosmosHttpResponseError, TypeError, ValueError) as error:
            raise RepositoryError(
                f"Cosmos DB origin query failed: {error}"
            ) from error
        return sorted(rows, key=lambda row: (row.city, row.country, row.id))

    async def find_origins_by_iata(self, iata: str) -> list[OriginItem]:
        """Resolve a 3-letter IATA code to origin city documents."""

        if self._origins is None:
            raise RepositoryError("Cosmos repository has not been connected")

        code = iata.strip().upper()
        query = """
            SELECT TOP 10 * FROM c
            WHERE ARRAY_CONTAINS(c.city_iata, @iata)
               OR ARRAY_CONTAINS(c.airports, @iata)
        """
        parameters: list[dict[str, Any]] = [{"name": "@iata", "value": code}]
        try:
            rows = [
                OriginItem.model_validate(item)
                async for item in self._origins.query_items(
                    query=query,
                    parameters=parameters,
                )
            ]
        except (CosmosHttpResponseError, TypeError, ValueError) as error:
            raise RepositoryError(
                f"Cosmos DB origin IATA query failed: {error}"
            ) from error
        return sorted(rows, key=lambda row: (row.city, row.country, row.id))

    async def get_origin(self, origin_id: str) -> OriginItem:
        """Point-read one origin; its id is also its partition key."""

        if self._origins is None:
            raise RepositoryError("Cosmos repository has not been connected")
        try:
            item = await self._origins.read_item(
                item=origin_id,
                partition_key=origin_id,
            )
        except CosmosHttpResponseError as error:
            if error.status_code == 404:
                raise RepositoryNotFoundError(
                    f"Origin {origin_id!r} was not found"
                ) from error
            raise RepositoryError(
                f"Cosmos DB origin read failed: {error.message}"
            ) from error
        return OriginItem.model_validate(item)

    async def get_candidates(
        self,
        request: FlightQuery,
    ) -> list[dict[str, Any]]:
        """Load flights using the required ``origin_id`` partition key."""

        if self._flights is None:
            raise RepositoryError("Cosmos repository has not been connected")

        query = "SELECT * FROM c WHERE c.origin_id = @origin_id"
        parameters: list[dict[str, Any]] = [
            {"name": "@origin_id", "value": request.origin_id}
        ]

        if request.max_price_eur is not None:
            query += " AND c.price_eur <= @max_price"
            parameters.append(
                {"name": "@max_price", "value": request.max_price_eur}
            )
        if request.min_temperature_c is not None:
            query += " AND c.temp_max_c >= @min_temp"
            parameters.append(
                {"name": "@min_temp", "value": request.min_temperature_c}
            )
        if request.destination_country_code:
            query += (
                " AND STRINGEQUALS("
                "c.destination_country_code, @country_code, true)"
            )
            parameters.append(
                {
                    "name": "@country_code",
                    "value": request.destination_country_code,
                }
            )
        if request.departure_date is not None:
            query += " AND STARTSWITH(c.departure_at, @departure_date)"
            parameters.append(
                {
                    "name": "@departure_date",
                    "value": request.departure_date.isoformat(),
                }
            )
        if request.return_date is not None:
            query += " AND STARTSWITH(c.return_at, @return_date)"
            parameters.append(
                {
                    "name": "@return_date",
                    "value": request.return_date.isoformat(),
                }
            )

        try:
            rows = [
                item
                async for item in self._flights.query_items(
                    query=query,
                    parameters=parameters,
                    partition_key=request.origin_id,
                )
            ]
        except (CosmosHttpResponseError, TypeError, ValueError) as error:
            raise RepositoryError(
                f"Cosmos DB flight query failed: {error}"
            ) from error

        # Sorting in Python avoids requiring a Cosmos composite index.
        rows.sort(
            key=lambda row: (
                row.get("price_eur") is None,
                row.get("price_eur") or 0,
                row.get("id") or "",
            )
        )
        return rows

    async def close(self) -> None:
        if self._client is not None:
            await self._client.close()
