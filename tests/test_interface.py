"""Storage-neutral preparation tests with synthetic records."""

from copy import deepcopy
from dataclasses import fields
from datetime import datetime, timezone
from unittest.mock import mock_open
import json

import pytest

from ranking import (
    CandidatePreparationResult,
    RankingConstraints,
    prepare_ranking_data,
    prepare_ranking_records,
    rank_destinations,
)


def flat_record(**overrides):
    record = {
        "destination_id": "offer-rome",
        "destination_iata": "FCO",
        "city": "Rome",
        "price_eur": 65,
        "changeover_count": 0,
        "flight_duration_minutes": 170,
        "trip_duration_days": 4,
        "average_max_temperature_c": 27.8,
        "precipitation_probability_percent": 13,
        "flight_retrieved_at": "2026-09-11T14:03:13Z",
        "weather_retrieved_at": "2026-09-11T14:03:16Z",
    }
    record.update(overrides)
    return record


def nested_record():
    return {
        "id": "offer-athens",
        "destination": {"city": "Athens"},
        "flight": {
            "destination_airport_iata": "ATH",
            "price": 260,
            "currency": "EUR",
            "outbound_stops": 1,
            "return_stops": 2,
            "outbound_duration_minutes": 215,
            "return_duration_minutes": 360,
            "duration_minutes": 1140,
            "departure_at": "2026-09-21T11:00:00+02:00",
            "return_at": "2026-09-29T09:35:00+03:00",
            "retrieved_at": "2026-09-11T14:03:13Z",
        },
        "weather": {
            "average_max_temperature_c": 28.82,
            "average_precipitation_probability_percent": 9,
            "retrieved_at": "2026-09-11T14:03:16Z",
        },
    }


def test_nested_round_trip_duration_and_changeovers():
    result = prepare_ranking_records([nested_record()])
    assert not result.rejected
    candidate, = result.candidates
    assert candidate.flight_duration_minutes == 575
    assert candidate.changeover_count == 3
    assert candidate.trip_duration_days == 8


def test_flat_totals_are_used_directly_and_take_precedence():
    record = nested_record()
    record.update(flight_duration_minutes=170, changeover_count=0)
    result = prepare_ranking_records([flat_record(), record])
    assert not result.rejected
    assert all(candidate.flight_duration_minutes == 170 for candidate in result.candidates)
    assert all(candidate.changeover_count == 0 for candidate in result.candidates)


@pytest.mark.parametrize("field,value", [
    ("outbound_duration_minutes", None),
    ("return_duration_minutes", None),
    ("outbound_duration_minutes", 215.5),
    ("return_duration_minutes", "invalid"),
    ("return_duration_minutes", -215),
])
def test_nested_duration_requires_both_whole_legs_and_positive_total(field, value):
    record = nested_record()
    record["flight"][field] = value
    result = prepare_ranking_records([record, flat_record()])
    assert len(result.candidates) == 1
    assert result.rejected[0].reasons[0].code == "invalid_data"


def test_legacy_duration_fields_are_not_used_as_fallback():
    record = flat_record()
    del record["flight_duration_minutes"]
    record["duration_minutes"] = 170
    result = prepare_ranking_records([record])
    assert not result.candidates
    assert result.rejected[0].reasons[0].code == "invalid_data"


def test_preparation_is_path_free_non_mutating_and_accepts_generators(monkeypatch):
    def unexpected_read(*args, **kwargs):
        pytest.fail("Core preparation must not read files")

    monkeypatch.setattr("ranking.interface._read_records", unexpected_read)
    records = [nested_record(), flat_record()]
    original = deepcopy(records)
    result = prepare_ranking_records(records)
    assert result == prepare_ranking_records(record for record in reversed(records))
    assert records == original
    assert {field.name for field in fields(CandidatePreparationResult)} == {
        "candidates", "rejected"
    }
    assert len(rank_destinations(list(result.candidates))) == 2
    assert prepare_ranking_records([]) == CandidatePreparationResult((), ())


@pytest.mark.parametrize("field,value", [
    ("destination_id", None), ("city", " "),
    ("destination_iata", "FC"), ("destination_iata", "F1O"),
    ("price_eur", 0), ("price_eur", -1), ("price_eur", float("nan")),
    ("price_eur", 10**400),
    ("changeover_count", -1), ("changeover_count", 0.5),
    ("flight_duration_minutes", 0), ("flight_duration_minutes", -1),
    ("flight_duration_minutes", 170.5),
    ("average_max_temperature_c", 71), ("average_max_temperature_c", -101),
    ("average_max_temperature_c", float("inf")),
    ("average_min_temperature_c", 71),
    ("precipitation_probability_percent", -1),
    ("precipitation_probability_percent", 101),
    ("flight_retrieved_at", None), ("weather_retrieved_at", None),
    ("weather_retrieved_at", "not-a-timestamp"),
])
def test_invalid_destination_is_rejected_without_blocking_valid_one(field, value):
    invalid = flat_record(destination_id="bad-offer")
    invalid[field] = value
    result = prepare_ranking_records([invalid, flat_record()])
    assert len(result.candidates) == len(result.rejected) == 1
    assert result.candidates[0].destination_id == "offer-rome"
    rejection = result.rejected[0]
    assert rejection.reasons[0].code == "invalid_data"
    assert rejection.reasons[0].message
    if field != "destination_id":
        assert rejection.destination_id == "bad-offer"


def test_non_eur_price_is_rejected():
    record = nested_record()
    record["flight"]["currency"] = "USD"
    result = prepare_ranking_records([record])
    assert not result.candidates
    assert "currency" in result.rejected[0].reasons[0].message


def test_malformed_records_have_structured_rejections():
    result = prepare_ranking_records([None, [], {}, flat_record()])
    assert len(result.candidates) == 1
    assert len(result.rejected) == 3
    assert all(item.reasons[0].code == "invalid_data" for item in result.rejected)


def test_all_hard_constraint_failures_and_inclusive_boundaries():
    constraints = RankingConstraints(
        max_price_eur=65, direct_only=True, max_flight_duration_minutes=170
    )
    result = prepare_ranking_records([nested_record(), flat_record()], constraints)
    assert len(result.candidates) == 1
    assert [reason.code for reason in result.rejected[0].reasons] == [
        "over_budget", "not_direct", "flight_too_long"
    ]
    # The corrected sum passes, even though flight.duration_minutes is 1140.
    result = prepare_ranking_records(
        [nested_record()], RankingConstraints(max_flight_duration_minutes=575)
    )
    assert len(result.candidates) == 1


def test_candidates_and_rejections_sort_by_iata_then_identity():
    records = [flat_record(destination_id="b"), flat_record(destination_id="a"),
               flat_record(destination_id="c", destination_iata="ATH"),
               flat_record(destination_id="bad-b", price_eur=-1),
               flat_record(destination_id="bad-a", price_eur=-1)]
    result = prepare_ranking_records(records)
    assert [item.destination_id for item in result.candidates] == ["c", "a", "b"]
    assert [item.destination_id for item in result.rejected] == ["bad-a", "bad-b"]
    assert result == prepare_ranking_records(reversed(records))


def test_optional_features_timestamps_and_numeric_strings():
    record = flat_record(
        destination_iata="fco", price_eur="65", flight_duration_minutes="170",
        changeover_count="0", average_min_temperature_c=18,
        sunshine_hours=12, max_wind_speed_kmh=20, airport_distance_km=30,
        flight_retrieved_at=datetime(2026, 9, 11, tzinfo=timezone.utc),
    )
    candidate, = prepare_ranking_records([record]).candidates
    assert candidate.destination_iata == "FCO"
    assert candidate.price_eur == 65
    assert candidate.flight_duration_minutes == 170
    assert candidate.average_min_temperature_c == 18
    assert candidate.sunshine_hours == 12
    assert candidate.max_wind_speed_kmh == 20
    assert candidate.airport_distance_km == 30
    assert candidate.flight_retrieved_at == record["flight_retrieved_at"]
    assert candidate.weather_retrieved_at.tzinfo is not None
    minimal, = prepare_ranking_records([flat_record()]).candidates
    assert minimal.average_min_temperature_c is None
    assert minimal.airport_distance_km is None


@pytest.mark.parametrize("suffix", ["json", "csv"])
def test_file_adapter_delegates_to_core_without_real_files(monkeypatch, suffix):
    record = flat_record()
    if suffix == "json":
        monkeypatch.setattr("pathlib.Path.read_text", lambda *args, **kwargs:
                            json.dumps({"destinations": [record]}))
    else:
        text = ",".join(record) + "\n" + ",".join(map(str, record.values())) + "\n"
        monkeypatch.setattr("pathlib.Path.open", mock_open(read_data=text))
    constraints = RankingConstraints(max_price_eur=60)
    calls = []

    def prepare_spy(records, active_constraints):
        calls.append(active_constraints)
        return prepare_ranking_records(records, active_constraints)

    monkeypatch.setattr("ranking.interface.prepare_ranking_records", prepare_spy)
    assert prepare_ranking_data(f"synthetic.{suffix}", constraints) == (
        prepare_ranking_records([record], constraints)
    )
    assert calls == [constraints]
