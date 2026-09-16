from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from backend.services.llm import parse_request
from tests.fake_llm import FakeLLMClient

REFERENCE_DATE = date(2026, 9, 14)
COMPLETE_TEXT = (
    "From ZAG, 21–25 September 2026, under EUR 400, somewhere warm and relaxing."
)
COMPLETE_EXTRACTION = {
    "origin_iata": "ZAG",
    "departure_date": "2026-09-21",
    "return_date": "2026-09-25",
    "budget": 400,
    "currency": "EUR",
    "moods": ["relaxing"],
    "weather_preference": "warm",
}


def _parse(text: str, responses: list, form_fields=None):
    return parse_request(
        text,
        form_fields=form_fields,
        reference_date=REFERENCE_DATE,
        llm_client=FakeLLMClient(responses),
    )


def test_complete_request_includes_mood():
    result = _parse(COMPLETE_TEXT, [COMPLETE_EXTRACTION])

    assert result.status == "ready"
    assert result.request is not None
    assert result.request.origin == "ZAG"
    assert result.request.departure_date == date(2026, 9, 21)
    assert result.request.return_date == date(2026, 9, 25)
    assert result.request.budget == 400
    assert result.request.currency == "EUR"
    assert result.request.moods == ["relaxing"]
    assert result.request.weather_preference == "warm"
    assert result.request.duration_days is None
    assert result.clarification_questions == []


def test_missing_dates_returns_needs_input():
    result = _parse(
        "From ZAG, under EUR 400, somewhere relaxing.",
        [
            {
                "origin_iata": "ZAG",
                "budget": 400,
                "currency": "EUR",
                "moods": ["relaxing"],
            }
        ],
    )

    assert result.status == "needs_input"
    assert result.request is None
    assert result.preferences is not None
    assert result.preferences.origin == "ZAG"
    assert result.preferences.moods == ["relaxing"]
    assert result.preferences.departure_date is None
    assert result.preferences.return_date is None
    assert any("departure date" in issue.lower() for issue in result.issues)
    assert any("departure date" in question.lower() for question in result.clarification_questions)


def test_invalid_budget_returns_needs_input():
    result = _parse(
        "From ZAG, 21-25 September 2026, budget -50 EUR.",
        [
            {
                "origin_iata": "ZAG",
                "departure_date": "2026-09-21",
                "return_date": "2026-09-25",
                "budget": -50,
                "currency": "EUR",
            }
        ],
    )

    assert result.status == "needs_input"
    assert result.request is None
    assert result.preferences is not None
    assert result.preferences.budget == -50
    assert any("Budget must be a positive number" in issue for issue in result.issues)


def test_return_date_before_departure_returns_needs_input():
    result = _parse(
        "From ZAG, leave 25 September 2026 and return 21 September 2026, EUR 400.",
        [
            {
                "origin_iata": "ZAG",
                "departure_date": "2026-09-25",
                "return_date": "2026-09-21",
                "budget": 400,
                "currency": "EUR",
            }
        ],
    )

    assert result.status == "needs_input"
    assert result.request is None
    assert any("Return date is before departure date" in issue for issue in result.issues)


def test_explicit_form_fields_are_preserved():
    result = _parse(
        "Somewhere warm and relaxing.",
        [
            {
                "moods": ["relaxing"],
                "weather_preference": "warm",
            }
        ],
        form_fields={
            "origin": "ZAG",
            "departure_date": "2026-09-21",
            "return_date": "2026-09-25",
            "budget": 400,
            "currency": "EUR",
        },
    )

    assert result.status == "ready"
    assert result.request is not None
    assert result.request.origin == "ZAG"
    assert result.request.departure_date == date(2026, 9, 21)
    assert result.request.return_date == date(2026, 9, 25)
    assert result.request.budget == 400
    assert result.request.currency == "EUR"
    assert result.request.moods == ["relaxing"]


def test_conflicting_form_and_text_asks_for_clarification():
    result = _parse(
        "From LIS, 21-25 September 2026, under EUR 400.",
        [
            {
                "origin_iata": "LIS",
                "departure_date": "2026-09-21",
                "return_date": "2026-09-25",
                "budget": 400,
                "currency": "EUR",
            }
        ],
        form_fields={"origin": "ZAG"},
    )

    assert result.status == "needs_input"
    assert result.request is None
    assert any("disagree about origin" in issue for issue in result.issues)
    assert result.clarification_questions
    assert result.preferences is not None
    assert result.preferences.origin == "LIS"


def test_invalid_model_output_is_repaired_on_second_attempt():
    result = _parse(COMPLETE_TEXT, ["not-json", COMPLETE_EXTRACTION])

    assert result.status == "ready"
    assert result.request is not None
    assert result.request.origin == "ZAG"
    assert result.request.moods == ["relaxing"]


def test_repeated_invalid_output_stops_at_retry_limit():
    client = FakeLLMClient(["not-json", "{still invalid"])
    result = parse_request(
        COMPLETE_TEXT,
        reference_date=REFERENCE_DATE,
        llm_client=client,
    )

    assert result.status == "error"
    assert result.request is None
    assert len(client.calls) == 2
    assert any("invalid output twice" in issue for issue in result.issues)


def test_missing_values_are_not_copied_from_fixtures():
    fixture_request = json.loads(
        (Path(__file__).resolve().parent / "fixtures" / "normalized_destinations.json").read_text(
            encoding="utf-8"
        )
    )["request"]

    result = _parse("I want something relaxing.", [{"moods": ["relaxing"]}])

    assert result.status == "needs_input"
    assert result.preferences is not None
    assert result.preferences.moods == ["relaxing"]
    assert result.preferences.origin is None
    assert result.preferences.departure_date is None
    assert result.preferences.return_date is None
    assert result.preferences.budget is None
    assert result.preferences.currency is None
    assert result.preferences.origin != fixture_request["origin"] or result.preferences.origin is None
    assert result.preferences.departure_date is None
    assert str(result.preferences.departure_date) != fixture_request["departure_date"]
    assert str(result.preferences.return_date) != fixture_request["return_date"]
    assert result.preferences.currency != fixture_request["currency"]


def test_mood_or_duration_only_is_preserved():
    result = _parse(
        "A relaxing 5-day trip.",
        [{"moods": ["relaxing"], "duration_days": 5}],
    )

    assert result.status == "needs_input"
    assert result.preferences is not None
    assert result.preferences.moods == ["relaxing"]
    assert result.preferences.duration_days == 5
    assert result.preferences.origin is None
    assert result.preferences.departure_date is None


def test_unresolved_place_name_does_not_become_an_iata_code():
    result = _parse(
        "From Zagreb, 21-25 September 2026, under EUR 400.",
        [
            {
                "origin_iata": None,
                "origin_text": "Zagreb",
                "departure_date": "2026-09-21",
                "return_date": "2026-09-25",
                "budget": 400,
                "currency": "EUR",
            }
        ],
    )

    assert result.status == "needs_input"
    assert result.request is None
    assert result.preferences is not None
    assert result.preferences.origin is None
    assert result.preferences.origin_text == "Zagreb"
    assert any("IATA" in question for question in result.clarification_questions)


def test_form_only_complete_request_skips_model():
    client = FakeLLMClient([{"should_not": "be_called"}])
    result = parse_request(
        "",
        form_fields={
            "origin": "ZAG",
            "departure_date": "2026-09-21",
            "return_date": "2026-09-25",
            "budget": 400,
            "currency": "EUR",
            "moods": ["relaxing"],
        },
        reference_date=REFERENCE_DATE,
        llm_client=client,
    )

    assert result.status == "ready"
    assert result.request is not None
    assert result.request.origin == "ZAG"
    assert client.calls == []
