"""FastAPI application entry point."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api import router
from backend.config import get_settings
from backend.data import DestinationDataService
from backend.repositories import CosmosDestinationRepository
from backend.services import CandidateService, RecommendationService


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Create and close process-wide database dependencies."""

    settings = get_settings()
    repository = CosmosDestinationRepository(settings)
    await repository.connect()
    app.state.candidate_service = CandidateService(
        data_service=DestinationDataService(repository)
    )
    app.state.recommendation_service = RecommendationService(
        candidate_service=app.state.candidate_service
    )
    try:
        yield
    finally:
        await repository.close()


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(
        title="Travel Planner API",
        version="0.1.0",
        lifespan=lifespan,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.frontend_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.include_router(router)
    return application


app = create_app()
