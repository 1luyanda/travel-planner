"""Deterministic MVP policy from semantic feedback to ranking preferences."""

from __future__ import annotations

from collections.abc import Iterable
from math import fsum, isclose
from typing import TYPE_CHECKING

from .ranking import CRITERIA, RankingPreferences

if TYPE_CHECKING:
    from backend.models.feedback import RankingIntent


_INTENT_CRITERIA = {
    "stronger_price_preference": "price",
    "prefer_warmer": "weather",
    "prefer_cooler": "weather",
    "prefer_colder": "weather",  # Public policy alias for the existing AI code.
    "prefer_more_sunshine": "sunshine",
    "prefer_less_sunshine": "sunshine",
    "prefer_less_rain": "precipitation",
    "prefer_more_rain": "precipitation",
    "prefer_fewer_stops": "stops",
    "stronger_duration_preference": "duration",
}
_ADJUSTMENT_STEP = 0.10
_MIN_WEIGHT = 0.05
_MAX_WEIGHT = 0.70


def _redistribute_weights(
    weights: dict[str, float], total: float = 1.0,
) -> dict[str, float]:
    """Allocate a total proportionally, pinning bounds and redistributing.

    Clamp incoming weights first so legacy zero/out-of-range relative weights
    also have a deterministic, feasible baseline. For an already bounded
    state, ratios are preserved until a criterion hits a bound.
    """
    remaining = {
        field: min(_MAX_WEIGHT, max(_MIN_WEIGHT, weight))
        for field, weight in weights.items()
    }
    result = {}
    while remaining:
        budget = total - fsum(result.values())
        denominator = fsum(remaining.values())
        shares = {
            field: weight / denominator * budget
            for field, weight in remaining.items()
        }
        bounded = {
            field: min(_MAX_WEIGHT, max(_MIN_WEIGHT, share))
            for field, share in shares.items()
            if share < _MIN_WEIGHT or share > _MAX_WEIGHT
        }
        if not bounded:
            result.update(shares)
            break
        result.update(bounded)
        for field in bounded:
            del remaining[field]
    return result


def preferences_from_intents(
    intents: Iterable[str | RankingIntent],
    current: RankingPreferences | None = None,
) -> RankingPreferences:
    """Increment current normalized preferences without mutating the input.

    Accept semantic codes or ``interpret_feedback(...).intents`` directly.
    Structured intents must target ``ranking_preferences``; hard constraints,
    unsupported targets and unknown codes are
    ignored.

    Deduplicate targets and increase each by 0.10, capped at 0.70, together.
    If donors cannot fund all increases while keeping their 0.05 floors,
    scale the increases by the same factor. Allocate the remaining total
    proportionally across non-targets, pinning any that reach their floor
    and redistributing again. Fixed criterion order makes intent order
    irrelevant. Repeated events build on the supplied current state.

    Legacy relative weights are normalized and bounded before adjustment.
    With no recognized intent, preserve current exactly (even legacy weights
    outside these policy bounds), or return model defaults.

    Warmer/cooler set temperature direction independently of positive weight.
    More/less sunshine and more/less rain set their own directions the same way.
    Conflicting directions in one event preserve the current direction, while
    still increasing the criterion weight once (deduplicated by criterion).
    """
    codes = set()
    for intent in intents:
        if isinstance(intent, str):
            code = intent
        elif intent.target == "ranking_preferences":
            code = intent.code
        else:
            continue
        if code in _INTENT_CRITERIA:
            codes.add(code)

    if not codes:
        return current if current is not None else RankingPreferences()

    current = current if current is not None else RankingPreferences()
    weights = _redistribute_weights(current.normalized_weights())
    targets = {_INTENT_CRITERIA[code] for code in codes}
    increases = {
        field: min(_ADJUSTMENT_STEP, _MAX_WEIGHT - weight)
        for field, weight in weights.items() if field in targets
    }
    donors = {field: weight for field, weight in weights.items() if field not in targets}
    available = max(0.0, fsum(weight - _MIN_WEIGHT for weight in donors.values()))
    requested = fsum(increases.values())
    scale = min(1.0, available / requested) if requested else 0.0
    adjusted = {field: weights[field] + increase * scale for field, increase in increases.items()}
    adjusted.update(_redistribute_weights(donors, 1.0 - fsum(adjusted.values())))
    if not isclose(fsum(adjusted.values()), 1.0, abs_tol=1e-12) or any(
        not _MIN_WEIGHT <= weight <= _MAX_WEIGHT for weight in adjusted.values()
    ):
        raise ValueError("Adjusted ranking weights must sum to one and respect policy bounds.")
    warmer = "prefer_warmer" in codes
    colder = bool(codes & {"prefer_colder", "prefer_cooler"})
    temperature_direction = current.temperature_direction
    if warmer != colder:
        temperature_direction = "higher_is_better" if warmer else "lower_is_better"
    more_sun = "prefer_more_sunshine" in codes
    less_sun = "prefer_less_sunshine" in codes
    sunshine_direction = current.sunshine_direction
    if more_sun != less_sun:
        sunshine_direction = "higher_is_better" if more_sun else "lower_is_better"
    less_rain = "prefer_less_rain" in codes
    more_rain = "prefer_more_rain" in codes
    precipitation_direction = current.precipitation_direction
    if less_rain != more_rain:
        precipitation_direction = "lower_is_better" if less_rain else "higher_is_better"
    return RankingPreferences(
        **{criterion.weight_field: adjusted[criterion.name] for criterion in CRITERIA},
        temperature_direction=temperature_direction,
        sunshine_direction=sunshine_direction,
        precipitation_direction=precipitation_direction,
    )
