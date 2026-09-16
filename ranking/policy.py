"""Deterministic MVP policy from semantic feedback to ranking preferences."""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

from .ranking import RankingPreferences

if TYPE_CHECKING:
    from backend.models.feedback import RankingIntent


_PRESETS = {
    "stronger_price_preference": {
        "price_weight": 0.50,
        "weather_weight": 0.20,
        "changeovers_weight": 0.15,
        "duration_weight": 0.15,
    },
    "prefer_warmer": {
        "price_weight": 0.20,
        "weather_weight": 0.50,
        "changeovers_weight": 0.15,
        "duration_weight": 0.15,
    },
}


def preferences_from_intents(
    intents: Iterable[str | RankingIntent],
    current: RankingPreferences | None = None,
) -> RankingPreferences:
    """Apply fixed presets without mutating or compounding current weights.

    Accept semantic codes or ``interpret_feedback(...).intents`` directly.
    Structured intents must target ``ranking_preferences``; hard constraints,
    unsupported meanings (including cooler weather), and unknown codes are
    ignored. No fewer-changeovers or shorter-flight codes exist in the current
    AI contract.

    Multiple distinct recognized intents contribute equally: sum their preset
    weights and normalize to one (equivalent to averaging these unit presets).
    Codes are deduplicated and sorted so order and repetition have no effect.
    Recognized feedback replaces current weights. If nothing is recognized,
    return the supplied immutable preferences unchanged, or model defaults.
    """
    codes = set()
    for intent in intents:
        if isinstance(intent, str):
            code = intent
        elif intent.target == "ranking_preferences":
            code = intent.code
        else:
            continue
        if code in _PRESETS:
            codes.add(code)

    if not codes:
        return current if current is not None else RankingPreferences()

    presets = [_PRESETS[code] for code in sorted(codes)]
    weights = {
        field: sum(preset[field] for preset in presets)
        for field in presets[0]
    }
    total = sum(weights.values())
    return RankingPreferences(**{
        field: weight / total for field, weight in weights.items()
    })
