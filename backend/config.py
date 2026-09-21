"""Environment-backed application configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv


FLEXIBLE_DATE_WINDOW_DAYS = 7
MIN_RECOMMENDATION_RESULTS = 5
MAX_RECOMMENDATION_RESULTS = 5


class ConfigurationError(RuntimeError):
    """Raised when required backend configuration is missing."""


@dataclass(frozen=True, slots=True)
class Settings:
    cosmos_connection_string: str
    cosmos_database_name: str
    frontend_origins: tuple[str, ...]
    api_auth_key: str | None = None
    api_auth_key_previous: str | None = None
    trusted_hosts: tuple[str, ...] = ("localhost", "127.0.0.1", "testserver")
    app_environment: str = "development"
    max_request_bytes: int = 64 * 1024
    users_container_name: str = "users"
    user_flights_container_name: str = "user-flights"
    auth_session_secret: str | None = None
    auth_cookie_name: str = "travel_planner_session"
    auth_session_ttl_seconds: int = 3600
    auth_cookie_secure: bool = False


def _optional_environment(name: str) -> str | None:
    value = os.getenv(name, "").strip()
    return value or None


def _csv_environment(name: str, default: str) -> tuple[str, ...]:
    raw = os.getenv(name, default)
    return tuple(item.strip() for item in raw.split(",") if item.strip())


def _bool_environment(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ConfigurationError(f"{name} must be a boolean value.")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Load validated application settings from the environment."""

    load_dotenv(override=False)
    app_environment = (
        _optional_environment("APP_ENV") or "development"
    ).lower()
    if app_environment not in {"development", "test", "production"}:
        raise ConfigurationError(
            "APP_ENV must be development, test, or production"
        )

    connection_string = _optional_environment("COSMOS_CONNECTION_STRING")
    if not connection_string:
        raise ConfigurationError(
            "Set COSMOS_CONNECTION_STRING to the Cosmos PRIMARY CONNECTION "
            "STRING"
        )

    database_name = _optional_environment("COSMOS_DATABASE")
    if not database_name:
        raise ConfigurationError("Set COSMOS_DATABASE (expected: TravelPlaner)")

    frontend_origins = _csv_environment(
        "FRONTEND_ORIGINS",
        "http://localhost:5173",
    )
    trusted_hosts = _csv_environment(
        "TRUSTED_HOSTS",
        "localhost,127.0.0.1,testserver",
    )
    api_auth_key = _optional_environment("API_AUTH_KEY")
    api_auth_key_previous = _optional_environment("API_AUTH_KEY_PREVIOUS")
    auth_session_secret = _optional_environment("AUTH_SESSION_SECRET")
    users_container_name = (
        _optional_environment("COSMOS_USERS_CONTAINER") or "users"
    )
    user_flights_container_name = (
        _optional_environment("COSMOS_USER_FLIGHTS_CONTAINER")
        or "user-flights"
    )

    if app_environment == "production":
        if not api_auth_key:
            raise ConfigurationError(
                "Set API_AUTH_KEY in production."
            )
        if not frontend_origins:
            raise ConfigurationError(
                "Set FRONTEND_ORIGINS explicitly in production."
            )
        if not trusted_hosts:
            raise ConfigurationError(
                "Set TRUSTED_HOSTS explicitly in production."
            )
        if not auth_session_secret:
            raise ConfigurationError(
                "Set AUTH_SESSION_SECRET in production."
            )
        if len(auth_session_secret) < 32:
            raise ConfigurationError(
                "AUTH_SESSION_SECRET must contain at least 32 characters."
            )

    max_request_bytes_raw = _optional_environment("MAX_REQUEST_BYTES")
    try:
        max_request_bytes = int(max_request_bytes_raw or 64 * 1024)
    except ValueError as error:
        raise ConfigurationError(
            "MAX_REQUEST_BYTES must be a positive integer."
        ) from error
    if max_request_bytes <= 0:
        raise ConfigurationError("MAX_REQUEST_BYTES must be positive.")

    auth_session_ttl_raw = _optional_environment("AUTH_SESSION_TTL_SECONDS")
    try:
        auth_session_ttl_seconds = int(auth_session_ttl_raw or 3600)
    except ValueError as error:
        raise ConfigurationError(
            "AUTH_SESSION_TTL_SECONDS must be a positive integer."
        ) from error
    if auth_session_ttl_seconds <= 0:
        raise ConfigurationError(
            "AUTH_SESSION_TTL_SECONDS must be positive."
        )

    auth_cookie_secure = _bool_environment(
        "AUTH_COOKIE_SECURE",
        app_environment == "production",
    )
    if app_environment == "production" and not auth_cookie_secure:
        raise ConfigurationError(
            "AUTH_COOKIE_SECURE must be true in production."
        )

    return Settings(
        cosmos_connection_string=connection_string,
        cosmos_database_name=database_name,
        frontend_origins=frontend_origins,
        api_auth_key=api_auth_key,
        api_auth_key_previous=api_auth_key_previous,
        trusted_hosts=trusted_hosts,
        app_environment=app_environment,
        max_request_bytes=max_request_bytes,
        users_container_name=users_container_name,
        user_flights_container_name=user_flights_container_name,
        auth_session_secret=auth_session_secret,
        auth_session_ttl_seconds=auth_session_ttl_seconds,
        auth_cookie_secure=auth_cookie_secure,
    )
