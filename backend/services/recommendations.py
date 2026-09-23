"""Orchestrates parser, Cosmos, ranking and explanations for FastAPI."""

from __future__ import annotations

import asyncio
from dataclasses import fields

from backend.config import MAX_RECOMMENDATION_RESULTS
from backend.contracts import (
    CandidateItem,
    RankingPreferencesBody,
    RecommendRequest,
    RecommendationResponse,
    RefineRequest,
)
from backend.contracts.candidates import FlightQuery, OriginItem
from backend.contracts.flight_dates import FlightDateMetadata
from backend.contracts.recommendations import RecommendationItem
from backend.models.explanation import DestinationExplanation
from backend.models.feedback import RankingIntent
from backend.models.trip_request import TripRequest
from backend.repositories import RepositoryError
from backend.services.candidates import CandidateService
from backend.services.explanations import explain_ranked_trips
from backend.services.feedback import interpret_feedback
from backend.services.hotels import HotelService
from backend.services.llm import (
    LLMClient,
    parse_request,
)
from ranking import (
    RankingCandidate,
    RankingPreferences,
    RankedDestination,
    preferences_from_intents,
    rank_candidates,
)
from ranking.ranking import CRITERIA


class RecommendationService:
    """Josip's recommend/refine pipeline. Weight numbers come from Ivan's policy."""

    def __init__(
        self,
        candidate_service: CandidateService,
        llm_client: LLMClient | None = None,
        hotel_service: HotelService | None = None,
    ) -> None:
        self._candidates = candidate_service
        self._llm_client = llm_client
        self._hotels = hotel_service
        self._explanation_cache: dict[tuple, tuple[str, list]] = {}
        self._explanation_cache_lock: asyncio.Lock | None = None

    async def recommend(self, body: RecommendRequest) -> RecommendationResponse:
        parsed = await parse_request(
            body.text,
            form_fields=body.form_fields,
            llm_client=self._client(),
        )
        if parsed.status != "ready" or parsed.request is None:
            return RecommendationResponse(
                status=parsed.status,
                request=parsed.request,
                preferences=parsed.preferences,
                issues=list(parsed.issues),
                clarification_questions=list(parsed.clarification_questions),
            )
        # A filter refresh carries already-adjusted effective weights. Its
        # repeated weather form value is trip context, not new feedback.
        preserve_preferences = (
            body.preserve_ranking_preferences and body.ranking_preferences is not None
        )
        initial_intents = [] if preserve_preferences else _initial_ranking_intents(parsed.request)
        return await self._search(
            trip=parsed.request,
            preferences=parsed.preferences,
            ranking_preferences=body.ranking_preferences,
            intents=initial_intents,
        )

    async def refine(self, body: RefineRequest) -> RecommendationResponse:
        interpreted = await interpret_feedback(
            body.text,
            body.request,
            llm_client=self._client(),
        )
        if interpreted.status != "ready" or interpreted.updated_request is None:
            return RecommendationResponse(
                status=interpreted.status,
                request=interpreted.request,
                updated_request=interpreted.updated_request,
                intents=list(interpreted.intents),
                changes=list(interpreted.changes),
                issues=list(interpreted.issues),
                clarification_questions=list(interpreted.clarification_questions),
            )
        result = await self._search(
            trip=interpreted.updated_request,
            ranking_preferences=body.ranking_preferences,
            intents=interpreted.intents,
            changes=interpreted.changes,
            reuse_explanations=True,
        )
        result.request = interpreted.request
        result.updated_request = interpreted.updated_request
        return result

    def _client(self) -> LLMClient | None:
        return self._llm_client

    def _cache_lock(self) -> asyncio.Lock:
        if self._explanation_cache_lock is None:
            self._explanation_cache_lock = asyncio.Lock()
        return self._explanation_cache_lock

    async def _search(
        self,
        trip: TripRequest,
        *,
        preferences=None,
        ranking_preferences: RankingPreferencesBody | None = None,
        intents=None,
        changes=None,
        reuse_explanations: bool = False,
    ) -> RecommendationResponse:
        origin, origin_issues, origin_questions = await self._resolve_origin(trip)
        if origin is None:
            return RecommendationResponse(
                status="needs_input",
                request=trip,
                preferences=preferences,
                intents=list(intents or []),
                changes=list(changes or []),
                issues=origin_issues,
                clarification_questions=origin_questions,
            )

        issues = list(origin_issues)
        if trip.currency != "EUR":
            issues.append(
                "Stored flight prices are EUR. The numeric budget was not "
                "applied as a price filter because the request currency is "
                f"{trip.currency}."
            )

        try:
            weights = preferences_from_intents(
                intents or [],
                _ranking_preferences(ranking_preferences),
            )
        except ValueError as error:
            return RecommendationResponse(
                status="error",
                request=trip,
                origin=origin,
                origin_id=origin.id,
                intents=list(intents or []),
                changes=list(changes or []),
                issues=[str(error)],
            )

        prepared = await self._candidates.prepare(
            _flight_query_from_trip(origin.id, trip)
        )
        ranked = rank_candidates(
            [_to_ranking_candidate(item) for item in prepared.candidates],
            weights,
        )
        ranked = ranked[:MAX_RECOMMENDATION_RESULTS]
        # Date distance selects fallback candidates, not recommendation order.
        # Preserve descending score order so explanations assign matching ranks.
        recommendations, explain_issues = await self._explanations_for(
            trip,
            ranked,
            ranking_weights=weights.normalized_weights(),
            reuse_explanations=reuse_explanations,
        )
        dates_by_id = {
            item.destination_id: item.model_dump(include=set(FlightDateMetadata.model_fields))
            for item in prepared.candidates
        }
        recommended_ids = {item.destination_id for item in recommendations}
        recommended_flights = [
            flight for flight in prepared.flights if flight.id in recommended_ids
        ]
        hotel_ids: dict[str, str | None] = {}
        if self._hotels is not None and recommended_flights:
            try:
                hotel_ids = await self._hotels.resolve_destination_ids(recommended_flights)
            except RepositoryError:
                # Hotel enrichment must not prevent an otherwise valid trip search.
                issues.append("Hotel destination lookup is temporarily unavailable.")
        recommendations = [
            RecommendationItem(
                **item.model_dump(),
                **dates_by_id[item.destination_id],
                hotel_destination_id=hotel_ids.get(item.destination_id),
            )
            for item in recommendations
        ]
        issues.extend(explain_issues)
        return RecommendationResponse(
            status="ready",
            request=trip,
            preferences=preferences,
            origin=origin,
            origin_id=origin.id,
            recommendations=recommendations,
            flights=recommended_flights,
            rejected=list(prepared.rejected),
            intents=list(intents or []),
            changes=list(changes or []),
            issues=issues,
            data_source=prepared.data_source,
            flexible_date_fallback_used=prepared.flexible_date_fallback_used,
            exact_match_count=prepared.exact_match_count,
            fallback_count=prepared.fallback_count,
            ranking_preferences=RankingPreferencesBody(
                **{criterion.weight_field: weights.normalized_weights()[criterion.name]
                   for criterion in CRITERIA},
                temperature_direction=weights.temperature_direction,
                sunshine_direction=weights.sunshine_direction,
                precipitation_direction=weights.precipitation_direction,
            ),
        )

    async def _resolve_origin(
        self,
        trip: TripRequest,
    ) -> tuple[OriginItem | None, list[str], list[str]]:
        matches = await self._candidates.find_origins_by_iata(trip.origin)
        if not matches:
            return (
                None,
                [f"No stored origin matched IATA code {trip.origin}."],
                [
                    "Which origin city should we use? Search /api/origins "
                    "and send that city if the IATA code is not in the data."
                ],
            )
        if len(matches) > 1:
            cities = ", ".join(f"{item.city} ({item.id})" for item in matches)
            return (
                None,
                [f"IATA code {trip.origin} matches more than one origin: {cities}."],
                ["Which origin city should we use?"],
            )
        return matches[0], [], []

    async def _explanations_for(
        self,
        trip: TripRequest,
        ranked: list[RankedDestination],
        *,
        ranking_weights: dict[str, float],
        reuse_explanations: bool,
    ) -> tuple[list[DestinationExplanation], list[str]]:
        if not ranked:
            return [], []

        cached_by_id: dict[str, tuple[str, list]] = {}
        missing: list[RankedDestination] = []
        async with self._cache_lock():
            if reuse_explanations:
                for item in ranked:
                    hit = self._explanation_cache.get(
                        _explanation_cache_key(trip, item.destination_id)
                    )
                    if hit is None:
                        missing.append(item)
                    else:
                        cached_by_id[item.destination_id] = hit
            else:
                missing = list(ranked)

        issues: list[str] = []
        generated_by_id: dict[str, DestinationExplanation] = {}
        if missing:
            generated, explain_issues = await _generate_explanations(
                trip,
                missing,
                llm_client=self._client(),
                ranking_weights=ranking_weights,
            )
            issues.extend(explain_issues)
            async with self._cache_lock():
                for item in generated:
                    generated_by_id[item.destination_id] = item
                    if item.summary:
                        _remember(
                            self._explanation_cache,
                            _explanation_cache_key(trip, item.destination_id),
                            (item.summary, list(item.evidence)),
                        )

        explanations: list[DestinationExplanation] = []
        for index, item in enumerate(ranked, start=1):
            generated = generated_by_id.get(item.destination_id)
            if generated is not None:
                explanations.append(generated.model_copy(update={"rank": index}))
                continue
            summary, evidence = cached_by_id[item.destination_id]
            explanations.append(_explanation_from_ranked(item, index, summary, evidence))
        return explanations, issues


def _ranking_preferences(
    body: RankingPreferencesBody | None,
) -> RankingPreferences:
    defaults = RankingPreferences()
    if body is None:
        return defaults
    return RankingPreferences(**{
        field.name: (getattr(defaults, field.name) if getattr(body, field.name) is None
                     else getattr(body, field.name))
        for field in fields(RankingPreferences)
    })


def _initial_ranking_intents(trip: TripRequest) -> list[RankingIntent]:
    """Turn an initial weather preference into the same policy intent as refine."""
    if trip.weather_preference == "warm":
        return [
            RankingIntent(
                code="prefer_warmer",
                target="ranking_preferences",
                ranking_field="weather_weight",
                meaning="Prefer warmer options in the initial ranking.",
            )
        ]
    if trip.weather_preference == "cool":
        return [
            RankingIntent(
                code="prefer_cooler",
                target="ranking_preferences",
                ranking_field="weather_weight",
                meaning="Prefer cooler options in the initial ranking.",
            )
        ]
    return []


def _flight_query_from_trip(origin_id: str, trip: TripRequest) -> FlightQuery:
    return FlightQuery(
        origin_id=origin_id,
        departure_date=trip.departure_date,
        return_date=trip.return_date,
        max_price_eur=trip.budget if trip.currency == "EUR" else None,
        max_changeovers=0 if trip.direct_flights_only else None,
    )


def _to_ranking_candidate(item: CandidateItem) -> RankingCandidate:
    values = item.model_dump()
    return RankingCandidate(
        **{field.name: values[field.name] for field in fields(RankingCandidate)}
    )


async def _generate_explanations(
    trip: TripRequest,
    ranked: list[RankedDestination],
    *,
    llm_client: LLMClient | None,
    ranking_weights: dict[str, float],
) -> tuple[list[DestinationExplanation], list[str]]:
    if not ranked:
        return [], []

    explained = await explain_ranked_trips(
        trip,
        ranked,
        llm_client=llm_client,
        ranking_weights=ranking_weights,
    )
    if explained.status == "ok":
        return list(explained.explanations), list(explained.issues)
    return _ranked_without_explanations(ranked), list(explained.issues)


def _explanation_cache_key(trip: TripRequest, destination_id: str) -> tuple:
    return (
        destination_id,
        trip.origin,
        str(trip.departure_date),
        str(trip.return_date),
        trip.budget,
        trip.currency,
        tuple(trip.moods),
    )


def _remember(cache: dict, key, value) -> None:
    if key in cache:
        cache.pop(key)
    elif len(cache) >= 64:
        cache.pop(next(iter(cache)))
    cache[key] = value


def _explanation_from_ranked(
    item: RankedDestination,
    rank: int,
    summary: str,
    evidence: list,
    issues: list[str] | None = None,
) -> DestinationExplanation:
    return DestinationExplanation(
        destination_id=item.destination_id,
        destination_iata=item.destination_iata,
        city=item.city,
        rank=rank,
        price_eur=item.price_eur,
        changeover_count=item.changeover_count,
        flight_duration_minutes=item.flight_duration_minutes,
        average_max_temperature_c=item.average_max_temperature_c,
        price_score=item.price_score,
        weather_score=item.weather_score,
        stops_score=item.stops_score,
        duration_score=item.duration_score,
        final_score=item.final_score,
        precipitation_score=item.precipitation_score,
        sunshine_score=item.sunshine_score,
        temperature_direction=item.temperature_direction,
        summary=summary,
        evidence=evidence,
        issues=list(issues or []),
    )


def _ranked_without_explanations(
    ranked: list[RankedDestination],
) -> list[DestinationExplanation]:
    return [
        _explanation_from_ranked(
            item,
            index,
            "",
            [],
            ["Explanation was unavailable."],
        )
        for index, item in enumerate(ranked, start=1)
    ]
