"""Deterministic scoring of validated RankingCandidate objects.

Custom preferences: rank_candidates(candidates, RankingPreferences(
    price_weight=0.8, weather_weight=0.1,
    changeovers_weight=0.05, duration_weight=0.05)).
Weights are normalized to sum to 1. Ties retain input order.
"""

import math
from collections.abc import Iterable
from dataclasses import dataclass, replace
from typing import Literal

from .interface import RankedDestination, RankingCandidate


ScoringDirection = Literal["lower_is_better", "higher_is_better"]


@dataclass(frozen=True, slots=True)
class CriterionConfig:
    """Independent source, importance field, score field, and default direction."""

    name: str
    source_field: str
    weight_field: str
    score_field: str
    direction: ScoringDirection


# Keep weather/stops keys for existing dictionary and explanation consumers.
CRITERIA = (
    CriterionConfig("price", "price_eur", "price_weight", "price_score", "lower_is_better"),
    CriterionConfig("weather", "average_max_temperature_c", "weather_weight", "weather_score", "higher_is_better"),
    CriterionConfig("precipitation", "precipitation_probability_percent", "precipitation_weight", "precipitation_score", "lower_is_better"),
    CriterionConfig("sunshine", "sunshine_hours", "sunshine_weight", "sunshine_score", "higher_is_better"),
    CriterionConfig("stops", "changeover_count", "changeovers_weight", "stops_score", "lower_is_better"),
    CriterionConfig("duration", "flight_duration_minutes", "duration_weight", "duration_score", "lower_is_better"),
)
DEFAULT_WEIGHTS = {
    "price": 0.25, "weather": 0.20, "precipitation": 0.10,
    "sunshine": 0.10, "stops": 0.20, "duration": 0.15,
}


def is_finite_number(value):
    """Reject missing values, strings, booleans, NaN and infinity."""
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


def normalize_scores(values, lower_is_better=False):
    """Min-max known values; equal known values score 1, missing values score 0."""
    if not values:
        return []
    known = [value for value in values if value is not None]
    if not known:
        return [0.0] * len(values)
    minimum, maximum = min(known), max(known)
    if minimum == maximum:
        return [1.0 if value is not None else 0.0 for value in values]
    scores = [(value - minimum) / (maximum - minimum) for value in known]
    normalized = iter([1.0 - score for score in scores] if lower_is_better else scores)
    return [next(normalized) if value is not None else 0.0 for value in values]


def prepare_weights(weights=None):
    """Merge preference overrides with defaults and normalize their total."""
    result = DEFAULT_WEIGHTS.copy()
    if weights is not None:
        if not isinstance(weights, dict) or set(weights) - set(result):
            raise ValueError(f"Weights must be a dictionary using {', '.join(DEFAULT_WEIGHTS)}.")
        result.update(weights)
    if any(not is_finite_number(value) or value < 0 for value in result.values()):
        raise ValueError("Weights must be finite, non-negative numbers.")
    total = sum(result.values())
    if not is_finite_number(total) or total <= 0:
        raise ValueError("Weights must have a finite, positive total.")
    return {name: value / total for name, value in result.items()}


@dataclass(frozen=True, slots=True)
class RankingPreferences:
    """Six relative weights plus temperature direction, independent of importance.

    Original four positional fields remain compatible. Omitted new weights use
    their defaults and all six normalize together. Weather means temperature.
    """

    price_weight: float = 0.25
    weather_weight: float = 0.20
    changeovers_weight: float = 0.20
    duration_weight: float = 0.15
    precipitation_weight: float = 0.10
    sunshine_weight: float = 0.10
    temperature_direction: ScoringDirection = "higher_is_better"

    def __post_init__(self) -> None:
        self.normalized_weights()
        if self.temperature_direction not in ("lower_is_better", "higher_is_better"):
            raise ValueError("Invalid temperature scoring direction.")

    def normalized_weights(self) -> dict[str, float]:
        """Validate and normalize without changing supplied preferences."""
        return prepare_weights({
            criterion.name: getattr(self, criterion.weight_field)
            for criterion in CRITERIA
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
    preferences = preferences or RankingPreferences()
    weights = preferences.normalized_weights()
    candidates = tuple(candidates)
    criteria = tuple(
        replace(criterion, direction=preferences.temperature_direction)
        if criterion.name == "weather" else criterion
        for criterion in CRITERIA
    )
    component_scores = {
        criterion.name: normalize_scores(
            [getattr(candidate, criterion.source_field) for candidate in candidates],
            criterion.direction == "lower_is_better",
        )
        for criterion in criteria
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
            **{criterion.score_field: scores[criterion.name] for criterion in criteria},
            temperature_direction=preferences.temperature_direction,
            final_score=calculate_final_score(scores, weights),
        ))
    return sorted(destinations, key=lambda item: item.final_score, reverse=True)


def rank_destinations(
    candidates: Iterable[RankingCandidate], weights: dict[str, float] | None = None,
) -> list[RankedDestination]:
    """Compatibility wrapper for dictionary weight overrides."""
    normalized = prepare_weights(weights)
    return rank_candidates(candidates, RankingPreferences(
        **{criterion.weight_field: normalized[criterion.name] for criterion in CRITERIA},
    ))
