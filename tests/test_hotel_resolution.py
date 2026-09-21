"""Resolve recommendation flight IDs to stored hotel IDs without live Cosmos."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from azure.cosmos.exceptions import CosmosHttpResponseError
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.routes import router
from backend.contracts.candidates import FlightItem
from backend.contracts.recommendations import RecommendationItem
from backend.repositories import CosmosDestinationRepository, RepositoryError
from backend.security import require_api_key
from backend.services import CandidateService, HotelService, RecommendationService
from tests.fake_llm import FakeLLMClient
from tests.test_hotels import FakeHotelRepository, FakeHotelsContainer, document, hotel, settings
from tests.test_integration_boundaries import cosmos_records
from tests.test_recommendations import (
    RecordingDataService, _feedback_payload, _trip,
)


@pytest.mark.parametrize("ids, expected", [
    (["stored-id-with-no-slug-assumption"], "stored-id-with-no-slug-assumption"),
    ([], None),
    (["rome-it", "another-rome-it"], None),
    (["rome-it", "rome-it"], None),
])
def test_repository_returns_only_unique_stored_id(ids, expected):
    repository = CosmosDestinationRepository(settings())
    container = FakeHotelsContainer(ids)
    repository._hotels = container
    result = asyncio.run(repository.resolve_hotel_destination_id(
        city="rome", country_code="IT", iata_codes=("FCO", "ROM"),
    ))
    assert result == expected
    args = container.query_arguments
    assert args["query"] == (
        "SELECT TOP 2 VALUE c.id FROM c WHERE (STRINGEQUALS(c.city, @city, true) OR "
        "EXISTS(SELECT VALUE code FROM code IN c.iata "
        "WHERE ARRAY_CONTAINS(@iata_codes, UPPER(code)))) "
        "AND STRINGEQUALS(c.country_code, @country_code, true)"
    )
    assert args["parameters"] == [
        {"name": "@city", "value": "rome"},
        {"name": "@iata_codes", "value": ["FCO", "ROM"]},
        {"name": "@country_code", "value": "IT"},
    ]
    assert "partition_key" not in args
    assert "enable_cross_partition_query" not in args


def test_city_and_country_lookup_does_not_construct_slug():
    repository = CosmosDestinationRepository(settings())
    container = FakeHotelsContainer(["sao-paulo-br"])
    repository._hotels = container
    result = asyncio.run(repository.resolve_hotel_destination_id(
        city="são paulo", country_code="BR", iata_codes=(),
    ))
    assert result == "sao-paulo-br"
    query = container.query_arguments["query"]
    assert "STRINGEQUALS(c.city, @city, true)" in query
    assert "AND STRINGEQUALS(c.country_code, @country_code, true)" in query
    assert "c.iata" not in query
    assert "são paulo" not in query


def test_iata_lookup_without_country_does_not_match_city_alone():
    repository = CosmosDestinationRepository(settings())
    container = FakeHotelsContainer(["abu-simbel-eg"])
    repository._hotels = container
    result = asyncio.run(repository.resolve_hotel_destination_id(
        city="different spelling", country_code="", iata_codes=("ABS",),
    ))
    assert result == "abu-simbel-eg"
    assert "c.city" not in container.query_arguments["query"]
    assert "c.country_code" not in container.query_arguments["query"]
    assert container.query_arguments["parameters"] == [
        {"name": "@iata_codes", "value": ["ABS"]},
    ]


@pytest.mark.parametrize("city,country", [("Rome", ""), ("", "IT"), ("", "")])
def test_insufficient_metadata_returns_null_without_query(city, country):
    # No connected container: this must return before any database access.
    repository = CosmosDestinationRepository(settings())
    assert asyncio.run(repository.resolve_hotel_destination_id(
        city=city, country_code=country, iata_codes=(),
    )) is None


def test_resolution_wraps_cosmos_failure():
    repository = CosmosDestinationRepository(settings())
    repository._hotels = FakeHotelsContainer(
        [], CosmosHttpResponseError(status_code=503, message="private details"),
    )
    with pytest.raises(RepositoryError, match="Hotel destination lookup failed"):
        asyncio.run(repository.resolve_hotel_destination_id(
            city="rome", country_code="IT", iata_codes=(),
        ))


def test_service_normalizes_metadata_and_reuses_only_identical_destinations():
    repository = FakeHotelRepository(document())
    repository.resolve_hotel_destination_id = AsyncMock(side_effect=["rome-it", None])
    flights = [
        FlightItem(id="offer-1", destination_city=" Rome ", destination_country_code=" it ",
                   destination_iata=" rom ", destination_airport="fco"),
        FlightItem(id="offer-2", destination_city="ROME", destination_country_code="IT",
                   destination_iata="ROM", destination_airport="FCO"),
        FlightItem(id="offer-3", destination_city="Rome", destination_country_code="US"),
        FlightItem(id="offer-4", destination_city="Rome", destination_country_code="US"),
    ]
    result = asyncio.run(HotelService(repository).resolve_destination_ids(flights))
    assert result == {"offer-1": "rome-it", "offer-2": "rome-it", "offer-3": None, "offer-4": None}
    assert repository.resolve_hotel_destination_id.await_count == 2
    assert repository.resolve_hotel_destination_id.await_args_list[0].kwargs == {
        "city": "rome", "country_code": "IT", "iata_codes": ("FCO", "ROM"),
    }
    assert repository.resolve_hotel_destination_id.await_args_list[1].kwargs["country_code"] == "US"


def test_empty_flights_do_not_query_hotels():
    repository = FakeHotelRepository(document())
    repository.resolve_hotel_destination_id = AsyncMock()
    assert asyncio.run(HotelService(repository).resolve_destination_ids([])) == {}
    repository.resolve_hotel_destination_id.assert_not_awaited()


class SameCityFlights(RecordingDataService):
    async def get_destination_records(self, request):
        base = cosmos_records()[0]
        return [
            {**base, "id": f"offer-{index}", "price_eur": 50 + index,
             "destination_country_code": "IT", "destination_airport": "FCO"}
            for index in range(3)
        ]


@pytest.mark.parametrize("refine", [False, True])
@pytest.mark.parametrize("resolution", ["actual-rome-hotel-id", None, "unavailable"])
def test_recommend_and_refine_expose_id_and_preserve_ranked_results(refine, resolution):
    repository = FakeHotelRepository(document(
        [hotel("Stored hotel")], id="actual-rome-hotel-id", city="Rome", country_code="IT",
    ))
    repository.resolve_hotel_destination_id = AsyncMock(
        return_value=resolution,
        side_effect=RepositoryError("private details") if resolution == "unavailable" else None,
    )
    hotels = HotelService(repository)
    responses = [_feedback_payload(prefer_warmer=True)] if refine else []
    service = RecommendationService(
        CandidateService(SameCityFlights()), FakeLLMClient(responses), hotel_service=hotels,
    )
    app = FastAPI()
    app.include_router(router)
    app.state.hotel_service = hotels
    app.state.recommendation_service = service
    app.dependency_overrides[require_api_key] = lambda: None
    # Use the real deterministic fallback explanations; no AI-generated hotel fields.
    with patch("backend.services.recommendations.explain_ranked_trips") as explain:
        explain.return_value.status = "error"
        explain.return_value.issues = []
        with TestClient(app) as client:
            trip = _trip().model_dump(mode="json")
            response = client.post(
                "/api/refine" if refine else "/api/recommend",
                json={"text": "Warmer", "request": trip} if refine
                else {"form_fields": trip},
            )
            assert response.status_code == 200
            body = response.json()
            assert body["status"] == "ready"
            items = body["recommendations"]
            assert [item["destination_id"] for item in items] == ["offer-0", "offer-1", "offer-2"]
            assert [item["rank"] for item in items] == [1, 2, 3]
            assert [item["final_score"] for item in items] == sorted(
                (item["final_score"] for item in items), reverse=True,
            )
            expected = None if resolution == "unavailable" else resolution
            assert [item["hotel_destination_id"] for item in items] == [expected] * 3
            assert repository.resolve_hotel_destination_id.await_count == 1
            if expected:
                hotel_response = client.get("/api/hotels", params={
                    "destination_id": items[0]["hotel_destination_id"], "limit": 5,
                })
                assert hotel_response.status_code == 200
                assert hotel_response.json()["destination_id"] == expected
                assert hotel_response.json()["hotels"][0]["name"] == "Stored hotel"
            if resolution == "unavailable":
                assert "Hotel destination lookup is temporarily unavailable." in body["issues"]
                assert "private details" not in response.text
            # Existing payloads remain valid without the new response field.
            legacy = {key: value for key, value in items[0].items() if key != "hotel_destination_id"}
            assert RecommendationItem.model_validate(legacy).hotel_destination_id is None
