"""Deterministic scoring of validated RankingCandidate objects.

Custom preferences: rank_candidates(candidates, RankingPreferences(
    price_weight=0.8, weather_weight=0.1,
    changeovers_weight=0.05, duration_weight=0.05)).
Weights are normalized to sum to 1. Ties retain input order.
"""

import math
from collections.abc import Iterable
from dataclasses import dataclass

from .interface import RankedDestination, RankingCandidate


DEFAULT_WEIGHTS = {"price": 0.30, "weather": 0.30, "stops": 0.20, "duration": 0.20}


def is_finite_number(value):
    """Reject missing values, strings, booleans, NaN and infinity."""
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


def normalize_scores(values, lower_is_better=False):
    """Min-max scores in [0, 1]; equal values all receive 1.0."""
    if not values:
        return []
    minimum, maximum = min(values), max(values)
    if minimum == maximum:
        return [1.0] * len(values)
    scores = [(value - minimum) / (maximum - minimum) for value in values]
    return [1.0 - score for score in scores] if lower_is_better else scores


def prepare_weights(weights=None):
    """Merge preference overrides with defaults and normalize their total."""
    result = DEFAULT_WEIGHTS.copy()
    if weights is not None:
        if not isinstance(weights, dict) or set(weights) - set(result):
            raise ValueError("Weights must be a dictionary using price, weather, stops, duration.")
        result.update(weights)
    if any(not is_finite_number(value) or value < 0 for value in result.values()):
        raise ValueError("Weights must be finite, non-negative numbers.")
    total = sum(result.values())
    if not is_finite_number(total) or total <= 0:
        raise ValueError("Weights must have a finite, positive total.")
    return {name: value / total for name, value in result.items()}


@dataclass(frozen=True, slots=True)
class RankingPreferences:
    """Relative weights for the four MVP criteria; freshness is not scored."""

    price_weight: float = 0.30
    weather_weight: float = 0.30
    changeovers_weight: float = 0.20
    duration_weight: float = 0.20

    def __post_init__(self) -> None:
        self.normalized_weights()

    def normalized_weights(self) -> dict[str, float]:
        """Validate and normalize without changing supplied preferences."""
        return prepare_weights({
            "price": self.price_weight,
            "weather": self.weather_weight,
            "stops": self.changeovers_weight,
            "duration": self.duration_weight,
        })


def calculate_final_score(scores: dict[str, float], weights: dict[str, float]) -> float:
    """Combine component scores using prepared weights."""
    return sum(scores[name] * weight for name, weight in weights.items())


def rank_candidates(
    candidates: Iterable[RankingCandidate],
    preferences: RankingPreferences | None = None,
) -> list[RankedDestination]:
    """Score prepared candidates without mutating them or their list.

    Validation and file parsing belong to the data layer. Stops and flight
    duration are already round-trip totals. Ties retain input order.
    """
    weights = (preferences or RankingPreferences()).normalized_weights()
    candidates = tuple(candidates)
    criteria = {
        "price": ("price_eur", True),
        "weather": ("average_max_temperature_c", False),
        "stops": ("changeover_count", True),
        "duration": ("flight_duration_minutes", True),
    }
    component_scores = {
        name: normalize_scores(
            [getattr(candidate, field) for candidate in candidates], lower_is_better
        )
        for name, (field, lower_is_better) in criteria.items()
    }
    destinations = []
    for index, candidate in enumerate(candidates):
        scores = {name: values[index] for name, values in component_scores.items()}
        destinations.append(RankedDestination(
            destination_id=candidate.destination_id,
            destination_iata=candidate.destination_iata,
            city=candidate.city,
            price_eur=candidate.price_eur,
            changeover_count=candidate.changeover_count,
            flight_duration_minutes=candidate.flight_duration_minutes,
            trip_duration_days=candidate.trip_duration_days,
            average_max_temperature_c=candidate.average_max_temperature_c,
            price_score=scores["price"],
            weather_score=scores["weather"],
            stops_score=scores["stops"],
            duration_score=scores["duration"],
            final_score=calculate_final_score(scores, weights),
        ))
    return sorted(destinations, key=lambda item: item.final_score, reverse=True)


def rank_destinations(
    candidates: Iterable[RankingCandidate], weights: dict[str, float] | None = None,
) -> list[RankedDestination]:
    """Compatibility wrapper for dictionary weight overrides."""
    normalized = prepare_weights(weights)
    return rank_candidates(candidates, RankingPreferences(
        price_weight=normalized["price"],
        weather_weight=normalized["weather"],
        changeovers_weight=normalized["stops"],
        duration_weight=normalized["duration"],
    ))
