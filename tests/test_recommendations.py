"""Tests for recommend/refine orchestration (Josip's FastAPI wiring)."""

from __future__ import annotations

import unittest
from dataclasses import asdict
from datetime import date
from typing import Any
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.api.routes import router
from backend.contracts import (
    OriginItem,
    RankingPreferencesBody,
    RecommendRequest,
    RefineRequest,
)
from backend.contracts.candidates import FlightQuery
from backend.models.feedback import InterpretFeedbackResult, RankingIntent
from backend.models.trip_request import TripRequest
from backend.security import require_api_key
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


class RankingPreferencesApiTests(unittest.TestCase):
    def test_filter_refreshes_preserve_weights_but_explicit_warmer_refines(self) -> None:
        service, data = _service([
            COMPLETE_EXTRACTION, _explain_payload(),
            _explain_payload(), _explain_payload(), _explain_payload(),
            _feedback_payload(prefer_warmer=True), _explain_payload(),
        ])
        app = FastAPI()
        app.include_router(router)
        app.state.recommendation_service = service
        app.dependency_overrides[require_api_key] = lambda: None
        with TestClient(app) as client:
            result = client.post('/api/recommend', json={
                'text': 'From ZAG, 21-25 September 2026, under EUR 400, somewhere warmer.',
            }).json()
            self.assertEqual(result['status'], 'ready')
            self.assertAlmostEqual(result['ranking_preferences']['weather_weight'], 0.30)
            initial_weights = result['ranking_preferences']
            for changes in (
                {'budget': 300},
                {'direct_flights_only': True},
                {'departure_date': '2026-09-22', 'return_date': '2026-09-26'},
            ):
                with self.subTest(changes=changes):
                    form = {**result['request'], 'weather_preference': 'warmer', **changes}
                    response = client.post('/api/recommend', json={
                        'text': '', 'form_fields': form,
                        'ranking_preferences': result['ranking_preferences'],
                        'preserve_ranking_preferences': True,
                    })
                    self.assertEqual(response.status_code, 200)
                    result = response.json()
                    self.assertEqual(result['status'], 'ready')
                    self.assertEqual(result['intents'], [])
                    self.assertEqual(result['ranking_preferences'], initial_weights)
                    for field, value in changes.items():
                        self.assertEqual(result['request'][field], value)
                    self.assertEqual(data.last_query.max_price_eur, result['request']['budget'])
                    self.assertEqual(data.last_query.max_changeovers, 0 if result['request']['direct_flights_only'] else None)
                    scores = [item['final_score'] for item in result['recommendations']]
                    self.assertEqual(scores, sorted(scores, reverse=True))
            response = client.post('/api/refine', json={
                'text': 'Warmer', 'request': result['request'],
                'ranking_preferences': result['ranking_preferences'],
            })
            self.assertEqual(response.status_code, 200)
            result = response.json()
            self.assertEqual(result['status'], 'ready')
            self.assertAlmostEqual(result['ranking_preferences']['weather_weight'], 0.40)

    def test_all_six_weights_retain_main_validation(self) -> None:
        for field in (
            "price_weight", "weather_weight", "precipitation_weight",
            "sunshine_weight", "changeovers_weight", "duration_weight",
        ):
            for value in (-0.1, 1.1, float("nan"), float("inf")):
                with self.subTest(field=field, value=value):
                    with self.assertRaises(ValidationError):
                        RankingPreferencesBody(**{field: value})

    def test_recommend_then_refine_round_trips_six_weights_and_direction(self) -> None:
        service, _ = _service([
            _explain_payload(),
            _feedback_payload(prefer_cooler=True), _explain_payload(),
            _feedback_payload(prefer_warmer=True), _explain_payload(),
        ])
        app = FastAPI()
        app.include_router(router)
        app.state.recommendation_service = service
        app.dependency_overrides[require_api_key] = lambda: None
        supplied = {
            "price_weight": 0.2, "weather_weight": 0.3,
            "precipitation_weight": 0.15, "sunshine_weight": 0.15,
            "changeovers_weight": 0.1, "duration_weight": 0.1,
            "temperature_direction": "lower_is_better",
        }
        with TestClient(app) as client:
            response = client.post("/api/recommend", json={
                "form_fields": _trip().model_dump(mode="json"),
                "ranking_preferences": supplied,
                "preserve_ranking_preferences": True,
            })
            self.assertEqual(response.status_code, 200)
            result = response.json()
            self.assertEqual(result["status"], "ready")
            self.assertEqual(result["ranking_preferences"], supplied)
            for text, expected_weight, direction in (
                ("Cooler", 0.4, "lower_is_better"),
                ("Warmer", 0.5, "higher_is_better"),
            ):
                response = client.post("/api/refine", json={
                    "text": text,
                    "request": result.get("updated_request") or result["request"],
                    "ranking_preferences": result["ranking_preferences"],
                })
                self.assertEqual(response.status_code, 200)
                result = response.json()
                self.assertEqual(result["status"], "ready")
                weights = result["ranking_preferences"]
                self.assertEqual(set(weights), set(supplied))
                self.assertAlmostEqual(weights["weather_weight"], expected_weight)
                self.assertEqual(weights["temperature_direction"], direction)
                self.assertAlmostEqual(sum(v for k, v in weights.items() if k.endswith("_weight")), 1)
                scores = [item["final_score"] for item in result["recommendations"]]
                self.assertTrue(scores)
                self.assertEqual(scores, sorted(scores, reverse=True))
                self.assertEqual(
                    {item["id"] for item in result["flights"]},
                    {item["destination_id"] for item in result["recommendations"]},
                )


class RecommendServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_preserve_mode_keeps_cool_direction_despite_repeated_warm_context(self) -> None:
        service, _ = _service([COMPLETE_EXTRACTION, _explain_payload()])
        weights = RankingPreferencesBody(**asdict(preferences_from_intents(['prefer_cooler'])))
        result = await service.recommend(RecommendRequest(
            text='Somewhere warm from ZAG', ranking_preferences=weights,
            preserve_ranking_preferences=True,
        ))
        self.assertEqual(result.status, 'ready')
        self.assertEqual(result.ranking_preferences, weights)
        self.assertTrue(all(item.temperature_direction == 'lower_is_better' for item in result.recommendations))

    async def test_legacy_recommend_still_applies_initial_intent_to_supplied_weights(self) -> None:
        for preserve_without_weights in (False, True):
            with self.subTest(preserve_without_weights=preserve_without_weights):
                service, _ = _service([COMPLETE_EXTRACTION, _explain_payload()])
                weights = RankingPreferencesBody(**asdict(preferences_from_intents(['prefer_warmer'])))
                result = await service.recommend(RecommendRequest(
                    text='Somewhere warmer from ZAG',
                    ranking_preferences=None if preserve_without_weights else weights,
                    preserve_ranking_preferences=preserve_without_weights,
                ))
                self.assertEqual(result.status, 'ready')
                self.assertAlmostEqual(result.ranking_preferences.weather_weight, 0.30 if preserve_without_weights else 0.40)

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
        self.assertEqual([intent.code for intent in result.intents], ["prefer_warmer"])
        self.assertAlmostEqual(result.ranking_preferences.weather_weight, 0.30)
        self.assertEqual(
            result.ranking_preferences.temperature_direction,
            "higher_is_better",
        )
        self.assertEqual(data.last_query.origin_id if data.last_query else None, "zagreb-hr")
        self.assertEqual(data.last_query.max_price_eur if data.last_query else None, 400)
        self.assertIsNone(data.last_query.max_changeovers if data.last_query else "missing")
        self.assertEqual(
            {flight.id for flight in result.flights},
            {item.destination_id for item in result.recommendations},
        )
        self.assertTrue(any(flight.destination_city == "Rome" for flight in result.flights))

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
    async def test_cheaper_keeps_budget_and_adjusts_price_weight(self) -> None:
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

    async def test_price_and_weather_feedback_change_order_using_dynamic_weights(self) -> None:
        cases = [
            ("Cheaper", "stronger_price_preference", 1, 0,
             RankingPreferences(0.35, 13 / 75, 13 / 75, 0.13, 13 / 150, 13 / 150),
             [MALTA_ID, ROME_ID, LISBON_ID], [ROME_ID, MALTA_ID, LISBON_ID]),
            ("Warmer", "prefer_warmer", 0, 1,
             RankingPreferences(0.21875, 0.30, 0.175, 0.13125, 0.0875, 0.0875),
             [ROME_ID, MALTA_ID, LISBON_ID], [MALTA_ID, ROME_ID, LISBON_ID]),
        ]
        for text, code, cheap_stops, warm_stops, expected, before, after in cases:
            for supplied in (None, RankingPreferencesBody(**asdict(RankingPreferences()))):
                with self.subTest(text=text, supplied=supplied):
                    records = cosmos_records()
                    records[0].update(price_eur=50, temp_max_c=10, outbound_stops=cheap_stops)
                    records[1].update(price_eur=200, temp_max_c=30, outbound_stops=warm_stops)
                    records[2].update(price_eur=200, temp_max_c=10, outbound_stops=3)
                    data = RecordingDataService()
                    data.get_destination_records = AsyncMock(return_value=records)
                    service, _ = _service(
                        [_feedback_payload(**{code: True}), _explain_payload()],
                        data,
                    )
                    body = RefineRequest(text=text, request=_trip(), ranking_preferences=supplied)
                    snapshot = body.model_dump()
                    default = rank_candidates(prepare_ranking_records(records).candidates)
                    self.assertEqual([item.destination_id for item in default], before)
                    self.assertGreater(default[0].final_score, default[1].final_score)

                    with patch(
                        "backend.services.recommendations.rank_candidates", wraps=rank_candidates,
                    ) as ranking:
                        result = await service.refine(body)

                    self.assertEqual(result.status, "ready")
                    ranking.assert_called_once()
                    for field, weight in asdict(expected).items():
                        if field.endswith("_weight"):
                            self.assertAlmostEqual(getattr(ranking.call_args.args[1], field), weight)
                        else:
                            self.assertEqual(getattr(ranking.call_args.args[1], field), weight)
                    self.assertEqual([item.code for item in result.intents], [code])
                    self.assertEqual([item.destination_id for item in result.recommendations], after)
                    self.assertGreater(
                        result.recommendations[0].final_score,
                        result.recommendations[1].final_score,
                    )
                    self.assertEqual(body.model_dump(), snapshot)

    async def test_repeated_cheaper_refinements_use_supplied_current_state_until_cap(self) -> None:
        service, data = _service([
            response
            for _ in range(6)
            for response in (_feedback_payload(stronger_price_preference=True), _explain_payload())
        ])
        current = RankingPreferences()
        trip = _trip()
        for expected_price in (0.35, 0.45, 0.55, 0.65, 0.7, 0.7):
            # The service is stateless: the caller supplies current preferences.
            body = RefineRequest(
                text="Cheaper", request=trip,
                ranking_preferences=RankingPreferencesBody(**asdict(current)),
            )
            snapshot = body.model_dump()
            with patch(
                "backend.services.recommendations.rank_candidates", wraps=rank_candidates,
            ) as ranking:
                result = await service.refine(body)
            self.assertEqual(result.status, "ready")
            ranking.assert_called_once()
            current = ranking.call_args.args[1]
            self.assertAlmostEqual(current.price_weight, expected_price)
            self.assertAlmostEqual(sum(value for field, value in asdict(current).items() if field.endswith("_weight")), 1)
            self.assertTrue(all(0.05 <= weight <= 0.70 for field, weight in asdict(current).items() if field.endswith("_weight")))
            self.assertEqual(data.last_query.max_price_eur, 400)
            self.assertEqual(body.model_dump(), snapshot)
            trip = result.updated_request

    async def test_ranking_intent_and_hard_constraints_can_apply_together(self) -> None:
        service, data = _service([
            _feedback_payload(stronger_price_preference=True, budget=70, currency="EUR",
                              direct_flights_only=True),
            _explain_payload(ROME_ID),
        ])
        with patch(
            "backend.services.recommendations.rank_candidates", wraps=rank_candidates,
        ) as ranking:
            result = await service.refine(RefineRequest(
                text="Cheaper, my budget is now EUR 70, direct flights only", request=_trip(),
                ranking_preferences=RankingPreferencesBody(
                    price_weight=0.4, weather_weight=0.3,
                    changeovers_weight=0.2, duration_weight=0.1,
                ),
            ))
        self.assertEqual(result.status, "ready")
        self.assertAlmostEqual(ranking.call_args.args[1].price_weight, 0.4 / 1.2 + 0.1)
        self.assertEqual(data.last_query.max_price_eur, 70)
        self.assertEqual(data.last_query.max_changeovers, 0)
        self.assertEqual([item.destination_id for item in result.recommendations], [ROME_ID])

    async def test_colder_direction_and_six_weights_round_trip_through_refinement(self) -> None:
        records = cosmos_records()
        for record, temperature in zip(records, (10, 30, 20)):
            record.update(price_eur=60, temp_max_c=temperature)
        data = RecordingDataService()
        data.get_destination_records = AsyncMock(return_value=records)
        explanation = {"explanations": [
            {"destination_id": identifier, "evidence_ids": [
                f"{identifier}::relative_weather_score",
                f"{identifier}::cool_preference_ranking_note",
            ]} for identifier in (ROME_ID, MALTA_ID, LISBON_ID)
        ]}
        service, _ = _service([
            _feedback_payload(prefer_cooler=True), explanation,
            _feedback_payload(direct_flights_only=True), explanation,
        ], data)
        first = await service.refine(RefineRequest(text="Colder", request=_trip()))
        self.assertEqual(first.status, "ready")
        self.assertEqual(first.recommendations[0].destination_id, ROME_ID)
        self.assertEqual(first.ranking_preferences.temperature_direction, "lower_is_better")
        self.assertAlmostEqual(first.ranking_preferences.weather_weight, 0.30)
        self.assertIn("lower maximum temperature", first.recommendations[0].summary)
        self.assertNotIn("higher maximum temperature", first.recommendations[0].summary)
        for item in first.recommendations:
            self.assertEqual(item.precipitation_score, 1)
            self.assertEqual(item.sunshine_score, 1)
            self.assertEqual(item.temperature_direction, "lower_is_better")
        serialized = first.model_dump(mode="json")
        second = await service.refine(RefineRequest(
            text="Direct flights only", request=first.updated_request,
            ranking_preferences=RankingPreferencesBody(**serialized["ranking_preferences"]),
        ))
        self.assertEqual(second.ranking_preferences, first.ranking_preferences)
        self.assertEqual([item.final_score for item in second.recommendations],
                         [item.final_score for item in first.recommendations])
        self.assertEqual(data.get_destination_records.call_args.args[0].max_changeovers, 0)

    async def test_colder_and_old_four_weight_body_preserve_hard_filters(self) -> None:
        service, data = _service([
            _feedback_payload(prefer_cooler=True, direct_flights_only=True, budget=70, currency="EUR"),
            _explain_payload(ROME_ID),
        ])
        body = RefineRequest(
            text="Colder, direct flights only, my budget is now EUR 70", request=_trip(),
            ranking_preferences=RankingPreferencesBody(
                price_weight=0.3, weather_weight=0.3, changeovers_weight=0.2, duration_weight=0.2,
            ),
        )
        snapshot = body.model_dump()
        result = await service.refine(body)
        self.assertEqual(result.status, "ready")
        self.assertEqual(data.last_query.max_price_eur, 70)
        self.assertEqual(data.last_query.max_changeovers, 0)
        self.assertEqual([item.destination_id for item in result.recommendations], [ROME_ID])
        self.assertEqual(result.ranking_preferences.temperature_direction, "lower_is_better")
        self.assertAlmostEqual(result.ranking_preferences.weather_weight, 0.3 / 1.2 + 0.1)
        self.assertEqual(result.updated_request.budget, 70)
        self.assertEqual(body.model_dump(), snapshot)

    async def test_new_scores_survive_when_explanation_is_unavailable(self) -> None:
        service, _ = _service([_feedback_payload(prefer_cooler=True)])
        result = await service.refine(RefineRequest(text="Colder", request=_trip()))
        self.assertEqual(result.status, "ready")
        self.assertTrue(result.recommendations)
        for item in result.recommendations:
            self.assertEqual(item.precipitation_score, 1)
            self.assertEqual(item.sunshine_score, 1)
            self.assertEqual(item.temperature_direction, "lower_is_better")
            self.assertEqual(item.summary, "")

    async def test_constraint_only_feedback_preserves_default_or_supplied_weights(self) -> None:
        cases = [
            ("My budget is now EUR 70", _feedback_payload(budget=70, currency="EUR"), 70, None),
            ("Direct flights only", _feedback_payload(direct_flights_only=True), 400, 0),
        ]
        for text, payload, budget, changeovers in cases:
            for supplied in (None, RankingPreferencesBody(price_weight=0.8)):
                with self.subTest(text=text, supplied=supplied):
                    service, data = _service([payload, _explain_payload()])
                    body = RefineRequest(text=text, request=_trip(), ranking_preferences=supplied)
                    snapshot = body.model_dump()
                    with patch(
                        "backend.services.recommendations.rank_candidates", wraps=rank_candidates,
                    ) as ranking:
                        result = await service.refine(body)

                    self.assertEqual(result.status, "ready")
                    ranking.assert_called_once()
                    self.assertEqual(
                        ranking.call_args.args[1],
                        RankingPreferences() if supplied is None else _ranking_preferences_for_test(),
                    )
                    self.assertEqual(data.last_query.max_price_eur, budget)
                    self.assertEqual(data.last_query.max_changeovers, changeovers)
                    self.assertFalse(any(item.target == "ranking_preferences" for item in result.intents))
                    self.assertEqual(body.model_dump(), snapshot)

    async def test_unknown_ranking_intent_preserves_supplied_preferences(self) -> None:
        trip = _trip()
        interpreted = InterpretFeedbackResult(
            status="ready", request=trip, updated_request=trip.model_copy(deep=True),
            intents=[RankingIntent(code="unknown_intent", target="ranking_preferences", meaning="Unknown")],
        )
        service, _ = _service([_explain_payload()])
        with (
            patch("backend.services.recommendations.interpret_feedback", return_value=interpreted),
            patch("backend.services.recommendations.rank_candidates", wraps=rank_candidates) as ranking,
        ):
            result = await service.refine(RefineRequest(
                text="A future preference", request=trip,
                ranking_preferences=RankingPreferencesBody(price_weight=0.8),
            ))

        self.assertEqual(result.status, "ready")
        ranking.assert_called_once()
        self.assertEqual(ranking.call_args.args[1], _ranking_preferences_for_test())
        self.assertEqual(result.intents, interpreted.intents)

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
