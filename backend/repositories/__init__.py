"""Persistence adapters."""

from .cosmos import (
    CosmosDestinationRepository,
    RepositoryConflictError,
    RepositoryError,
    RepositoryNotFoundError,
)

__all__ = [
    "CosmosDestinationRepository",
    "RepositoryConflictError",
    "RepositoryError",
    "RepositoryNotFoundError",
]
