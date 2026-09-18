"""FastAPI request and response contracts."""

from .activities import ActivitiesRequest, ActivitiesResponse, ActivityItem
from .candidates import (
    CandidateItem,
    CandidateResponse,
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
    "ActivitiesRequest",
    "ActivitiesResponse",
    "ActivityItem",
    "CandidateItem",
    "CandidateResponse",
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
