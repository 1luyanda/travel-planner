"""Grounded explanations for ranked travel destinations.

Backend integration (Luyanda) should call `explain_ranked_trips` after ranking.

Signature:
    explain_ranked_trips(
        request: TripRequest,
        ranked: Sequence[RankedTripLike],
        *,
        llm_client: LLMClient | None = None,
        ranking_weights: Mapping[str, float] | None = None,
    ) -> ExplainRankedTripsResult

`ranked` must expose the canonical RankedDestination fields from
origin/feature/ranking. The ranking package is not imported here; a Protocol
is used until that package is on this branch.

The LLM only selects allowed evidence IDs. Factual numbers are rendered from
the ranked records, not from model prose.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any, Protocol, runtime_checkable

from backend.models.explanation import (
    DestinationExplanation,
    EvidenceReference,
    ExplainRankedTripsResult,
)
from backend.models.trip_request import TripRequest
from backend.services.llm import (
    LLMClient,
    LLMConfigurationError,
    create_llm_client_from_env,
)

EXPLAIN_FUNCTION_NAME = "select_explanation_evidence"
MAX_MODEL_ATTEMPTS = 2
MAX_EVIDENCE_PER_DESTINATION = 4
RANKING_CURRENCY = "EUR"

WARM_WEATHER_TERMS = frozenset({"warm", "warmer", "hot", "sunny"})
COOL_WEATHER_TERMS = frozenset({"cool", "cooler", "cold", "colder", "chilly"})

EXPLAIN_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": EXPLAIN_FUNCTION_NAME,
        "description": (
            "Select allowed evidence IDs for each ranked destination. "
            "Do not invent IDs, prices, temperatures, dates or attractions."
        ),
        "parameters": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "explanations": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "destination_id": {"type": "string"},
                            "evidence_ids": {
                                "type": "array",
                                "items": {"type": "string"},
                                "maxItems": MAX_EVIDENCE_PER_DESTINATION,
                            },
                        },
                        "required": ["destination_id", "evidence_ids"],
                    },
                }
            },
            "required": ["explanations"],
        },
    },
}


@runtime_checkable
class RankedTripLike(Protocol):
    """Narrow view of ranking.RankedDestination. Integration is pending."""

    destination_id: str
    destination_iata: str
    city: str
    price_eur: float
    changeover_count: int
    flight_duration_minutes: int
    trip_duration_days: int
    average_max_temperature_c: float
    price_score: float
    weather_score: float
    stops_score: float
    duration_score: float
    final_score: float


def explain_ranked_trips(
    request: TripRequest,
    ranked: Sequence[RankedTripLike],
    *,
    llm_client: LLMClient | None = None,
    ranking_weights: Mapping[str, float] | None = None,
) -> ExplainRankedTripsResult:
    """Explain ranked destinations using only supplied facts and ranking meanings."""
    trips = list(ranked)
    if not trips:
        return ExplainRankedTripsResult(status="ok", explanations=[], issues=[])

    catalogs = [
        _catalog_for_trip(request, trip, index + 1, ranking_weights)
        for index, trip in enumerate(trips)
    ]
    allowed_by_id = {
        item.id: item
        for catalog in catalogs
        for item in catalog
    }

    client = llm_client
    if client is None:
        try:
            client = create_llm_client_from_env()
        except LLMConfigurationError as exc:
            return ExplainRankedTripsResult(
                status="error",
                explanations=[],
                issues=[str(exc)],
            )

    selection, model_error = _select_evidence_with_retry(
        request, trips, catalogs, client
    )
    if model_error:
        return ExplainRankedTripsResult(
            status="error",
            explanations=[],
            issues=[model_error],
        )

    explanations, issues = _build_explanations(trips, catalogs, allowed_by_id, selection)
    return ExplainRankedTripsResult(
        status="ok",
        explanations=explanations,
        issues=issues,
    )


def _catalog_for_trip(
    request: TripRequest,
    trip: RankedTripLike,
    rank: int,
    ranking_weights: Mapping[str, float] | None,
) -> list[EvidenceReference]:
    destination_id = str(trip.destination_id)
    colder = getattr(trip, "temperature_direction", "higher_is_better") == "lower_is_better"
    preferred_temperature = "lower" if colder else "higher"
    items: list[EvidenceReference] = []

    def add(code: str, statement: str) -> None:
        items.append(
            EvidenceReference(
                id=f"{destination_id}::{code}",
                code=code,
                destination_id=destination_id,
                statement=statement,
            )
        )

    add(
        "relative_final_score",
        (
            f"Relative ranking score is {_score(trip.final_score)}. "
            "This is a comparison within this result set, not a match percentage."
        ),
    )
    add(
        "relative_price_score",
        (
            f"Relative price score is {_score(trip.price_score)}. "
            "Lower prices score higher in the current ranking."
        ),
    )
    add(
        "relative_weather_score",
        (
            f"Relative weather score is {_score(trip.weather_score)}. "
            f"The current ranking treats {preferred_temperature} maximum temperature as better."
        ),
    )
    add(
        "relative_stops_score",
        (
            f"Relative stops score is {_score(trip.stops_score)}. "
            "Fewer changeovers score higher in the current ranking."
        ),
    )
    add(
        "relative_duration_score",
        (
            f"Relative duration score is {_score(trip.duration_score)}. "
            "Shorter recorded round-trip air time scores higher."
        ),
    )
    add(
        "recorded_price",
        f"Recorded price is {_money(trip.price_eur)} {RANKING_CURRENCY}.",
    )
    add(
        "recorded_temperature",
        (
            "Recorded average maximum temperature is "
            f"{_number(trip.average_max_temperature_c)} C."
        ),
    )
    add(
        "flight_air_duration",
        (
            "Recorded round-trip air time is "
            f"{int(trip.flight_duration_minutes)} minutes "
            "(outbound plus return, as documented by ranking). "
            "This is not total holiday time or calendar dates."
        ),
    )
    add(
        "recorded_changeovers",
        f"Recorded changeover count is {int(trip.changeover_count)}.",
    )

    if request.currency == RANKING_CURRENCY:
        if trip.price_eur <= request.budget:
            add(
                "within_budget",
                (
                    f"Recorded price {_money(trip.price_eur)} {RANKING_CURRENCY} "
                    f"is within the {_money(request.budget)} {request.currency} budget."
                ),
            )
        else:
            add(
                "over_budget",
                (
                    f"Recorded price {_money(trip.price_eur)} {RANKING_CURRENCY} "
                    f"is above the {_money(request.budget)} {request.currency} budget."
                ),
            )
    else:
        add(
            "price_not_comparable",
            (
                f"Recorded price is {_money(trip.price_eur)} {RANKING_CURRENCY}, "
                f"but the budget is {_money(request.budget)} {request.currency}, "
                "so they cannot be compared."
            ),
        )

    if int(trip.changeover_count) == 0:
        add("direct_flight", "Recorded changeover count is 0 (no stops).")
    if request.direct_flights_only is True and int(trip.changeover_count) > 0:
        add(
            "misses_direct_preference",
            (
                "Direct flights were requested, but the recorded changeover "
                f"count is {int(trip.changeover_count)}."
            ),
        )
    if request.direct_flights_only is True and int(trip.changeover_count) == 0:
        add(
            "matches_direct_preference",
            "Direct flights were requested and the recorded changeover count is 0.",
        )

    weather = (request.weather_preference or "").strip().lower()
    if weather in WARM_WEATHER_TERMS:
        add(
            "warm_preference_ranking_note",
            (
                f"The request prefers {request.weather_preference}. "
                f"The current ranking gives a higher weather score to {preferred_temperature} "
                "maximum temperatures; this does not prove local conditions."
            ),
        )
    if weather in COOL_WEATHER_TERMS and colder:
        add(
            "cool_preference_ranking_note",
            "The current ranking prefers lower maximum temperatures; "
            "this is a relative score, not a guarantee of cool local conditions.",
        )
    elif weather in COOL_WEATHER_TERMS:
        add(
            "cool_preference_not_supported",
            (
                f"The request prefers {request.weather_preference}, but the "
                "current ranking treats higher maximum temperature as better. "
                "A cooler-weather preference is not shown as satisfied."
            ),
        )

    if request.moods:
        moods = ", ".join(request.moods)
        add(
            "mood_not_verified",
            (
                f"Requested mood ({moods}) is not a ranked destination quality "
                "and is not verified by these records."
            ),
        )

    if ranking_weights:
        formatted = ", ".join(
            f"{name}={_number(value)}" for name, value in ranking_weights.items()
        )
        add(
            "supplied_ranking_weights",
            f"These relative scores used the supplied weights: {formatted}.",
        )

    add(
        "rank_position",
        f"{trip.city} is in supplied rank position {rank}.",
    )
    return items


def _select_evidence_with_retry(
    request: TripRequest,
    trips: Sequence[RankedTripLike],
    catalogs: Sequence[list[EvidenceReference]],
    llm_client: LLMClient,
) -> tuple[list[dict[str, Any]] | None, str | None]:
    messages = [
        {"role": "system", "content": _system_prompt()},
        {"role": "user", "content": _user_prompt(request, trips, catalogs)},
    ]
    last_error = "The model returned invalid output."

    for attempt in range(MAX_MODEL_ATTEMPTS):
        try:
            raw_arguments = llm_client.complete_function_call(
                messages=messages,
                tools=[EXPLAIN_TOOL],
                tool_choice={
                    "type": "function",
                    "function": {"name": EXPLAIN_FUNCTION_NAME},
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
                            f"{EXPLAIN_FUNCTION_NAME} again with valid JSON. "
                            "Select only allowed evidence IDs."
                        ),
                    }
                )
                continue
            break

        selection, parse_error = _parse_selection(raw_arguments)
        if selection is not None:
            return selection, None
        last_error = parse_error or last_error
        if attempt == 0:
            messages.append(
                {
                    "role": "user",
                    "content": (
                        f"Your previous function call was invalid: {last_error} "
                        f"Call {EXPLAIN_FUNCTION_NAME} again. Use only allowed "
                        "evidence IDs. Do not invent facts."
                    ),
                }
            )

    return None, (
        last_error
        if last_error == "The model request failed."
        else "The model returned invalid output twice. Please try again."
    )


def _parse_selection(
    raw_arguments: str,
) -> tuple[list[dict[str, Any]] | None, str | None]:
    if raw_arguments is None or not str(raw_arguments).strip():
        return None, "The model did not return a function call."
    try:
        payload = json.loads(raw_arguments)
    except json.JSONDecodeError:
        return None, "The model output was not valid JSON."
    if not isinstance(payload, dict):
        return None, "The model output was not a JSON object."
    explanations = payload.get("explanations")
    if not isinstance(explanations, list):
        return None, "The model output did not include an explanations list."
    cleaned: list[dict[str, Any]] = []
    for item in explanations:
        if not isinstance(item, dict):
            return None, "Each explanation must be an object."
        destination_id = item.get("destination_id")
        evidence_ids = item.get("evidence_ids")
        if not isinstance(destination_id, str) or not destination_id.strip():
            return None, "Each explanation needs a destination_id."
        if not isinstance(evidence_ids, list) or any(
            not isinstance(value, str) for value in evidence_ids
        ):
            return None, "evidence_ids must be a list of strings."
        cleaned.append(
            {
                "destination_id": destination_id.strip(),
                "evidence_ids": evidence_ids[:MAX_EVIDENCE_PER_DESTINATION],
            }
        )
    return cleaned, None


def _build_explanations(
    trips: Sequence[RankedTripLike],
    catalogs: Sequence[list[EvidenceReference]],
    allowed_by_id: dict[str, EvidenceReference],
    selection: list[dict[str, Any]],
) -> tuple[list[DestinationExplanation], list[str]]:
    issues: list[str] = []
    selected_by_destination: dict[str, list[str]] = {}
    known_ids = {str(trip.destination_id) for trip in trips}

    for item in selection:
        destination_id = item["destination_id"]
        if destination_id not in known_ids:
            issues.append(f"Ignored unknown destination_id {destination_id!r}.")
            continue
        selected_by_destination.setdefault(destination_id, [])
        for evidence_id in item["evidence_ids"]:
            allowed = allowed_by_id.get(evidence_id)
            if allowed is None:
                issues.append(
                    f"Ignored unknown evidence_id {evidence_id!r} "
                    f"for {destination_id}."
                )
                continue
            if allowed.destination_id != destination_id:
                issues.append(
                    f"Ignored evidence {evidence_id!r} because it belongs to "
                    f"{allowed.destination_id}, not {destination_id}."
                )
                continue
            if evidence_id not in selected_by_destination[destination_id]:
                selected_by_destination[destination_id].append(evidence_id)

    explanations: list[DestinationExplanation] = []
    for index, trip in enumerate(trips):
        destination_id = str(trip.destination_id)
        chosen_ids = selected_by_destination.get(destination_id, [])
        evidence = [allowed_by_id[item_id] for item_id in chosen_ids]
        row_issues: list[str] = []
        if not evidence:
            row_issues.append("No verified evidence was selected for this destination.")
        summary = " ".join(item.statement for item in evidence) if evidence else (
            f"{trip.city} is in the ranked list. No verified explanation reasons "
            "were selected."
        )
        explanations.append(
            DestinationExplanation(
                destination_id=destination_id,
                destination_iata=str(trip.destination_iata),
                city=str(trip.city),
                rank=index + 1,
                price_eur=float(trip.price_eur),
                changeover_count=int(trip.changeover_count),
                flight_duration_minutes=int(trip.flight_duration_minutes),
                average_max_temperature_c=float(trip.average_max_temperature_c),
                price_score=float(trip.price_score),
                weather_score=float(trip.weather_score),
                stops_score=float(trip.stops_score),
                duration_score=float(trip.duration_score),
                final_score=float(trip.final_score),
                precipitation_score=float(getattr(trip, "precipitation_score", 0.0)),
                sunshine_score=float(getattr(trip, "sunshine_score", 0.0)),
                temperature_direction=getattr(trip, "temperature_direction", "higher_is_better"),
                summary=summary,
                evidence=evidence,
                issues=row_issues,
            )
        )
    return explanations, issues


def _system_prompt() -> str:
    return (
        "You write grounded travel explanations by selecting evidence IDs.\n"
        f"Call {EXPLAIN_FUNCTION_NAME}.\n"
        "Rules:\n"
        "- Use only the allowed evidence IDs listed for each destination.\n"
        "- Do not invent prices, temperatures, dates, attractions, availability "
        "or total holiday costs.\n"
        "- A requested mood does not prove a destination has that quality.\n"
        "- Do not claim a cooler-weather preference is satisfied. Ranking treats "
        "higher maximum temperature as better.\n"
        "- Scores are relative ranking values, not confidence or match percentages.\n"
        "- Compare price with budget only through the provided budget evidence.\n"
        "- Duration evidence is round-trip air minutes, not calendar stay length.\n"
        "- Preserve ranking order by covering each listed destination_id.\n"
    )


def _user_prompt(
    request: TripRequest,
    trips: Sequence[RankedTripLike],
    catalogs: Sequence[list[EvidenceReference]],
) -> str:
    lines = [
        "Trip request:",
        f"- origin IATA: {request.origin}",
        f"- dates: {request.departure_date.isoformat()} to {request.return_date.isoformat()}",
        f"- budget: {_money(request.budget)} {request.currency}",
        f"- moods: {request.moods or []}",
        f"- direct_flights_only: {request.direct_flights_only}",
        f"- weather_preference: {request.weather_preference}",
        "",
        "Ranked destinations and allowed evidence:",
    ]
    for trip, catalog in zip(trips, catalogs, strict=True):
        lines.append(
            f"\n{trip.destination_id} | {trip.city} | {trip.destination_iata} | "
            f"final_score={_score(trip.final_score)}"
        )
        for item in catalog:
            lines.append(f"- {item.id}: {item.statement}")
    return "\n".join(lines)


def _score(value: float) -> str:
    return f"{float(value):.2f}"


def _money(value: float) -> str:
    number = float(value)
    if number.is_integer():
        return str(int(number))
    return f"{number:.2f}"


def _number(value: float) -> str:
    number = float(value)
    if number.is_integer():
        return str(int(number))
    return f"{number:.2f}"
