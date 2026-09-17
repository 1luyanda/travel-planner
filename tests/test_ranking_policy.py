"""Offline policy and real-ranking checks for incremental semantic feedback."""

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
    ("stronger_price_preference", RankingPreferences(0.40, 9 / 35, 6 / 35, 6 / 35)),
    ("prefer_warmer", RankingPreferences(9 / 35, 0.40, 6 / 35, 6 / 35)),
])
def test_first_adjustment_increases_target_and_reduces_others_proportionally(code, expected):
    actual = preferences_from_intents([code])
    assert asdict(actual) == pytest.approx(asdict(expected))
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
def test_non_ranking_targets_cannot_apply_a_known_adjustment(target):
    intent = RankingIntent(
        code="stronger_price_preference", target=target, meaning="Not a preference",
        ranking_field="price_weight",
    )
    current = RankingPreferences(1, 2, 3, 4)
    assert preferences_from_intents([intent], current) == current


def test_multiple_intents_adjust_together_regardless_of_order_or_duplicates():
    codes = ["stronger_price_preference", "prefer_warmer"]
    actual = preferences_from_intents(codes)
    assert asdict(actual) == pytest.approx(asdict(RankingPreferences(0.40, 0.40, 0.10, 0.10)))
    assert preferences_from_intents(reversed(codes)) == actual
    assert preferences_from_intents(iter(codes * 3 + [codes[0], "unknown"])) == actual


@pytest.mark.parametrize("codes", [
    ["stronger_price_preference"], ["prefer_warmer"],
    ["stronger_price_preference", "prefer_warmer"],
])
def test_recognized_feedback_adjusts_current_without_mutation(codes):
    current = RankingPreferences(8, 1, 2, 3)
    before = asdict(current)
    result = preferences_from_intents(codes, current)
    assert result != preferences_from_intents(codes)
    assert preferences_from_intents(codes, result) != result
    assert result == preferences_from_intents(codes, current)
    assert preferences_from_intents(codes * 3, current) == result
    assert asdict(current) == before


@pytest.mark.parametrize("codes", [
    [], ["stronger_price_preference"], ["prefer_warmer"],
    ["stronger_price_preference", "prefer_warmer"],
])
def test_policy_weights_are_valid_and_normalized(codes):
    preferences = preferences_from_intents(codes)
    weights = asdict(preferences)
    assert sum(weights.values()) == pytest.approx(1)
    assert all(0.05 <= weight <= 0.70 for weight in weights.values())
    assert RankingPreferences(**weights) == preferences
    assert sum(preferences.normalized_weights().values()) == pytest.approx(1)


@pytest.mark.parametrize("text,payload,expected", [
    ("Cheaper", {"stronger_price_preference": True},
     RankingPreferences(0.40, 9 / 35, 6 / 35, 6 / 35)),
    ("Warmer", {"prefer_warmer": True},
     RankingPreferences(9 / 35, 0.40, 6 / 35, 6 / 35)),
    ("Cheaper and warmer", {"stronger_price_preference": True, "prefer_warmer": True},
     RankingPreferences(0.40, 0.40, 0.10, 0.10)),
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
    assert asdict(preferences_from_intents(feedback.intents)) == pytest.approx(asdict(expected))
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
     [_candidate("Warm", 200, 30, 0), _candidate("Cheap", 50, 10, 1)],
     "Warm", "Cheap"),
    ("prefer_warmer",
     [_candidate("Cheap", 50, 10, 0), _candidate("Warm", 200, 30, 1)],
     "Cheap", "Warm"),
])
def test_feedback_can_change_the_winner(code, candidates, default_winner, feedback_winner):
    candidates = [*candidates, _candidate("Dominated", 200, 10, 3)]
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


@pytest.mark.parametrize("code,field", [
    ("stronger_price_preference", "price_weight"),
    ("prefer_warmer", "weather_weight"),
])
def test_repeated_feedback_increases_incrementally_and_stops_at_cap(code, field):
    current = RankingPreferences()
    for expected in [0.4, 0.5, 0.6, 0.7, 0.7, 0.7]:
        current = preferences_from_intents([code], current)
        assert getattr(current, field) == pytest.approx(expected)
        assert sum(asdict(current).values()) == pytest.approx(1)
        assert all(0.05 <= weight <= 0.70 for weight in asdict(current).values())


def test_floor_is_pinned_and_remaining_donors_preserve_their_ratio():
    current = RankingPreferences(0.3, 0.05, 0.25, 0.4)
    result = preferences_from_intents(["stronger_price_preference"], current)
    assert result.price_weight == pytest.approx(0.4)
    assert result.weather_weight == 0.05
    assert result.changeovers_weight / result.duration_weight == pytest.approx(0.25 / 0.4)
    assert sum(asdict(result).values()) == pytest.approx(1)


def test_multiple_targets_share_limited_donor_capacity():
    current = RankingPreferences(0.5, 0.35, 0.1, 0.05)
    codes = ["stronger_price_preference", "prefer_warmer"]
    result = preferences_from_intents(codes, current)
    assert asdict(result) == pytest.approx(asdict(RankingPreferences(0.525, 0.375, 0.05, 0.05)))
    assert preferences_from_intents(reversed(codes), current) == result
    assert asdict(preferences_from_intents(codes, result)) == pytest.approx(asdict(result))


def test_one_target_at_cap_does_not_block_the_other_target():
    current = RankingPreferences(0.7, 0.1, 0.1, 0.1)
    result = preferences_from_intents(["prefer_warmer", "stronger_price_preference"], current)
    assert asdict(result) == pytest.approx(asdict(RankingPreferences(0.7, 0.2, 0.05, 0.05)))


@pytest.mark.parametrize("current", [
    RankingPreferences(8, 1, 2, 3), RankingPreferences(1, 0, 0, 0),
    RankingPreferences(0, 0, 1, 0), RankingPreferences(0.01, 0.01, 0.28, 0.7),
])
@pytest.mark.parametrize("codes", [
    ["stronger_price_preference"], ["prefer_warmer"],
    ["stronger_price_preference", "prefer_warmer"],
])
def test_legacy_relative_or_zero_weights_are_bounded_on_recognized_feedback(current, codes):
    before = asdict(current)
    for _ in range(10):
        result = preferences_from_intents(codes, current)
        assert sum(asdict(result).values()) == pytest.approx(1)
        assert all(0.05 <= weight <= 0.70 for weight in asdict(result).values())
        assert asdict(current) == before
        current = result
        before = asdict(current)


def test_relative_weights_are_normalized_before_adding_the_step():
    result = preferences_from_intents(["stronger_price_preference"], RankingPreferences(3, 3, 2, 2))
    assert result == preferences_from_intents(["stronger_price_preference"])
