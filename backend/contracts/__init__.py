"""FastAPI request and response contracts."""

from .candidates import (
    CandidateItem,
    CandidateResponse,
    FlightQuery,
    OriginItem,
    RejectedCandidateItem,
    RejectionItem,
)

__all__ = [
    "CandidateItem",
    "CandidateResponse",
    "FlightQuery",
    "OriginItem",
    "RejectedCandidateItem",
    "RejectionItem",
]
