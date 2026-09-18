"""Retrieves and validates candidate data without ranking or LLM logic."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from backend.config import FLEXIBLE_DATE_WINDOW_DAYS, MIN_RECOMMENDATION_RESULTS
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
    """Cosmos retrieval and validation. Ranking and LLM live in RecommendationService."""

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

    async def find_origins_by_iata(self, iata: str) -> list[OriginItem]:
        return await self._data_service.find_origins_by_iata(iata)

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
        """Retain validated exact matches and fill only a short dated shortlist.

        Reuse the partition-scoped repository query with all non-date filters.
        Window comparisons use each record's local calendar dates, not UTC or
        string ordering. Undated/partially dated searches remain exact-only.
        """
        records = await self._data_service.get_destination_records(request)
        exact = self._prepare_records(records, request)
        exact.exact_match_count = len(exact.candidates)
        if (
            len(exact.candidates) >= MIN_RECOMMENDATION_RESULTS
            or request.departure_date is None
            or request.return_date is None
        ):
            return exact

        nearby_request = request.model_copy(update={"departure_date": None, "return_date": None})
        nearby_records = await self._data_service.get_destination_records(nearby_request)
        nearby_records = [
            record for record in nearby_records
            if _within_date_window(record, request)
        ]
        nearby = self._prepare_records(nearby_records, request, flexible=True)
        seen = {item.destination_id for item in exact.candidates}
        alternatives = [item for item in nearby.candidates if item.destination_id not in seen]
        alternatives.sort(key=lambda item: _date_distance_key(item, request))
        needed = MIN_RECOMMENDATION_RESULTS - len(exact.candidates)
        additions = alternatives[:needed]
        exact.candidates.extend(additions)
        exact.fallback_count = len(additions)
        exact.flexible_date_fallback_used = bool(additions)
        rejected_ids = {item.destination_id for item in exact.rejected} | seen
        exact.rejected.extend(
            item for item in nearby.rejected if item.destination_id not in rejected_ids
        )
        return exact

    def _prepare_records(
        self, records: list[dict[str, Any]], request: FlightQuery, *, flexible: bool = False,
    ) -> CandidateResponse:
        """Share ranking validation and hard constraints between both searches."""
        constraints = RankingConstraints(
            max_price_eur=request.max_price_eur,
            max_changeovers=request.max_changeovers,
            max_flight_duration_minutes=request.max_flight_duration_minutes,
        )
        candidates = []
        rejected = []
        for record in records:
            # Keep each validated candidate paired with its source dates even
            # when duplicate IDs have different dates or invalid versions.
            prepared = prepare_ranking_records([record], constraints)
            rejected.extend(prepared.rejected)
            if not prepared.candidates:
                continue
            candidate = prepared.candidates[0]
            # These constraints are already in the repository query. Recheck
            # alternatives at this boundary as well; ranking has no country
            # or origin fields and must never admit a relaxed fallback.
            if flexible and (
                record.get("origin_id") != request.origin_id
                or (request.destination_country_code and str(
                    record.get("destination_country_code", "")
                ).upper() != request.destination_country_code)
                or (request.min_temperature_c is not None
                    and candidate.average_max_temperature_c < request.min_temperature_c)
            ):
                continue
            item = CandidateItem.model_validate(candidate, from_attributes=True)
            item.is_flexible_date_option = flexible
            item.requested_departure_date = request.departure_date
            item.requested_return_date = request.return_date
            item.actual_departure_date = _local_date(record.get("departure_at"))
            item.actual_return_date = _local_date(record.get("return_at"))
            candidates.append(item)

        candidates.sort(key=(
            (lambda item: _date_distance_key(item, request)) if flexible
            else (lambda item: (item.destination_iata, item.destination_id))
        ))
        unique = {}
        for item in candidates:
            unique.setdefault(item.destination_id, item)
        rejected.sort(key=lambda item: (item.destination_iata or "", item.destination_id or ""))

        # /api/candidates stays unranked. /api/recommend ranks these models.
        return CandidateResponse(
            origin_id=request.origin_id,
            candidates=list(unique.values()),
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
                for item in rejected
            ],
            data_source=self._data_service.source_name,
        )


def _local_date(value: Any) -> date | None:
    """Preserve the calendar date represented by an ISO datetime's offset."""
    if isinstance(value, datetime):
        return value.date()
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value).date()
    except ValueError:
        return None


def _within_date_window(record: dict[str, Any], request: FlightQuery) -> bool:
    if not isinstance(record, dict):
        return False
    departure = _local_date(record.get("departure_at"))
    returning = _local_date(record.get("return_at"))
    if departure is None or returning is None or returning < departure:
        return False
    return (
        abs((departure - request.departure_date).days) <= FLEXIBLE_DATE_WINDOW_DAYS
        and abs((returning - request.return_date).days) <= FLEXIBLE_DATE_WINDOW_DAYS
        and (departure, returning) != (request.departure_date, request.return_date)
    )


def _date_distance_key(item: CandidateItem, request: FlightQuery) -> tuple[int, int, str]:
    departure_delta = abs((item.actual_departure_date - request.departure_date).days)
    return_delta = abs((item.actual_return_date - request.return_date).days)
    actual_days = (item.actual_return_date - item.actual_departure_date).days
    requested_days = (request.return_date - request.departure_date).days
    return departure_delta + return_delta, abs(actual_days - requested_days), item.destination_id
