"""Load slim ranking JSON into Azure Cosmos DB.

One origins document per origin city, one flights document per trip.
Partition key on flights is origin_id (city + country, e.g. zagreb-hr).

Reads COSMOS_CONNECTION_STRING from .env. Does not print the secret.

Usage:
    python load_to_cosmos.py mock_data
    python load_to_cosmos.py Real_data
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import unicodedata
from pathlib import Path
from typing import Any

from concurrent.futures import ThreadPoolExecutor, as_completed

from azure.cosmos import CosmosClient, exceptions

PROJECT_DIR = Path(__file__).resolve().parent
ENV_FILE = PROJECT_DIR / ".env"
DEFAULT_DATABASE = "TravelPlaner"
ORIGINS_CONTAINER = "origins"
FLIGHTS_CONTAINER = "flights"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(line_buffering=True)


def slug(value: str) -> str:
    folded = unicodedata.normalize("NFKD", value)
    ascii_text = folded.encode("ascii", "ignore").decode("ascii")
    cleaned = re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")
    return cleaned or "unknown"


def origin_fields(item: dict[str, Any]) -> dict[str, str]:
    origin = item.get("origin") or {}
    flight = item.get("flight") or {}
    city = str(origin.get("city") or "").strip()
    country = str(origin.get("country") or "").strip()
    country_code = str(origin.get("country_code") or "").strip().upper()
    city_iata = str(origin.get("iata") or flight.get("origin_iata") or "").strip().upper()
    airport = str(
        origin.get("airport_iata") or flight.get("origin_airport_iata") or ""
    ).strip().upper()
    if not city:
        city = city_iata or "Unknown"
    if not country_code:
        country_code = "XX"
    return {
        "city": city,
        "country": country,
        "country_code": country_code,
        "city_iata": city_iata,
        "airport": airport,
    }


def make_id(city: str, country_code: str, used: set[str]) -> str:
    base = f"{slug(city)}-{country_code.lower()}"
    candidate = base
    n = 2
    while candidate in used:
        candidate = f"{base}-{n}"
        n += 1
    used.add(candidate)
    return candidate


def resolve_files(raw: str | None) -> list[Path]:
    if not raw:
        return [PROJECT_DIR / "mock_data" / "normalized_destinations.json"]
    target = Path(raw)
    if not target.is_absolute():
        target = PROJECT_DIR / target
    if target.is_dir():
        return [target / "normalized_destinations.json"]
    return [target]


def load_dotenv(path: Path = ENV_FILE) -> None:
    if not path.exists():
        raise SystemExit(f"Missing {path}. Add COSMOS_CONNECTION_STRING there.")
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ[key] = value


def parse_cosmos_connection(conn: str) -> tuple[str, str]:
    """Return (endpoint_url, account_key). Never print these."""
    conn = conn.strip().strip('"').strip("'")
    settings: dict[str, str] = {}
    if conn.startswith("https://"):
        settings["AccountEndpoint"] = conn
    else:
        for part in conn.rstrip(";").split(";"):
            part = part.strip()
            if not part or "=" not in part:
                continue
            key, value = part.split("=", 1)
            settings[key.strip()] = value.strip().strip('"').strip("'")

    endpoint = settings.get("AccountEndpoint") or ""
    while endpoint.startswith("AccountEndpoint="):
        endpoint = endpoint.split("=", 1)[1].strip().strip('"').strip("'")
    account_key = (
        settings.get("AccountKey")
        or os.getenv("COSMOS_ACCOUNT_KEY")
        or os.getenv("AccountKey")
        or ""
    ).strip().strip('"').strip("'")

    if not endpoint.startswith("https://"):
        raise SystemExit(
            "COSMOS_CONNECTION_STRING must be the PRIMARY CONNECTION STRING "
            "from Cosmos → Keys (AccountEndpoint=https://...;AccountKey=...)."
        )
    if not account_key:
        raise SystemExit(
            "COSMOS_CONNECTION_STRING is missing AccountKey. "
            "Copy the full PRIMARY CONNECTION STRING, not only the endpoint."
        )
    return endpoint, account_key


def cosmos_settings() -> tuple[str, str, str]:
    load_dotenv()
    conn = (os.getenv("COSMOS_CONNECTION_STRING") or "").strip()
    if not conn:
        raise SystemExit("Set COSMOS_CONNECTION_STRING in .env first.")
    endpoint, account_key = parse_cosmos_connection(conn)
    database = (os.getenv("COSMOS_DATABASE") or DEFAULT_DATABASE).strip()
    return endpoint, account_key, database


def flatten(item: dict[str, Any]) -> dict[str, Any]:
    flight = item.get("flight") or {}
    origin = item.get("origin") or {}
    dest = item.get("destination") or {}
    weather = item.get("weather") or {}
    country = item.get("country") or {}
    return {
        "id": item.get("id"),
        "origin_city": origin.get("city"),
        "origin_country": origin.get("country"),
        "origin_country_code": origin.get("country_code"),
        "origin_iata": origin.get("iata") or flight.get("origin_iata"),
        "origin_airport_iata": origin.get("airport_iata")
        or flight.get("origin_airport_iata"),
        "city": dest.get("city"),
        "country": country.get("common_name"),
        "country_code": dest.get("country_code") or country.get("alpha_2"),
        "destination_iata": flight.get("destination_iata"),
        "destination_airport_iata": flight.get("destination_airport_iata"),
        "airport_name": dest.get("airport"),
        "price_eur": flight.get("price"),
        "currency": flight.get("currency"),
        "departure_at": flight.get("departure_at"),
        "return_at": flight.get("return_at"),
        "outbound_stops": flight.get("outbound_stops"),
        "return_stops": flight.get("return_stops"),
        "duration_minutes": flight.get("duration_minutes"),
        "outbound_duration_minutes": flight.get("outbound_duration_minutes"),
        "return_duration_minutes": flight.get("return_duration_minutes"),
        "airline_code": flight.get("airline_code"),
        "temp_max_c": weather.get("average_max_temperature_c"),
        "temp_min_c": weather.get("average_min_temperature_c"),
        "rain_pct": weather.get("average_precipitation_probability_percent"),
        "sunshine_hours": weather.get("average_sunshine_hours"),
        "latitude": dest.get("latitude"),
        "longitude": dest.get("longitude"),
    }


def to_number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def flight_document(item: dict[str, Any], origin_id: str, fields: dict[str, str]) -> dict[str, Any]:
    row = flatten(item)
    doc_id = str(row.get("id") or "").strip()
    if not doc_id:
        doc_id = (
            f"{fields['city_iata'] or 'UNK'}-"
            f"{row.get('destination_iata') or 'UNK'}"
        )
    return {
        "id": doc_id,
        "origin_id": origin_id,
        "origin_city": fields["city"],
        "origin_country": fields["country"],
        "origin_country_code": fields["country_code"],
        "origin_iata": fields["city_iata"] or None,
        "origin_airport": fields["airport"] or None,
        "destination_city": row.get("city"),
        "destination_country": row.get("country"),
        "destination_country_code": row.get("country_code"),
        "destination_iata": row.get("destination_iata"),
        "destination_airport": row.get("destination_airport_iata"),
        "airport_name": row.get("airport_name"),
        "price_eur": to_number(row.get("price_eur")),
        "currency": row.get("currency"),
        "departure_at": row.get("departure_at"),
        "return_at": row.get("return_at"),
        "outbound_stops": to_number(row.get("outbound_stops")),
        "return_stops": to_number(row.get("return_stops")),
        "duration_minutes": to_number(row.get("duration_minutes")),
        "outbound_duration_minutes": to_number(row.get("outbound_duration_minutes")),
        "return_duration_minutes": to_number(row.get("return_duration_minutes")),
        "airline_code": row.get("airline_code"),
        "temp_max_c": to_number(row.get("temp_max_c")),
        "temp_min_c": to_number(row.get("temp_min_c")),
        "rain_pct": to_number(row.get("rain_pct")),
        "sunshine_hours": to_number(row.get("sunshine_hours")),
        "latitude": to_number(row.get("latitude")),
        "longitude": to_number(row.get("longitude")),
    }


def origin_document(origin_id: str, bucket: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": origin_id,
        "city": bucket["city"],
        "country": bucket["country"],
        "country_code": bucket["country_code"],
        "airports": sorted(bucket["airports"]),
        "city_iata": sorted(bucket["city_iata"]),
        "flight_count": len(bucket["flights"]),
    }


def upsert_with_retry(container, document: dict[str, Any], attempts: int = 8) -> None:
    delay = 0.5
    for attempt in range(attempts):
        try:
            container.upsert_item(document)
            return
        except exceptions.CosmosHttpResponseError as error:
            if error.status_code != 429 or attempt == attempts - 1:
                raise
            time.sleep(delay)
            delay = min(delay * 2, 8)


def upsert_many(container, documents: list[dict[str, Any]], workers: int) -> int:
    done = 0
    chunk_size = max(workers * 8, 32)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for start in range(0, len(documents), chunk_size):
            chunk = documents[start : start + chunk_size]
            futures = [pool.submit(upsert_with_retry, container, doc) for doc in chunk]
            for future in as_completed(futures):
                future.result()
                done += 1
                if done % 1000 == 0 or done == len(documents):
                    print(f"  upserted {done:,} / {len(documents):,} flights...")
    return done


def build_groups(items: list[dict[str, Any]]) -> list[tuple[str, dict[str, Any]]]:
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    order: list[tuple[str, str]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        fields = origin_fields(item)
        key = (fields["city"], fields["country_code"])
        bucket = grouped.get(key)
        if bucket is None:
            bucket = {
                "city": fields["city"],
                "country": fields["country"],
                "country_code": fields["country_code"],
                "airports": set(),
                "city_iata": set(),
                "flights": [],
            }
            grouped[key] = bucket
            order.append(key)
        if fields["airport"]:
            bucket["airports"].add(fields["airport"])
        if fields["city_iata"]:
            bucket["city_iata"].add(fields["city_iata"])
        if fields["country"] and not bucket["country"]:
            bucket["country"] = fields["country"]
        bucket["flights"].append((item, fields))
    order.sort(key=lambda key: (key[0].casefold(), key[1]))
    used_ids: set[str] = set()
    rows = []
    for key in order:
        bucket = grouped[key]
        origin_id = make_id(bucket["city"], bucket["country_code"], used_ids)
        rows.append((origin_id, bucket))
    return rows


def load_file(
    json_path: Path, origins_container, flights_container, workers: int
) -> None:
    print(f"Loading {json_path}...")
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SystemExit(f"{json_path} should be an object with a destinations list.")
    groups = build_groups(payload.get("destinations") or [])
    origin_docs = []
    flight_docs = []
    for origin_id, bucket in groups:
        origin_docs.append(origin_document(origin_id, bucket))
        for item, fields in bucket["flights"]:
            flight_docs.append(flight_document(item, origin_id, fields))
    print(f"  upserting {len(origin_docs):,} origins...")
    for i, document in enumerate(origin_docs, 1):
        upsert_with_retry(origins_container, document)
        if i % 100 == 0 or i == len(origin_docs):
            print(f"  upserted {i:,} / {len(origin_docs):,} origins...")
    print(f"  upserting {len(flight_docs):,} flights ({workers} workers)...")
    upsert_many(flights_container, flight_docs, workers)
    print(f"  {len(origin_docs):,} origins  {len(flight_docs):,} flights")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Load ranking JSON into Cosmos DB origins and flights containers."
    )
    parser.add_argument(
        "path",
        nargs="?",
        default="mock_data",
        help="JSON file or folder (default: mock_data).",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=8,
        help="Parallel flight upserts (default: 8).",
    )
    args = parser.parse_args(argv)
    workers = max(1, args.workers)

    endpoint, account_key, database_name = cosmos_settings()
    client = CosmosClient(url=endpoint, credential=account_key)
    database = client.get_database_client(database_name)
    origins = database.get_container_client(ORIGINS_CONTAINER)
    flights = database.get_container_client(FLIGHTS_CONTAINER)
    print(f"Database: {database_name}  containers: {ORIGINS_CONTAINER}, {FLIGHTS_CONTAINER}")

    files = resolve_files(args.path)
    for path in files:
        if not path.exists():
            print(f"Skip missing {path}")
            continue
        load_file(path, origins, flights, workers)
    print("Done. Check Data Explorer → Items. Do not upload the 148 MB JSON there.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
