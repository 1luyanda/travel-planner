"""Security regression tests for the FastAPI boundary."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request

from backend.config import Settings
from backend.contracts import FlightItem, FlightQuery, OriginItem
from backend.security import require_api_key


def security_settings(**overrides: object) -> Settings:
    values = {
        "cosmos_connection_string": "placeholder",
        "cosmos_database_name": "TravelPlaner",
        "frontend_origins": ("http://localhost:5173",),
        "api_auth_key": "current-test-key",
        "api_auth_key_previous": "previous-test-key",
        "trusted_hosts": ("testserver", "localhost"),
        "app_environment": "test",
    }
    values.update(overrides)
    return Settings(**values)


def request_with_key(value: str | None) -> Request:
    headers = [] if value is None else [(b"x-api-key", value.encode())]
    return Request({"type": "http", "headers": headers})


def test_api_key_accepts_current_and_previous_keys() -> None:
    settings = security_settings()
    with patch("backend.security.get_settings", return_value=settings):
        require_api_key(request_with_key("current-test-key"), "current-test-key")
        require_api_key(request_with_key("previous-test-key"), "previous-test-key")


@pytest.mark.parametrize("provided_key", [None, "", "wrong-key"])
def test_api_key_rejects_missing_or_invalid_keys(provided_key: str | None) -> None:
    settings = security_settings()
    with patch("backend.security.get_settings", return_value=settings):
        with pytest.raises(HTTPException) as raised:
            require_api_key(request_with_key(provided_key), provided_key)

    assert raised.value.status_code == 401


def test_public_models_ignore_internal_cosmos_fields() -> None:
    origin = OriginItem.model_validate(
        {
            "id": "zagreb-hr",
            "city": "Zagreb",
            "country": "Croatia",
            "country_code": "HR",
            "_etag": "internal",
        }
    )
    flight = FlightItem.model_validate(
        {
            "id": "ZAG-ROM-2026-09-18",
            "origin_id": "zagreb-hr",
            "destination_iata": "FCO",
            "_rid": "internal",
        }
    )

    assert "_etag" not in origin.model_dump()
    assert "_rid" not in flight.model_dump()


def test_flight_query_has_a_bounded_result_limit() -> None:
    with pytest.raises(ValueError):
        FlightQuery(origin_id="zagreb-hr", limit=201)


def test_health_is_public_and_data_routes_require_authentication(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import backend.main as main
    import backend.security as security

    settings = security_settings()
    monkeypatch.setattr(main, "get_settings", lambda: settings)
    monkeypatch.setattr(security, "get_settings", lambda: settings)

    async def connect_without_network(self: object) -> None:
        return None

    async def close_without_network(self: object) -> None:
        return None

    monkeypatch.setattr(
        main.CosmosDestinationRepository,
        "connect",
        connect_without_network,
    )
    monkeypatch.setattr(
        main.CosmosDestinationRepository,
        "close",
        close_without_network,
    )

    with TestClient(main.create_app()) as client:
        assert client.get("/api/health").status_code == 200
        response = client.get("/api/origins?q=zag")

    assert response.status_code == 401


def test_cors_allows_configured_origin_and_rejects_other_origins(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import backend.main as main

    settings = security_settings()
    monkeypatch.setattr(main, "get_settings", lambda: settings)

    client = TestClient(main.create_app())
    allowed = client.options(
        "/api/health",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    disallowed = client.options(
        "/api/health",
        headers={
            "Origin": "https://evil.example",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert allowed.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert "access-control-allow-origin" not in disallowed.headers


def test_trusted_hosts_reject_unknown_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import backend.main as main

    settings = security_settings()
    monkeypatch.setattr(main, "get_settings", lambda: settings)

    client = TestClient(main.create_app())
    response = client.get(
        "/api/health",
        headers={"host": "evil.example"},
    )

    assert response.status_code == 400


def test_request_size_limit_returns_413(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import backend.main as main

    settings = security_settings(max_request_bytes=10)
    monkeypatch.setattr(main, "get_settings", lambda: settings)

    client = TestClient(main.create_app())
    response = client.post(
        "/api/recommend",
        content=b"01234567890",
    )

    assert response.status_code == 413
