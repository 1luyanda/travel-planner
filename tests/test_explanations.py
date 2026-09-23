from __future__ import annotations

import asyncio
from datetime import date
from types import SimpleNamespace

from backend.models.trip_request import TripRequest
from backend.services.explanations import explain_ranked_trips
from tests.fake_llm import FakeLLMClient

ROME_ID = "ZAG-ROM-2026-09-18"
LISBON_ID = "ZAG-LIS-2026-09-18"


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


def _ranked(destination_id: str, city: str, **overrides) -> SimpleNamespace:
    values = {
        "destination_id": destination_id,
        "destination_iata": "FCO" if city == "Rome" else "LIS",
        "city": city,
        "price_eur": 65,
        "changeover_count": 0,
        "flight_duration_minutes": 170,
        "trip_duration_days": 4,
        "average_max_temperature_c": 27.8,
        "price_score": 1.0,
        "weather_score": 0.8,
        "stops_score": 1.0,
        "duration_score": 0.9,
        "final_score": 0.92,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _explain(request, ranked, responses):
    client = FakeLLMClient(responses)
    result = asyncio.run(explain_ranked_trips(request, ranked, llm_client=client))
    return result, client


def test_supported_explanations_keep_destination_ids_and_order():
    ranked = [
        _ranked(ROME_ID, "Rome", price_eur=65, final_score=0.92),
        _ranked(LISBON_ID, "Lisbon", price_eur=189, final_score=0.70, destination_iata="LIS"),
    ]
    result, client = _explain(
        _request(),
        ranked,
        [
            {
                "explanations": [
                    {
                        "destination_id": LISBON_ID,
                        "evidence_ids": [f"{LISBON_ID}::within_budget"],
                    },
                    {
                        "destination_id": ROME_ID,
                        "evidence_ids": [
                            f"{ROME_ID}::within_budget",
                            f"{ROME_ID}::direct_flight",
                        ],
                    },
                ]
            }
        ],
    )

    assert result.status == "ok"
    assert [item.destination_id for item in result.explanations] == [ROME_ID, LISBON_ID]
    assert result.explanations[0].rank == 1
    assert result.explanations[1].rank == 2
    assert result.explanations[0].final_score == 0.92
    assert result.explanations[0].price_eur == 65
    assert {item.code for item in result.explanations[0].evidence} == {
        "within_budget",
        "direct_flight",
    }
    assert "65" in result.explanations[0].summary
    assert "189" in result.explanations[1].summary
    assert client.calls


def test_empty_ranked_input_does_not_call_the_model():
    client = FakeLLMClient([{"should_not": "be_called"}])
    result = asyncio.run(explain_ranked_trips(_request(), [], llm_client=client))

    assert result.status == "ok"
    assert result.explanations == []
    assert client.calls == []


def test_unknown_destination_id_is_ignored():
    ranked = [_ranked(ROME_ID, "Rome")]
    result, _ = _explain(
        _request(),
        ranked,
        [
            {
                "explanations": [
                    {
                        "destination_id": "UNKNOWN-ID",
                        "evidence_ids": [f"{ROME_ID}::within_budget"],
                    }
                ]
            }
        ],
    )

    assert result.status == "ok"
    assert [item.destination_id for item in result.explanations] == [ROME_ID]
    assert result.explanations[0].evidence == []
    assert any("UNKNOWN-ID" in issue for issue in result.issues)


def test_evidence_from_another_destination_is_rejected():
    ranked = [
        _ranked(ROME_ID, "Rome"),
        _ranked(LISBON_ID, "Lisbon", price_eur=189, destination_iata="LIS"),
    ]
    result, _ = _explain(
        _request(),
        ranked,
        [
            {
                "explanations": [
                    {
                        "destination_id": ROME_ID,
                        "evidence_ids": [f"{LISBON_ID}::within_budget"],
                    },
                    {
                        "destination_id": LISBON_ID,
                        "evidence_ids": [f"{LISBON_ID}::recorded_price"],
                    },
                ]
            }
        ],
    )

    assert result.status == "ok"
    rome = result.explanations[0]
    assert rome.destination_id == ROME_ID
    assert rome.evidence == []
    assert any("belongs to" in issue for issue in result.issues)
    assert "189" not in rome.summary


def test_over_budget_evidence_is_available_and_used():
    ranked = [_ranked(ROME_ID, "Rome", price_eur=500)]
    result, _ = _explain(
        _request(budget=400),
        ranked,
        [
            {
                "explanations": [
                    {
                        "destination_id": ROME_ID,
                        "evidence_ids": [f"{ROME_ID}::over_budget"],
                    }
                ]
            }
        ],
    )

    assert result.status == "ok"
    assert result.explanations[0].evidence[0].code == "over_budget"
    assert "500" in result.explanations[0].summary
    assert "400" in result.explanations[0].summary
    assert "within the" not in result.explanations[0].summary


def test_incompatible_currency_does_not_compare_budget():
    ranked = [_ranked(ROME_ID, "Rome", price_eur=65)]
    result, _ = _explain(
        _request(currency="USD"),
        ranked,
        [
            {
                "explanations": [
                    {
                        "destination_id": ROME_ID,
                        "evidence_ids": [
                            f"{ROME_ID}::within_budget",
                            f"{ROME_ID}::price_not_comparable",
                        ],
                    }
                ]
            }
        ],
    )

    codes = {item.code for item in result.explanations[0].evidence}
    assert "within_budget" not in codes
    assert "over_budget" not in codes
    assert "price_not_comparable" in codes
    assert "USD" in result.explanations[0].summary
    assert any("within_budget" in issue for issue in result.issues)


def test_requested_mood_is_not_treated_as_destination_quality():
    ranked = [_ranked(ROME_ID, "Rome")]
    result, _ = _explain(
        _request(moods=["relaxing"]),
        ranked,
        [
            {
                "explanations": [
                    {
                        "destination_id": ROME_ID,
                        "evidence_ids": [
                            f"{ROME_ID}::is_relaxing",
                            f"{ROME_ID}::mood_not_verified",
                        ],
                    }
                ]
            }
        ],
    )

    codes = {item.code for item in result.explanations[0].evidence}
    assert "mood_not_verified" in codes
    assert "is_relaxing" not in codes
    assert "not verified" in result.explanations[0].summary
    assert "is relaxing" not in result.explanations[0].summary.lower()


def test_cooler_weather_preference_uses_ranking_note():
    ranked = [_ranked(ROME_ID, "Rome", average_max_temperature_c=27.8)]
    result, _ = _explain(
        _request(weather_preference="cool"),
        ranked,
        [
            {
                "explanations": [
                    {
                        "destination_id": ROME_ID,
                        "evidence_ids": [
                            f"{ROME_ID}::cool_match",
                            f"{ROME_ID}::cool_preference_ranking_note",
                        ],
                    }
                ]
            }
        ],
    )

    codes = {item.code for item in result.explanations[0].evidence}
    assert "cool_preference_ranking_note" in codes
    assert "cool_match" not in codes
    summary = result.explanations[0].summary.lower()
    assert "lower maximum temperatures" in summary
    assert "is cool" not in summary


def test_invalid_model_output_is_repaired_on_second_attempt():
    ranked = [_ranked(ROME_ID, "Rome")]
    result, client = _explain(
        _request(),
        ranked,
        [
            "not-json",
            {
                "explanations": [
                    {
                        "destination_id": ROME_ID,
                        "evidence_ids": [f"{ROME_ID}::within_budget"],
                    }
                ]
            },
        ],
    )

    assert result.status == "ok"
    assert result.explanations[0].evidence[0].code == "within_budget"
    assert len(client.calls) == 2


def test_repeated_invalid_output_returns_error_without_explanations():
    ranked = [_ranked(ROME_ID, "Rome")]
    result, client = _explain(
        _request(),
        ranked,
        ["not-json", "{still invalid"],
    )

    assert result.status == "error"
    assert result.explanations == []
    assert len(client.calls) == 2
    assert any("invalid output twice" in issue for issue in result.issues)


def test_model_failure_returns_error_without_explanations():
    ranked = [_ranked(ROME_ID, "Rome")]
    result, client = _explain(
        _request(),
        ranked,
        [RuntimeError("network down"), RuntimeError("network down")],
    )

    assert result.status == "error"
    assert result.explanations == []
    assert len(client.calls) == 2
    assert any("failed" in issue for issue in result.issues)
