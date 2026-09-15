"""Tests for the data bridge and FastAPI candidate service boundary."""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from typing import Any

from backend.config import Settings
from backend.contracts import FlightQuery, OriginItem
from backend.repositories import CosmosDestinationRepository
from backend.services import CandidateService
from ranking import RankingConstraints, RankingPreferences, prepare_ranking_records, rank_candidates


MOCK_PATH = (
    Path(__file__).parents[1] / "mock_data" / "normalized_destinations.json"
)


def mock_records() -> list[dict[str, Any]]:
    payload = json.loads(MOCK_PATH.read_text(encoding="utf-8"))
    return payload["destinations"]


def cosmos_records() -> list[dict[str, Any]]:
    base = {
        "origin_id": "zagreb-hr",
        "origin_city": "Zagreb",
        "origin_country": "Croatia",
        "origin_iata": "ZAG",
        "currency": "EUR",
        "departure_at": "2026-09-21T15:55:00+02:00",
        "return_at": "2026-09-22T23:50:00+02:00",
        "outbound_stops": 0,
        "return_stops": 0,
        "duration_minutes": 170,
        "outbound_duration_minutes": 85,
        "return_duration_minutes": 85,
        "temp_max_c": 27.8,
        "temp_min_c": 18.75,
        "rain_pct": 13.0,
        "sunshine_hours": 11.96,
    }
    return [
        {
            **base,
            "id": "ZAG-ROM-2026-09-18",
            "destination_iata": "ROM",
            "destination_airport": "FCO",
            "destination_city": "Rome",
            "price_eur": 65,
        },
        {
            **base,
            "id": "ZAG-MLA-2026-09-18",
            "destination_iata": "MLA",
            "destination_city": "Malta",
            "price_eur": 76,
        },
        {
            **base,
            "id": "ZAG-LIS-2026-09-18",
            "destination_iata": "LIS",
            "destination_city": "Lisbon",
            "price_eur": 189,
        },
    ]


class FakeDataService:
    source_name = "test://normalized-destinations"

    async def get_destination_records(
        self,
        request: FlightQuery,
    ) -> list[dict[str, Any]]:
        return cosmos_records()


class FakeFlightsContainer:
    def __init__(self) -> None:
        self.query_arguments: dict[str, Any] = {}

    def query_items(self, **kwargs: Any) -> Any:
        self.query_arguments = kwargs

        async def rows() -> Any:
            for item in cosmos_records():
                yield item

        return rows()


class RankingBridgeTests(unittest.TestCase):
    def test_normalized_records_are_accepted(self) -> None:
        result = prepare_ranking_records(mock_records())

        self.assertGreaterEqual(len(result.candidates), 3)
        self.assertEqual(result.rejected, ())

    def test_hard_price_constraint_preserves_rejections(self) -> None:
        result = prepare_ranking_records(
            cosmos_records(),
            RankingConstraints(max_price_eur=70),
        )

        self.assertTrue(result.candidates)
        self.assertTrue(result.rejected)
        self.assertTrue(
            all(
                rejected.reasons[0].code == "over_budget"
                for rejected in result.rejected
            )
        )

    def test_flat_cosmos_records_are_accepted(self) -> None:
        result = prepare_ranking_records(cosmos_records())

        self.assertEqual(len(result.candidates), 3)
        self.assertEqual(result.rejected, ())
        self.assertIsNone(result.candidates[0].flight_retrieved_at)
        self.assertIsNone(result.candidates[0].weather_retrieved_at)
        rome = next(candidate for candidate in result.candidates if candidate.city == "Rome")
        self.assertEqual(rome.destination_iata, "FCO")
        self.assertEqual(rome.average_max_temperature_c, 27.8)
        self.assertEqual(rome.average_min_temperature_c, 18.75)
        self.assertEqual(rome.precipitation_probability_percent, 13)
        self.assertEqual(rome.sunshine_hours, 11.96)
        self.assertEqual(rome.flight_duration_minutes, 170)
        self.assertEqual(rome.trip_duration_days, 1)
        ranked = rank_candidates(result.candidates, RankingPreferences())
        self.assertEqual(len(ranked), 3)
        self.assertEqual(ranked[0].city, "Rome")

    def test_cosmos_stops_and_invalid_record_isolation(self) -> None:
        records = cosmos_records()
        records[0].update(outbound_stops=1, return_stops=2)
        records[1]["temp_max_c"] = "invalid"
        result = prepare_ranking_records(records)
        self.assertEqual(len(result.candidates), 2)
        self.assertEqual(len(result.rejected), 1)
        self.assertEqual(result.rejected[0].reasons[0].code, "invalid_data")
        rome = next(candidate for candidate in result.candidates if candidate.city == "Rome")
        self.assertEqual(rome.changeover_count, 3)

    def test_real_cosmos_origin_and_flight_documents_are_accepted(self) -> None:
        origin = OriginItem.model_validate(
            {
                "id": "zagreb-hr",
                "city": "Zagreb",
                "country": "Croatia",
                "country_code": "HR",
                "airports": ["ZAG"],
                "city_iata": ["ZAG"],
                "flight_count": 154,
                "_rid": "rPUJAIcvhrABAAAAAAAAAA==",
                "_self": "dbs/rPUJAA==/colls/rPUJAIcvhrA=/docs/rPUJAIcvhrABAAAAAAAAAA==/",
                "_etag": '"4b00c7ac-0000-1100-0000-6aa7fc9b0000"',
                "_attachments": "attachments/",
                "_ts": 1789394075,
            }
        )
        result = prepare_ranking_records(
            [
                {
                    "id": "ZAG-ROM-2026-09-18",
                    "origin_id": "zagreb-hr",
                    "origin_city": "Zagreb",
                    "origin_country": "Croatia",
                    "origin_country_code": "HR",
                    "origin_iata": "ZAG",
                    "origin_airport": "ZAG",
                    "destination_city": "Rome",
                    "destination_country": "Italy",
                    "destination_country_code": "IT",
                    "destination_iata": "ROM",
                    "destination_airport": "FCO",
                    "airport_name": "Leonardo da Vinci-Fiumicino Airport",
                    "price_eur": 65,
                    "currency": "EUR",
                    "departure_at": "2026-09-21T15:55:00+02:00",
                    "return_at": "2026-09-22T23:50:00+02:00",
                    "outbound_stops": 0,
                    "return_stops": 0,
                    "duration_minutes": 170,
                    "outbound_duration_minutes": 85,
                    "return_duration_minutes": 85,
                    "airline_code": "FR",
                    "temp_max_c": 27.8,
                    "temp_min_c": 18.75,
                    "rain_pct": 13,
                    "sunshine_hours": 11.96,
                    "latitude": 41.794594,
                    "longitude": 12.250346,
                    "_rid": "rPUJAOf9hykBAAAAAAAAAA==",
                    "_self": "dbs/rPUJAA==/colls/rPUJAOf9hyk=/docs/rPUJAOf9hykBAAAAAAAAAA==/",
                    "_etag": '"4c00bbc9-0000-1100-0000-6aa7fb630000"',
                    "_attachments": "attachments/",
                    "_ts": 1789393763,
                }
            ]
        )
        candidate = result.candidates[0]

        self.assertEqual(origin.id, "zagreb-hr")
        self.assertEqual(len(result.candidates), 1)
        self.assertEqual(candidate.city, "Rome")
        self.assertEqual(candidate.destination_iata, "FCO")
        self.assertEqual(candidate.price_eur, 65)
        self.assertEqual(candidate.precipitation_probability_percent, 13)


class CandidateServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_service_connects_data_and_validation_bridge(self) -> None:
        service = CandidateService(
            data_service=FakeDataService(),  # type: ignore[arg-type]
        )
        request = FlightQuery(
            origin_id="zagreb-hr",
        )

        response = await service.prepare(request)

        self.assertGreaterEqual(len(response.candidates), 3)
        self.assertEqual(response.rejected, [])
        self.assertTrue(all(candidate.flight_retrieved_at is None for candidate in response.candidates))
        self.assertEqual(
            response.data_source,
            "test://normalized-destinations",
        )

    async def test_cosmos_flight_query_uses_origin_partition(self) -> None:
        repository = CosmosDestinationRepository(
            Settings(
                cosmos_connection_string="placeholder",
                cosmos_database_name="TravelPlaner",
                frontend_origins=("http://localhost:5173",),
            )
        )
        container = FakeFlightsContainer()
        repository._flights = container  # type: ignore[assignment]

        records = await repository.get_candidates(
            FlightQuery(origin_id="zagreb-hr")
        )

        self.assertEqual(len(records), 3)
        prepared = prepare_ranking_records(records)
        self.assertFalse(prepared.rejected)
        self.assertEqual(len(rank_candidates(prepared.candidates)), 3)
        self.assertIn("c.origin_id = @origin_id", container.query_arguments["query"])
        self.assertIn(
            {"name": "@origin_id", "value": "zagreb-hr"},
            container.query_arguments["parameters"],
        )
        self.assertEqual(
            container.query_arguments["partition_key"],
            "zagreb-hr",
        )
        self.assertNotIn(
            "enable_cross_partition_query",
            container.query_arguments,
        )


if __name__ == "__main__":
    unittest.main()
