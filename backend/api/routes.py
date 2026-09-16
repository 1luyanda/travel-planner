"""Public HTTP endpoints consumed by the React frontend."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, HTTPException, Query, Request, status

from backend.contracts import (
    CandidateResponse,
    FlightListResponse,
    FlightQuery,
    OriginItem,
    RecommendRequest,
    RecommendationResponse,
    RefineRequest,
)
from backend.repositories import RepositoryError, RepositoryNotFoundError
from backend.services import CandidateService, RecommendationService


router = APIRouter(prefix="/api")


def _candidate_service(request: Request) -> CandidateService:
    return request.app.state.candidate_service


def _recommendation_service(request: Request) -> RecommendationService:
    return request.app.state.recommendation_service


def _flight_query(
    origin_id: str,
    departure_date: date | None = None,
    return_date: date | None = None,
    max_price: float | None = None,
    min_temp: float | None = None,
    country: str | None = None,
    max_changeovers: int | None = None,
    max_duration_minutes: int | None = None,
) -> FlightQuery:
    return FlightQuery(
        origin_id=origin_id,
        departure_date=departure_date,
        return_date=return_date,
        max_price_eur=max_price,
        min_temperature_c=min_temp,
        destination_country_code=country,
        max_changeovers=max_changeovers,
        max_flight_duration_minutes=max_duration_minutes,
    )


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/origins", response_model=list[OriginItem])
async def search_origins(
    request: Request,
    q: str = Query(min_length=1, max_length=100),
    country: str | None = Query(default=None, max_length=100),
) -> list[OriginItem]:
    """Autocomplete origin cities, optionally restricted by country."""

    try:
        return await _candidate_service(request).search_origins(q, country)
    except RepositoryError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Origin data is temporarily unavailable.",
        ) from error


@router.get("/origins/{origin_id}", response_model=OriginItem)
async def get_origin(origin_id: str, request: Request) -> OriginItem:
    """Point-read one origin by its city/country identifier."""

    try:
        return await _candidate_service(request).get_origin(origin_id.lower())
    except RepositoryNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        ) from error
    except RepositoryError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Origin data is temporarily unavailable.",
        ) from error


@router.get("/flights", response_model=FlightListResponse)
async def get_flights(
    request: Request,
    origin_id: str = Query(min_length=3, max_length=150),
    departure_date: date | None = None,
    return_date: date | None = None,
    max_price: float | None = Query(default=None, gt=0),
    min_temp: float | None = None,
    country: str | None = Query(default=None, min_length=2, max_length=2),
) -> FlightListResponse:
    """Load every Cosmos flight document for one origin partition."""

    query = _flight_query(
        origin_id,
        departure_date,
        return_date,
        max_price,
        min_temp,
        country,
    )

    try:
        return await _candidate_service(request).list_flights(query)
    except RepositoryError as error:
        # Do not expose Cosmos credentials or low-level response details.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Destination data is temporarily unavailable.",
        ) from error


@router.get("/candidates", response_model=CandidateResponse)
async def get_candidates(
    request: Request,
    origin_id: str = Query(min_length=3, max_length=150),
    departure_date: date | None = None,
    return_date: date | None = None,
    max_price: float | None = Query(default=None, gt=0),
    min_temp: float | None = None,
    country: str | None = Query(default=None, min_length=2, max_length=2),
    max_changeovers: int | None = Query(default=None, ge=0),
    max_duration_minutes: int | None = Query(default=None, gt=0),
) -> CandidateResponse:
    """Validate Cosmos flights and return ranking-ready candidates."""

    query = _flight_query(
        origin_id,
        departure_date,
        return_date,
        max_price,
        min_temp,
        country,
        max_changeovers,
        max_duration_minutes,
    )

    try:
        return await _candidate_service(request).prepare(query)
    except RepositoryError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Destination data is temporarily unavailable.",
        ) from error


@router.post("/recommend", response_model=RecommendationResponse)
async def recommend(
    request: Request,
    body: RecommendRequest,
) -> RecommendationResponse:
    """Parse a trip request, rank Cosmos candidates, and explain the shortlist."""

    try:
        return await _recommendation_service(request).recommend(body)
    except RepositoryError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Destination data is temporarily unavailable.",
        ) from error


@router.post("/refine", response_model=RecommendationResponse)
async def refine(
    request: Request,
    body: RefineRequest,
) -> RecommendationResponse:
    """Apply user feedback, then rank and explain again."""

    try:
        return await _recommendation_service(request).refine(body)
    except RepositoryError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Destination data is temporarily unavailable.",
        ) from error
