from __future__ import annotations

from datetime import date

from backend.models.trip_request import TripRequest
from backend.services.feedback import interpret_feedback
from tests.fake_llm import FakeLLMClient

REFERENCE = date(2026, 9, 15)


def test_existing_cooler_ai_intent_is_now_a_ranking_preference():
    result, original = _interpret("Colder", [_payload(prefer_cooler=True)])
    assert result.status == "ready"
    assert result.intents[0].code == "prefer_cooler"
    assert result.intents[0].target == "ranking_preferences"
    assert result.intents[0].ranking_field == "weather_weight"
    assert result.updated_request.weather_preference == "cooler"
    assert result.updated_request.budget == original.budget
    assert result.issues == []
    assert original.weather_preference == "warm"


def _request(**overrides) -> TripRequest:
    values = {
        "origin": "ZAG",
        "departure_date": date(2026, 9, 21),
        "return_date": date(2026, 9, 25),
        "budget": 400,
        "currency": "EUR",
        "moods": ["relaxing"],
        "direct_flights_only": None,
        "weather_preference": "warm",
    }
    values.update(overrides)
    return TripRequest.model_validate(values)


def _payload(**overrides) -> dict:
    values = {
        "stronger_price_preference": False,
        "prefer_warmer": False,
        "prefer_cooler": False,
        "direct_flights_only": None,
        "budget": None,
        "currency": None,
        "weather_preference": None,
        "moods_add": [],
        "unclear": False,
        "clarification_needed": None,
    }
    values.update(overrides)
    return values


def _interpret(text: str, responses: list, request: TripRequest | None = None):
    current = request or _request()
    return interpret_feedback(
        text,
        current,
        llm_client=FakeLLMClient(responses),
    ), current


def test_cheaper_does_not_invent_a_lower_budget():
    result, original = _interpret(
        "Cheaper",
        [_payload(stronger_price_preference=True)],
    )

    assert result.status == "ready"
    assert result.updated_request is not None
    assert result.updated_request.budget == 400
    assert result.updated_request.currency == "EUR"
    assert result.updated_request.origin == "ZAG"
    assert result.updated_request.moods == ["relaxing"]
    assert [item.code for item in result.intents] == ["stronger_price_preference"]
    assert result.intents[0].ranking_field == "price_weight"
    assert all(item.field != "budget" for item in result.changes)
    assert original.budget == 400
    assert result.updated_request is not original
    assert result.request is not original


def test_cheaper_drops_an_invented_budget_from_the_model():
    result, original = _interpret(
        "Cheaper",
        [_payload(stronger_price_preference=True, budget=200, currency="EUR")],
    )

    assert result.status == "ready"
    assert result.updated_request is not None
    assert result.updated_request.budget == 400
    assert original.budget == 400
    assert any("not stated in the feedback" in item for item in result.issues)


def test_warmer_does_not_invent_a_temperature_threshold():
    result, original = _interpret(
        "Warmer",
        [_payload(prefer_warmer=True, weather_preference="warmer")],
    )

    assert result.status == "ready"
    assert result.updated_request is not None
    assert result.updated_request.weather_preference == "warmer"
    assert result.updated_request.budget == 400
    assert result.updated_request.moods == ["relaxing"]
    assert [item.code for item in result.intents] == ["prefer_warmer"]
    assert original.weather_preference == "warm"
    assert not any(
        isinstance(item.proposed, (int, float)) and item.field == "weather_preference"
        for item in result.changes
    )


def test_explicit_budget_update_is_applied():
    result, original = _interpret(
        "My budget is now EUR 300",
        [_payload(budget=300, currency="EUR")],
    )

    assert result.status == "ready"
    assert result.updated_request is not None
    assert result.updated_request.budget == 300
    assert result.updated_request.currency == "EUR"
    assert result.updated_request.origin == "ZAG"
    assert result.updated_request.departure_date == date(2026, 9, 21)
    assert original.budget == 400
    assert [item.field for item in result.changes] == ["budget"]


def test_direct_flights_only_sets_a_hard_constraint():
    result, original = _interpret(
        "Direct flights only",
        [_payload(direct_flights_only=True)],
    )

    assert result.status == "ready"
    assert result.updated_request is not None
    assert result.updated_request.direct_flights_only is True
    assert result.updated_request.budget == 400
    assert result.intents[0].code == "direct_flights_only"
    assert result.intents[0].target == "ranking_constraints"
    assert original.direct_flights_only is None


def test_unrelated_preferences_are_preserved():
    result, _ = _interpret(
        "Cheaper",
        [_payload(stronger_price_preference=True)],
        _request(duration_days=4, weather_preference="warm"),
    )

    updated = result.updated_request
    assert updated is not None
    assert updated.origin == "ZAG"
    assert updated.departure_date == date(2026, 9, 21)
    assert updated.return_date == date(2026, 9, 25)
    assert updated.duration_days == 4
    assert updated.moods == ["relaxing"]
    assert updated.weather_preference == "warm"
    assert updated.direct_flights_only is None


def test_currency_conversion_is_not_invented():
    result, original = _interpret(
        "Cheaper",
        [_payload(stronger_price_preference=True, currency="USD")],
    )

    assert result.updated_request is not None
    assert result.updated_request.currency == "EUR"
    assert original.currency == "EUR"
    assert any("Currency conversion is not invented" in item for item in result.issues)


def test_ambiguous_feedback_needs_input():
    result, original = _interpret(
        "Make it better.",
        [_payload(unclear=True, clarification_needed="What should we change?")],
    )

    assert result.status == "needs_input"
    assert result.updated_request is None
    assert result.intents == []
    assert result.clarification_questions
    assert original.budget == 400


def test_invalid_model_output_is_repaired_on_second_attempt():
    result, _ = _interpret(
        "Cheaper",
        ["{", _payload(stronger_price_preference=True)],
    )

    assert result.status == "ready"
    assert result.updated_request is not None
    assert result.updated_request.budget == 400
    assert result.intents[0].code == "stronger_price_preference"


def test_repeated_invalid_output_returns_error_without_changing_request():
    result, original = _interpret("Cheaper", ["{", "{"])

    assert result.status == "error"
    assert result.updated_request is None
    assert original.budget == 400
    assert original.moods == ["relaxing"]
    assert any("twice" in item for item in result.issues)


def test_empty_feedback_does_not_call_the_model():
    client = FakeLLMClient([_payload()])
    result = interpret_feedback("  ", _request(), llm_client=client)

    assert result.status == "needs_input"
    assert client.calls == []
    assert result.updated_request is None
