"""Offline coverage of flexible retrieval, validation, and response metadata."""

import asyncio
from copy import deepcopy
from datetime import date, datetime, timedelta

import pytest

from backend.config import FLEXIBLE_DATE_WINDOW_DAYS, MIN_RECOMMENDATION_RESULTS, Settings
from backend.contracts import FlightQuery, RecommendRequest, RefineRequest
from backend.contracts.candidates import CandidateResponse
from backend.contracts.recommendations import RecommendationResponse
from backend.data import DestinationDataService
from backend.models.trip_request import TripRequest
from backend.repositories import CosmosDestinationRepository
from backend.services import CandidateService, RecommendationService
from tests.fake_llm import FakeLLMClient
from tests.test_integration_boundaries import cosmos_records
from tests.test_recommendations import ZAGREB


DEPARTURE = date(2026, 10, 8)
RETURN = date(2026, 10, 16)


def flight(identifier, departure_delta=0, return_delta=0, **overrides):
    record = {
        **cosmos_records()[0],
        "id": identifier,
        "departure_at": f"{DEPARTURE + timedelta(days=departure_delta)}T23:00:00+02:00",
        "return_at": f"{RETURN + timedelta(days=return_delta)}T05:50:00+02:00",
        "destination_country_code": "IT",
    }
    record.update(overrides)
    return record


def query(**overrides):
    return FlightQuery(**{
        "origin_id": "zagreb-hr", "departure_date": DEPARTURE,
        "return_date": RETURN, "max_price_eur": 100, **overrides,
    })


class FakeRepository:
    source_name = "test://flexible-dates"

    def __init__(self, records):
        self.records = records
        self.requests = []

    async def get_candidates(self, request):
        self.requests.append(request.model_copy(deep=True))
        # Respect the existing exact-date repository contract. Deliberately
        # leave other filters to CandidateService to test fallback guardrails.
        result = self.records
        for field, requested in (("departure_at", request.departure_date),
                                 ("return_at", request.return_date)):
            if requested is not None:
                def matches(record):
                    try:
                        return datetime.fromisoformat(record[field]).date() == requested
                    except (KeyError, TypeError, ValueError):
                        return False
                result = [record for record in result if matches(record)]
        return result

    async def find_origins_by_iata(self, iata):
        return [ZAGREB]


def prepare(records, request=None):
    repository = FakeRepository(records)
    service = CandidateService(DestinationDataService(repository))
    return asyncio.run(service.prepare(request or query())), repository


@pytest.mark.parametrize("exact_count", [0, 1, 2, 3, 4])
def test_fill_only_the_shortfall_and_keep_exact_matches_first(exact_count):
    records = [flight(f"exact-{i}") for i in range(exact_count)] + [
        flight("far", 5, 5), flight("middle", 2, 2), flight("near", 1, 1),
        flight("outside", 8, 0),
    ]
    snapshot = deepcopy(records)
    request = query()
    request_snapshot = request.model_dump()
    result, repository = prepare(records, request)
    needed = max(0, 3 - exact_count)
    assert [item.destination_id for item in result.candidates] == (
        [f"exact-{i}" for i in range(exact_count)] + ["near", "middle", "far"][:needed]
    )
    assert len(repository.requests) == (1 if exact_count >= 3 else 2)
    assert result.exact_match_count == exact_count
    assert result.fallback_count == needed
    assert result.flexible_date_fallback_used == bool(needed)
    assert [item.is_flexible_date_option for item in result.candidates] == (
        [False] * exact_count + [True] * needed
    )
    assert records == snapshot
    assert request.model_dump() == request_snapshot


def test_both_date_distance_and_duration_difference_then_identifier_order():
    result, _ = prepare([
        flight("longer-trip", -1, 1),  # distance 2, duration difference 2
        flight("b-same-duration", 1, 1),  # distance 2, duration difference 0
        flight("a-same-duration", -1, -1),  # same metrics, identifier wins
        flight("nearest", 0, 1),  # distance 1 wins despite duration difference
    ])
    assert [item.destination_id for item in result.candidates] == [
        "nearest", "a-same-duration", "b-same-duration",
    ]


@pytest.mark.parametrize("overrides", [
    {"price_eur": 100.01},
    {"outbound_stops": 1},
    {"return_stops": 1},
    {"duration_minutes": 201},
    {"origin_id": "split-hr"},
    {"destination_country_code": "FR"},
    {"destination_country_code": None},
    {"temp_max_c": 19.9},
    {"temp_max_c": "invalid"},
    {"price_eur": -1},
    {"rain_pct": 101},
])
def test_fallback_preserves_every_hard_filter_and_validation(overrides):
    request = query(max_changeovers=0, max_flight_duration_minutes=200,
                    min_temperature_c=20, destination_country_code="IT")
    result, repository = prepare([
        flight("exact"), flight("valid", 1, 1, price_eur=100, temp_max_c=20,
                               duration_minutes=200, destination_country_code="it"),
        flight("invalid", 0, 1, **overrides),
    ], request)
    assert [item.destination_id for item in result.candidates] == ["exact", "valid"]
    assert result.fallback_count == 1
    assert repository.requests[0] == request
    assert repository.requests[1].model_dump() == {
        **request.model_dump(), "departure_date": None, "return_date": None,
    }


def test_counts_valid_exact_candidates_before_deciding_to_fallback():
    result, repository = prepare([
        flight("exact"), flight("over-budget", price_eur=500),
        flight("invalid", temp_max_c="invalid"), flight("near", 1, 1),
    ])
    assert len(repository.requests) == 2
    assert result.exact_match_count == 1
    assert [item.destination_id for item in result.candidates] == ["exact", "near"]


def test_duplicate_ids_cannot_fill_slots_or_replace_exact_matches():
    result, _ = prepare([
        flight("exact"), flight("exact"), flight("exact", 1, 1, price_eur=1),
        flight("near", 1, 1), flight("near", 1, 1), flight("far", 2, 2),
    ])
    assert [item.destination_id for item in result.candidates] == ["exact", "near", "far"]
    assert result.candidates[0].price_eur == 65
    assert result.exact_match_count == 1


def test_duplicate_versions_keep_nearest_valid_record_and_its_own_metadata():
    records = [
        flight("duplicate", 5, 5, price_eur=90),
        flight("duplicate", 0, 1, price_eur=1000),
        flight("duplicate", -1, -1, price_eur=80),
    ]
    for ordered in (records, list(reversed(records))):
        result, _ = prepare(ordered)
        assert len(result.candidates) == 1
        assert result.candidates[0].price_eur == 80
        assert result.candidates[0].actual_departure_date == DEPARTURE - timedelta(days=1)
        assert result.candidates[0].actual_return_date == RETURN - timedelta(days=1)


@pytest.mark.parametrize("departure_delta,return_delta,allowed", [
    (-7, -7, True), (7, 7, True), (0, 7, True), (-7, 0, True),
    (-8, 0, False), (8, 0, False), (0, -8, False), (0, 8, False),
])
def test_window_is_inclusive_and_applies_to_each_date(departure_delta, return_delta, allowed):
    result, _ = prepare([flight("option", departure_delta, return_delta)])
    assert len(result.candidates) == int(allowed)


@pytest.mark.parametrize("overrides", [
    {"departure_at": "invalid"}, {"return_at": None},
    {"departure_at": "2026-10-15T23:00:00+02:00", "return_at": "2026-10-14T23:00:00+02:00"},
])
def test_unusable_dates_are_not_fallback_options(overrides):
    result, _ = prepare([flight("bad-date", 1, 1, **overrides)])
    assert result.candidates == []
    assert result.flexible_date_fallback_used is False


def test_metadata_preserves_local_dates_across_timezone_offsets():
    result, _ = prepare([
        flight("exact"),
        flight("alternative", departure_at="2026-10-07T00:30:00+14:00",
               return_at="2026-10-15T23:50:00-10:00"),
    ])
    payload = result.model_dump(mode="json")
    assert payload["candidates"][0]["is_flexible_date_option"] is False
    alternative = payload["candidates"][1]
    assert alternative["is_flexible_date_option"] is True
    assert alternative["requested_departure_date"] == "2026-10-08"
    assert alternative["requested_return_date"] == "2026-10-16"
    assert alternative["actual_departure_date"] == "2026-10-07"
    assert alternative["actual_return_date"] == "2026-10-15"
    assert CandidateResponse.model_validate_json(result.model_dump_json()) == result


@pytest.mark.parametrize("count", [0, 1, 2])
def test_short_data_returns_only_available_valid_options(count):
    result, _ = prepare([flight(f"near-{i}", i + 1, i + 1) for i in range(count)])
    assert len(result.candidates) == count
    assert result.fallback_count == count
    assert result.flexible_date_fallback_used == bool(count)


@pytest.mark.parametrize("dates", [
    {"departure_date": None}, {"return_date": None},
    {"departure_date": None, "return_date": None},
])
def test_partial_or_missing_dates_do_not_trigger_fallback(dates):
    result, repository = prepare([flight("exact")], query(**dates))
    assert len(repository.requests) == 1
    assert result.fallback_count == 0


@pytest.mark.parametrize("use_refine", [False, True])
@pytest.mark.parametrize("explanation_available", [False, True])
def test_recommend_and_refine_keep_score_order_and_expose_metadata(use_refine, explanation_available):
    repository = FakeRepository([
        flight("exact", price_eur=95, temp_max_c=15),
        flight("near", 0, 1, price_eur=80),
        flight("far", 2, 2, price_eur=10, temp_max_c=35),
    ])
    responses = [{"direct_flights_only": True}] if use_refine else []
    if explanation_available:
        responses.append({"explanations": [
            {"destination_id": identifier, "evidence_ids": [f"{identifier}::within_budget"]}
            for identifier in ("exact", "near", "far")
        ]})
    service = RecommendationService(CandidateService(DestinationDataService(repository)),
                                    FakeLLMClient(responses))
    trip = TripRequest(origin="ZAG", departure_date=DEPARTURE, return_date=RETURN,
                       budget=100, currency="EUR")
    if use_refine:
        result = asyncio.run(service.refine(RefineRequest(text="Direct flights only", request=trip)))
    else:
        result = asyncio.run(service.recommend(RecommendRequest(form_fields=trip.model_dump(mode="json"))))
    assert result.status == "ready"
    # The best-scoring alternative must lead even though retrieval assembled
    # exact, near, far. The LLM payload also uses that non-score order above.
    assert [item.destination_id for item in result.recommendations] == ["far", "near", "exact"]
    assert [item.rank for item in result.recommendations] == [1, 2, 3]
    scores = [item.final_score for item in result.recommendations]
    assert scores == sorted(scores, reverse=True)
    assert scores[0] > scores[1] > scores[2]
    assert result.exact_match_count == 1
    assert result.fallback_count == 2
    assert result.flexible_date_fallback_used is True
    by_id = {item.destination_id: item for item in result.recommendations}
    assert by_id["exact"].is_flexible_date_option is False
    assert by_id["near"].is_flexible_date_option is True
    assert by_id["far"].is_flexible_date_option is True
    for identifier, departure_delta, return_delta in (("exact", 0, 0), ("near", 0, 1), ("far", 2, 2)):
        item = by_id[identifier]
        assert item.requested_departure_date == DEPARTURE
        assert item.requested_return_date == RETURN
        assert item.actual_departure_date == DEPARTURE + timedelta(days=departure_delta)
        assert item.actual_return_date == RETURN + timedelta(days=return_delta)
    assert bool(result.recommendations[0].summary) == explanation_available
    assert RecommendationResponse.model_validate_json(result.model_dump_json()) == result


def test_repository_exact_sql_and_non_date_filters_are_reused_for_fallback():
    class Container:
        calls = []

        def query_items(self, **kwargs):
            self.calls.append(kwargs)

            async def rows():
                if len(self.calls) == 2:
                    yield flight("near", 1, 1)
            return rows()

    repository = CosmosDestinationRepository(Settings("placeholder", "TravelPlaner", ()))
    container = Container()
    repository._flights = container
    request = query(min_temperature_c=20, destination_country_code="IT", max_changeovers=0)
    result = asyncio.run(CandidateService(DestinationDataService(repository)).prepare(request))
    assert result.fallback_count == 1
    exact, fallback = container.calls
    assert "STARTSWITH(c.departure_at, @departure_date)" in exact["query"]
    assert "STARTSWITH(c.return_at, @return_date)" in exact["query"]
    assert "STARTSWITH" not in fallback["query"]
    for call in container.calls:
        assert call["partition_key"] == "zagreb-hr"
        assert "c.price_eur <= @max_price" in call["query"]
        assert "c.temp_max_c >= @min_temp" in call["query"]
        assert "c.destination_country_code, @country_code" in call["query"]
    assert FLEXIBLE_DATE_WINDOW_DAYS == 7
    assert MIN_RECOMMENDATION_RESULTS == 3
