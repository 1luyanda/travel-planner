"""Saved-flight snapshots, user isolation, and flights-container hydration."""

from __future__ import annotations

from typing import Any

import pytest
from azure.cosmos.exceptions import CosmosHttpResponseError
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api import auth_router, router
from backend.config import Settings, get_settings
from backend.contracts import SaveFlightRequest
from backend.models.user import UserDocument
from backend.models.user_flight import SavedFlightSnapshot, UserSavedFlightsDocument
from backend.repositories import (
    CosmosDestinationRepository,
    RepositoryError,
    RepositoryNotFoundError,
)
from backend.services import SavedFlightNotFoundError, SavedFlightsService, UserService


ROME_FLIGHT = {
    "id": "ZAG-ROM-2026-09-18",
    "origin_id": "zagreb-hr",
    "origin_iata": "ZAG",
    "origin_airport": "ZAG",
    "destination_iata": "FCO",
    "destination_airport": "FCO",
    "destination_city": "Rome",
    "destination_country": "Italy",
    "destination_country_code": "IT",
    "airport_name": "Fiumicino",
    "price_eur": 65,
    "currency": "EUR",
    "departure_at": "2026-09-18T06:10:00+02:00",
    "return_at": "2026-09-22T21:40:00+02:00",
    "outbound_stops": 0,
    "return_stops": 0,
    "duration_minutes": 95,
    "airline_code": "OU",
    "airline_name": "Croatia Airlines",
    "flight_number": "OU380",
    "latitude": 41.79,
    "longitude": 12.25,
    "photo_url": "https://example.com/rome.jpg",
    "photo_url_small": "https://example.com/rome-small.jpg",
    "temp_max_c": 27.8,
    "temp_min_c": 18.5,
    "rain_pct": 12,
    "sunshine_hours": 9,
    "max_wind_speed_kmh": 18,
}

LISBON_FLIGHT = {
    **ROME_FLIGHT,
    "id": "ZAG-LIS-2026-09-18",
    "destination_iata": "LIS",
    "destination_airport": "LIS",
    "destination_city": "Lisbon",
    "destination_country": "Portugal",
    "destination_country_code": "PT",
    "airport_name": "Humberto Delgado",
    "price_eur": 189,
    "latitude": 38.77,
    "longitude": -9.13,
    "photo_url": "https://example.com/lisbon.jpg",
    "photo_url_small": "https://example.com/lisbon-small.jpg",
}


class _StatusResponse:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code
        self.reason = "Error"
        self.headers = {}
        self.text = ""
        self.content = b""


def cosmos_error(status_code: int, message: str = "cosmos error") -> CosmosHttpResponseError:
    return CosmosHttpResponseError(message=message, response=_StatusResponse(status_code))


class FakeFlightsStore:
    def __init__(self, flights: list[dict[str, Any]] | None = None) -> None:
        records = [ROME_FLIGHT] if flights is None else flights
        self.flights = {item["id"]: dict(item) for item in records}
        self.query_arguments: dict[str, Any] = {}

    def query_items(self, **kwargs: Any) -> Any:
        self.query_arguments = kwargs

        async def rows() -> Any:
            ids = set(kwargs.get("parameters", [{}])[0].get("value") or [])
            for item in self.flights.values():
                if item["id"] in ids:
                    yield dict(item)

        return rows()


class FakeUserFlightsStore:
    def __init__(self) -> None:
        self.items: dict[str, dict[str, Any]] = {}
        self.fail_read = False

    async def read_item(self, item: str, partition_key: str) -> dict[str, Any]:
        if self.fail_read:
            raise cosmos_error(503, "unavailable")
        if item != partition_key or item not in self.items:
            raise cosmos_error(404, "not found")
        return dict(self.items[item])

    async def create_item(self, body: dict[str, Any]) -> dict[str, Any]:
        if body["id"] in self.items:
            raise cosmos_error(409, "conflict")
        self.items[body["id"]] = dict(body)
        return dict(body)

    async def replace_item(self, item: str, body: dict[str, Any]) -> dict[str, Any]:
        if item not in self.items:
            raise cosmos_error(404, "not found")
        self.items[item] = dict(body)
        return dict(body)


class FakeUserRepository:
    def __init__(self) -> None:
        self.users: dict[str, UserDocument] = {}

    async def find_user_by_email(self, email_normalized: str):
        return next(
            (
                user
                for user in self.users.values()
                if user.email_normalized == email_normalized
            ),
            None,
        )

    async def create_user(self, user: UserDocument) -> UserDocument:
        self.users[user.id] = user
        return user

    async def get_user(self, user_id: str) -> UserDocument:
        if user_id not in self.users:
            raise RepositoryNotFoundError("missing")
        return self.users[user_id]


def saved_settings(**overrides: object) -> Settings:
    values = {
        "cosmos_connection_string": "placeholder",
        "cosmos_database_name": "TravelPlaner",
        "frontend_origins": ("http://localhost:5173",),
        "api_auth_key": "test-api-key",
        "trusted_hosts": ("testserver",),
        "app_environment": "test",
        "auth_session_secret": "test-session-secret-value-32chars",
        "user_flights_container_name": "user-flights",
    }
    values.update(overrides)
    return Settings(**values)


def connected_repository(
    flights: FakeFlightsStore | None = None,
    user_flights: FakeUserFlightsStore | None = None,
) -> CosmosDestinationRepository:
    repository = CosmosDestinationRepository(saved_settings())
    repository._flights = flights or FakeFlightsStore()
    repository._user_flights = user_flights or FakeUserFlightsStore()
    return repository


def test_user_flights_container_defaults_and_env_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("COSMOS_CONNECTION_STRING", "AccountEndpoint=https://x/;AccountKey=abc==")
    monkeypatch.setenv("COSMOS_DATABASE", "TravelPlaner")
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("COSMOS_USER_FLIGHTS_CONTAINER", "")
    get_settings.cache_clear()
    try:
        assert get_settings().user_flights_container_name == "user-flights"
        monkeypatch.setenv("COSMOS_USER_FLIGHTS_CONTAINER", "saved-user-flights")
        get_settings.cache_clear()
        assert get_settings().user_flights_container_name == "saved-user-flights"
    finally:
        get_settings.cache_clear()


def test_user_document_stores_snapshots_and_keeps_legacy_ids() -> None:
    document = UserSavedFlightsDocument(
        id="user-1",
        flight_ids=["ZAG-ROM-2026-09-18", "ZAG-ROM-2026-09-18", "ZAG-LIS-2026-09-18"],
    )
    dumped = document.model_dump()
    assert dumped["id"] == "user-1"
    assert dumped["flight_ids"] == ["ZAG-ROM-2026-09-18", "ZAG-LIS-2026-09-18"]
    assert dumped["flights"] == []

    snapshot = SavedFlightSnapshot.from_flight(ROME_FLIGHT)
    stored = UserSavedFlightsDocument(id="user-1", flights=[snapshot])
    stored_dump = stored.model_dump(mode="json")
    assert stored_dump["flights"][0]["flight_id"] == "ZAG-ROM-2026-09-18"
    assert stored_dump["flights"][0]["price_eur"] == 65
    assert stored_dump["flights"][0]["destination_city"] == "Rome"
    assert stored_dump["flight_ids"] == ["ZAG-ROM-2026-09-18"]


@pytest.mark.anyio
async def test_save_stores_a_complete_snapshot_not_only_an_id() -> None:
    flights = FakeFlightsStore([ROME_FLIGHT])
    user_flights = FakeUserFlightsStore()
    repository = connected_repository(flights=flights, user_flights=user_flights)
    saved = await SavedFlightsService(repository).save(
        "user-1",
        SaveFlightRequest(flight_id="ZAG-ROM-2026-09-18"),
    )

    stored = user_flights.items["user-1"]
    snapshot = stored["flights"][0]
    assert saved.flight is not None
    assert saved.flight.price_eur == 65
    assert snapshot["flight_id"] == ROME_FLIGHT["id"]
    assert snapshot["id"] == ROME_FLIGHT["id"]
    assert snapshot["flight_id"] == snapshot["id"]
    assert saved.flight_id == ROME_FLIGHT["id"]
    assert snapshot["saved_at"]
    assert snapshot["origin_id"] == "zagreb-hr"
    assert snapshot["origin_iata"] == "ZAG"
    assert snapshot["destination_iata"] == "FCO"
    assert snapshot["destination_city"] == "Rome"
    assert snapshot["destination_country"] == "Italy"
    assert snapshot["price_eur"] == 65
    assert snapshot["currency"] == "EUR"
    assert snapshot["departure_at"]
    assert snapshot["return_at"]
    assert snapshot["airline_code"] == "OU"
    assert snapshot["outbound_stops"] == 0
    assert snapshot["duration_minutes"] == 95
    assert snapshot["latitude"] == 41.79
    assert snapshot["temp_max_c"] == 27.8
    assert snapshot["photo_url"] == "https://example.com/rome.jpg"
    assert stored["flight_ids"] == ["ZAG-ROM-2026-09-18"]


@pytest.mark.anyio
async def test_snapshot_flight_id_is_the_exact_cosmos_document_id() -> None:
    stable_id = "fl_7f3c2e91-keep-as-is"
    flight = {**ROME_FLIGHT, "id": stable_id}
    flights = FakeFlightsStore([flight])
    user_flights = FakeUserFlightsStore()
    repository = connected_repository(flights=flights, user_flights=user_flights)
    saved = await SavedFlightsService(repository).save(
        "user-1",
        SaveFlightRequest(flight_id=stable_id),
    )

    snapshot = user_flights.items["user-1"]["flights"][0]
    assert saved.flight_id == stable_id
    assert snapshot["flight_id"] == stable_id
    assert snapshot["id"] == stable_id
    assert snapshot["origin_iata"] == "ZAG"
    assert snapshot["destination_city"] == "Rome"
    assert snapshot["flight_id"] != f"{flight['origin_iata']}-{flight['destination_iata']}"


@pytest.mark.anyio
async def test_save_is_idempotent_and_prepends_newest_ids() -> None:
    flights = FakeFlightsStore([ROME_FLIGHT, LISBON_FLIGHT])
    repository = connected_repository(flights=flights)
    service = SavedFlightsService(repository)

    await service.save("user-1", SaveFlightRequest(flight_id="ZAG-ROM-2026-09-18"))
    later = await service.save("user-1", SaveFlightRequest(flight_id="ZAG-LIS-2026-09-18"))
    again = await service.save("user-1", SaveFlightRequest(flight_id="ZAG-ROM-2026-09-18"))

    assert later.flight is not None
    assert later.flight.destination_city == "Lisbon"
    assert again.flight_id == "ZAG-ROM-2026-09-18"
    assert await repository.list_user_saved_flight_ids("user-1") == [
        "ZAG-LIS-2026-09-18",
        "ZAG-ROM-2026-09-18",
    ]
    document = await repository.list_user_saved_flights("user-1")
    assert document is not None
    assert [item.flight_id for item in document.flights] == [
        "ZAG-LIS-2026-09-18",
        "ZAG-ROM-2026-09-18",
    ]


@pytest.mark.anyio
async def test_save_rejects_missing_flights() -> None:
    repository = connected_repository(flights=FakeFlightsStore([]))
    with pytest.raises(SavedFlightNotFoundError):
        await SavedFlightsService(repository).save(
            "user-1",
            SaveFlightRequest(flight_id="missing"),
        )


@pytest.mark.anyio
async def test_saved_price_remains_after_source_flight_is_removed() -> None:
    flights = FakeFlightsStore([ROME_FLIGHT])
    repository = connected_repository(flights=flights)
    service = SavedFlightsService(repository)
    await service.save("user-1", SaveFlightRequest(flight_id="ZAG-ROM-2026-09-18"))
    del flights.flights["ZAG-ROM-2026-09-18"]

    items = await service.list_for_user("user-1")

    assert len(items) == 1
    assert items[0].availability == "unavailable"
    assert items[0].flight is not None
    assert items[0].flight.price_eur == 65
    assert items[0].flight.destination_city == "Rome"
    assert items[0].flight.airline_code == "OU"


@pytest.mark.anyio
async def test_list_updates_snapshot_when_current_flight_changed() -> None:
    flights = FakeFlightsStore([ROME_FLIGHT])
    repository = connected_repository(flights=flights)
    service = SavedFlightsService(repository)
    await service.save("user-1", SaveFlightRequest(flight_id="ZAG-ROM-2026-09-18"))
    flights.flights["ZAG-ROM-2026-09-18"] = {
        **ROME_FLIGHT,
        "price_eur": 81,
        "temp_max_c": 30.1,
        "airline_name": "Updated Air",
    }

    items = await service.list_for_user("user-1")
    stored = (await repository.list_user_saved_flights("user-1")).flights[0]

    assert items[0].availability == "available"
    assert items[0].flight is not None
    assert items[0].flight.price_eur == 81
    assert stored.price_eur == 81
    assert stored.temp_max_c == 30.1
    assert stored.airline_name == "Updated Air"
    assert stored.flight_id == "ZAG-ROM-2026-09-18"
    assert stored.id == "ZAG-ROM-2026-09-18"


@pytest.mark.anyio
async def test_list_does_not_rewrite_snapshot_when_current_matches() -> None:
    flights = FakeFlightsStore([ROME_FLIGHT])
    user_flights = FakeUserFlightsStore()
    repository = connected_repository(flights=flights, user_flights=user_flights)
    service = SavedFlightsService(repository)
    await service.save("user-1", SaveFlightRequest(flight_id="ZAG-ROM-2026-09-18"))
    saved_at = user_flights.items["user-1"]["flights"][0]["saved_at"]

    await service.list_for_user("user-1")

    assert user_flights.items["user-1"]["flights"][0]["saved_at"] == saved_at
    assert user_flights.items["user-1"]["flights"][0]["price_eur"] == 65


@pytest.mark.anyio
async def test_list_hydrates_legacy_ids_and_keeps_unavailable_ids() -> None:
    flights = FakeFlightsStore([ROME_FLIGHT])
    user_flights = FakeUserFlightsStore()
    user_flights.items["user-1"] = {
        "id": "user-1",
        "flight_ids": ["ZAG-ROM-2026-09-18", "ZAG-LIS-2026-09-18"],
    }
    repository = connected_repository(flights=flights, user_flights=user_flights)

    items = await SavedFlightsService(repository).list_for_user("user-1")

    assert [item.flight_id for item in items] == [
        "ZAG-ROM-2026-09-18",
        "ZAG-LIS-2026-09-18",
    ]
    assert items[0].availability == "available"
    assert items[0].flight is not None
    assert items[0].flight.destination_city == "Rome"
    assert items[1].availability == "unavailable"
    assert items[1].flight is None
    stored = user_flights.items["user-1"]
    assert stored["flights"][0]["flight_id"] == "ZAG-ROM-2026-09-18"
    assert stored["flights"][0]["price_eur"] == 65
    assert stored["flight_ids"] == ["ZAG-ROM-2026-09-18", "ZAG-LIS-2026-09-18"]
    assert "ARRAY_CONTAINS(@ids, c.id)" in flights.query_arguments["query"]
    assert "SELECT * FROM" not in flights.query_arguments["query"]
    assert "c.price_eur" in flights.query_arguments["query"]
    assert flights.query_arguments.get("partition_key") is None


@pytest.mark.anyio
async def test_delete_is_scoped_to_the_authenticated_user() -> None:
    flights = FakeFlightsStore([ROME_FLIGHT])
    repository = connected_repository(flights=flights)
    service = SavedFlightsService(repository)
    await service.save("user-a", SaveFlightRequest(flight_id="ZAG-ROM-2026-09-18"))
    await service.save("user-b", SaveFlightRequest(flight_id="ZAG-ROM-2026-09-18"))

    await service.delete("user-a", "ZAG-ROM-2026-09-18")

    assert await repository.list_user_saved_flight_ids("user-a") == []
    assert await repository.list_user_saved_flight_ids("user-b") == ["ZAG-ROM-2026-09-18"]
    remaining = await repository.list_user_saved_flights("user-b")
    assert remaining is not None
    assert remaining.flights[0].price_eur == 65


@pytest.mark.anyio
async def test_repository_hides_cosmos_errors() -> None:
    user_flights = FakeUserFlightsStore()
    user_flights.fail_read = True
    repository = connected_repository(user_flights=user_flights)
    with pytest.raises(RepositoryError, match="Saved flight lookup failed"):
        await repository.list_user_saved_flight_ids("user-1")


def _auth_headers() -> dict[str, str]:
    return {"X-API-Key": "test-api-key"}


def _build_app(
    monkeypatch: pytest.MonkeyPatch,
    repository: CosmosDestinationRepository,
) -> FastAPI:
    import backend.security as security

    app = FastAPI()
    app.include_router(auth_router)
    app.include_router(router)
    app.state.user_service = UserService(FakeUserRepository())
    app.state.saved_flights_service = SavedFlightsService(repository)
    monkeypatch.setattr(security, "get_settings", saved_settings)
    return app


def _register(client: TestClient, email: str, name: str) -> None:
    response = client.post(
        "/api/auth/register",
        headers=_auth_headers(),
        json={
            "email": email,
            "password": "a-long-demo-password",
            "display_name": name,
        },
    )
    assert response.status_code == 201


def test_saved_flight_routes_require_session_and_isolate_users(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = connected_repository()
    app = _build_app(monkeypatch, repository)

    with TestClient(app) as anonymous:
        denied = anonymous.get("/api/saved-flights", headers=_auth_headers())
        assert denied.status_code == 401

    with TestClient(app) as first:
        _register(first, "first@example.com", "First")
        created = first.post(
            "/api/saved-flights",
            headers=_auth_headers(),
            json={"flight_id": "ZAG-ROM-2026-09-18", "origin_id": "zagreb-hr"},
        )
        assert created.status_code == 200
        listed = first.get("/api/saved-flights", headers=_auth_headers())
        assert listed.status_code == 200
        assert listed.json()["items"][0]["flight_id"] == "ZAG-ROM-2026-09-18"
        assert listed.json()["items"][0]["flight"]["destination_city"] == "Rome"
        assert b"max_price" not in listed.request.url.query

        with TestClient(app) as second:
            _register(second, "second@example.com", "Second")
            empty = second.get("/api/saved-flights", headers=_auth_headers())
            assert empty.json()["items"] == []
            second.delete(
                "/api/saved-flights/ZAG-ROM-2026-09-18",
                headers=_auth_headers(),
            )
            still_there = first.get("/api/saved-flights", headers=_auth_headers())
            assert len(still_there.json()["items"]) == 1

        removed = first.delete(
            "/api/saved-flights/ZAG-ROM-2026-09-18",
            headers=_auth_headers(),
        )
        assert removed.status_code == 204
        assert first.get("/api/saved-flights", headers=_auth_headers()).json()["items"] == []


def test_saved_flight_cosmos_errors_are_not_leaked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_flights = FakeUserFlightsStore()
    user_flights.fail_read = True
    app = _build_app(monkeypatch, connected_repository(user_flights=user_flights))

    with TestClient(app) as client:
        _register(client, "person@example.com", "Person")
        response = client.get("/api/saved-flights", headers=_auth_headers())

    assert response.status_code == 503
    assert response.json()["detail"] == "Saved flights are temporarily unavailable."
    assert "Cosmos" not in response.text
