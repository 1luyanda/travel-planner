"""Retrieves and validates candidate data without ranking or LLM logic."""

from __future__ import annotations

from backend.contracts import (
    CandidateItem,
    CandidateResponse,
    FlightListResponse,
    FlightQuery,
    OriginItem,
    RejectedCandidateItem,
    RejectionItem,
)
from backend.data import DestinationDataService
from ranking import RankingConstraints, prepare_ranking_records


class CandidateService:
    """Backend boundary handed to future ranking and agent integrations."""

    def __init__(self, data_service: DestinationDataService) -> None:
        self._data_service = data_service

    async def search_origins(
        self,
        city_query: str,
        country: str | None = None,
    ) -> list[OriginItem]:
        return await self._data_service.search_origins(city_query, country)

    async def get_origin(self, origin_id: str) -> OriginItem:
        return await self._data_service.get_origin(origin_id)

    async def list_flights(self, request: FlightQuery) -> FlightListResponse:
        """Return every Cosmos flight document for the origin partition."""

        flights = await self._data_service.get_destination_records(request)
        return FlightListResponse(
            origin_id=request.origin_id,
            flights=flights,
            count=len(flights),
            data_source=self._data_service.source_name,
        )

    async def prepare(self, request: FlightQuery) -> CandidateResponse:
        records = await self._data_service.get_destination_records(request)
        prepared = prepare_ranking_records(
            records,
            RankingConstraints(
                max_price_eur=request.max_price_eur,
                max_changeovers=request.max_changeovers,
                max_flight_duration_minutes=(
                    request.max_flight_duration_minutes
                ),
            ),
        )

        # Future ranked response integration uses these models directly:
        # ranked = rank_candidates(prepared.candidates, preferences)
        # This endpoint's contract currently returns unranked candidates.
        return CandidateResponse(
            origin_id=request.origin_id,
            candidates=[
                CandidateItem.model_validate(
                    candidate,
                    from_attributes=True,
                )
                for candidate in prepared.candidates
            ],
            rejected=[
                RejectedCandidateItem(
                    destination_id=item.destination_id,
                    destination_iata=item.destination_iata,
                    reasons=[
                        RejectionItem(
                            code=reason.code,
                            message=reason.message,
                        )
                        for reason in item.reasons
                    ],
                )
                for item in prepared.rejected
            ],
            data_source=self._data_service.source_name,
        )
