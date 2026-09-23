"""Nearby activity tests. HTTP is faked; Google is never called."""

from __future__ import annotations

import asyncio
import json
from typing import Any
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.api.routes import router
from backend.contracts.activities import NearbyActivitiesRequest
from backend.security import require_api_key
from backend.services.places import PlacesService, PlacesUnavailableError

SECRET_KEY = "test-google-places-key-do-not-leak"
PHOTO_NAME = "places/ChIJA/photos/AbCd_123"


class _FakeResponse:
    def __init__(
        self,
        status_code: int,
        payload: dict[str, Any] | None = None,
        *,
        content: bytes = b"",
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status_code = status_code
        self._payload = payload
        self.content = content
        self.headers = headers or {}
        self.text = json.dumps(payload) if payload is not None else ""

    def json(self) -> Any:
        if self._payload is None:
            raise ValueError("invalid json")
        return self._payload


def _place(place_id: str, name: str, **overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": place_id,
        "displayName": {"text": name, "languageCode": "en"},
        "formattedAddress": "Piazza del Colosseo, Rome",
        "types": ["tourist_attraction", "point_of_interest"],
        "businessStatus": "OPERATIONAL",
        "rating": 4.7,
        "userRatingCount": 1800,
        "location": {"latitude": 41.8902, "longitude": 12.4922},
        "googleMapsUri": "https://maps.google.com/?cid=123",
        "photos": [
            {
                "name": PHOTO_NAME,
                "authorAttributions": [
                    {
                        "displayName": "Ada Lovelace",
                        "uri": "https://maps.google.com/maps/contrib/1",
                        "photoUri": "https://lh3.googleusercontent.com/author.jpg",
                    }
                ],
                "googleMapsUri": "https://www.google.com/maps/place/photo",
            }
        ],
    }
    payload.update(overrides)
    return payload


def _api_client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_api_key] = lambda: None
    return TestClient(app)


def _run_nearby(
    places: list[dict[str, Any]] | None = None,
    *,
    request: NearbyActivitiesRequest | None = None,
    responses: list[_FakeResponse] | None = None,
    captured: dict[str, Any] | None = None,
) -> Any:
    queue = list(responses or [])

    async def fake_post(url: str, **kwargs: Any) -> _FakeResponse:
        if captured is not None:
            captured.setdefault("calls", []).append(
                {"url": url, "json": kwargs.get("json"), "headers": kwargs.get("headers")}
            )
        if queue:
            return queue.pop(0)
        return _FakeResponse(200, {"places": places or []})

    service = PlacesService(SECRET_KEY, http_post=fake_post)
    body = request or NearbyActivitiesRequest(latitude=41.89, longitude=12.49, limit=10)
    return asyncio.run(service.search_nearby(body))


def test_coordinates_search_uses_nearby_field_mask_and_radius() -> None:
    captured: dict[str, Any] = {}
    result = _run_nearby([_place("ChIJA", "Colosseum")], captured=captured)

    assert result.status == "ready"
    assert result.radius_meters == 5000
    assert result.attribution == "Google Maps"
    assert result.search_center.latitude == 41.89
    assert result.activities[0].place_id == "ChIJA"
    assert result.activities[0].name == "Colosseum"
    assert result.activities[0].rating == 4.7
    assert result.activities[0].user_ratings_total == 1800
    assert result.activities[0].latitude == 41.8902
    assert result.activities[0].photo is not None
    assert result.activities[0].photo.name == PHOTO_NAME
    assert result.activities[0].photo.author_attributions[0].display_name == "Ada Lovelace"
    assert result.activities[0].google_maps_uri == "https://maps.google.com/?cid=123"
    call = captured["calls"][0]
    assert call["url"] == "https://places.googleapis.com/v1/places:searchNearby"
    assert call["json"]["locationRestriction"]["circle"]["radius"] == 5000.0
    assert call["json"]["maxResultCount"] == 10
    assert "tourist_attraction" in call["json"]["includedTypes"]
    assert "places.photos.name" in call["headers"]["X-Goog-FieldMask"]
    assert "places.priceLevel" not in call["headers"]["X-Goog-FieldMask"]
    assert SECRET_KEY not in result.model_dump_json()
    assert SECRET_KEY not in json.dumps(call["json"])


def test_missing_rating_photo_and_coordinates_are_omitted() -> None:
    result = _run_nearby(
        [
            _place(
                "ChIJA",
                "Quiet Square",
                rating=None,
                userRatingCount=None,
                location=None,
                photos=[],
                googleMapsUri="javascript:alert(1)",
            )
        ]
    )
    item = result.activities[0]
    assert item.rating is None
    assert item.user_ratings_total is None
    assert item.latitude is None
    assert item.longitude is None
    assert item.photo is None
    assert item.google_maps_uri is None


def test_permanently_closed_and_duplicate_places_are_excluded() -> None:
    result = _run_nearby(
        [
            _place("closed", "Old Gate", businessStatus="CLOSED_PERMANENTLY"),
            _place("ChIJA", "Colosseum"),
            _place("ChIJA", "Colosseum again"),
        ]
    )
    assert [item.place_id for item in result.activities] == ["ChIJA"]


def test_city_search_resolves_a_locality_then_searches_nearby() -> None:
    captured: dict[str, Any] = {}
    result = _run_nearby(
        request=NearbyActivitiesRequest(city="Rome", country_code="it", radius_meters=2000, limit=3),
        responses=[
            _FakeResponse(
                200,
                {"places": [{"location": {"latitude": 41.9, "longitude": 12.5}, "displayName": {"text": "Rome"}}]},
            ),
            _FakeResponse(200, {"places": [_place("ChIJA", "Colosseum")]}),
        ],
        captured=captured,
    )

    assert result.city == "Rome"
    assert result.search_center.latitude == 41.9
    assert result.activities[0].place_id == "ChIJA"
    assert captured["calls"][0]["url"].endswith(":searchText")
    assert captured["calls"][0]["json"]["textQuery"] == "Rome, IT"
    assert captured["calls"][0]["json"]["includedType"] == "locality"
    assert captured["calls"][1]["url"].endswith(":searchNearby")
    assert captured["calls"][1]["json"]["maxResultCount"] == 3
    assert captured["calls"][1]["json"]["regionCode"] == "IT"


def test_unknown_city_does_not_call_nearby_search() -> None:
    captured: dict[str, Any] = {}
    result = _run_nearby(
        request=NearbyActivitiesRequest(city="Nowhereville"),
        responses=[_FakeResponse(200, {"places": []})],
        captured=captured,
    )
    assert result.activities == []
    assert result.search_center is None
    assert result.issues == ["No matching city location was found."]
    assert len(captured["calls"]) == 1


def test_coordinates_skip_city_geocoding() -> None:
    captured: dict[str, Any] = {}
    _run_nearby(
        [_place("ChIJA", "Colosseum")],
        request=NearbyActivitiesRequest(city="Rome", latitude=41.89, longitude=12.49),
        captured=captured,
    )
    assert len(captured["calls"]) == 1
    assert captured["calls"][0]["url"].endswith(":searchNearby")


def test_backend_rejects_invalid_nearby_queries() -> None:
    with pytest.raises(ValidationError):
        NearbyActivitiesRequest()
    with pytest.raises(ValidationError):
        NearbyActivitiesRequest(latitude=41.0)
    with pytest.raises(ValidationError):
        NearbyActivitiesRequest(latitude=95, longitude=12)
    with pytest.raises(ValidationError):
        NearbyActivitiesRequest(latitude=41, longitude=12, radius_meters=50001)
    with pytest.raises(ValidationError):
        NearbyActivitiesRequest(latitude=41, longitude=12, limit=21)
    with pytest.raises(ValidationError):
        NearbyActivitiesRequest(city="Rome", included_types=["restaurant"])
    with pytest.raises(ValidationError):
        NearbyActivitiesRequest(city="Rome", country_code="ITALY")

    client = _api_client()
    response = client.post("/api/activities/nearby", json={"included_types": ["restaurant"]})
    assert response.status_code == 422
    assert SECRET_KEY not in response.text


def test_nearby_failure_does_not_leak_the_api_key() -> None:
    async def fake_post(url: str, **kwargs: Any) -> _FakeResponse:
        return _FakeResponse(500, {"error": {"message": SECRET_KEY}})

    service = PlacesService(SECRET_KEY, http_post=fake_post)
    with pytest.raises(PlacesUnavailableError) as raised:
        asyncio.run(
            service.search_nearby(NearbyActivitiesRequest(latitude=41.89, longitude=12.49))
        )
    assert SECRET_KEY not in str(raised.value)

    async def boom(*args: Any, **kwargs: Any) -> Any:
        raise PlacesUnavailableError("Activity data is temporarily unavailable.")

    with patch("backend.api.routes.PlacesService.from_env") as from_env:
        from_env.return_value.search_nearby = boom
        response = _api_client().post(
            "/api/activities/nearby",
            json={"latitude": 41.89, "longitude": 12.49},
        )
    assert response.status_code == 503
    assert response.json()["detail"] == "Activity data is temporarily unavailable."
    assert SECRET_KEY not in response.text


def test_photo_proxy_strips_the_api_key_and_rejects_bad_names() -> None:
    captured: list[dict[str, Any]] = []

    async def fake_get(url: str, **kwargs: Any) -> _FakeResponse:
        captured.append({"url": url, "params": kwargs.get("params"), "headers": kwargs.get("headers")})
        if url.endswith("/media"):
            return _FakeResponse(200, {"photoUri": "https://lh3.googleusercontent.com/photo.jpg"})
        return _FakeResponse(200, content=b"image-bytes", headers={"content-type": "image/jpeg"})

    service = PlacesService(SECRET_KEY, http_get=fake_get)
    content, media_type = asyncio.run(service.fetch_photo(PHOTO_NAME, max_height_px=400))
    assert content == b"image-bytes"
    assert media_type == "image/jpeg"
    assert captured[0]["headers"]["X-Goog-Api-Key"] == SECRET_KEY
    assert captured[1]["headers"] == {}
    assert SECRET_KEY not in captured[1]["url"]

    client = _api_client()
    rejected = client.get("/api/activities/photo", params={"name": "https://evil.example/photo.jpg"})
    assert rejected.status_code == 422
    assert SECRET_KEY not in rejected.text

    with patch("backend.api.routes.PlacesService.from_env", return_value=service):
        response = client.get(
            "/api/activities/photo",
            params={"name": PHOTO_NAME, "max_height_px": 400},
        )
    assert response.status_code == 200
    assert response.content == b"image-bytes"
    assert response.headers["cache-control"] == "no-store"
    assert SECRET_KEY not in response.text
    assert SECRET_KEY.encode() not in response.content
