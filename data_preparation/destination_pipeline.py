#!/usr/bin/env python3
"""Fetch and snapshot destination data used by the Travel Planner.

The script calls Travelpayouts, Open-Meteo, and REST Countries, then writes
``normalized_destinations.json``. That is the only file ranking, frontend, and
``check_missing_data.py`` need. Weather is stored as averages only (temperature,
rain chance, sunshine — no daily arrays and no wind).

Raw API snapshots may also be written next to it for pipeline debugging. They
are optional and are not consumed by the rest of the team.

Required .env values:
    TRAVELPAYOUTS_TOKEN=YOUR_TRAVELPAYOUTS_TOKEN
    REST_COUNTRIES_API_KEY=YOUR_REST_COUNTRIES_API_KEY

Optional .env values:
    TRAVEL_ORIGIN=ALL
    TRAVEL_DESTINATIONS=BCN,LIS,FCO,ATH,PMI,AGP,NAP,MLA
    TRAVEL_CURRENCY=EUR
    TRAVEL_DEPARTURE_DATE=2026-09-18
    TRAVEL_RETURN_DATE=2026-09-22
    TRAVEL_LIMIT=50
    TRAVEL_MARKET=
    MOCK_OUTPUT_DIR=mock_data

TRAVEL_ORIGIN=ALL (default) queries every flightable city as origin.
Set TRAVEL_ORIGIN=ZAG to restrict to one city.
"""

from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any


PROJECT_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_DIR / ".env"
HTTP_TIMEOUT_SECONDS = 25
USER_AGENT = "team-4-travel-planner/1.0"

TRAVELPAYOUTS_FLIGHTS_URL = (
    "https://api.travelpayouts.com/aviasales/v3/prices_for_dates"
)
TRAVELPAYOUTS_CITIES_URL = "https://api.travelpayouts.com/data/en/cities.json"
TRAVELPAYOUTS_AIRPORTS_URL = "https://api.travelpayouts.com/data/en/airports.json"
TRAVELPAYOUTS_AIRLINES_URL = "https://api.travelpayouts.com/data/en/airlines.json"
TRAVELPAYOUTS_COUNTRIES_URL = "https://api.travelpayouts.com/data/en/countries.json"

# Travelpayouts uses non-ISO codes for a few places. Map them so country
# lookup and frontend labels still work (Ercan, Sukhumi).
COUNTRY_CODE_ALIASES = {
    "NY": "CY",
    "AB": "GE",
}
OPEN_METEO_GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
OPEN_METEO_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
REST_COUNTRIES_URL = "https://api.restcountries.com/countries/v5"

PLACEHOLDER_VALUES = {
    "",
    "YOUR_TRAVELPAYOUTS_TOKEN",
    "YOUR_REST_COUNTRIES_API_KEY",
    "replace_me",
}


@dataclass(frozen=True)
class Config:
    travelpayouts_token: str
    rest_countries_api_key: str
    origin: str
    destinations: tuple[str, ...]
    currency: str
    departure_date: date
    return_date: date
    limit: int
    market: str
    output_dir: Path


class PipelineError(RuntimeError):
    """Raised when required data cannot be fetched or normalized."""


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_z(value: datetime | None = None) -> str:
    timestamp = value or utc_now()
    return timestamp.astimezone(timezone.utc).isoformat(
        timespec="seconds"
    ).replace("+00:00", "Z")


def load_dotenv(path: Path = ENV_FILE) -> None:
    """Load a simple .env file without adding a third-party dependency."""
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, value)


def required_secret(name: str, placeholder: str) -> str:
    value = os.getenv(name, placeholder).strip()
    if value in PLACEHOLDER_VALUES or value.startswith("YOUR_"):
        raise PipelineError(
            f"Set {name} in {ENV_FILE} before running the pipeline."
        )
    return value


def parse_iso_date(name: str, default: date) -> date:
    raw_value = os.getenv(name, default.isoformat())
    try:
        return date.fromisoformat(raw_value)
    except ValueError as error:
        raise PipelineError(f"{name} must use YYYY-MM-DD format.") from error


def load_config() -> Config:
    load_dotenv()
    today = utc_now().date()
    departure_date = parse_iso_date(
        "TRAVEL_DEPARTURE_DATE", today + timedelta(days=7)
    )
    return_date = parse_iso_date(
        "TRAVEL_RETURN_DATE", departure_date + timedelta(days=4)
    )
    if return_date <= departure_date:
        raise PipelineError(
            "TRAVEL_RETURN_DATE must be after TRAVEL_DEPARTURE_DATE."
        )
    if return_date > today + timedelta(days=16):
        raise PipelineError(
            "Open-Meteo forecasts support at most 16 days. Choose an earlier "
            "TRAVEL_RETURN_DATE when generating live forecast fixtures."
        )

    try:
        limit = int(os.getenv("TRAVEL_LIMIT", "50"))
    except ValueError as error:
        raise PipelineError("TRAVEL_LIMIT must be an integer.") from error
    if not 1 <= limit <= 1000:
        raise PipelineError("TRAVEL_LIMIT must be between 1 and 1000.")

    output_setting = Path(os.getenv("MOCK_OUTPUT_DIR", "mock_data"))
    output_dir = (
        output_setting
        if output_setting.is_absolute()
        else PROJECT_DIR / output_setting
    )

    return Config(
        travelpayouts_token=required_secret(
            "TRAVELPAYOUTS_TOKEN", "YOUR_TRAVELPAYOUTS_TOKEN"
        ),
        rest_countries_api_key=required_secret(
            "REST_COUNTRIES_API_KEY", "YOUR_REST_COUNTRIES_API_KEY"
        ),
        origin=os.getenv("TRAVEL_ORIGIN", "ALL").strip().upper(),
        destinations=tuple(
            code.strip().upper()
            for code in os.getenv(
                "TRAVEL_DESTINATIONS",
                "BCN,LIS,FCO,ATH,PMI,AGP,NAP,MLA,CTA,DBV",
            ).split(",")
            if code.strip()
        ),
        currency=os.getenv("TRAVEL_CURRENCY", "EUR").strip().upper(),
        departure_date=departure_date,
        return_date=return_date,
        limit=limit,
        market=os.getenv("TRAVEL_MARKET", "").strip().lower(),
        output_dir=output_dir,
    )


def get_json(
    base_url: str,
    *,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[Any, str, str]:
    """Return decoded JSON, retrieval time, and a secret-free request URL."""
    query = urllib.parse.urlencode(params or {})
    request_url = f"{base_url}?{query}" if query else base_url
    request_headers = {
        "Accept": "application/json",
        "Accept-Encoding": "identity",
        "User-Agent": USER_AGENT,
        **(headers or {}),
    }
    request = urllib.request.Request(request_url, headers=request_headers)

    last_error: Exception | None = None
    for attempt in range(5):
        try:
            with urllib.request.urlopen(
                request, timeout=HTTP_TIMEOUT_SECONDS
            ) as response:
                charset = response.headers.get_content_charset() or "utf-8"
                payload = json.loads(response.read().decode(charset))
            return payload, iso_z(), request_url
        except urllib.error.HTTPError as error:
            details = error.read().decode("utf-8", errors="replace")[:500]
            last_error = PipelineError(
                f"HTTP {error.code} from {base_url}: {details}"
            )
            if error.code in {429, 500, 502, 503, 504} and attempt < 4:
                time.sleep(2 ** attempt)
                continue
            raise last_error from error
        except urllib.error.URLError as error:
            last_error = PipelineError(
                f"Could not reach {base_url}: {error.reason}"
            )
            if attempt < 4:
                time.sleep(2 ** attempt)
                continue
            raise last_error from error
        except json.JSONDecodeError as error:
            raise PipelineError(f"Invalid JSON returned by {base_url}.") from error
    raise last_error or PipelineError(f"Could not reach {base_url}.")


def snapshot(
    source: str,
    request_url: str | list[str],
    retrieved_at: str,
    data: Any,
) -> dict[str, Any]:
    return {
        "source": source,
        "request_url": request_url,
        "retrieved_at": retrieved_at,
        "data": data,
    }


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    compact = path.name == "normalized_destinations.json"
    path.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=None if compact else 2,
            separators=(",", ":") if compact else None,
        )
        + "\n",
        encoding="utf-8",
    )


def fetch_travelpayouts_flights(
    config: Config,
    origins: list[str],
) -> tuple[dict[str, Any], str, list[str]]:
    """Pull unique cached routes for every origin (or one origin if restricted)."""
    headers = {"X-Access-Token": config.travelpayouts_token}
    request_log: list[dict[str, Any]] = []
    candidates: dict[str, dict[str, Any]] = {}
    log_lock = threading.Lock()
    candidate_lock = threading.Lock()
    latest_retrieved_at = iso_z()

    def ingest(rows: list[dict[str, Any]]) -> None:
        for row in rows:
            origin_code = str(row.get("origin") or "").upper()
            dest_code = str(row.get("destination") or "").upper()
            if not origin_code or not dest_code or origin_code == dest_code:
                continue
            key = f"{origin_code}-{dest_code}"
            with candidate_lock:
                current = candidates.get(key)
                if current is None or float(row.get("price", float("inf"))) < float(
                    current.get("price", float("inf"))
                ):
                    candidates[key] = row

    def run_query(
        *,
        origin: str | None,
        destination: str | None,
        use_month: bool,
        unique: bool,
        include_dates: bool = True,
        page: int = 1,
        page_size: int = 1000,
    ) -> int:
        nonlocal latest_retrieved_at
        if not origin and not destination:
            raise PipelineError("Travelpayouts requires origin or destination.")
        params: dict[str, Any] = {
            "one_way": "false",
            "direct": "false",
            "sorting": "price" if include_dates else "route",
            "unique": str(unique).lower(),
            "currency": config.currency.lower(),
            "limit": page_size,
            "page": page,
        }
        if origin:
            params["origin"] = origin
        if destination:
            params["destination"] = destination
        if include_dates:
            params["departure_at"] = (
                config.departure_date.strftime("%Y-%m")
                if use_month
                else config.departure_date.isoformat()
            )
            params["return_at"] = (
                config.return_date.strftime("%Y-%m")
                if use_month
                else config.return_date.isoformat()
            )
        if config.market:
            params["market"] = config.market

        payload, retrieved_at, request_url = get_json(
            TRAVELPAYOUTS_FLIGHTS_URL,
            params=params,
            headers=headers,
        )
        latest_retrieved_at = retrieved_at
        rows = payload.get("data") if payload.get("success") else []
        rows = rows if isinstance(rows, list) else []
        with log_lock:
            request_log.append(
                {
                    "request_url": request_url,
                    "retrieved_at": retrieved_at,
                    "origin": origin,
                    "destination": destination,
                    "date_precision": (
                        "none"
                        if not include_dates
                        else "month"
                        if use_month
                        else "day"
                    ),
                    "success": bool(payload.get("success")),
                    "error": payload.get("error"),
                    "result_count": len(rows),
                }
            )
        ingest(rows)
        return len(rows)

    def discover_origin(origin: str) -> None:
        try:
            run_query(
                origin=origin,
                destination=None,
                use_month=True,
                unique=True,
                include_dates=True,
            )
            run_query(
                origin=origin,
                destination=None,
                use_month=False,
                unique=True,
                include_dates=False,
            )
        except PipelineError:
            return

    print(f"Querying {len(origins)} origins for cached unique routes...")
    workers = 1 if len(origins) == 1 else 6
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(discover_origin, origin) for origin in origins]
        done = 0
        for _ in as_completed(futures):
            done += 1
            if done % 100 == 0 or done == len(origins):
                print(
                    f"  origins {done}/{len(origins)} "
                    f"unique routes {len(candidates)}"
                )

    for destination in config.destinations:
        if not any(
            str(row.get("destination", "")).upper() == destination
            for row in candidates.values()
        ):
            seed_origin = (
                config.origin
                if config.origin not in {"", "ALL", "*"}
                else "LON"
            )
            try:
                run_query(
                    origin=seed_origin,
                    destination=destination,
                    use_month=True,
                    unique=False,
                )
            except PipelineError:
                continue

    selected = sorted(
        candidates.values(),
        key=lambda row: (
            float(row.get("price", float("inf"))),
            str(row.get("origin", "")),
            str(row.get("destination", "")),
        ),
    )
    if not selected:
        raise PipelineError(
            "Travelpayouts returned no cached flights after searching "
            f"{len(origins)} origins."
        )

    combined_payload = {
        "success": True,
        "currency": config.currency.lower(),
        "data": selected,
        "origin_count": len(origins),
        "route_count": len(selected),
        "requests": request_log,
    }
    return (
        combined_payload,
        latest_retrieved_at,
        [item["request_url"] for item in request_log],
    )


def fetch_travelpayouts_metadata(
    token: str,
) -> tuple[dict[str, Any], dict[str, str], dict[str, str]]:
    headers = {"X-Access-Token": token}
    result: dict[str, Any] = {}
    retrieval_times: dict[str, str] = {}
    request_urls: dict[str, str] = {}

    for name, url in {
        "cities": TRAVELPAYOUTS_CITIES_URL,
        "airports": TRAVELPAYOUTS_AIRPORTS_URL,
        "airlines": TRAVELPAYOUTS_AIRLINES_URL,
        "countries": TRAVELPAYOUTS_COUNTRIES_URL,
    }.items():
        payload, retrieved_at, request_url = get_json(url, headers=headers)
        if not isinstance(payload, list):
            raise PipelineError(f"Travelpayouts {name} metadata was not a list.")
        result[name] = payload
        retrieval_times[name] = retrieved_at
        request_urls[name] = request_url

    return result, retrieval_times, request_urls


def index_by(items: list[dict[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    return {
        str(item[key]).upper(): item
        for item in items
        if item.get(key) not in (None, "")
    }


def choose_place_metadata(
    flight: dict[str, Any],
    airports_by_code: dict[str, dict[str, Any]],
    cities_by_code: dict[str, dict[str, Any]],
    *,
    side: str,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    if side == "origin":
        airport_code = str(
            flight.get("origin_airport") or flight.get("origin") or ""
        ).upper()
        city_fallback = str(flight.get("origin") or "").upper()
    else:
        airport_code = str(
            flight.get("destination_airport") or flight.get("destination") or ""
        ).upper()
        city_fallback = str(flight.get("destination") or "").upper()
    airport = airports_by_code.get(airport_code)
    city_code = str((airport or {}).get("city_code") or city_fallback).upper()
    city = cities_by_code.get(city_code)
    return airport, city


def choose_destination_metadata(
    flight: dict[str, Any],
    airports_by_code: dict[str, dict[str, Any]],
    cities_by_code: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    return choose_place_metadata(
        flight, airports_by_code, cities_by_code, side="destination"
    )


def place_labels(
    airport: dict[str, Any] | None,
    city: dict[str, Any] | None,
    fallback_iata: str,
) -> tuple[str, str | None, str | None]:
    city_name = str(
        (city or {}).get("name")
        or (airport or {}).get("name")
        or fallback_iata
    )
    airport_name = (airport or {}).get("name")
    country_code = str(
        (airport or {}).get("country_code")
        or (city or {}).get("country_code")
        or ""
    ).upper() or None
    return city_name, airport_name, country_code


def iso_country_code(country_code: str | None) -> str | None:
    if not country_code:
        return None
    return COUNTRY_CODE_ALIASES.get(country_code, country_code)


def country_display_name(
    country_code: str | None,
    countries_by_code: dict[str, dict[str, Any]],
    rest_country: dict[str, Any] | None = None,
) -> str | None:
    if rest_country:
        name = (rest_country.get("names") or {}).get("common")
        if name:
            return str(name)
    lookup = iso_country_code(country_code)
    for code in (lookup, country_code):
        if not code:
            continue
        name = (countries_by_code.get(code) or {}).get("name")
        if name:
            return str(name)
    return country_code


def build_origin_record(
    flight: dict[str, Any],
    airports_by_code: dict[str, dict[str, Any]],
    cities_by_code: dict[str, dict[str, Any]],
    countries_by_code: dict[str, dict[str, Any]],
    rest_country: dict[str, Any] | None = None,
) -> dict[str, Any]:
    origin_iata = str(flight.get("origin") or "").upper()
    airport, city = choose_place_metadata(
        flight, airports_by_code, cities_by_code, side="origin"
    )
    city_name, airport_name, country_code = place_labels(
        airport, city, origin_iata
    )
    return {
        "city": city_name,
        "airport": airport_name,
        "country_code": country_code,
        "country": country_display_name(
            country_code, countries_by_code, rest_country
        ),
        "iata": origin_iata or None,
        "airport_iata": flight.get("origin_airport") or origin_iata or None,
    }


def coordinates_from_metadata(
    airport: dict[str, Any] | None,
    city: dict[str, Any] | None,
) -> tuple[float | None, float | None, str | None]:
    for source, item in (("airport", airport), ("city", city)):
        coordinates = (item or {}).get("coordinates") or {}
        if coordinates.get("lat") is not None and coordinates.get("lon") is not None:
            return (
                float(coordinates["lat"]),
                float(coordinates["lon"]),
                f"travelpayouts_{source}_metadata",
            )
    return None, None, None


def fetch_geocoding(
    city_name: str, country_code: str
) -> tuple[dict[str, Any], str, str]:
    payload, retrieved_at, request_url = get_json(
        OPEN_METEO_GEOCODING_URL,
        params={
            "name": city_name,
            "count": 10,
            "language": "en",
            "format": "json",
            "countryCode": country_code,
        },
    )
    matches = payload.get("results") or []
    match = next(
        (
            item
            for item in matches
            if item.get("country_code", "").upper() == country_code.upper()
        ),
        None,
    )
    if not match:
        raise PipelineError(
            f"No Open-Meteo geocoding result for {city_name}, {country_code}."
        )
    return match, retrieved_at, request_url


def fetch_weather(
    latitude: float,
    longitude: float,
    start_date: date,
    end_date: date,
) -> tuple[dict[str, Any], str, str]:
    return get_json(
        OPEN_METEO_FORECAST_URL,
        params={
            "latitude": latitude,
            "longitude": longitude,
            "timezone": "auto",
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "daily": ",".join(
                [
                    "weather_code",
                    "temperature_2m_max",
                    "temperature_2m_min",
                    "precipitation_probability_max",
                    "sunshine_duration",
                ]
            ),
        },
    )


def fetch_country(
    country_code: str,
    api_key: str,
) -> tuple[dict[str, Any], str, str]:
    response_fields = ",".join(
        [
            "names.common",
            "names.official",
            "codes.alpha_2",
            "codes.alpha_3",
            "capitals",
            "currencies",
            "languages",
            "region",
            "subregion",
            "flag",
            "timezones",
        ]
    )
    payload, retrieved_at, request_url = get_json(
        f"{REST_COUNTRIES_URL}/codes.alpha_2/{country_code}",
        params={"response_fields": response_fields},
        headers={"Authorization": f"Bearer {api_key}"},
    )
    objects = (payload.get("data") or {}).get("objects") or []
    if not objects:
        raise PipelineError(f"No REST Countries result for {country_code}.")
    return objects[0], retrieved_at, request_url


def average(values: list[float | int | None]) -> float | None:
    available = [float(value) for value in values if value is not None]
    if not available:
        return None
    return round(sum(available) / len(available), 2)


def parse_flight_date(value: Any, fallback: date) -> date:
    if not value:
        return fallback
    try:
        return datetime.fromisoformat(
            str(value).replace("Z", "+00:00")
        ).date()
    except ValueError:
        return fallback


def normalize_weather(payload: dict[str, Any]) -> dict[str, Any]:
    daily = payload.get("daily") or {}
    sunshine_seconds = average(daily.get("sunshine_duration", []))
    return {
        "average_max_temperature_c": average(
            daily.get("temperature_2m_max", [])
        ),
        "average_min_temperature_c": average(
            daily.get("temperature_2m_min", [])
        ),
        "average_precipitation_probability_percent": average(
            daily.get("precipitation_probability_max", [])
        ),
        "average_sunshine_hours": (
            round(sunshine_seconds / 3600, 2)
            if sunshine_seconds is not None
            else None
        ),
        "timezone": payload.get("timezone"),
    }


def build_fixtures(config: Config) -> dict[str, Any]:
    metadata, metadata_times, metadata_urls = fetch_travelpayouts_metadata(
        config.travelpayouts_token
    )

    airports_by_code = index_by(metadata["airports"], "code")
    cities_by_code = index_by(metadata["cities"], "code")
    airlines_by_code = index_by(metadata["airlines"], "iata")
    countries_by_code = index_by(metadata["countries"], "code")

    if config.origin in {"", "ALL", "*"}:
        origins = sorted(
            code
            for code, city in cities_by_code.items()
            if city.get("has_flightable_airport")
        )
    else:
        origins = [config.origin]

    flights_payload, flights_at, flights_url = fetch_travelpayouts_flights(
        config, origins
    )

    selected_airports: dict[str, Any] = {}
    selected_cities: dict[str, Any] = {}
    selected_airlines: dict[str, Any] = {}
    geocoding_snapshots: dict[str, Any] = {}
    weather_snapshots: dict[str, Any] = {}
    country_snapshots: dict[str, Any] = {}
    normalized: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    weather_cache: dict[str, tuple[dict[str, Any], str, str]] = {}
    country_cache: dict[str, tuple[dict[str, Any], str, str]] = {}

    for flight in flights_payload["data"]:
        destination_iata = str(flight.get("destination", "")).upper()
        origin_iata = str(flight.get("origin") or "").upper()
        try:
            airport, city = choose_destination_metadata(
                flight, airports_by_code, cities_by_code
            )
            if not airport and not city:
                raise PipelineError(
                    f"No Travelpayouts metadata for {destination_iata}."
                )

            if airport:
                selected_airports[str(airport["code"]).upper()] = airport
            if city:
                selected_cities[str(city["code"]).upper()] = city

            origin_airport, origin_city_meta = choose_place_metadata(
                flight, airports_by_code, cities_by_code, side="origin"
            )
            if origin_airport:
                selected_airports[str(origin_airport["code"]).upper()] = origin_airport
            if origin_city_meta:
                selected_cities[str(origin_city_meta["code"]).upper()] = origin_city_meta

            airline_code = str(flight.get("airline") or "").upper()
            airline = airlines_by_code.get(airline_code)
            if airline:
                selected_airlines[airline_code] = airline

            country_code = str(
                (airport or {}).get("country_code")
                or (city or {}).get("country_code")
                or ""
            ).upper()
            city_name = str(
                (city or {}).get("name")
                or (airport or {}).get("name")
                or destination_iata
            )
            if not country_code:
                raise PipelineError(
                    f"No country code in metadata for {destination_iata}."
                )

            latitude, longitude, coordinate_source = coordinates_from_metadata(
                airport, city
            )
            if latitude is None or longitude is None:
                geocoding, geocoding_at, geocoding_url = fetch_geocoding(
                    city_name, country_code
                )
                geocoding_snapshots[destination_iata] = snapshot(
                    "open_meteo_geocoding",
                    geocoding_url,
                    geocoding_at,
                    geocoding,
                )
                latitude = float(geocoding["latitude"])
                longitude = float(geocoding["longitude"])
                coordinate_source = "open_meteo_geocoding"

            flight_departure_date = parse_flight_date(
                flight.get("departure_at"), config.departure_date
            )
            flight_return_date = parse_flight_date(
                flight.get("return_at"), config.return_date
            )
            today = utc_now().date()
            forecast_end = today + timedelta(days=16)
            if (
                flight_departure_date < today
                or flight_return_date > forecast_end
                or flight_return_date < flight_departure_date
            ):
                # Month-level flight cache results can fall outside the forecast
                # horizon. Keep the price fixture, but fetch weather for the
                # user's requested dates and label the two date ranges separately.
                weather_start_date = config.departure_date
                weather_end_date = config.return_date
                weather_date_basis = "requested_dates"
            else:
                weather_start_date = flight_departure_date
                weather_end_date = flight_return_date
                weather_date_basis = "flight_dates"

            if destination_iata not in weather_cache:
                weather_cache[destination_iata] = fetch_weather(
                    latitude,
                    longitude,
                    weather_start_date,
                    weather_end_date,
                )
            weather, weather_at, weather_url = weather_cache[destination_iata]
            weather_snapshots[destination_iata] = snapshot(
                "open_meteo_forecast", weather_url, weather_at, weather
            )

            if country_code not in country_cache:
                country_cache[country_code] = fetch_country(
                    country_code, config.rest_countries_api_key
                )
            country, country_at, country_url = country_cache[country_code]
            country_snapshots[country_code] = snapshot(
                "rest_countries_v5", country_url, country_at, country
            )

            origin_country_code = place_labels(
                origin_airport, origin_city_meta, origin_iata
            )[2]
            origin_lookup = iso_country_code(origin_country_code)
            origin_rest = None
            if origin_lookup:
                try:
                    if origin_lookup not in country_cache:
                        country_cache[origin_lookup] = fetch_country(
                            origin_lookup, config.rest_countries_api_key
                        )
                    origin_rest, origin_rest_at, origin_rest_url = country_cache[
                        origin_lookup
                    ]
                    country_snapshots[origin_lookup] = snapshot(
                        "rest_countries_v5",
                        origin_rest_url,
                        origin_rest_at,
                        origin_rest,
                    )
                except PipelineError:
                    origin_rest = None

            origin_record = build_origin_record(
                flight,
                airports_by_code,
                cities_by_code,
                countries_by_code,
                origin_rest,
            )

            normalized.append(
                {
                    "id": (
                        f"{origin_iata or 'UNK'}-{destination_iata}-"
                        f"{config.departure_date.isoformat()}"
                    ),
                    "origin": origin_record,
                    "flight": {
                        "origin_iata": flight.get("origin"),
                        "destination_iata": destination_iata,
                        "origin_airport_iata": flight.get("origin_airport"),
                        "destination_airport_iata": flight.get(
                            "destination_airport"
                        ),
                        "price": flight.get("price"),
                        "currency": (
                            flights_payload.get("currency")
                            or config.currency
                        ).upper(),
                        "departure_at": flight.get("departure_at"),
                        "return_at": flight.get("return_at"),
                        "outbound_stops": flight.get("transfers"),
                        "return_stops": flight.get("return_transfers"),
                        "duration_minutes": flight.get("duration"),
                        "outbound_duration_minutes": flight.get("duration_to"),
                        "return_duration_minutes": flight.get("duration_back"),
                        "airline_code": airline_code or None,
                        "airline_name": (airline or {}).get("name"),
                        "flight_number": flight.get("flight_number"),
                        "retrieved_at": flights_at,
                        "is_cached_offer": True,
                    },
                    "destination": {
                        "city": city_name,
                        "airport": (airport or {}).get("name"),
                        "country_code": country_code,
                        "latitude": latitude,
                        "longitude": longitude,
                        "coordinate_source": coordinate_source,
                        "timezone": (
                            (airport or {}).get("time_zone")
                            or (city or {}).get("time_zone")
                            or weather.get("timezone")
                        ),
                    },
                    "weather": {
                        **normalize_weather(weather),
                        "retrieved_at": weather_at,
                        "date_basis": weather_date_basis,
                        "start_date": weather_start_date.isoformat(),
                        "end_date": weather_end_date.isoformat(),
                    },
                    "country": {
                        "common_name": (country.get("names") or {}).get("common"),
                        "official_name": (country.get("names") or {}).get(
                            "official"
                        ),
                        "alpha_2": (country.get("codes") or {}).get("alpha_2"),
                        "alpha_3": (country.get("codes") or {}).get("alpha_3"),
                        "currencies": country.get("currencies", {}),
                        "region": country.get("region"),
                        "subregion": country.get("subregion"),
                        "flag": {
                            key: (country.get("flag") or {}).get(key)
                            for key in ("emoji", "description", "url_png", "url_svg")
                            if (country.get("flag") or {}).get(key)
                        },
                        "retrieved_at": country_at,
                    },
                }
            )
        except (PipelineError, KeyError, TypeError, ValueError) as error:
            errors.append(
                {
                    "destination_iata": destination_iata or "unknown",
                    "error": str(error),
                }
            )

    if not normalized:
        raise PipelineError(
            "No destination could be fully normalized. See API errors above."
        )

    selected_metadata = {
        "cities": list(selected_cities.values()),
        "airports": list(selected_airports.values()),
        "airlines": list(selected_airlines.values()),
    }
    return {
        "travelpayouts_flights": snapshot(
            "travelpayouts_prices_for_dates",
            flights_url,
            flights_at,
            flights_payload,
        ),
        "travelpayouts_metadata": {
            name: snapshot(
                f"travelpayouts_{name}",
                metadata_urls[name],
                metadata_times[name],
                selected_metadata[name],
            )
            for name in selected_metadata
        },
        "open_meteo_geocoding": geocoding_snapshots,
        "open_meteo_weather": weather_snapshots,
        "rest_countries": country_snapshots,
        "normalized_destinations": {
            "generated_at": iso_z(),
            "request": {
                "origin": config.origin,
                "currency": config.currency,
                "departure_date": config.departure_date.isoformat(),
                "return_date": config.return_date.isoformat(),
                "limit": config.limit,
                "market": config.market or None,
                "destinations": list(config.destinations),
            },
            "destinations": normalized,
            "errors": errors,
        },
    }


def save_fixtures(config: Config, fixtures: dict[str, Any]) -> None:
    output_files = {
        "travelpayouts_flights.json": fixtures["travelpayouts_flights"],
        "travelpayouts_cities.json": fixtures["travelpayouts_metadata"]["cities"],
        "travelpayouts_airports.json": fixtures["travelpayouts_metadata"][
            "airports"
        ],
        "travelpayouts_airlines.json": fixtures["travelpayouts_metadata"][
            "airlines"
        ],
        "open_meteo_geocoding.json": fixtures["open_meteo_geocoding"],
        "open_meteo_weather.json": fixtures["open_meteo_weather"],
        "rest_countries.json": fixtures["rest_countries"],
        "normalized_destinations.json": fixtures["normalized_destinations"],
    }
    for filename, payload in output_files.items():
        write_json(config.output_dir / filename, payload)

    manifest = {
        "generated_at": iso_z(),
        "output_directory": str(config.output_dir),
        "files": sorted(output_files),
        "destination_count": len(
            fixtures["normalized_destinations"]["destinations"]
        ),
        "error_count": len(fixtures["normalized_destinations"]["errors"]),
        "contains_secrets": False,
        "note": (
            "normalized_destinations.json is the shared team file. "
            "The other JSON files are optional API snapshots. "
            "Refresh them by rerunning destination_pipeline.py."
        ),
    }
    write_json(config.output_dir / "manifest.json", manifest)


def main() -> None:
    try:
        config = load_config()
        fixtures = build_fixtures(config)
        save_fixtures(config, fixtures)
    except PipelineError as error:
        raise SystemExit(f"Destination pipeline failed: {error}") from error

    destination_count = len(
        fixtures["normalized_destinations"]["destinations"]
    )
    print(
        f"Saved {destination_count} destination fixtures to {config.output_dir}"
    )


if __name__ == "__main__":
    main()
