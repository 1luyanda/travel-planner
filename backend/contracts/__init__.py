"""FastAPI request and response contracts."""

from .auth import AuthResponse, LoginRequest, RegisterRequest
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
from .saved_flights import SaveFlightRequest, SavedFlightItem, SavedFlightsResponse

__all__ = [
    "AuthResponse",
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
    "LoginRequest",
    "RegisterRequest",
    "RejectedCandidateItem",
    "RejectionItem",
    "SaveFlightRequest",
    "SavedFlightItem",
    "SavedFlightsResponse",
]
