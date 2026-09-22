"""Asynchronous Cosmos DB access for normalized destination records."""

from __future__ import annotations

from typing import Any

from azure.cosmos.aio import ContainerProxy, CosmosClient
from azure.cosmos.exceptions import CosmosHttpResponseError

from backend.config import Settings
from backend.contracts import FlightQuery, OriginItem
from backend.models.hotel import HotelDocument
from backend.models.user import UserDocument
from backend.models.user_flight import SavedFlightSnapshot, UserSavedFlightsDocument


ORIGINS_CONTAINER = "origins"
FLIGHTS_CONTAINER = "flights"
FLIGHT_SELECT_FIELDS = (
    "c.id",
    "c.origin_id",
    "c.origin_iata",
    "c.origin_airport",
    "c.destination_iata",
    "c.destination_airport",
    "c.destination_city",
    "c.destination_country",
    "c.destination_country_code",
    "c.airport_name",
    "c.price_eur",
    "c.currency",
    "c.departure_at",
    "c.return_at",
    "c.outbound_stops",
    "c.return_stops",
    "c.duration_minutes",
    "c.outbound_duration_minutes",
    "c.return_duration_minutes",
    "c.trip_duration_days",
    "c.airline_code",
    "c.airline_name",
    "c.flight_number",
    "c.latitude",
    "c.longitude",
    "c.photo_url",
    "c.photo_url_small",
    "c.temp_max_c",
    "c.temp_min_c",
    "c.rain_pct",
    "c.sunshine_hours",
    "c.max_wind_speed_kmh",
    "c.airport_distance_km",
    "c.flight_retrieved_at",
    "c.weather_retrieved_at",
)


def _flight_select(limit: int | None = None) -> str:
    fields = ", ".join(FLIGHT_SELECT_FIELDS)
    if limit is None:
        return f"SELECT {fields} FROM c"
    return f"SELECT TOP {int(limit)} {fields} FROM c"


def _replace_saved_snapshot(
    current: SavedFlightSnapshot,
    snapshot: SavedFlightSnapshot,
) -> SavedFlightSnapshot:
    """Overwrite the stored snapshot. Keep the old summary if the new save has none."""

    if snapshot.explanation is None and current.explanation is not None:
        return snapshot.model_copy(update={"explanation": current.explanation})
    return snapshot


class RepositoryError(RuntimeError):
    """Raised when normalized destination data cannot be retrieved."""


class RepositoryNotFoundError(RepositoryError):
    """Raised when a requested Cosmos item does not exist."""


class RepositoryConflictError(RepositoryError):
    """Raised when a Cosmos create conflicts with an existing item."""


class CosmosDestinationRepository:
    """Reads the data team's flat ``origins`` and ``flights`` containers."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client: CosmosClient | None = None
        self._origins: ContainerProxy | None = None
        self._flights: ContainerProxy | None = None
        self._users: ContainerProxy | None = None
        self._user_flights: ContainerProxy | None = None
        self._hotels: ContainerProxy | None = None

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
        self._users = database.get_container_client(
            self._settings.users_container_name
        )
        self._user_flights = database.get_container_client(
            self._settings.user_flights_container_name
        )
        self._hotels = database.get_container_client(
            self._settings.hotels_container_name
        )

    async def get_hotel_document(self, destination_id: str) -> HotelDocument:
        """Find a destination's hotel document by exact id across partitions."""

        if self._hotels is None:
            raise RepositoryError("Cosmos repository has not been connected")
        try:
            rows = [
                HotelDocument.model_validate(item)
                async for item in self._hotels.query_items(
                    query="SELECT TOP 1 * FROM c WHERE c.id = @destination_id",
                    parameters=[
                        {"name": "@destination_id", "value": destination_id}
                    ],
                    # The hotel partition key is not established. Async Cosmos
                    # queries across partitions when partition_key is omitted.
                )
            ]
        except (CosmosHttpResponseError, TypeError, ValueError) as error:
            raise RepositoryError("Hotel lookup failed.") from error
        if not rows:
            raise RepositoryNotFoundError(
                f"Hotel destination {destination_id!r} was not found"
            )
        return rows[0]

    async def resolve_hotel_destination_id(
        self, *, city: str, country_code: str, iata_codes: tuple[str, ...],
    ) -> str | None:
        """Return the stored ID only when destination metadata matches uniquely."""

        # City alone is unsafe: names can be shared by different countries.
        if not iata_codes and not (city and country_code):
            return None
        if self._hotels is None:
            raise RepositoryError("Cosmos repository has not been connected")
        matches = []
        parameters: list[dict[str, Any]] = []
        if city and country_code:
            matches.append("STRINGEQUALS(c.city, @city, true)")
            parameters.append({"name": "@city", "value": city})
        if iata_codes:
            matches.append(
                "EXISTS(SELECT VALUE code FROM code IN c.iata "
                "WHERE ARRAY_CONTAINS(@iata_codes, UPPER(code)))"
            )
            parameters.append({"name": "@iata_codes", "value": list(iata_codes)})
        query = "SELECT TOP 2 VALUE c.id FROM c WHERE (" + " OR ".join(matches) + ")"
        if country_code:
            query += " AND STRINGEQUALS(c.country_code, @country_code, true)"
            parameters.append({"name": "@country_code", "value": country_code})
        try:
            rows = [
                item async for item in self._hotels.query_items(
                    query=query, parameters=parameters,
                )
            ]
        except (CosmosHttpResponseError, TypeError, ValueError) as error:
            raise RepositoryError("Hotel destination lookup failed.") from error
        # Two matches are ambiguous, including conflicting city/IATA matches.
        return rows[0] if len(rows) == 1 else None

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
            WHERE CONTAINS(c.city, @query, true)
               OR CONTAINS(c.country, @query, true)
               OR CONTAINS(c.country_code, @query, true)
               OR EXISTS(
                    SELECT VALUE code
                    FROM code IN c.city_iata
                    WHERE STRINGEQUALS(code, @query, true)
               )
               OR EXISTS(
                    SELECT VALUE code
                    FROM code IN c.airports
                    WHERE STRINGEQUALS(code, @query, true)
               )
        """
        parameters: list[dict[str, Any]] = [
            {"name": "@query", "value": city_query.strip()}
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

        query = (
            f"{_flight_select(request.limit)} "
            "WHERE c.origin_id = @origin_id"
        )
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

    async def find_user_by_email(
        self,
        email_normalized: str,
    ) -> UserDocument | None:
        """Find a user by normalized email in the users container."""

        if self._users is None:
            raise RepositoryError("Cosmos repository has not been connected")

        try:
            rows = [
                UserDocument.model_validate(item)
                async for item in self._users.query_items(
                    query=(
                        "SELECT TOP 1 * FROM c "
                        "WHERE c.email_normalized = @email"
                    ),
                    parameters=[
                        {"name": "@email", "value": email_normalized}
                    ],
                    partition_key=email_normalized,
                )
            ]
        except (CosmosHttpResponseError, TypeError, ValueError) as error:
            raise RepositoryError("User lookup failed.") from error
        return rows[0] if rows else None

    async def get_user(self, user_id: str) -> UserDocument:
        """Read a user by ID across the users container partitions."""

        if self._users is None:
            raise RepositoryError("Cosmos repository has not been connected")
        try:
            rows = [
                UserDocument.model_validate(item)
                async for item in self._users.query_items(
                    query=(
                        "SELECT TOP 1 * FROM c "
                        "WHERE c.id = @user_id"
                    ),
                    parameters=[{"name": "@user_id", "value": user_id}],
                )
            ]
        except CosmosHttpResponseError as error:
            if error.status_code == 404:
                raise RepositoryNotFoundError(
                    f"User {user_id!r} was not found"
                ) from error
            raise RepositoryError("User lookup failed.") from error
        if not rows:
            raise RepositoryNotFoundError(
                f"User {user_id!r} was not found"
            )
        return rows[0]

    async def create_user(self, user: UserDocument) -> UserDocument:
        """Create a user and preserve duplicate-email conflict handling."""

        if self._users is None:
            raise RepositoryError("Cosmos repository has not been connected")
        try:
            item = await self._users.create_item(
                body=user.model_dump(mode="json")
            )
        except CosmosHttpResponseError as error:
            if error.status_code == 409:
                raise RepositoryConflictError(
                    "User already exists."
                ) from error
            raise RepositoryError("User creation failed.") from error
        return UserDocument.model_validate(item)

    async def get_flight_by_id(self, flight_id: str) -> dict[str, Any]:
        """Find one flight by document id. This may cross partitions."""

        flights = await self.get_flights_by_ids([flight_id])
        if not flights:
            raise RepositoryNotFoundError(f"Flight {flight_id!r} was not found")
        return flights[0]

    async def get_flights_by_ids(self, flight_ids: list[str]) -> list[dict[str, Any]]:
        """Load saved flights by id from the flights container."""

        if self._flights is None:
            raise RepositoryError("Cosmos repository has not been connected")
        ids = [flight_id.strip() for flight_id in flight_ids if flight_id and flight_id.strip()]
        if not ids:
            return []
        try:
            rows = [
                item
                async for item in self._flights.query_items(
                    query=f"{_flight_select()} WHERE ARRAY_CONTAINS(@ids, c.id)",
                    parameters=[{"name": "@ids", "value": ids}],
                )
            ]
        except (CosmosHttpResponseError, TypeError, ValueError) as error:
            raise RepositoryError("Flight lookup failed.") from error
        return rows

    def _require_user_flights(self) -> ContainerProxy:
        if self._user_flights is None:
            raise RepositoryError("Cosmos repository has not been connected")
        return self._user_flights

    async def _read_user_saved_flights(
        self,
        user_id: str,
    ) -> UserSavedFlightsDocument | None:
        container = self._require_user_flights()
        try:
            item = await container.read_item(item=user_id, partition_key=user_id)
        except CosmosHttpResponseError as error:
            if error.status_code == 404:
                return None
            raise RepositoryError("Saved flight lookup failed.") from error
        return UserSavedFlightsDocument.model_validate(item)

    async def list_user_saved_flights(
        self,
        user_id: str,
    ) -> UserSavedFlightsDocument | None:
        """Return the authenticated user's saved-flight document."""

        return await self._read_user_saved_flights(user_id)

    async def list_user_saved_flight_ids(self, user_id: str) -> list[str]:
        """Return the authenticated user's saved flight IDs, newest first."""

        document = await self._read_user_saved_flights(user_id)
        return list(document.all_flight_ids()) if document else []

    async def add_user_saved_flight(
        self,
        user_id: str,
        snapshot: SavedFlightSnapshot,
    ) -> UserSavedFlightsDocument:
        """Add a flight snapshot to the user's list. Idempotent by flight_id."""

        container = self._require_user_flights()
        document = await self._read_user_saved_flights(user_id)
        if document is None:
            created = UserSavedFlightsDocument(
                id=user_id,
                flights=[snapshot],
                flight_ids=[snapshot.flight_id],
            )
            try:
                item = await container.create_item(body=created.model_dump(mode="json"))
            except CosmosHttpResponseError as error:
                if error.status_code == 409:
                    return await self.add_user_saved_flight(user_id, snapshot)
                raise RepositoryError("Saved flight create failed.") from error
            return UserSavedFlightsDocument.model_validate(item)

        if any(item.flight_id == snapshot.flight_id for item in document.flights):
            flights = [
                _replace_saved_snapshot(item, snapshot)
                if item.flight_id == snapshot.flight_id
                else item
                for item in document.flights
            ]
        else:
            flights = [snapshot, *document.flights]
        leftover = [
            flight_id
            for flight_id in document.flight_ids
            if flight_id != snapshot.flight_id
            and flight_id not in {item.flight_id for item in flights}
        ]
        updated = document.model_copy(
            update={
                "flights": flights,
                "flight_ids": [item.flight_id for item in flights] + leftover,
            }
        )
        try:
            item = await container.replace_item(
                item=updated.id,
                body=updated.model_dump(mode="json"),
            )
        except CosmosHttpResponseError as error:
            if error.status_code == 404:
                return await self.add_user_saved_flight(user_id, snapshot)
            raise RepositoryError("Saved flight update failed.") from error
        return UserSavedFlightsDocument.model_validate(item)

    async def replace_user_saved_flights(
        self,
        document: UserSavedFlightsDocument,
    ) -> UserSavedFlightsDocument:
        """Replace the user's saved-flight document after a snapshot refresh."""

        container = self._require_user_flights()
        try:
            item = await container.replace_item(
                item=document.id,
                body=document.model_dump(mode="json"),
            )
        except CosmosHttpResponseError as error:
            if error.status_code == 404:
                return document
            raise RepositoryError("Saved flight update failed.") from error
        return UserSavedFlightsDocument.model_validate(item)

    async def remove_user_saved_flight(self, user_id: str, flight_id: str) -> None:
        """Remove a saved snapshot from the authenticated user's list only."""

        container = self._require_user_flights()
        document = await self._read_user_saved_flights(user_id)
        if document is None:
            return
        remaining = [
            item for item in document.flights if item.flight_id != flight_id
        ]
        leftover = [
            item for item in document.all_flight_ids() if item != flight_id
        ]
        if remaining == document.flights and leftover == document.all_flight_ids():
            return
        updated = document.model_copy(
            update={
                "flights": remaining,
                "flight_ids": leftover,
            }
        )
        try:
            await container.replace_item(
                item=updated.id,
                body=updated.model_dump(mode="json"),
            )
        except CosmosHttpResponseError as error:
            if error.status_code == 404:
                return
            raise RepositoryError("Saved flight delete failed.") from error

    async def close(self) -> None:
        if self._client is not None:
            await self._client.close()
