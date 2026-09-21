"""Interpret user feedback against a validated TripRequest.

Backend integration (Luyanda) should call ``interpret_feedback`` after the
user comments on an existing request. Ranking is not called here.

Signature:
    interpret_feedback(
        feedback_text: str,
        request: TripRequest,
        *,
        llm_client: LLMClient | None = None,
    ) -> InterpretFeedbackResult

Behaviour:
    - "Cheaper" → stronger price intent; budget is not lowered.
    - "Warmer" → warmer intent and weather_preference; no temperature number.
    - Explicit "budget is now EUR 300" → proposed budget/currency update.
    - "Direct flights only" → direct_flights_only=True (hard constraint).
    - Unrelated fields are copied onto a new TripRequest.
    - The input request object is not mutated.
    - Explicit feedback updates are applied; parse_request conflict rules
      are not used.
    - Budget is never cleared. Currency is not converted unless the user
      stated a new 3-letter code together with an explicit amount, or an
      explicit same-currency amount.

The LLM only extracts what the user stated. Application and guards are
deterministic. Invented budgets, temperatures and weights are dropped.
"""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import ValidationError

from backend.models.feedback import (
    FieldChange,
    InterpretFeedbackResult,
    RankingIntent,
)
from backend.models.trip_request import TripRequest
from backend.services.llm import (
    LLMClient,
    LLMConfigurationError,
    create_llm_client_from_env,
)

INTERPRET_FUNCTION_NAME = "interpret_travel_feedback"
MAX_MODEL_ATTEMPTS = 2
CURRENCY_PATTERN = re.compile(r"^[A-Za-z]{3}$")

CHEAPER_TERMS = frozenset({"cheaper", "cheapest", "less expensive", "lower price"})
SHORTER_TERMS = frozenset(
    {"shorter", "shorter travel", "shorter flights", "less flying", "faster"}
)
WARMER_TERMS = frozenset(
    {
        "warmer",
        "warm",
        "hotter",
        "hot",
        "sunnier",
        "sunny",
        "sunshine",
        "more sunshine",
        "more sunny",
        "less rain",
        "less rainy",
        "drier",
    }
)
COOLER_TERMS = frozenset(
    {
        "cooler",
        "cool",
        "colder",
        "cold",
        "chilly",
        "rain",
        "rainy",
        "rainier",
        "more rain",
        "more rainy",
        "wetter",
        "less sunshine",
        "cloudy",
        "cloudier",
    }
)

INTERPRET_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": INTERPRET_FUNCTION_NAME,
        "description": (
            "Interpret feedback about an existing trip request. "
            "Record only what the user stated. Do not invent a lower budget "
            "for cheaper, a temperature for warmer, ranking weights, or a "
            "currency conversion."
        ),
        "parameters": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "stronger_price_preference": {
                    "type": "boolean",
                    "description": (
                        "True when the user wants cheaper options and did not "
                        "state a new numeric budget."
                    ),
                },
                "stronger_duration_preference": {
                    "type": "boolean",
                    "description": "True when the user wants shorter or faster travel.",
                },
                "prefer_warmer": {
                    "type": "boolean",
                    "description": "True when the user wants warmer options.",
                },
                "prefer_cooler": {
                    "type": "boolean",
                    "description": "True when the user wants cooler options.",
                },
                "direct_flights_only": {
                    "type": ["boolean", "null"],
                    "description": (
                        "True if the user asked for direct flights only, "
                        "false if they allowed stops, otherwise null."
                    ),
                },
                "budget": {
                    "type": ["number", "null"],
                    "description": "New numeric budget only if the user stated one.",
                },
                "currency": {
                    "type": ["string", "null"],
                    "description": "New 3-letter currency only if the user stated one.",
                },
                "weather_preference": {
                    "type": ["string", "null"],
                    "description": "Weather words such as warmer. Never a number.",
                },
                "moods_add": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Extra mood words the user stated.",
                },
                "unclear": {
                    "type": "boolean",
                    "description": "True when the feedback is too vague to apply.",
                },
                "clarification_needed": {
                    "type": ["string", "null"],
                    "description": "Question to ask when unclear is true.",
                },
            },
        },
    },
}


def interpret_feedback(
    feedback_text: str,
    request: TripRequest,
    *,
    llm_client: LLMClient | None = None,
) -> InterpretFeedbackResult:
    """Validate feedback against a snapshot of the current trip request."""

    snapshot = request.model_copy(deep=True)
    text = (feedback_text or "").strip()
    if not text:
        return InterpretFeedbackResult(
            status="needs_input",
            request=snapshot,
            issues=["Feedback is empty."],
            clarification_questions=[
                "What would you like to change about this trip?"
            ],
        )

    client = llm_client
    if client is None:
        try:
            client = create_llm_client_from_env()
        except LLMConfigurationError as exc:
            return InterpretFeedbackResult(
                status="error",
                request=snapshot,
                issues=[str(exc)],
            )

    payload, model_error = _extract_with_retry(text, snapshot, client)
    if payload is None:
        return InterpretFeedbackResult(
            status="error",
            request=snapshot,
            issues=[model_error or "The model returned invalid output."],
        )

    return _apply_feedback(text, snapshot, payload)


def _extract_with_retry(
    feedback_text: str,
    request: TripRequest,
    llm_client: LLMClient,
) -> tuple[dict[str, Any] | None, str | None]:
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": _system_prompt(request)},
        {"role": "user", "content": feedback_text},
    ]
    last_error = "The model returned invalid output."

    for attempt in range(MAX_MODEL_ATTEMPTS):
        try:
            raw_arguments = llm_client.complete_function_call(
                messages=messages,
                tools=[INTERPRET_TOOL],
                tool_choice={
                    "type": "function",
                    "function": {"name": INTERPRET_FUNCTION_NAME},
                },
            )
        except Exception:
            last_error = "The model request failed."
            if attempt == 0:
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "The previous model call failed. Call "
                            f"{INTERPRET_FUNCTION_NAME} again with valid JSON. "
                            "Do not invent a budget, temperature or weights."
                        ),
                    }
                )
                continue
            break

        payload, parse_error = _payload_from_tool_arguments(raw_arguments)
        if payload is not None:
            return payload, None

        last_error = parse_error or last_error
        if attempt == 0:
            messages.append(
                {
                    "role": "user",
                    "content": (
                        f"Your previous function call was invalid: {last_error} "
                        f"Call {INTERPRET_FUNCTION_NAME} again with JSON that "
                        "matches the schema. Do not invent values."
                    ),
                }
            )

    return None, (
        "The model returned invalid output twice. Please try again."
    )


def _payload_from_tool_arguments(
    raw_arguments: str,
) -> tuple[dict[str, Any] | None, str | None]:
    if raw_arguments is None or not str(raw_arguments).strip():
        return None, "The model did not return a function call."
    try:
        payload = json.loads(raw_arguments)
    except json.JSONDecodeError:
        return None, "The model output was not valid JSON."
    if not isinstance(payload, dict):
        return None, "The model output was not a JSON object."
    try:
        return _normalise_payload(payload), None
    except (TypeError, ValueError, ValidationError) as exc:
        return None, str(exc)


def _normalise_payload(payload: dict[str, Any]) -> dict[str, Any]:
    moods = payload.get("moods_add") or []
    if isinstance(moods, str):
        moods = [part.strip() for part in moods.split(",") if part.strip()]
    if not isinstance(moods, list):
        raise ValueError("moods_add must be a list of strings.")
    return {
        "stronger_price_preference": bool(payload.get("stronger_price_preference")),
        "stronger_duration_preference": bool(
            payload.get("stronger_duration_preference")
        ),
        "prefer_warmer": bool(payload.get("prefer_warmer")),
        "prefer_cooler": bool(payload.get("prefer_cooler")),
        "direct_flights_only": payload.get("direct_flights_only"),
        "budget": payload.get("budget"),
        "currency": payload.get("currency"),
        "weather_preference": payload.get("weather_preference"),
        "moods_add": [str(item).strip() for item in moods if str(item).strip()],
        "unclear": bool(payload.get("unclear")),
        "clarification_needed": payload.get("clarification_needed"),
    }


def _apply_feedback(
    text: str,
    snapshot: TripRequest,
    payload: dict[str, Any],
) -> InterpretFeedbackResult:
    intents: list[RankingIntent] = []
    changes: list[FieldChange] = []
    issues: list[str] = []
    questions: list[str] = []
    updates: dict[str, Any] = {}

    cheaper = payload["stronger_price_preference"] or _mentions_any(text, CHEAPER_TERMS)
    shorter = payload.get("stronger_duration_preference", False) or _mentions_any(
        text, SHORTER_TERMS
    )
    warmer = payload["prefer_warmer"] or _mentions_any(text, WARMER_TERMS)
    cooler = payload["prefer_cooler"] or _mentions_any(text, COOLER_TERMS)

    if cheaper:
        intents.append(
            RankingIntent(
                code="stronger_price_preference",
                target="ranking_preferences",
                ranking_field="price_weight",
                meaning=(
                    "Prefer cheaper options more strongly within the current "
                    "budget. The numeric budget must not be lowered. Ranking "
                    "already scores lower price_eur higher. Ivan's "
                    "RankingPreferences.price_weight is the related field; no "
                    "weight value is supplied because that mapping is not defined."
                ),
            )
        )

    if shorter:
        intents.append(
            RankingIntent(
                code="stronger_duration_preference",
                target="ranking_preferences",
                ranking_field="duration_weight",
                meaning=(
                    "Prefer shorter recorded flight durations more strongly. "
                    "This changes ranking preference, not calendar trip length."
                ),
            )
        )

    if warmer:
        intents.append(
            RankingIntent(
                code="prefer_warmer",
                target="ranking_preferences",
                ranking_field="weather_weight",
                meaning=(
                    "Prefer warmer options. Do not apply a temperature "
                    "threshold. Ranking already scores higher "
                    "average_max_temperature_c higher. Ivan's "
                    "RankingPreferences.weather_weight is related; no weight "
                    "value is supplied because that mapping is not defined."
                ),
            )
        )
        _propose_weather(snapshot, updates, changes, "warmer")

    if cooler and not warmer:
        intents.append(
            RankingIntent(
                code="prefer_cooler",
                target="ranking_preferences",
                ranking_field="weather_weight",
                meaning=(
                    "Prefer cooler options more strongly. Increase temperature "
                    "importance and score lower maximum temperatures higher. "
                    "Do not apply a temperature threshold or a negative weight."
                ),
            )
        )
        _propose_weather(snapshot, updates, changes, "cool")

    direct = payload.get("direct_flights_only")
    if direct is True or _mentions_direct_only(text):
        intents.append(
            RankingIntent(
                code="direct_flights_only",
                target="ranking_constraints",
                ranking_field="max_changeovers",
                meaning=(
                    "Require direct flights. Proposed TripRequest."
                    "direct_flights_only=True. Luyanda may map this to "
                    "RankingConstraints.max_changeovers=0. This is a hard "
                    "filter, not a changeovers_weight value."
                ),
            )
        )
        if snapshot.direct_flights_only is not True:
            updates["direct_flights_only"] = True
            changes.append(
                FieldChange(
                    field="direct_flights_only",
                    previous=snapshot.direct_flights_only,
                    proposed=True,
                )
            )

    _apply_budget_and_currency(text, snapshot, payload, updates, changes, issues, questions)

    extra_moods = payload.get("moods_add") or []
    if extra_moods:
        new_moods = list(snapshot.moods)
        added = False
        existing = {item.lower() for item in new_moods}
        for mood in extra_moods:
            if mood.lower() not in existing:
                new_moods.append(mood)
                existing.add(mood.lower())
                added = True
        if added:
            updates["moods"] = new_moods
            changes.append(
                FieldChange(
                    field="moods",
                    previous=list(snapshot.moods),
                    proposed=new_moods,
                )
            )

    if payload.get("unclear") and not intents and not changes:
        question = payload.get("clarification_needed") or (
            "What would you like to change: cheaper, shorter, warmer, or cooler "
            "options, a new budget, or direct flights?"
        )
        return InterpretFeedbackResult(
            status="needs_input",
            request=snapshot,
            issues=["The feedback is too vague to apply."],
            clarification_questions=[str(question)],
        )

    if not intents and not changes:
        return InterpretFeedbackResult(
            status="needs_input",
            request=snapshot,
            issues=["No validated change or ranking intent could be taken from the feedback."],
            clarification_questions=[
                "Please say whether you want cheaper, shorter, warmer, or cooler "
                "options, a new budget amount, or direct flights only."
            ],
        )

    if questions:
        return InterpretFeedbackResult(
            status="needs_input",
            request=snapshot,
            intents=intents,
            changes=changes,
            issues=issues,
            clarification_questions=questions,
        )

    updated = snapshot.model_copy(deep=True, update=updates)
    return InterpretFeedbackResult(
        status="ready",
        request=snapshot,
        updated_request=updated,
        intents=intents,
        changes=changes,
        issues=issues,
    )


def _apply_budget_and_currency(
    text: str,
    snapshot: TripRequest,
    payload: dict[str, Any],
    updates: dict[str, Any],
    changes: list[FieldChange],
    issues: list[str],
    questions: list[str],
) -> None:
    raw_budget = payload.get("budget")
    raw_currency = payload.get("currency")
    stated_currency = None
    if isinstance(raw_currency, str) and CURRENCY_PATTERN.fullmatch(raw_currency.strip()):
        stated_currency = raw_currency.strip().upper()
        if not _token_mentioned(text, stated_currency):
            issues.append(
                f"Currency {stated_currency} was not applied because it was not "
                "stated in the feedback. Currency conversion is not invented."
            )
            stated_currency = None

    if raw_budget is None:
        if stated_currency and stated_currency != snapshot.currency:
            issues.append(
                "A currency change without a stated amount was not applied. "
                "Currency conversion is not invented."
            )
            questions.append(
                f"The current budget is {snapshot.budget:g} {snapshot.currency}. "
                f"What amount in {stated_currency} should we use?"
            )
        return

    try:
        budget = float(raw_budget)
    except (TypeError, ValueError):
        issues.append("The proposed budget was not a number.")
        questions.append("What is the new maximum budget?")
        return

    if not _number_mentioned(text, budget):
        issues.append(
            "A new budget was not applied because that amount was not stated "
            "in the feedback. 'Cheaper' does not lower the numeric budget."
        )
        return

    if budget <= 0:
        issues.append("Budget must be a positive number.")
        questions.append("What is your maximum budget? It must be greater than zero.")
        return

    currency = stated_currency or snapshot.currency
    if budget != snapshot.budget:
        updates["budget"] = budget
        changes.append(
            FieldChange(field="budget", previous=snapshot.budget, proposed=budget)
        )
    if currency != snapshot.currency:
        updates["currency"] = currency
        changes.append(
            FieldChange(field="currency", previous=snapshot.currency, proposed=currency)
        )


def _propose_weather(
    snapshot: TripRequest,
    updates: dict[str, Any],
    changes: list[FieldChange],
    value: str,
) -> None:
    if snapshot.weather_preference != value:
        updates["weather_preference"] = value
        changes.append(
            FieldChange(
                field="weather_preference",
                previous=snapshot.weather_preference,
                proposed=value,
            )
        )


def _mentions_direct_only(text: str) -> bool:
    lowered = text.lower()
    return "direct flight" in lowered or "direct flights" in lowered or "nonstop" in lowered or "non-stop" in lowered


def _mentions_any(text: str, terms: frozenset[str]) -> bool:
    lowered = text.lower()
    return any(term in lowered for term in terms)


def _number_mentioned(text: str, value: float) -> bool:
    compact = text.replace(",", "")
    if float(value).is_integer():
        candidates = {str(int(value)), f"{int(value)}.0"}
    else:
        candidates = {str(value), f"{value:g}"}
    return any(re.search(rf"(?<![\d.]){re.escape(item)}(?![\d.])", compact) for item in candidates)


def _token_mentioned(text: str, token: str) -> bool:
    return re.search(rf"\b{re.escape(token)}\b", text, flags=re.IGNORECASE) is not None


def _system_prompt(request: TripRequest) -> str:
    current = request.model_dump(mode="json")
    return (
        "You interpret feedback about an existing validated trip request.\n"
        f"Current request JSON: {json.dumps(current, default=str)}\n"
        f"Call the {INTERPRET_FUNCTION_NAME} function.\n"
        "Rules:\n"
        "- Record only what the user stated in this feedback.\n"
        "- cheaper / less expensive: stronger_price_preference=true. "
        "Do not change budget.\n"
        "- warmer / hotter / sunnier / less rain: prefer_warmer=true. "
        "weather_preference may be 'warmer'. Never invent a temperature number.\n"
        "- cooler / colder / rainier / more rain: prefer_cooler=true. "
        "weather_preference may be 'cooler'.\n"
        "- shorter / faster travel: stronger_duration_preference=true.\n"
        "- A new budget such as EUR 300: set budget and currency only if stated.\n"
        "- direct flights only: direct_flights_only=true.\n"
        "- Do not invent ranking weights, currency conversion, or origin codes.\n"
        "- unclear=true only when nothing actionable was stated.\n"
        "- Leave unrelated fields null so they stay as they are.\n"
    )
