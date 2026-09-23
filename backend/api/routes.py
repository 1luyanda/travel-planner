"""Public HTTP endpoints consumed by the React frontend."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import Response

from backend.contracts import (
    ActivitiesRequest,
    ActivitiesResponse,
    NearbyActivitiesRequest,
    NearbyActivitiesResponse,
    CandidateResponse,
    FlightListResponse,
    FlightQuery,
    HotelsResponse,
    OriginItem,
    RecommendRequest,
    RecommendationResponse,
    RefineRequest,
    SaveActivityRequest,
    SavedActivitiesResponse,
    SavedActivityItem,
    SaveFlightRequest,
    SavedFlightItem,
    SavedFlightsResponse,
)
from backend.models.user import UserDocument
from backend.repositories import RepositoryError, RepositoryNotFoundError
from backend.security import require_api_key, require_user
from backend.services import (
    CandidateService,
    HotelService,
    RecommendationService,
    SavedActivitiesService,
    SavedFlightNotFoundError,
    SavedFlightsService,
)
from backend.services.places import (
    PHOTO_NAME_RE,
    PlacesConfigurationError,
    PlacesService,
    PlacesUnavailableError,
)


router = APIRouter(prefix="/api")


def _candidate_service(request: Request) -> CandidateService:
    return request.app.state.candidate_service


def _recommendation_service(request: Request) -> RecommendationService:
    return request.app.state.recommendation_service


def _saved_flights_service(request: Request) -> SavedFlightsService:
    return request.app.state.saved_flights_service


def _saved_activities_service(request: Request) -> SavedActivitiesService:
    return request.app.state.saved_activities_service


def _hotel_service(request: Request) -> HotelService:
    return request.app.state.hotel_service


def _flight_query(
    origin_id: str,
    departure_date: date | None = None,
    return_date: date | None = None,
    max_price: float | None = None,
    min_temp: float | None = None,
    country: str | None = None,
    max_changeovers: int | None = None,
    max_duration_minutes: int | None = None,
    limit: int = 100,
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
        limit=limit,
    )


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get(
    "/origins",
    response_model=list[OriginItem],
    dependencies=[Depends(require_api_key)],
)
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


@router.get(
    "/origins/{origin_id}",
    response_model=OriginItem,
    dependencies=[Depends(require_api_key)],
)
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


@router.get(
    "/flights",
    response_model=FlightListResponse,
    dependencies=[Depends(require_api_key)],
)
async def get_flights(
    request: Request,
    origin_id: str = Query(min_length=3, max_length=150),
    departure_date: date | None = None,
    return_date: date | None = None,
    max_price: float | None = Query(default=None, gt=0, le=1_000_000),
    min_temp: float | None = Query(default=None, ge=-100, le=100),
    country: str | None = Query(default=None, min_length=2, max_length=2),
    limit: int = Query(default=100, ge=1, le=200),
) -> FlightListResponse:
    """Load every Cosmos flight document for one origin partition."""

    query = _flight_query(
        origin_id,
        departure_date,
        return_date,
        max_price,
        min_temp,
        country,
        limit=limit,
    )

    try:
        return await _candidate_service(request).list_flights(query)
    except RepositoryError as error:
        # Do not expose Cosmos credentials or low-level response details.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Destination data is temporarily unavailable.",
        ) from error


@router.get(
    "/candidates",
    response_model=CandidateResponse,
    dependencies=[Depends(require_api_key)],
)
async def get_candidates(
    request: Request,
    origin_id: str = Query(min_length=3, max_length=150),
    departure_date: date | None = None,
    return_date: date | None = None,
    max_price: float | None = Query(default=None, gt=0, le=1_000_000),
    min_temp: float | None = Query(default=None, ge=-100, le=100),
    country: str | None = Query(default=None, min_length=2, max_length=2),
    max_changeovers: int | None = Query(default=None, ge=0, le=20),
    max_duration_minutes: int | None = Query(default=None, gt=0, le=10_080),
    limit: int = Query(default=100, ge=1, le=200),
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
        limit,
    )

    try:
        return await _candidate_service(request).prepare(query)
    except RepositoryError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Destination data is temporarily unavailable.",
        ) from error


@router.post(
    "/recommend",
    response_model=RecommendationResponse,
    dependencies=[Depends(require_api_key)],
)
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


@router.post(
    "/refine",
    response_model=RecommendationResponse,
    dependencies=[Depends(require_api_key)],
)
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


@router.post(
    "/activities",
    response_model=ActivitiesResponse,
    dependencies=[Depends(require_api_key)],
)
async def list_activities(body: ActivitiesRequest) -> ActivitiesResponse:
    """Return verified Google Places activities for a selected destination."""

    try:
        return await PlacesService.from_env().search(body)
    except (PlacesConfigurationError, PlacesUnavailableError) as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Activity data is temporarily unavailable.",
        ) from error


@router.post(
    "/activities/nearby",
    response_model=NearbyActivitiesResponse,
    dependencies=[Depends(require_api_key)],
)
async def list_nearby_activities(body: NearbyActivitiesRequest) -> NearbyActivitiesResponse:
    """Return nearby activities around a city or an explicit coordinate."""

    try:
        return await PlacesService.from_env().search_nearby(body)
    except (PlacesConfigurationError, PlacesUnavailableError) as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Activity data is temporarily unavailable.",
        ) from error


@router.get(
    "/activities/photo",
    dependencies=[Depends(require_api_key)],
)
async def activity_photo(
    name: str = Query(min_length=1, max_length=1200),
    max_height_px: int = Query(default=400, ge=1, le=480),
) -> Response:
    """Stream one Places photo. The image is not stored."""

    if PHOTO_NAME_RE.fullmatch(name) is None:
        raise HTTPException(
            status_code=422,
            detail="Activity photo is unavailable.",
        )
    try:
        content, media_type = await PlacesService.from_env().fetch_photo(
            name,
            max_height_px=max_height_px,
        )
    except (PlacesConfigurationError, PlacesUnavailableError) as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Activity photo is unavailable.",
        ) from error
    return Response(
        content=content,
        media_type=media_type,
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )


@router.get(
    "/hotels",
    response_model=HotelsResponse,
    dependencies=[Depends(require_api_key)],
)
async def get_hotels(
    destination_id: str = Query(min_length=1, max_length=150, pattern=r"^\S+$"),
    limit: int = Query(default=5, ge=1, le=20),
    hotels: HotelService = Depends(_hotel_service),
) -> HotelsResponse:
    """Return stored hotels nearest to the destination centre/reference point."""

    try:
        return await hotels.recommend(destination_id, limit)
    except RepositoryNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        ) from error
    except RepositoryError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Hotel data is temporarily unavailable.",
        ) from error


@router.get(
    "/saved-flights",
    response_model=SavedFlightsResponse,
    dependencies=[Depends(require_api_key)],
)
async def list_saved_flights(
    user: UserDocument = Depends(require_user),
    saved_flights: SavedFlightsService = Depends(_saved_flights_service),
) -> SavedFlightsResponse:
    """Return the authenticated user's saved flights, independent of search filters."""

    try:
        items = await saved_flights.list_for_user(user.id)
    except RepositoryError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Saved flights are temporarily unavailable.",
        ) from error
    return SavedFlightsResponse(items=items)


@router.post(
    "/saved-flights",
    response_model=SavedFlightItem,
    dependencies=[Depends(require_api_key)],
)
async def save_flight(
    body: SaveFlightRequest,
    user: UserDocument = Depends(require_user),
    saved_flights: SavedFlightsService = Depends(_saved_flights_service),
) -> SavedFlightItem:
    """Add a flight ID to the authenticated user's saved list."""

    try:
        return await saved_flights.save(user.id, body)
    except SavedFlightNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        ) from error
    except RepositoryError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Saved flights are temporarily unavailable.",
        ) from error


@router.delete(
    "/saved-flights/{flight_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_api_key)],
)
async def delete_saved_flight(
    flight_id: str,
    user: UserDocument = Depends(require_user),
    saved_flights: SavedFlightsService = Depends(_saved_flights_service),
) -> None:
    """Remove a flight ID from the authenticated user's saved list."""

    try:
        await saved_flights.delete(user.id, flight_id)
    except RepositoryError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Saved flights are temporarily unavailable.",
        ) from error


@router.get(
    "/saved-activities",
    response_model=SavedActivitiesResponse,
    dependencies=[Depends(require_api_key)],
)
async def list_saved_activities(
    user: UserDocument = Depends(require_user),
    saved_activities: SavedActivitiesService = Depends(_saved_activities_service),
) -> SavedActivitiesResponse:
    """Return the authenticated user's liked activities."""

    try:
        items = await saved_activities.list_for_user(user.id)
    except RepositoryError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Saved activities are temporarily unavailable.",
        ) from error
    return SavedActivitiesResponse(items=items)


@router.post(
    "/saved-activities",
    response_model=SavedActivityItem,
    dependencies=[Depends(require_api_key)],
)
async def save_activity(
    body: SaveActivityRequest,
    user: UserDocument = Depends(require_user),
    saved_activities: SavedActivitiesService = Depends(_saved_activities_service),
) -> SavedActivityItem:
    """Add a liked activity to the authenticated user's saved list."""

    try:
        return await saved_activities.save(user.id, body)
    except RepositoryError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Saved activities are temporarily unavailable.",
        ) from error


@router.delete(
    "/saved-activities/{place_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_api_key)],
)
async def delete_saved_activity(
    place_id: str,
    user: UserDocument = Depends(require_user),
    saved_activities: SavedActivitiesService = Depends(_saved_activities_service),
) -> None:
    """Remove a liked activity from the authenticated user's saved list."""

    try:
        await saved_activities.delete(user.id, place_id)
    except RepositoryError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Saved activities are temporarily unavailable.",
        ) from error
