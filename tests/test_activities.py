"""Unit tests for destination activities. HTTP is faked; Google is never called."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.api.routes import router
from backend.contracts.activities import ActivitiesRequest, ActivityItem
from backend.services.places import (
    PlacesConfigurationError,
    PlacesService,
    PlacesUnavailableError,
    build_text_queries,
)

SECRET_KEY = "test-google-places-key-do-not-leak"


class _FakeResponse:
    def __init__(
        self,
        status_code: int,
        payload: dict[str, Any] | None = None,
        text: str = "",
    ) -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = text or (json.dumps(payload) if payload is not None else "")

    def json(self) -> Any:
        if self._payload is None:
            raise ValueError("invalid json")
        return self._payload


def _place(
    place_id: str,
    name: str,
    **overrides: Any,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": place_id,
        "displayName": {"text": name, "languageCode": "en"},
        "formattedAddress": "Rome, Italy",
        "types": ["tourist_attraction"],
        "businessStatus": "OPERATIONAL",
        "rating": 4.6,
        "userRatingCount": 1200,
        "priceLevel": "PRICE_LEVEL_MODERATE",
    }
    payload.update(overrides)
    return payload


def _search(
    places: list[dict[str, Any]] | None = None,
    *,
    request: ActivitiesRequest | None = None,
    status_code: int = 200,
    payload: dict[str, Any] | None = None,
    error: Exception | None = None,
    captured: dict[str, Any] | None = None,
):
    async def fake_post(url: str, **kwargs: Any) -> _FakeResponse:
        if captured is not None:
            captured["url"] = url
            captured["json"] = kwargs.get("json")
            captured["headers"] = kwargs.get("headers")
            captured.setdefault("calls", []).append(kwargs.get("json"))
        if error is not None:
            raise error
        if payload is not None:
            return _FakeResponse(status_code, payload, text=json.dumps(payload))
        return _FakeResponse(status_code, {"places": places or []})

    service = PlacesService(SECRET_KEY, http_post=fake_post)
    body = request or ActivitiesRequest(city="Rome", moods=["cultural"], limit=8)
    return asyncio.run(service.search(body))


def _api_client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_valid_request_returns_normalized_activities() -> None:
    captured: dict[str, Any] = {}
    result = _search(
        [
            _place(
                "ChIJA",
                "Colosseum",
                types=["tourist_attraction", "historical_landmark"],
            )
        ],
        captured=captured,
    )

    assert result.status == "ready"
    assert result.city == "Rome"
    assert result.issues == []
    assert len(result.activities) == 1
    item = result.activities[0]
    assert item.place_id == "ChIJA"
    assert item.name == "Colosseum"
    assert item.address == "Rome, Italy"
    assert item.types == ["tourist_attraction", "historical_landmark"]
    assert item.rating == 4.6
    assert item.user_ratings_total == 1200
    assert item.business_status == "OPERATIONAL"
    assert item.price_level == "PRICE_LEVEL_MODERATE"
    assert captured["url"] == "https://places.googleapis.com/v1/places:searchText"
    assert captured["calls"][0]["textQuery"] == "museums in Rome"
    assert SECRET_KEY not in result.model_dump_json()


def test_empty_city_is_rejected() -> None:
    with pytest.raises(ValidationError):
        ActivitiesRequest(city="")
    with pytest.raises(ValidationError):
        ActivitiesRequest(city="   ")

    response = _api_client().post("/api/activities", json={"city": ""})
    assert response.status_code == 422


def test_missing_api_key_handled_safely(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("GOOGLE_PLACES_API_KEY", raising=False)
    monkeypatch.setattr(
        "backend.services.places._ENV_PATH",
        tmp_path / "missing.env",
    )

    with pytest.raises(PlacesConfigurationError, match="temporarily unavailable"):
        PlacesService.from_env()

    client = _api_client()
    response = client.post("/api/activities", json={"city": "Rome"})
    assert response.status_code == 503
    assert response.json()["detail"] == "Activity data is temporarily unavailable."
    assert SECRET_KEY not in response.text
    assert "GOOGLE_PLACES_API_KEY" not in response.text


def test_empty_places_response() -> None:
    result = _search([])
    assert result.status == "ready"
    assert result.activities == []
    assert result.issues == []


def test_duplicate_place_ids_are_deduplicated() -> None:
    duplicate = _place("ChIJA", "Colosseum")
    result = _search([duplicate, dict(duplicate)])
    assert [item.place_id for item in result.activities] == ["ChIJA"]


def test_missing_rating_works() -> None:
    result = _search([_place("ChIJA", "Colosseum", rating=None)])
    assert result.activities[0].rating is None
    assert result.activities[0].name == "Colosseum"


def test_missing_price_level_works() -> None:
    result = _search([_place("ChIJA", "Colosseum", priceLevel=None)])
    assert result.activities[0].price_level is None
    assert result.activities[0].rating == 4.6


def test_permanently_closed_places_are_excluded() -> None:
    result = _search(
        [
            _place("closed", "Old Shop", businessStatus="CLOSED_PERMANENTLY"),
            _place("open", "Trevi Fountain"),
        ]
    )
    assert [item.place_id for item in result.activities] == ["open"]


def test_google_api_failure_handled_safely() -> None:
    with pytest.raises(PlacesUnavailableError, match="temporarily unavailable"):
        _search(status_code=500, payload={"error": f"denied {SECRET_KEY}"})

    async def boom(*args: Any, **kwargs: Any) -> Any:
        raise PlacesUnavailableError("Activity data is temporarily unavailable.")

    with patch("backend.api.routes.PlacesService.from_env") as from_env:
        from_env.return_value.search = boom
        response = _api_client().post("/api/activities", json={"city": "Rome"})

    assert response.status_code == 503
    assert response.json()["detail"] == "Activity data is temporarily unavailable."
    assert SECRET_KEY not in response.text
    assert "denied" not in response.text


def test_limit_is_respected() -> None:
    places = [_place(f"id-{index}", f"Place {index}") for index in range(10)]
    result = _search(
        places,
        request=ActivitiesRequest(city="Rome", limit=3),
    )
    assert len(result.activities) == 3
    assert [item.place_id for item in result.activities] == ["id-0", "id-1", "id-2"]


def test_api_key_never_appears_in_response_or_errors() -> None:
    result = _search(
        [_place("ChIJA", "Colosseum")],
        request=ActivitiesRequest(
            city="Rome",
            country_code="IT",
            destination_id="ZAG-ROM-2026-09-18",
            moods=["cultural"],
        ),
    )
    dumped = result.model_dump_json()
    assert SECRET_KEY not in dumped

    with pytest.raises(PlacesUnavailableError) as raised:
        _search(status_code=403, payload={"error": {"message": SECRET_KEY}})
    assert SECRET_KEY not in str(raised.value)


def test_empty_moods_use_tourist_attractions_query() -> None:
    assert build_text_queries("Rome", "IT", []) == [
        "tourist attractions in Rome, IT"
    ]
    assert build_text_queries("Rome", None, ["cultural"])[0] == "museums in Rome"


def test_endpoint_returns_ready_payload() -> None:
    response_body = {
        "status": "ready",
        "city": "Rome",
        "destination_id": "ZAG-ROM-2026-09-18",
        "activities": [
            ActivityItem(place_id="ChIJA", name="Colosseum").model_dump(),
        ],
        "issues": [],
    }

    async def fake_search(body: ActivitiesRequest) -> Any:
        from backend.contracts.activities import ActivitiesResponse

        return ActivitiesResponse.model_validate(
            {**response_body, "city": body.city, "destination_id": body.destination_id}
        )

    with patch("backend.api.routes.PlacesService.from_env") as from_env:
        from_env.return_value.search = fake_search
        response = _api_client().post(
            "/api/activities",
            json={
                "city": "Rome",
                "country_code": "IT",
                "destination_id": "ZAG-ROM-2026-09-18",
                "moods": ["cultural"],
                "limit": 8,
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ready"
    assert payload["city"] == "Rome"
    assert payload["destination_id"] == "ZAG-ROM-2026-09-18"
    assert payload["activities"][0]["name"] == "Colosseum"
    assert SECRET_KEY not in response.text
