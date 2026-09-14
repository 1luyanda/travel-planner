"""Ranking behavior tested with shared models, without source files."""

from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone

import pytest

from ranking import RankedDestination, RankingCandidate, rank_destinations
from ranking.ranking import DEFAULT_WEIGHTS, normalize_scores


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
        sunshine_hours=None,
        max_wind_speed_kmh=None,
        airport_distance_km=None,
        flight_retrieved_at=timestamp,
        weather_retrieved_at=timestamp,
    )


def test_price_dominates_other_preferences():
    candidates = [destination("Expensive", 200, 0, 100, 30),
                  destination("Cheap", 50, 2, 300, 10)]
    result = rank_destinations(candidates, {"price": 0.8, "weather": 0.1,
                                            "stops": 0.05, "duration": 0.05})
    assert result[0].city == "Cheap"
    assert result[0].final_score == pytest.approx(0.8)


@pytest.mark.parametrize("field,better,worse,score", [
    ("stops", 0, 2, "stops_score"),
    ("duration", 80, 250, "duration_score"),
    ("temperature", 30, 10, "weather_score"),
])
def test_component_preferences(field, better, worse, score):
    result = rank_destinations([destination("Worse", **{field: worse}),
                                destination("Better", **{field: better})])
    assert result[0].city == "Better"
    assert getattr(result[0], score) == 1.0
    assert getattr(result[1], score) == 0.0


def test_sorted_scores_and_default_weighted_sum():
    result = rank_destinations([destination("Middle", price=100),
                                destination("Worst", price=150),
                                destination("Best", price=50)])
    assert [item.city for item in result] == ["Best", "Middle", "Worst"]
    assert [item.final_score for item in result] == pytest.approx([1, 0.85, 0.7])


def test_preserves_identity_and_supplied_totals_without_mutating_input():
    candidates = [destination("Expensive", price=200),
                  destination("Cheap", price=50, stops=3, duration=575)]
    original = deepcopy(candidates)
    result = rank_destinations(candidates)
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
    assert rank_destinations([]) == []
    assert normalize_scores([5, 5]) == [1.0, 1.0]
    assert normalize_scores([-20, -10, 0]) == [0.0, 0.5, 1.0]
    assert normalize_scores([50, 100, 150], lower_is_better=True) == [1.0, 0.5, 0.0]
    result = rank_destinations([destination("First"), destination("Second")])
    assert [item.city for item in result] == ["First", "Second"]
    assert [item.final_score for item in result] == pytest.approx([1, 1])
    assert rank_destinations([destination()])[0].final_score == pytest.approx(1)
    cold = rank_destinations([destination("Colder", temperature=-20),
                              destination("Warmer", temperature=-10)])
    assert cold[0].city == "Warmer"


def test_ties_are_stable_and_repeated_calls_are_deterministic():
    candidates = [destination("Zulu"), destination("Alpha")]
    result = rank_destinations(candidates)
    assert result == rank_destinations(candidates)
    assert [item.city for item in result] == ["Zulu", "Alpha"]


def test_only_four_mvp_criteria_affect_score():
    candidate = destination()
    other = replace(candidate, trip_duration_days=10,
                    average_min_temperature_c=5, precipitation_probability_percent=90,
                    sunshine_hours=12, max_wind_speed_kmh=50, airport_distance_km=100)
    result = rank_destinations([candidate, other])
    assert result[0].final_score == result[1].final_score


def test_partial_weights_are_normalized_without_mutation():
    weights = {"price": 0.7}
    defaults = DEFAULT_WEIGHTS.copy()
    result = rank_destinations([destination(price=200), destination(price=100)], weights)
    assert result[1].final_score == pytest.approx(0.7 / 1.4)
    assert weights == {"price": 0.7}
    assert DEFAULT_WEIGHTS == defaults


@pytest.mark.parametrize("weights", [
    {"price": -1}, {"price": float("nan")}, {"price": float("inf")},
    {"price": True}, {"unknown": 1},
    {"price": 0, "weather": 0, "stops": 0, "duration": 0},
])
def test_invalid_weights_raise_clear_error(weights):
    with pytest.raises(ValueError, match="Weights"):
        rank_destinations([], weights)
