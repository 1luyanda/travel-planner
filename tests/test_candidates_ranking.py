"""Live check: FastAPI /api/candidates → rank_candidates.

Requires the API: python3.13.exe -m uvicorn backend.main:app --reload

Run from the project root:

    python3.13.exe -m unittest tests.test_candidates_ranking
"""

from __future__ import annotations

import json
import unittest
from datetime import datetime
from urllib.error import URLError
from urllib.request import urlopen

from ranking import RankingCandidate, RankingPreferences, rank_candidates

URL = "http://127.0.0.1:8000/api/candidates?origin_id=zagreb-hr"


def _parse_timestamp(value: object) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _to_ranking_candidate(record: dict) -> RankingCandidate:
    return RankingCandidate(
        destination_id=record["destination_id"],
        destination_iata=record["destination_iata"],
        city=record["city"],
        price_eur=record["price_eur"],
        changeover_count=record["changeover_count"],
        flight_duration_minutes=record["flight_duration_minutes"],
        trip_duration_days=record["trip_duration_days"],
        average_max_temperature_c=record["average_max_temperature_c"],
        average_min_temperature_c=record.get("average_min_temperature_c"),
        precipitation_probability_percent=record[
            "precipitation_probability_percent"
        ],
        sunshine_hours=record.get("sunshine_hours"),
        max_wind_speed_kmh=record.get("max_wind_speed_kmh"),
        airport_distance_km=record.get("airport_distance_km"),
        flight_retrieved_at=_parse_timestamp(record.get("flight_retrieved_at")),
        weather_retrieved_at=_parse_timestamp(
            record.get("weather_retrieved_at")
        ),
    )


class CandidatesRankingTests(unittest.TestCase):
    payload: dict
    candidates: tuple[RankingCandidate, ...]

    @classmethod
    def setUpClass(cls) -> None:
        try:
            with urlopen(URL, timeout=30) as response:
                cls.payload = json.load(response)
        except (URLError, TimeoutError, OSError) as error:
            raise unittest.SkipTest(
                f"FastAPI is not reachable at {URL}: {error}"
            ) from error

        records = cls.payload.get("candidates")
        if not isinstance(records, list):
            raise unittest.SkipTest(
                "Response has no candidates list; is the API using /api/candidates?"
            )
        cls.candidates = tuple(_to_ranking_candidate(item) for item in records)

    def test_response_is_for_zagreb(self) -> None:
        self.assertEqual(self.payload["origin_id"], "zagreb-hr")
        self.assertGreaterEqual(len(self.candidates), 1)

    def test_rank_candidates_keeps_every_valid_offer(self) -> None:
        ranked = rank_candidates(self.candidates, RankingPreferences())

        self.assertEqual(len(ranked), len(self.candidates))
        scores = [item.final_score for item in ranked]
        self.assertEqual(scores, sorted(scores, reverse=True))
        self.assertTrue(all(item.city for item in ranked))

        print(f"\nReceived {len(ranked)} candidates\n")
        for position, item in enumerate(ranked, start=1):
            print(
                f"{position}. {item.city:15} "
                f"€{item.price_eur:<6} "
                f"stops={item.changeover_count:<2} "
                f"duration={item.flight_duration_minutes:<4} "
                f"temp={item.average_max_temperature_c:<5} "
                f"score={item.final_score:.3f}"
            )


if __name__ == "__main__":
    unittest.main()
