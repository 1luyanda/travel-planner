"""FastAPI application entry point."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

from backend.api import auth_router, router
from backend.config import get_settings
from backend.data import DestinationDataService
from backend.repositories import CosmosDestinationRepository
from backend.services import (
    CandidateService,
    HotelService,
    RecommendationService,
    SavedActivitiesService,
    SavedFlightsService,
    UserService,
)
from backend.services.llm import LLMConfigurationError, create_llm_client_from_env


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Create and close process-wide database dependencies."""

    settings = get_settings()
    repository = CosmosDestinationRepository(settings)
    await repository.connect()
    llm_client = None
    try:
        llm_client = create_llm_client_from_env()
    except LLMConfigurationError:
        llm_client = None
    app.state.llm_client = llm_client
    app.state.candidate_service = CandidateService(
        data_service=DestinationDataService(repository)
    )
    app.state.hotel_service = HotelService(repository)
    app.state.recommendation_service = RecommendationService(
        candidate_service=app.state.candidate_service,
        hotel_service=app.state.hotel_service,
        llm_client=llm_client,
    )
    app.state.user_service = UserService(
        repository,
        identity_secret=settings.auth_session_secret or settings.api_auth_key or "",
    )
    app.state.saved_flights_service = SavedFlightsService(repository)
    app.state.saved_activities_service = SavedActivitiesService(repository)
    try:
        yield
    finally:
        try:
            if llm_client is not None:
                await llm_client.aclose()
        finally:
            await repository.close()


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(
        title="Travel Planner API",
        version="0.1.0",
        lifespan=lifespan,
        docs_url=None if settings.app_environment == "production" else "/docs",
        redoc_url=None if settings.app_environment == "production" else "/redoc",
        openapi_url=(
            None
            if settings.app_environment == "production"
            else "/openapi.json"
        ),
    )
    application.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=list(settings.trusted_hosts),
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.frontend_origins),
        allow_credentials=True,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Content-Type", "X-API-Key"],
    )

    @application.middleware("http")
    async def limit_request_size(request, call_next):
        content_length = request.headers.get("content-length")
        if content_length is not None:
            try:
                request_size = int(content_length)
            except ValueError:
                return JSONResponse(
                    status_code=400,
                    content={"detail": "Invalid Content-Length header."},
                )
            if request_size < 0 or request_size > settings.max_request_bytes:
                return JSONResponse(
                    status_code=413,
                    content={"detail": "Request body is too large."},
                )
        return await call_next(request)

    application.include_router(auth_router)
    application.include_router(router)
    return application


app = create_app()
