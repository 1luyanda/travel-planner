"""FastAPI request and response contracts."""

from .activities import (
    ActivitiesRequest,
    ActivitiesResponse,
    ActivityItem,
    ActivityPhoto,
    NearbyActivitiesRequest,
    NearbyActivitiesResponse,
    NearbyActivityItem,
    PhotoAttribution,
    SearchCenter,
)
from .auth import AuthResponse, LoginRequest, RegisterRequest
from .hotels import HotelItem, HotelsResponse
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
from .saved_activities import (
    SaveActivityRequest,
    SavedActivitiesResponse,
    SavedActivityItem,
)
from .saved_flights import (
    SaveFlightRequest,
    SavedEvidenceBody,
    SavedExplanationBody,
    SavedFlightItem,
    SavedFlightsResponse,
)

__all__ = [
    "ActivitiesRequest",
    "ActivitiesResponse",
    "ActivityItem",
    "ActivityPhoto",
    "NearbyActivitiesRequest",
    "NearbyActivitiesResponse",
    "NearbyActivityItem",
    "PhotoAttribution",
    "SearchCenter",
    "AuthResponse",
    "CandidateItem",
    "CandidateResponse",
    "FlightItem",
    "FlightListResponse",
    "FlightQuery",
    "HotelItem",
    "HotelsResponse",
    "OriginItem",
    "RankingPreferencesBody",
    "RecommendRequest",
    "RecommendationResponse",
    "RefineRequest",
    "LoginRequest",
    "RegisterRequest",
    "RejectedCandidateItem",
    "RejectionItem",
    "SaveActivityRequest",
    "SavedActivitiesResponse",
    "SavedActivityItem",
    "SaveFlightRequest",
    "SavedEvidenceBody",
    "SavedExplanationBody",
    "SavedFlightItem",
    "SavedFlightsResponse",
]
