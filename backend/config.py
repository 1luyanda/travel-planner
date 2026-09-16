"""Environment-backed application configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv


class ConfigurationError(RuntimeError):
    """Raised when required backend configuration is missing."""


@dataclass(frozen=True, slots=True)
class Settings:
    cosmos_connection_string: str
    cosmos_database_name: str
    frontend_origins: tuple[str, ...]


def _optional_environment(name: str) -> str | None:
    value = os.getenv(name, "").strip()
    return value or None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Load the Cosmos connection settings agreed with the data team."""

    load_dotenv()
    connection_string = _optional_environment("COSMOS_CONNECTION_STRING")
    if not connection_string:
        raise ConfigurationError(
            "Set COSMOS_CONNECTION_STRING to the Cosmos PRIMARY CONNECTION "
            "STRING"
        )

    database_name = _optional_environment("COSMOS_DATABASE")
    if not database_name:
        raise ConfigurationError("Set COSMOS_DATABASE (expected: TravelPlaner)")

    origins = _optional_environment("FRONTEND_ORIGINS")
    return Settings(
        cosmos_connection_string=connection_string,
        cosmos_database_name=database_name,
        frontend_origins=tuple(
            origin.strip()
            for origin in (origins or "http://localhost:5173").split(",")
            if origin.strip()
        ),
    )
