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


def _weights(preferences):
    return {field: value for field, value in asdict(preferences).items() if field.endswith("_weight")}


@pytest.mark.parametrize("code,expected", [
    ("stronger_price_preference", RankingPreferences(0.35, 13 / 75, 13 / 75, 0.13, 13 / 150, 13 / 150)),
    ("prefer_warmer", RankingPreferences(0.21875, 0.30, 0.175, 0.13125, 0.0875, 0.0875)),
])
def test_first_adjustment_increases_target_and_reduces_others_proportionally(code, expected):
    actual = preferences_from_intents([code])
    assert _weights(actual) == pytest.approx(_weights(expected))
    assert actual == preferences_from_intents([code])


@pytest.mark.parametrize("intents", [
    [], ["unknown_intent"], ["direct_flights_only"], ["not_a_ranking_intent"],
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
    assert _weights(actual) == pytest.approx(_weights(RankingPreferences(0.35, 0.30, 7 / 55, 21 / 220, 7 / 110, 7 / 110)))
    assert preferences_from_intents(reversed(codes)) == actual
    assert preferences_from_intents(iter(codes * 3 + [codes[0], "unknown"])) == actual


@pytest.mark.parametrize("codes", [
    ["stronger_price_preference"], ["prefer_warmer"],
    ["stronger_price_preference", "prefer_warmer"],
])
def test_recognized_feedback_adjusts_current_without_mutation(codes):
    current = RankingPreferences(8, 1, 2, 3)
    before = _weights(current)
    result = preferences_from_intents(codes, current)
    assert result != preferences_from_intents(codes)
    assert preferences_from_intents(codes, result) != result
    assert result == preferences_from_intents(codes, current)
    assert preferences_from_intents(codes * 3, current) == result
    assert _weights(current) == before


@pytest.mark.parametrize("codes", [
    [], ["stronger_price_preference"], ["prefer_warmer"],
    ["stronger_price_preference", "prefer_warmer"],
])
def test_policy_weights_are_valid_and_normalized(codes):
    preferences = preferences_from_intents(codes)
    weights = _weights(preferences)
    assert sum(weights.values()) == pytest.approx(1)
    assert all(0.05 <= weight <= 0.70 for weight in weights.values())
    assert RankingPreferences(**weights) == preferences
    assert sum(preferences.normalized_weights().values()) == pytest.approx(1)


@pytest.mark.parametrize("text,payload,expected", [
    ("Cheaper", {"stronger_price_preference": True},
     RankingPreferences(0.35, 13 / 75, 13 / 75, 0.13, 13 / 150, 13 / 150)),
    ("Warmer", {"prefer_warmer": True},
     RankingPreferences(0.21875, 0.30, 0.175, 0.13125, 0.0875, 0.0875)),
    ("Cheaper and warmer", {"stronger_price_preference": True, "prefer_warmer": True},
     RankingPreferences(0.35, 0.30, 7 / 55, 21 / 220, 7 / 110, 7 / 110)),
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
    assert _weights(preferences_from_intents(feedback.intents)) == pytest.approx(_weights(expected))
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
    for step in range(1, 8):
        expected = min(0.70, getattr(RankingPreferences(), field) + step * 0.10)
        current = preferences_from_intents([code], current)
        assert getattr(current, field) == pytest.approx(expected)
        assert sum(_weights(current).values()) == pytest.approx(1)
        assert all(0.05 <= weight <= 0.70 for weight in _weights(current).values())


def test_floor_is_pinned_and_remaining_donors_preserve_their_ratio():
    current = RankingPreferences(0.3, 0.05, 0.2, 0.35, 0.05, 0.05)
    result = preferences_from_intents(["stronger_price_preference"], current)
    assert result.price_weight == pytest.approx(0.4)
    assert result.weather_weight == 0.05
    assert result.changeovers_weight / result.duration_weight == pytest.approx(0.2 / 0.35)
    assert sum(_weights(result).values()) == pytest.approx(1)


def test_multiple_targets_share_limited_donor_capacity():
    current = RankingPreferences(0.45, 0.3, 0.1, 0.05, 0.05, 0.05)
    codes = ["stronger_price_preference", "prefer_warmer"]
    result = preferences_from_intents(codes, current)
    assert _weights(result) == pytest.approx(_weights(RankingPreferences(0.475, 0.325, 0.05, 0.05, 0.05, 0.05)))
    assert preferences_from_intents(reversed(codes), current) == result
    assert _weights(preferences_from_intents(codes, result)) == pytest.approx(_weights(result))


def test_one_target_at_cap_does_not_block_the_other_target():
    current = RankingPreferences(0.7, 0.05, 0.1, 0.05, 0.05, 0.05)
    result = preferences_from_intents(["prefer_warmer", "stronger_price_preference"], current)
    assert _weights(result) == pytest.approx(_weights(RankingPreferences(0.7, 0.1, 0.05, 0.05, 0.05, 0.05)))


@pytest.mark.parametrize("current", [
    RankingPreferences(8, 1, 2, 3), RankingPreferences(1, 0, 0, 0),
    RankingPreferences(0, 0, 1, 0), RankingPreferences(0.01, 0.01, 0.28, 0.7),
])
@pytest.mark.parametrize("codes", [
    ["stronger_price_preference"], ["prefer_warmer"],
    ["stronger_price_preference", "prefer_warmer"],
])
def test_legacy_relative_or_zero_weights_are_bounded_on_recognized_feedback(current, codes):
    before = _weights(current)
    for _ in range(10):
        result = preferences_from_intents(codes, current)
        assert sum(_weights(result).values()) == pytest.approx(1)
        assert all(0.05 <= weight <= 0.70 for weight in _weights(result).values())
        assert _weights(current) == before
        current = result
        before = _weights(current)


def test_relative_weights_are_normalized_before_adding_the_step():
    result = preferences_from_intents(["stronger_price_preference"], RankingPreferences(2.5, 2, 2, 1.5, 1, 1))
    assert result == preferences_from_intents(["stronger_price_preference"])


@pytest.mark.parametrize("code", ["prefer_colder", "prefer_cooler"])
def test_colder_increases_positive_temperature_importance_incrementally(code):
    current = RankingPreferences()
    for expected in [0.30, 0.40, 0.50, 0.60, 0.70, 0.70]:
        snapshot = asdict(current)
        result = preferences_from_intents([code], current)
        assert result.weather_weight == pytest.approx(expected)
        assert result.temperature_direction == "lower_is_better"
        assert all(0.05 <= weight <= 0.70 for weight in _weights(result).values())
        assert sum(_weights(result).values()) == pytest.approx(1)
        assert asdict(current) == snapshot
        current = result


def test_temperature_aliases_deduplicate_by_criterion():
    result = preferences_from_intents(["prefer_colder", "prefer_cooler"] * 3)
    assert result == preferences_from_intents(["prefer_cooler"])


@pytest.mark.parametrize("direction", ["higher_is_better", "lower_is_better"])
def test_conflicting_temperature_intents_are_order_independent(direction):
    from itertools import permutations

    current = RankingPreferences(temperature_direction=direction)
    codes = ["prefer_warmer", "prefer_colder", "stronger_price_preference"]
    result = preferences_from_intents(codes, current)
    assert result.temperature_direction == direction
    assert result.weather_weight == pytest.approx(0.30)
    assert result.price_weight == pytest.approx(0.35)
    for ordered in permutations(codes):
        assert preferences_from_intents(ordered, current) == result


def test_warmer_switches_back_and_other_feedback_preserves_cold_direction():
    cold = preferences_from_intents(["prefer_colder"])
    assert preferences_from_intents(["unknown"], cold) is cold
    assert preferences_from_intents(["direct_flights_only"], cold) is cold
    assert preferences_from_intents(["stronger_price_preference"], cold).temperature_direction == "lower_is_better"
    warm = preferences_from_intents(["prefer_warmer"], cold)
    assert warm.temperature_direction == "higher_is_better"
    assert warm.weather_weight == pytest.approx(0.40)


def test_real_ranking_winner_changes_when_feedback_switches_to_colder():
    candidates = [_candidate("Cold", 100, -5, 0), _candidate("Warm", 100, 30, 0)]
    warm = preferences_from_intents(["prefer_warmer"])
    cold = preferences_from_intents(["prefer_colder"], warm)
    assert rank_candidates(candidates, warm)[0].city == "Warm"
    assert rank_candidates(candidates, cold)[0].city == "Cold"
