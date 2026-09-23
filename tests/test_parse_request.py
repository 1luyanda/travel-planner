from __future__ import annotations

import asyncio
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
    return asyncio.run(
        parse_request(
            text,
            form_fields=form_fields,
            reference_date=REFERENCE_DATE,
            llm_client=FakeLLMClient(responses),
        )
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


def test_conflicting_form_and_text_keeps_the_message():
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
        form_fields={
            "origin": "ZAG",
            "departure_date": "2026-09-30",
            "return_date": "2026-09-30",
            "budget": 100,
            "currency": "EUR",
        },
    )

    assert result.status == "ready"
    assert result.request is not None
    assert result.request.origin == "LIS"
    assert result.request.departure_date == date(2026, 9, 21)
    assert result.request.return_date == date(2026, 9, 25)
    assert result.request.budget == 400
    assert not any("disagree" in issue for issue in result.issues)
    assert not any("Which should we use" in question for question in result.clarification_questions)


def test_invalid_model_output_is_repaired_on_second_attempt():
    result = _parse(COMPLETE_TEXT, ["not-json", COMPLETE_EXTRACTION])

    assert result.status == "ready"
    assert result.request is not None
    assert result.request.origin == "ZAG"
    assert result.request.moods == ["relaxing"]


def test_repeated_invalid_output_stops_at_retry_limit():
    client = FakeLLMClient(["not-json", "{still invalid"])
    result = asyncio.run(
        parse_request(
            COMPLETE_TEXT,
            reference_date=REFERENCE_DATE,
            llm_client=client,
        )
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


def test_euro_symbol_and_warm_escape_fill_missing_llm_fields():
    result = _parse(
        "A warm escape under €400",
        [{"budget": 400}],
        form_fields={
            "origin": "ZAG",
            "departure_date": "2026-10-08",
            "return_date": "2026-10-15",
        },
    )

    assert result.status == "ready"
    assert result.request is not None
    assert result.request.origin == "ZAG"
    assert result.request.departure_date == date(2026, 10, 8)
    assert result.request.return_date == date(2026, 10, 15)
    assert result.request.budget == 400
    assert result.request.currency == "EUR"
    assert result.request.weather_preference == "warm"
    assert result.clarification_questions == []


def test_amount_with_eur_code_before_or_after_number():
    form = {
        "origin": "ZAG",
        "departure_date": "2026-10-08",
        "return_date": "2026-10-16",
    }
    after = _parse("My budget is 400 EUR and I prefer warmer weather.", [{"budget": 400}], form_fields=form)
    before = _parse("EUR 400 somewhere warm.", [{"budget": 400}], form_fields=form)

    assert after.status == "ready"
    assert after.request.currency == "EUR"
    assert after.request.weather_preference == "warm"
    assert before.status == "ready"
    assert before.request.currency == "EUR"


def test_bare_amount_without_currency_cue_still_asks():
    result = _parse(
        "A getaway under 400",
        [{"budget": 400}],
        form_fields={
            "origin": "ZAG",
            "departure_date": "2026-10-08",
            "return_date": "2026-10-15",
        },
    )

    assert result.status == "needs_input"
    assert result.request is None
    assert result.preferences is not None
    assert result.preferences.budget == 400
    assert result.preferences.currency is None
    assert any("currency" in question.lower() for question in result.clarification_questions)


def test_currency_clarification_keeps_origin_dates_budget_and_weather():
    result = asyncio.run(
        parse_request(
            "\n\n".join(
                [
                    "Original request:\nA warm escape under €400",
                    "Initial form selections:\norigin: ZAG\ndeparture date: 2026-10-08\nreturn date: 2026-10-15\nbudget: 400\nweather preference: warm",
                    "The planner asked:\nWhat currency is the budget in (for example EUR)?",
                    "Authoritative answer (this overrides any conflicting initial form values):\nEUR",
                ]
            ),
            form_fields={
                "origin": "ZAG",
                "departure_date": "2026-10-08",
                "return_date": "2026-10-15",
                "budget": 400,
                "weather_preference": "warm",
            },
            reference_date=REFERENCE_DATE,
            llm_client=FakeLLMClient([{"currency": "EUR"}]),
        )
    )

    assert result.status == "ready"
    assert result.request is not None
    assert result.request.origin == "ZAG"
    assert result.request.departure_date == date(2026, 10, 8)
    assert result.request.return_date == date(2026, 10, 15)
    assert result.request.budget == 400
    assert result.request.currency == "EUR"
    assert result.request.weather_preference == "warm"


def test_negated_warm_is_not_treated_as_a_warm_preference():
    result = _parse(
        "I do not want a warm escape under €95",
        [{"budget": 95}],
        form_fields={
            "origin": "ZAG",
            "departure_date": "2026-09-24",
            "return_date": "2026-10-01",
        },
    )

    assert result.status == "ready"
    assert result.request is not None
    assert result.request.currency == "EUR"
    assert result.request.budget == 95
    assert result.request.weather_preference is None


def test_conflicting_currencies_are_not_silently_resolved():
    result = _parse(
        "Under €95 or USD 95 from ZAG.",
        [{"budget": 95}],
        form_fields={
            "origin": "ZAG",
            "departure_date": "2026-09-24",
            "return_date": "2026-10-01",
        },
    )

    assert result.status == "needs_input"
    assert result.request is None
    assert result.preferences is not None
    assert result.preferences.currency is None
    assert any("currency" in question.lower() for question in result.clarification_questions)


def test_clarification_answer_can_replace_dates_and_budget():
    result = asyncio.run(
        parse_request(
            "\n\n".join(
                [
                    "Original request:\nA warm escape under €400",
                    "Initial form selections:\norigin: ZAG\ndeparture date: 2026-10-08\nreturn date: 2026-10-15\nbudget: 400\nweather preference: warm",
                    "The planner asked:\nWhat currency is the budget in (for example EUR)?",
                    "Authoritative answer (this overrides any conflicting initial form values):\nEUR 95 from 2026-09-24 to 2026-10-01",
                ]
            ),
            form_fields={
                "origin": "ZAG",
                "weather_preference": "warm",
            },
            reference_date=REFERENCE_DATE,
            llm_client=FakeLLMClient([{"currency": "EUR"}]),
        )
    )

    assert result.status == "ready"
    assert result.request is not None
    assert result.request.origin == "ZAG"
    assert result.request.departure_date == date(2026, 9, 24)
    assert result.request.return_date == date(2026, 10, 1)
    assert result.request.budget == 95
    assert result.request.currency == "EUR"
    assert result.request.weather_preference == "warm"


def test_clarification_usd_answer_is_not_overridden_by_earlier_euro_symbol():
    result = asyncio.run(
        parse_request(
            "\n\n".join(
                [
                    "Original request:\nA warm escape under €95",
                    "Initial form selections:\norigin: ZAG\ndeparture date: 2026-09-24\nreturn date: 2026-10-01\nbudget: 95",
                    "The planner asked:\nWhat currency is the budget in (for example EUR)?",
                    "Authoritative answer (this overrides any conflicting initial form values):\nUSD",
                ]
            ),
            form_fields={
                "origin": "ZAG",
                "departure_date": "2026-09-24",
                "return_date": "2026-10-01",
                "budget": 95,
            },
            reference_date=REFERENCE_DATE,
            llm_client=FakeLLMClient([{}]),
        )
    )

    assert result.preferences is not None
    assert result.preferences.currency == "USD"
    assert result.preferences.budget == 95
    assert result.preferences.departure_date == date(2026, 9, 24)
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
    result = asyncio.run(
        parse_request(
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
    )

    assert result.status == "ready"
    assert result.request is not None
    assert result.request.origin == "ZAG"
    assert client.calls == []


def test_warm_and_warmer_form_and_text_do_not_conflict():
    from backend.models.trip_request import ExtractedPreferences, merge_preferences

    extracted = ExtractedPreferences(weather_preference="warm")
    form = ExtractedPreferences(weather_preference="warmer")
    merged, issues, questions = merge_preferences(extracted, form)

    assert issues == []
    assert questions == []
    assert merged.weather_preference == "warm"

    result = _parse(
        COMPLETE_TEXT,
        [COMPLETE_EXTRACTION],
        form_fields={"weather_preference": "warmer"},
    )

    assert result.status == "ready"
    assert result.request is not None
    assert result.request.weather_preference == "warm"
    assert not any("weather" in issue.lower() for issue in result.issues)
    assert not any("weather" in question.lower() for question in result.clarification_questions)


def test_common_written_date_formats_are_normalized():
    result = _parse(
        "From ZAG, dates are 21/09/2026 to 25/09/2026, EUR 400.",
        [
            {
                "origin_iata": "ZAG",
                "departure_date": "21/09/2026",
                "return_date": "September 25 2026",
                "budget": 400,
                "currency": "EUR",
            }
        ],
    )

    assert result.status == "ready"
    assert result.request is not None
    assert result.request.departure_date == date(2026, 9, 21)
    assert result.request.return_date == date(2026, 9, 25)


def test_yearless_dates_use_current_or_next_year():
    result = _parse(
        "From ZAG, 12.10 to 20.10, EUR 400.",
        [
            {
                "origin_iata": "ZAG",
                "departure_date": "12.10",
                "return_date": "20.10",
                "budget": 400,
                "currency": "EUR",
            }
        ],
    )
    next_year = _parse(
        "From ZAG, 01.02 to 05.02, EUR 400.",
        [
            {
                "origin_iata": "ZAG",
                "departure_date": "01.02",
                "return_date": "05.02",
                "budget": 400,
                "currency": "EUR",
            }
        ],
    )

    assert result.request is not None
    assert result.request.departure_date == date(2026, 10, 12)
    assert result.request.return_date == date(2026, 10, 20)
    assert next_year.request is not None
    assert next_year.request.departure_date == date(2027, 2, 1)
    assert next_year.request.return_date == date(2027, 2, 5)


def test_ambiguous_numeric_date_needs_input():
    result = _parse(
        "From ZAG, dates are 03/04/2026 to 08/04/2026, EUR 400.",
        [
            {
                "origin_iata": "ZAG",
                "departure_date": "03/04/2026",
                "return_date": "08/04/2026",
                "budget": 400,
                "currency": "EUR",
            }
        ],
    )

    assert result.status == "needs_input"
    assert any("departure date" in question.lower() for question in result.clarification_questions)


def test_weather_aliases_canonicalize_to_warm_or_cool():
    warm = _parse(
        "From ZAG, 21-25 September 2026, EUR 400, with less rain.",
        [
            {
                "origin_iata": "ZAG",
                "departure_date": "2026-09-21",
                "return_date": "2026-09-25",
                "budget": 400,
                "currency": "EUR",
                "weather_preference": "less rain",
            }
        ],
    )
    cool = _parse(
        "From ZAG, 21-25 September 2026, EUR 400, with more rain.",
        [
            {
                "origin_iata": "ZAG",
                "departure_date": "2026-09-21",
                "return_date": "2026-09-25",
                "budget": 400,
                "currency": "EUR",
                "weather_preference": "more rain",
            }
        ],
    )

    assert warm.request is not None and warm.request.weather_preference == "warm"
    assert cool.request is not None and cool.request.weather_preference == "cool"


def test_yearless_date_in_text_is_used_when_model_omits_dates():
    result = _parse(
        "warm 12.10, 500eur",
        [{"weather_preference": "warm", "budget": 500, "currency": "EUR"}],
        form_fields={"origin": "LAX", "budget": 500, "currency": "EUR"},
    )

    assert result.preferences is not None
    assert result.preferences.departure_date == date(2026, 10, 12)
    assert result.preferences.return_date is None
    assert result.status == "needs_input"
    assert any("return date" in question.lower() for question in result.clarification_questions)
    assert not any("departure date" in question.lower() for question in result.clarification_questions)


def test_yearless_date_range_in_text_is_used_when_model_omits_dates():
    result = _parse(
        "From ZAG, 12.10 to 20.10, EUR 400.",
        [{"origin_iata": "ZAG", "budget": 400, "currency": "EUR"}],
    )

    assert result.status == "ready"
    assert result.request is not None
    assert result.request.departure_date == date(2026, 10, 12)
    assert result.request.return_date == date(2026, 10, 20)


def test_single_yearless_date_plus_duration_infers_return():
    result = _parse(
        "From ZAG, 12.10, 4 days, EUR 400.",
        [
            {
                "origin_iata": "ZAG",
                "budget": 400,
                "currency": "EUR",
                "duration_days": 4,
            }
        ],
    )

    assert result.status == "ready"
    assert result.request is not None
    assert result.request.departure_date == date(2026, 10, 12)
    assert result.request.return_date == date(2026, 10, 16)
    assert result.request.duration_days == 4


def test_clarification_answer_ignores_example_dates_in_planner_questions():
    text = (
        "Original request:\nwarm 05.11, 500eur\n\n"
        "Initial form selections:\norigin: LAX\nbudget: 500\ncurrency: EUR\n\n"
        "The planner asked:\n"
        "What is your return date? For example: 16.10, 16/10/2026, or 2026-10-16.\n\n"
        "Authoritative answer (this overrides any conflicting initial form values):\n10.11"
    )
    result = _parse(
        text,
        [{"weather_preference": "warm", "budget": 500, "currency": "EUR"}],
        form_fields={"origin": "LAX", "budget": 500, "currency": "EUR"},
    )

    assert result.status == "ready"
    assert result.request is not None
    assert result.request.departure_date == date(2026, 11, 5)
    assert result.request.return_date == date(2026, 11, 10)


def test_from_until_yearless_dates_with_trailing_periods_are_ready():
    text = "warm, from 10.10. until 16.10. budget is 500eur, from LAX"
    omitted = _parse(
        text,
        [
            {
                "origin_iata": "LAX",
                "budget": 500,
                "currency": "EUR",
                "weather_preference": "warm",
            }
        ],
    )
    departure_only = _parse(
        text,
        [
            {
                "origin_iata": "LAX",
                "budget": 500,
                "currency": "EUR",
                "weather_preference": "warm",
                "departure_date": "10.10.",
            }
        ],
    )
    range_in_departure = _parse(
        text,
        [
            {
                "origin_iata": "LAX",
                "budget": 500,
                "currency": "EUR",
                "weather_preference": "warm",
                "departure_date": "from 10.10. until 16.10.",
            }
        ],
    )

    for result in (omitted, departure_only, range_in_departure):
        assert result.status == "ready"
        assert result.request is not None
        assert result.request.departure_date == date(2026, 10, 10)
        assert result.request.return_date == date(2026, 10, 16)
        assert not any("return date" in question.lower() for question in result.clarification_questions)

