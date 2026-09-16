"""Tests for recommend/refine orchestration (Josip's FastAPI wiring)."""

from __future__ import annotations

import unittest
from datetime import date
from typing import Any

from backend.contracts import (
    OriginItem,
    RankingPreferencesBody,
    RecommendRequest,
    RefineRequest,
)
from backend.contracts.candidates import FlightQuery
from backend.models.trip_request import TripRequest
from backend.services import CandidateService, RecommendationService
from ranking import (
    RankingConstraints,
    RankingPreferences,
    preferences_from_intents,
    prepare_ranking_records,
    rank_candidates,
)
from tests.fake_llm import FakeLLMClient
from tests.test_integration_boundaries import cosmos_records


ZAGREB = OriginItem(
    id="zagreb-hr",
    city="Zagreb",
    country="Croatia",
    country_code="HR",
    airports=["ZAG"],
    city_iata=["ZAG"],
    flight_count=154,
)
ROME_ID = "ZAG-ROM-2026-09-18"
MALTA_ID = "ZAG-MLA-2026-09-18"
LISBON_ID = "ZAG-LIS-2026-09-18"
COMPLETE_EXTRACTION = {
    "origin_iata": "ZAG",
    "departure_date": "2026-09-21",
    "return_date": "2026-09-25",
    "budget": 400,
    "currency": "EUR",
    "moods": ["relaxing"],
    "weather_preference": "warm",
}


def _trip() -> TripRequest:
    return TripRequest(
        origin="ZAG",
        departure_date=date(2026, 9, 21),
        return_date=date(2026, 9, 25),
        budget=400,
        currency="EUR",
        moods=["relaxing"],
        weather_preference="warm",
    )


def _explain_payload(*destination_ids: str) -> dict[str, Any]:
    ids = destination_ids or (ROME_ID, MALTA_ID, LISBON_ID)
    return {
        "explanations": [
            {
                "destination_id": destination_id,
                "evidence_ids": [f"{destination_id}::within_budget"],
            }
            for destination_id in ids
        ]
    }


def _feedback_payload(**overrides: Any) -> dict[str, Any]:
    values: dict[str, Any] = {
        "stronger_price_preference": False,
        "prefer_warmer": False,
        "prefer_cooler": False,
        "direct_flights_only": None,
        "budget": None,
        "currency": None,
        "weather_preference": None,
        "moods_add": [],
        "unclear": False,
        "clarification_needed": None,
    }
    values.update(overrides)
    return values


class RecordingDataService:
    source_name = "test://recommendations"

    def __init__(self, origins: list[OriginItem] | None = None) -> None:
        self.origins = origins if origins is not None else [ZAGREB]
        self.last_query: FlightQuery | None = None

    async def get_destination_records(self, request: FlightQuery) -> list[dict[str, Any]]:
        self.last_query = request
        if request.origin_id != "zagreb-hr":
            return []
        return cosmos_records()

    async def find_origins_by_iata(self, iata: str) -> list[OriginItem]:
        code = iata.strip().upper()
        return [
            origin
            for origin in self.origins
            if code in {item.upper() for item in origin.city_iata}
            or code in {item.upper() for item in origin.airports}
        ]


def _service(
    responses: list[Any],
    data: RecordingDataService | None = None,
) -> tuple[RecommendationService, RecordingDataService]:
    data_service = data or RecordingDataService()
    service = RecommendationService(
        candidate_service=CandidateService(data_service=data_service),  # type: ignore[arg-type]
        llm_client=FakeLLMClient(responses),
    )
    return service, data_service


class RecommendServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_complete_request_ranks_and_explains(self) -> None:
        service, data = _service([COMPLETE_EXTRACTION, _explain_payload()])
        result = await service.recommend(
            RecommendRequest(
                text="From ZAG, 21–25 September 2026, under EUR 400, somewhere warm."
            )
        )

        self.assertEqual(result.status, "ready")
        self.assertEqual(result.origin_id, "zagreb-hr")
        self.assertEqual(result.origin.city if result.origin else None, "Zagreb")
        self.assertEqual(result.request.origin if result.request else None, "ZAG")
        self.assertGreaterEqual(len(result.recommendations), 3)
        self.assertEqual(result.recommendations[0].city, "Rome")
        self.assertEqual(result.recommendations[0].rank, 1)
        self.assertTrue(result.recommendations[0].summary)
        self.assertEqual(result.intents, [])
        self.assertEqual(data.last_query.origin_id if data.last_query else None, "zagreb-hr")
        self.assertEqual(data.last_query.max_price_eur if data.last_query else None, 400)
        self.assertIsNone(data.last_query.max_changeovers if data.last_query else "missing")

    async def test_incomplete_request_does_not_query_cosmos(self) -> None:
        service, data = _service(
            [{"origin_iata": "ZAG", "moods": ["relaxing"]}]
        )
        result = await service.recommend(
            RecommendRequest(text="I want something relaxing.")
        )

        self.assertEqual(result.status, "needs_input")
        self.assertEqual(result.recommendations, [])
        self.assertTrue(result.clarification_questions)
        self.assertIsNone(data.last_query)

    async def test_unknown_origin_asks_for_clarification(self) -> None:
        service, data = _service(
            [COMPLETE_EXTRACTION],
            RecordingDataService(origins=[]),
        )
        result = await service.recommend(
            RecommendRequest(text="From ZAG, 21–25 September 2026, under EUR 400.")
        )

        self.assertEqual(result.status, "needs_input")
        self.assertTrue(any("ZAG" in issue for issue in result.issues))
        self.assertIsNone(data.last_query)

    async def test_form_direct_flights_maps_to_max_changeovers(self) -> None:
        service, data = _service([_explain_payload()])
        result = await service.recommend(
            RecommendRequest(
                text="",
                form_fields={
                    "origin": "ZAG",
                    "departure_date": "2026-09-21",
                    "return_date": "2026-09-25",
                    "budget": 400,
                    "currency": "EUR",
                    "direct_flights_only": True,
                },
            )
        )

        self.assertEqual(result.status, "ready")
        self.assertEqual(
            data.last_query.max_changeovers if data.last_query else None,
            0,
        )


class RefineServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_cheaper_keeps_budget_and_applies_price_weight_preset(self) -> None:
        service, data = _service(
            [
                _feedback_payload(stronger_price_preference=True),
                _explain_payload(),
            ]
        )
        result = await service.refine(
            RefineRequest(text="Cheaper", request=_trip())
        )
        expected = rank_candidates(
            prepare_ranking_records(
                cosmos_records(),
                RankingConstraints(max_price_eur=400),
            ).candidates,
            preferences_from_intents(["stronger_price_preference"]),
        )
        default = rank_candidates(
            prepare_ranking_records(
                cosmos_records(),
                RankingConstraints(max_price_eur=400),
            ).candidates,
        )

        self.assertEqual(result.status, "ready")
        self.assertEqual(result.updated_request.budget if result.updated_request else None, 400)
        self.assertEqual(
            [item.code for item in result.intents],
            ["stronger_price_preference"],
        )
        self.assertEqual(
            [item.city for item in result.recommendations],
            [item.city for item in expected],
        )
        self.assertEqual(
            [item.final_score for item in result.recommendations],
            [item.final_score for item in expected],
        )
        self.assertNotEqual(
            [item.final_score for item in expected],
            [item.final_score for item in default],
        )
        self.assertEqual(data.last_query.max_price_eur if data.last_query else None, 400)

    async def test_explicit_budget_filters_candidates(self) -> None:
        service, data = _service(
            [
                _feedback_payload(budget=70, currency="EUR"),
                _explain_payload(ROME_ID),
            ]
        )
        result = await service.refine(
            RefineRequest(text="My budget is now EUR 70", request=_trip())
        )

        self.assertEqual(result.status, "ready")
        self.assertEqual(result.updated_request.budget if result.updated_request else None, 70)
        self.assertEqual([item.city for item in result.recommendations], ["Rome"])
        self.assertTrue(result.rejected)
        self.assertEqual(data.last_query.max_price_eur if data.last_query else None, 70)

    async def test_client_weights_apply_when_feedback_has_no_ranking_intent(self) -> None:
        service, data = _service(
            [
                _feedback_payload(direct_flights_only=True),
                _explain_payload(),
            ]
        )
        result = await service.refine(
            RefineRequest(
                text="Direct flights only",
                request=_trip(),
                ranking_preferences=RankingPreferencesBody(price_weight=0.8),
            )
        )
        expected = rank_candidates(
            prepare_ranking_records(
                cosmos_records(),
                RankingConstraints(max_price_eur=400, max_changeovers=0),
            ).candidates,
            _ranking_preferences_for_test(),
        )

        self.assertEqual(result.status, "ready")
        self.assertEqual(result.updated_request.direct_flights_only, True)
        self.assertEqual(data.last_query.max_changeovers if data.last_query else None, 0)
        self.assertEqual(
            [item.final_score for item in result.recommendations],
            [item.final_score for item in expected],
        )


def _ranking_preferences_for_test() -> RankingPreferences:
    defaults = RankingPreferences()
    return RankingPreferences(
        price_weight=0.8,
        weather_weight=defaults.weather_weight,
        changeovers_weight=defaults.changeovers_weight,
        duration_weight=defaults.duration_weight,
    )
