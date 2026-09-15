"""Persistence adapters."""

from .cosmos import (
    CosmosDestinationRepository,
    RepositoryError,
    RepositoryNotFoundError,
)

__all__ = [
    "CosmosDestinationRepository",
    "RepositoryError",
    "RepositoryNotFoundError",
]
