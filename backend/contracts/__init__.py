"""FastAPI request and response contracts."""

from .candidates import (
    CandidateItem,
    CandidateResponse,
    FlightItem,
    FlightListResponse,
    FlightQuery,
    OriginItem,
    RejectedCandidateItem,
    RejectionItem,
)
from .recommendations import (
    RankingPreferencesBody,
    RecommendRequest,
    RecommendationResponse,
    RefineRequest,
)

__all__ = [
    "CandidateItem",
    "CandidateResponse",
    "FlightItem",
    "FlightListResponse",
    "FlightQuery",
    "OriginItem",
    "RankingPreferencesBody",
    "RecommendRequest",
    "RecommendationResponse",
    "RefineRequest",
    "RejectedCandidateItem",
    "RejectionItem",
]
