"""Hotel distance, service, API and Cosmos tests; no live database required."""

from __future__ import annotations

import asyncio
from copy import deepcopy
from math import pi
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from azure.cosmos.exceptions import CosmosHttpResponseError
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.routes import router
from backend.config import Settings, get_settings
from backend.models.hotel import HotelDocument
from backend.repositories import (
    CosmosDestinationRepository,
    RepositoryError,
    RepositoryNotFoundError,
)
from backend.security import require_api_key
from backend.services.hotels import HotelService, haversine_km


def hotel(name: str = "Hotel", **overrides: Any) -> dict[str, Any]:
    return {"name": name, "latitude": 0.0, "longitude": 0.0, **overrides}


def document(hotels: list[Any] | None = None, **overrides: Any) -> dict[str, Any]:
    return {
        "id": "abu-simbel-eg",
        "city": "Abu Simbel",
        "country_code": "EG",
        "latitude": 0.0,
        "longitude": 0.0,
        "attribution": "© OpenStreetMap contributors",
        "hotels": hotels if hotels is not None else [],
        **overrides,
    }


def settings(**overrides: Any) -> Settings:
    return Settings(
        cosmos_connection_string="placeholder",
        cosmos_database_name="TravelPlaner",
        frontend_origins=(),
        **overrides,
    )


class FakeHotelRepository:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.document = HotelDocument.model_validate(payload)
        self.requested_ids: list[str] = []

    async def get_hotel_document(self, destination_id: str) -> HotelDocument:
        self.requested_ids.append(destination_id)
        if destination_id != self.document.id:
            raise RepositoryNotFoundError("Hotel destination was not found")
        return self.document


class FakeHotelsContainer:
    def __init__(self, rows: list[dict], error: Exception | None = None) -> None:
        self.rows = rows
        self.error = error
        self.query_arguments: dict[str, Any] = {}

    def query_items(self, **kwargs: Any) -> Any:
        self.query_arguments = kwargs

        async def items():
            if self.error:
                raise self.error
            for row in self.rows:
                yield row

        return items()


def recommend(hotels: list[Any], limit: int = 5):
    repository = FakeHotelRepository(document(hotels))
    result = asyncio.run(HotelService(repository).recommend("abu-simbel-eg", limit))
    assert repository.requested_ids == ["abu-simbel-eg"]
    return result


def api_client(repository: Any) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.state.hotel_service = HotelService(repository)
    app.dependency_overrides[require_api_key] = lambda: None
    return TestClient(app)


@pytest.mark.parametrize(
    ("coordinates", "expected"),
    [
        ((22.3457, 31.61624, 22.3457, 31.61624), 0.0),
        ((0, 0, 0, 1), 111.19492664455873),
        ((51.5074, -0.1278, 48.8566, 2.3522), 343.55606034104164),
        ((0, 179.5, 0, -179.5), 111.19492664455873),
        ((0, 0, 0, 180), pi * 6371),
    ],
)
def test_haversine_known_distances(coordinates, expected) -> None:
    assert haversine_km(*coordinates) == pytest.approx(expected, abs=1e-8)
    assert haversine_km(*coordinates[2:], *coordinates[:2]) == pytest.approx(expected)


def test_nearest_first_without_star_preference_or_input_mutation() -> None:
    hotels = [
        hotel("Far", longitude=0.02, stars=5),
        hotel("Nearest", longitude=0.001, stars=None),
        hotel("Middle", longitude=0.01, stars=1),
    ]
    original = deepcopy(hotels)
    result = recommend(hotels)
    assert [item.name for item in result.hotels] == ["Nearest", "Middle", "Far"]
    assert result.hotels[0].stars is None
    assert hotels == original


def test_ties_use_name_then_stable_osm_id_independent_of_input_order() -> None:
    hotels = [
        hotel("Zulu", osm_id="node/3", stars=5),
        hotel("Alpha", osm_id="node/2", stars=5),
        hotel("Alpha", osm_id="node/1", stars=None),
    ]
    forward = recommend(hotels)
    reverse = recommend(list(reversed(hotels)))
    assert forward == reverse
    assert [item.osm_id for item in forward.hotels] == ["node/1", "node/2", "node/3"]


def test_sorting_retains_distance_precision() -> None:
    result = recommend([
        hotel("Alpha farther", longitude=0.000002),
        hotel("Zulu nearer", longitude=0.000001),
    ])
    assert result.hotels[0].name == "Zulu nearer"
    assert 0 < result.hotels[0].distance_km < result.hotels[1].distance_km < 0.005


def test_default_shortlist_and_requested_limit_applied_after_sorting() -> None:
    hotels = [hotel(str(index), longitude=index) for index in range(8, 0, -1)]
    result = recommend(hotels)
    assert [item.name for item in result.hotels] == ["1", "2", "3", "4", "5"]
    assert result.hotel_count == 8
    assert result.returned_count == 5
    assert recommend(hotels, limit=2).returned_count == 2


@pytest.mark.parametrize("field", ["latitude", "longitude"])
@pytest.mark.parametrize("value", [None, "invalid", "1.5", True, float("nan"), float("inf"), -181, 181])
def test_invalid_coordinates_are_excluded(field, value) -> None:
    result = recommend([hotel("Bad", **{field: value}), hotel("Valid")])
    assert [item.name for item in result.hotels] == ["Valid"]
    assert result.hotel_count == 2
    assert result.returned_count == 1


@pytest.mark.parametrize("latitude", [-90.01, 90.01])
def test_latitude_range_is_stricter_than_longitude(latitude) -> None:
    assert recommend([hotel(latitude=latitude)]).hotels == []


@pytest.mark.parametrize("field", ["latitude", "longitude"])
def test_missing_coordinates_are_excluded(field) -> None:
    invalid = hotel()
    del invalid[field]
    assert recommend([invalid]).hotels == []


def test_malformed_entries_do_not_hide_valid_hotels() -> None:
    result = recommend([None, {}, "invalid", hotel(name=" "), hotel("Valid")])
    assert [item.name for item in result.hotels] == ["Valid"]


def test_empty_hotels_return_empty_success() -> None:
    with api_client(FakeHotelRepository(document())) as client:
        response = client.get("/api/hotels", params={"destination_id": "abu-simbel-eg"})
    assert response.status_code == 200
    assert response.json()["hotels"] == []
    assert response.json()["hotel_count"] == response.json()["returned_count"] == 0


def test_api_response_contract_and_nullable_metadata() -> None:
    payload = document(
        [hotel("Eskaleh", latitude=22.346627, longitude=31.618582,
               stars=None, address=None, website=None, booking_url=None,
               _etag="internal", price=100)],
        latitude=22.3457, longitude=31.61624, hotel_count=999, _rid="internal",
    )
    with api_client(FakeHotelRepository(payload)) as client:
        response = client.get("/api/hotels?destination_id=abu-simbel-eg")
    assert response.status_code == 200
    body = response.json()
    assert body == {
        "destination_id": "abu-simbel-eg",
        "city": "Abu Simbel",
        "country_code": "EG",
        "latitude": 22.3457,
        "longitude": 31.61624,
        "attribution": "© OpenStreetMap contributors",
        "hotel_count": 1,
        "returned_count": 1,
        "hotels": [{
            "name": "Eskaleh", "osm_id": None, "stars": None,
            "latitude": 22.346627, "longitude": 31.618582,
            "distance_km": pytest.approx(0.2612, abs=0.001),
            "address": None, "website": None, "booking_url": None,
        }],
    }


def test_api_preserves_stored_links_and_requested_limit() -> None:
    payload = document([
        hotel("Near", website="https://example.com", booking_url="https://example.com/book"),
        hotel("Far", longitude=1),
    ])
    with api_client(FakeHotelRepository(payload)) as client:
        body = client.get("/api/hotels?destination_id=abu-simbel-eg&limit=1").json()
    assert body["returned_count"] == 1
    assert body["hotels"][0]["website"] == "https://example.com"
    assert body["hotels"][0]["booking_url"] == "https://example.com/book"


def test_destination_not_found() -> None:
    repository = FakeHotelRepository(document())
    with pytest.raises(RepositoryNotFoundError):
        asyncio.run(HotelService(repository).recommend("missing"))
    with api_client(repository) as client:
        assert client.get("/api/hotels?destination_id=missing").status_code == 404


@pytest.mark.parametrize("query", [
    "", "destination_id=", "destination_id=%20", "destination_id=" + "a" * 151,
    "destination_id=abu-simbel-eg&limit=0", "destination_id=abu-simbel-eg&limit=21",
    "destination_id=abu-simbel-eg&limit=1.5", "destination_id=abu-simbel-eg&limit=abc",
])
def test_api_rejects_invalid_queries_before_retrieval(query) -> None:
    repository = FakeHotelRepository(document())
    with api_client(repository) as client:
        assert client.get(f"/api/hotels?{query}").status_code == 422
    assert repository.requested_ids == []


def test_api_requires_existing_api_key() -> None:
    with api_client(FakeHotelRepository(document())) as client:
        client.app.dependency_overrides.clear()
        with patch("backend.security.get_settings", return_value=settings(api_auth_key="secret")):
            assert client.get("/api/hotels?destination_id=abu-simbel-eg").status_code == 401


def test_cosmos_lookup_is_parameterized_without_assumed_partition_key() -> None:
    repository = CosmosDestinationRepository(settings())
    container = FakeHotelsContainer([document()])
    repository._hotels = container
    destination_id = "city' OR true --"
    result = asyncio.run(repository.get_hotel_document(destination_id))
    assert result.id == "abu-simbel-eg"
    assert container.query_arguments == {
        "query": "SELECT TOP 1 * FROM c WHERE c.id = @destination_id",
        "parameters": [{"name": "@destination_id", "value": destination_id}],
    }


def test_cosmos_empty_result_is_not_found() -> None:
    repository = CosmosDestinationRepository(settings())
    repository._hotels = FakeHotelsContainer([])
    with pytest.raises(RepositoryNotFoundError):
        asyncio.run(repository.get_hotel_document("missing"))


def test_cosmos_requires_connection() -> None:
    with pytest.raises(RepositoryError, match="not been connected"):
        asyncio.run(CosmosDestinationRepository(settings()).get_hotel_document("city"))


@pytest.mark.parametrize("container", [
    FakeHotelsContainer([], CosmosHttpResponseError(status_code=503, message="private details")),
    FakeHotelsContainer([document(latitude=None)]),
    FakeHotelsContainer([document(longitude=181)]),
    FakeHotelsContainer([document(latitude=float("nan"))]),
])
def test_unavailable_or_invalid_destination_data_returns_generic_503(container) -> None:
    repository = CosmosDestinationRepository(settings())
    repository._hotels = container
    with api_client(repository) as client:
        response = client.get("/api/hotels?destination_id=abu-simbel-eg")
    assert response.status_code == 503
    assert response.json() == {"detail": "Hotel data is temporarily unavailable."}


def test_cosmos_connect_uses_configured_hotels_container_and_closes_client() -> None:
    client = MagicMock()
    client.close = AsyncMock()
    with patch("backend.repositories.cosmos.CosmosClient.from_connection_string", return_value=client):
        repository = CosmosDestinationRepository(settings(hotels_container_name="stored-hotels"))
        asyncio.run(repository.connect())
        client.get_database_client.assert_called_once_with("TravelPlaner")
        client.get_database_client.return_value.get_container_client.assert_any_call("stored-hotels")
        asyncio.run(repository.close())
    client.close.assert_awaited_once()


def test_hotels_container_default_and_environment_override(monkeypatch) -> None:
    monkeypatch.setenv("COSMOS_CONNECTION_STRING", "placeholder")
    monkeypatch.setenv("COSMOS_DATABASE", "TravelPlaner")
    monkeypatch.setenv("APP_ENV", "test")
    with patch("backend.config.load_dotenv"):
        try:
            for value, expected in [("", "hotels"), ("stored-hotels", "stored-hotels")]:
                monkeypatch.setenv("COSMOS_HOTELS_CONTAINER", value)
                get_settings.cache_clear()
                assert get_settings().hotels_container_name == expected
        finally:
            get_settings.cache_clear()
