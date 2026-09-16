"""Offline policy and real-ranking checks for semantic feedback presets."""

from dataclasses import asdict, replace
from datetime import date

import pytest

from backend.models.feedback import RankingIntent
from backend.models.trip_request import TripRequest
from backend.services.feedback import interpret_feedback
from ranking import (
    RankingCandidate,
    RankingPreferences,
    preferences_from_intents,
    rank_candidates,
)
from tests.fake_llm import FakeLLMClient


@pytest.mark.parametrize("code,expected", [
    ("stronger_price_preference", RankingPreferences(0.50, 0.20, 0.15, 0.15)),
    ("prefer_warmer", RankingPreferences(0.20, 0.50, 0.15, 0.15)),
])
def test_agreed_presets(code, expected):
    actual = preferences_from_intents([code])
    assert actual == expected
    assert actual == preferences_from_intents([code])


@pytest.mark.parametrize("intents", [
    [], ["unknown_intent"], ["direct_flights_only"], ["prefer_cooler"],
    [RankingIntent(code="unknown_intent", target="ranking_preferences", meaning="Unknown")],
])
@pytest.mark.parametrize("current", [None, RankingPreferences(8, 1, 2, 3)])
def test_unrecognized_intents_preserve_current_or_return_defaults(intents, current):
    assert preferences_from_intents(intents, current) == (
        current if current is not None else RankingPreferences()
    )


@pytest.mark.parametrize("target", ["ranking_constraints", "trip_request", "unsupported"])
def test_non_ranking_targets_cannot_apply_a_known_preset(target):
    intent = RankingIntent(
        code="stronger_price_preference", target=target, meaning="Not a preference",
        ranking_field="price_weight",
    )
    current = RankingPreferences(1, 2, 3, 4)
    assert preferences_from_intents([intent], current) == current


def test_multiple_intents_are_equal_normalized_priorities_regardless_of_order():
    codes = ["stronger_price_preference", "prefer_warmer"]
    expected = RankingPreferences(0.35, 0.35, 0.15, 0.15)
    assert preferences_from_intents(codes) == expected
    assert preferences_from_intents(reversed(codes)) == expected
    assert preferences_from_intents(iter(codes * 3 + [codes[0], "unknown"])) == expected


@pytest.mark.parametrize("codes", [
    ["stronger_price_preference"], ["prefer_warmer"],
    ["stronger_price_preference", "prefer_warmer"],
])
def test_recognized_feedback_replaces_current_without_mutation_or_compounding(codes):
    current = RankingPreferences(8, 1, 2, 3)
    before = asdict(current)
    result = preferences_from_intents(codes, current)
    assert result == preferences_from_intents(codes)
    assert preferences_from_intents(codes, result) == result
    assert asdict(current) == before


@pytest.mark.parametrize("codes", [
    [], ["stronger_price_preference"], ["prefer_warmer"],
    ["stronger_price_preference", "prefer_warmer"],
])
def test_policy_weights_are_valid_and_normalized(codes):
    preferences = preferences_from_intents(codes)
    weights = asdict(preferences)
    assert sum(weights.values()) == pytest.approx(1)
    assert all(0 <= weight <= 1 for weight in weights.values())
    assert RankingPreferences(**weights) == preferences
    assert sum(preferences.normalized_weights().values()) == pytest.approx(1)


@pytest.mark.parametrize("text,payload,expected", [
    ("Cheaper", {"stronger_price_preference": True},
     RankingPreferences(0.50, 0.20, 0.15, 0.15)),
    ("Warmer", {"prefer_warmer": True},
     RankingPreferences(0.20, 0.50, 0.15, 0.15)),
    ("Cheaper and warmer", {"stronger_price_preference": True, "prefer_warmer": True},
     RankingPreferences(0.35, 0.35, 0.15, 0.15)),
    ("My budget is now EUR 70", {"budget": 70, "currency": "EUR"},
     RankingPreferences()),
    ("Direct flights only", {"direct_flights_only": True}, RankingPreferences()),
])
def test_existing_feedback_contract_flows_into_policy_without_live_services(text, payload, expected):
    request = TripRequest(
        origin="ZAG", departure_date=date(2026, 9, 21),
        return_date=date(2026, 9, 25), budget=400, currency="EUR",
    )
    feedback = interpret_feedback(text, request, llm_client=FakeLLMClient([payload]))
    assert feedback.status == "ready"
    before = feedback.model_dump()
    assert preferences_from_intents(feedback.intents) == expected
    assert feedback.model_dump() == before


def _candidate(city, price, temperature, stops):
    return RankingCandidate(
        destination_id=city, destination_iata="FCO", city=city,
        price_eur=price, average_max_temperature_c=temperature,
        changeover_count=stops, flight_duration_minutes=200, trip_duration_days=4,
        average_min_temperature_c=None, precipitation_probability_percent=10,
        sunshine_hours=None, max_wind_speed_kmh=None, airport_distance_km=None,
    )


@pytest.mark.parametrize("code,candidates,default_winner,feedback_winner", [
    ("stronger_price_preference",
     [_candidate("Warm", 200, 30, 0), _candidate("Cheap", 50, 10, 2)],
     "Warm", "Cheap"),
    ("prefer_warmer",
     [_candidate("Cheap", 50, 10, 0), _candidate("Warm", 200, 30, 2)],
     "Cheap", "Warm"),
])
def test_feedback_can_change_the_winner(code, candidates, default_winner, feedback_winner):
    default_result = rank_candidates(candidates)
    result = rank_candidates(candidates, preferences_from_intents([code]))
    assert default_result[0].city == default_winner
    assert default_result[0].final_score > default_result[1].final_score
    assert result[0].city == feedback_winner
    assert result[0].final_score > result[1].final_score


def test_unknown_and_hard_constraint_intents_do_not_change_ranking():
    candidate = _candidate("First", 100, 20, 1)
    candidates = [candidate, replace(candidate, city="Second", price_eur=80)]
    current = RankingPreferences(0.50, 0.20, 0.15, 0.15)
    preferences = preferences_from_intents(["unknown", "direct_flights_only"], current)
    assert rank_candidates(candidates, preferences) == rank_candidates(candidates, current)
