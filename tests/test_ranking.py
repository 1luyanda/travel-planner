"""Ranking behavior tested with shared models, without source files."""

from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone

import pytest

from ranking import (RankedDestination, RankingCandidate, RankingPreferences,
                     rank_candidates, rank_destinations)
from ranking.ranking import CRITERIA, DEFAULT_WEIGHTS, normalize_scores


def destination(city="Example", price=100, stops=0, duration=200, temperature=20):
    timestamp = datetime(2026, 9, 11, tzinfo=timezone.utc)
    return RankingCandidate(
        destination_id=f"offer-{city}",
        destination_iata="FCO",
        city=city,
        price_eur=price,
        changeover_count=stops,
        flight_duration_minutes=duration,
        trip_duration_days=4,
        average_max_temperature_c=temperature,
        average_min_temperature_c=None,
        precipitation_probability_percent=10,
        sunshine_hours=8,
        max_wind_speed_kmh=None,
        airport_distance_km=None,
        flight_retrieved_at=timestamp,
        weather_retrieved_at=timestamp,
    )


def test_price_dominates_other_preferences():
    candidates = [destination("Expensive", 200, 0, 100, 30),
                  destination("Cheap", 50, 2, 300, 10)]
    result = rank_candidates(candidates, RankingPreferences(0.8, 0.1, 0.05, 0.05, 0, 0))
    assert result[0].city == "Cheap"
    assert result[0].final_score == pytest.approx(0.8)


@pytest.mark.parametrize("field,better,worse,score", [
    ("stops", 0, 2, "stops_score"),
    ("duration", 80, 250, "duration_score"),
    ("temperature", 30, 10, "weather_score"),
])
def test_component_preferences(field, better, worse, score):
    result = rank_candidates([destination("Worse", **{field: worse}),
                                destination("Better", **{field: better})])
    assert result[0].city == "Better"
    assert getattr(result[0], score) == 1.0
    assert getattr(result[1], score) == 0.0


def test_sorted_scores_and_default_weighted_sum():
    result = rank_candidates([destination("Middle", price=100),
                                destination("Worst", price=150),
                                destination("Best", price=50)])
    assert [item.city for item in result] == ["Best", "Middle", "Worst"]
    assert [item.final_score for item in result] == pytest.approx([1, 0.875, 0.75])


def test_preserves_identity_and_supplied_totals_without_mutating_input():
    candidates = [destination("Expensive", price=200),
                  destination("Cheap", price=50, stops=3, duration=575)]
    original = deepcopy(candidates)
    result = rank_candidates(candidates)
    assert candidates == original
    cheap = next(item for item in result if item.city == "Cheap")
    assert isinstance(cheap, RankedDestination)
    assert cheap.destination_id == candidates[1].destination_id
    assert cheap.destination_iata == candidates[1].destination_iata
    assert cheap.price_eur == 50
    assert cheap.flight_duration_minutes == 575
    assert cheap.changeover_count == 3
    assert cheap.trip_duration_days == 4
    assert cheap.average_max_temperature_c == 20


def test_empty_equal_and_negative_temperature_values():
    assert rank_candidates([]) == []
    assert normalize_scores([5, 5]) == [1.0, 1.0]
    assert normalize_scores([-20, -10, 0]) == [0.0, 0.5, 1.0]
    assert normalize_scores([50, 100, 150], lower_is_better=True) == [1.0, 0.5, 0.0]
    result = rank_candidates([destination("First"), destination("Second")])
    assert [item.city for item in result] == ["First", "Second"]
    assert [item.final_score for item in result] == pytest.approx([1, 1])
    assert rank_candidates([destination()])[0].final_score == pytest.approx(1)
    cold = rank_candidates([destination("Colder", temperature=-20),
                              destination("Warmer", temperature=-10)])
    assert cold[0].city == "Warmer"


def test_ties_are_stable_and_repeated_calls_are_deterministic():
    candidates = [destination("Zulu"), destination("Alpha")]
    result = rank_candidates(candidates)
    assert result == rank_candidates(candidates)
    assert [item.city for item in result] == ["Zulu", "Alpha"]


def test_unscored_fields_do_not_affect_score():
    candidate = destination()
    other = replace(candidate, trip_duration_days=10,
                    average_min_temperature_c=5, max_wind_speed_kmh=50, airport_distance_km=100)
    result = rank_candidates([candidate, other])
    assert result[0].final_score == result[1].final_score


def test_partial_weights_are_normalized_without_mutation():
    weights = {"price": 0.7}
    defaults = DEFAULT_WEIGHTS.copy()
    result = rank_destinations([destination(price=200), destination(price=100)], weights)
    assert result[1].final_score == pytest.approx(0.75 / 1.45)
    assert weights == {"price": 0.7}
    assert DEFAULT_WEIGHTS == defaults


@pytest.mark.parametrize("weights", [
    {"price": -1}, {"price": float("nan")}, {"price": float("inf")},
    {"price": True}, {"unknown": 1},
    {key: 0 for key in DEFAULT_WEIGHTS},
])
def test_invalid_weights_raise_clear_error(weights):
    with pytest.raises(ValueError, match="Weights"):
        rank_destinations([], weights)


@pytest.mark.parametrize("field", [
    "price_weight", "weather_weight", "changeovers_weight", "duration_weight",
    "precipitation_weight", "sunshine_weight",
])
@pytest.mark.parametrize("value", [-1, float("nan"), float("inf"), -float("inf"), True])
def test_preferences_reject_invalid_weights(field, value):
    with pytest.raises(ValueError, match="Weights"):
        RankingPreferences(**{field: value})


def test_preferences_require_positive_total():
    with pytest.raises(ValueError, match="positive total"):
        RankingPreferences(0, 0, 0, 0, 0, 0)


def test_preferences_change_winner_and_normalize_for_iterables():
    candidates = (destination("Cheap", price=50, temperature=10),
                  destination("Warm", price=200, temperature=30))
    preferences = RankingPreferences(8, 1, 0, 0, 0, 0)
    original = deepcopy(preferences)
    cheap = rank_candidates(iter(candidates), preferences)
    warm = rank_candidates(candidates, RankingPreferences(1, 8, 0, 0, 0, 0))
    assert cheap[0].city == "Cheap"
    assert cheap[0].final_score == pytest.approx(8 / 9)
    assert warm[0].city == "Warm"
    assert preferences == original
    scaled = rank_candidates(candidates, RankingPreferences(0.8, 0.1, 0, 0, 0, 0))
    assert [item.city for item in cheap] == [item.city for item in scaled]
    assert [item.final_score for item in cheap] == pytest.approx(
        [item.final_score for item in scaled]
    )


def test_six_defaults_and_independent_criterion_directions():
    assert RankingPreferences().normalized_weights() == pytest.approx({
        "price": 0.25, "weather": 0.20, "precipitation": 0.10,
        "sunshine": 0.10, "stops": 0.20, "duration": 0.15,
    })
    assert sum(DEFAULT_WEIGHTS.values()) == pytest.approx(1)
    assert {item.name: item.direction for item in CRITERIA} == {
        "price": "lower_is_better", "weather": "higher_is_better",
        "precipitation": "lower_is_better", "sunshine": "higher_is_better",
        "stops": "lower_is_better", "duration": "lower_is_better",
    }


@pytest.mark.parametrize("field,better,worse,score", [
    ("precipitation_probability_percent", 10, 90, "precipitation_score"),
    ("sunshine_hours", 12, 2, "sunshine_score"),
])
def test_new_weather_criteria_can_change_the_winner(field, better, worse, score):
    candidates = [replace(destination("Worse"), **{field: worse}),
                  replace(destination("Better"), **{field: better})]
    result = rank_candidates(candidates)
    assert result[0].city == "Better"
    assert getattr(result[0], score) == 1
    assert getattr(result[1], score) == 0
    assert result[0].final_score > result[1].final_score
    disabled = RankingPreferences(precipitation_weight=0, sunshine_weight=0)
    tied = rank_candidates(candidates, disabled)
    assert tied[0].final_score == tied[1].final_score


def test_missing_sunshine_scores_zero_without_inventing_raw_values():
    candidates = [replace(destination("Unknown"), sunshine_hours=None),
                  replace(destination("Low"), sunshine_hours=2),
                  replace(destination("High"), sunshine_hours=10)]
    before = deepcopy(candidates)
    results = {item.city: item for item in rank_candidates(candidates)}
    assert results["Unknown"].sunshine_score == 0
    assert results["Low"].sunshine_score == 0
    assert results["High"].sunshine_score == 1
    assert candidates == before
    missing = rank_candidates([candidates[0], replace(candidates[0], city="Also unknown")])
    assert all(item.sunshine_score == 0 for item in missing)
    assert all(item.final_score == pytest.approx(0.9) for item in missing)
    assert normalize_scores([None, 2, 2]) == [0, 1, 1]
    assert normalize_scores([None, 2, 10], lower_is_better=True) == [0, 1, 0]


def test_direction_changes_temperature_winner_with_identical_positive_weights():
    candidates = [destination("Warm", temperature=30), destination("Cold", temperature=-5)]
    warmer = RankingPreferences()
    colder = replace(warmer, temperature_direction="lower_is_better")
    assert warmer.normalized_weights() == colder.normalized_weights()
    assert rank_candidates(candidates, warmer)[0].city == "Warm"
    cold = rank_candidates(candidates, colder)
    assert cold[0].city == "Cold"
    assert cold[0].weather_score == 1
    assert cold[1].weather_score == 0
    assert colder.weather_weight > 0


def test_each_final_score_is_sum_of_six_weighted_components():
    candidates = [destination("One", price=50, stops=2),
                  replace(destination("Two", temperature=30), sunshine_hours=12,
                          precipitation_probability_percent=90)]
    preferences = RankingPreferences(temperature_direction="lower_is_better")
    weights = preferences.normalized_weights()
    for item in rank_candidates(candidates, preferences):
        assert all(0 <= getattr(item, criterion.score_field) <= 1 for criterion in CRITERIA)
        assert item.final_score == pytest.approx(sum(
            getattr(item, criterion.score_field) * weights[criterion.name] for criterion in CRITERIA
        ))


@pytest.mark.parametrize("direction", [None, "cold", "negative", True])
def test_invalid_temperature_direction_is_rejected(direction):
    with pytest.raises(ValueError, match="direction"):
        RankingPreferences(temperature_direction=direction)


def test_old_four_weight_shape_still_normalizes_with_new_defaults():
    preferences = RankingPreferences(0.3, 0.3, 0.2, 0.2)
    weights = preferences.normalized_weights()
    assert weights["price"] == pytest.approx(0.3 / 1.2)
    assert weights["sunshine"] == pytest.approx(0.1 / 1.2)
    assert weights["precipitation"] == pytest.approx(0.1 / 1.2)
    assert sum(weights.values()) == pytest.approx(1)
