"""Deterministic scoring of validated RankingCandidate objects.

Custom preferences: rank_destinations(candidates, weights={"price": 0.8,
"weather": 0.1, "stops": 0.05, "duration": 0.05}). Partial overrides
are supported; supplied weights replace defaults and are normalized to sum to 1.
"""

import math

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


def calculate_final_score(scores: dict[str, float], weights: dict[str, float]) -> float:
    """Combine component scores using prepared weights."""
    return sum(scores[name] * weight for name, weight in weights.items())


def rank_destinations(
    candidates: list[RankingCandidate], weights: dict[str, float] | None = None,
) -> list[RankedDestination]:
    """Score prepared candidates without mutating them or their list.

    Validation and file parsing belong to the data layer. Stops and flight
    duration are already round-trip totals. Ties retain input order.
    """
    weights = prepare_weights(weights)
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
