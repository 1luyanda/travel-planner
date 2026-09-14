"""Ask for origin city + country, then print matching flights from Cosmos DB.

Uses the same database/containers as load_to_cosmos.py:
  TravelPlaner / origins / flights

Usage:
    python data_preparation/query_cosmos.py
"""

from __future__ import annotations

import sys
from typing import Any

from azure.cosmos import CosmosClient

from load_to_cosmos import (
    FLIGHTS_CONTAINER,
    ORIGINS_CONTAINER,
    cosmos_settings,
)

MAX_ROWS = 25

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(line_buffering=True)


def ask(prompt: str) -> str:
    try:
        return input(prompt).strip()
    except EOFError:
        raise SystemExit(1)


def query_all(container, query: str, parameters: list[dict[str, Any]], partition_key=None):
    kwargs: dict[str, Any] = {
        "query": query,
        "parameters": parameters,
    }
    if partition_key is None:
        kwargs["enable_cross_partition_query"] = True
    else:
        kwargs["partition_key"] = partition_key
    return list(container.query_items(**kwargs))


def find_origins(origins, city: str, country: str) -> list[dict[str, Any]]:
    exact = query_all(
        origins,
        """
        SELECT * FROM c
        WHERE STRINGEQUALS(c.city, @city, true)
          AND (
            STRINGEQUALS(c.country, @country, true)
            OR STRINGEQUALS(c.country_code, @country, true)
          )
        """,
        [
            {"name": "@city", "value": city},
            {"name": "@country", "value": country},
        ],
    )
    if exact:
        return exact

    by_city = query_all(
        origins,
        "SELECT * FROM c WHERE STRINGEQUALS(c.city, @city, true)",
        [{"name": "@city", "value": city}],
    )
    return by_city


def suggest_origins(origins, city: str) -> list[dict[str, Any]]:
    return query_all(
        origins,
        "SELECT TOP 10 * FROM c WHERE CONTAINS(c.city, @city, true)",
        [{"name": "@city", "value": city}],
    )


def pick_origin(matches: list[dict[str, Any]], country: str) -> dict[str, Any] | None:
    if not matches:
        return None
    if len(matches) == 1:
        origin = matches[0]
        origin_country = str(origin.get("country") or "")
        origin_code = str(origin.get("country_code") or "")
        if country and not (
            origin_country.casefold() == country.casefold()
            or origin_code.casefold() == country.casefold()
        ):
            print(
                f"\nNo origin for that country. Closest city match: "
                f"{origin.get('city')}, {origin_country} ({origin_code}) "
                f"[{origin.get('id')}]"
            )
            answer = ask("Use this origin? [y/N]: ").casefold()
            if answer not in {"y", "yes"}:
                return None
        return origin

    print(f"\nFound {len(matches)} origins. Pick one:")
    for index, origin in enumerate(matches, 1):
        print(
            f"  {index}. {origin.get('city')}, {origin.get('country')} "
            f"({origin.get('country_code')})  id={origin.get('id')}  "
            f"flights={origin.get('flight_count')}"
        )
    choice = ask("Number: ")
    if not choice.isdigit():
        return None
    index = int(choice)
    if index < 1 or index > len(matches):
        return None
    return matches[index - 1]


def short_dt(value: Any) -> str:
    text = str(value or "")
    if "T" in text:
        date, time = text.split("T", 1)
        return f"{date} {time[:5]}"
    return text or "-"


def format_price(value: Any, currency: Any) -> str:
    if value is None or value == "":
        return "-"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    code = str(currency or "EUR")
    if number.is_integer():
        return f"{int(number)} {code}"
    return f"{number:.2f} {code}"


def print_origin(origin: dict[str, Any]) -> None:
    iata = origin.get("city_iata") or []
    airports = origin.get("airports") or []
    print(
        f"\nOrigin: {origin.get('city')}, {origin.get('country')} "
        f"({origin.get('country_code')})"
    )
    print(f"  id:        {origin.get('id')}")
    print(f"  IATA:      {', '.join(iata) if iata else '-'}")
    print(f"  airports:  {', '.join(airports) if airports else '-'}")
    print(f"  flights:   {origin.get('flight_count')}")


def print_flights(rows: list[dict[str, Any]]) -> None:
    if not rows:
        print("\nNo flights for this origin.")
        return

    rows = sorted(
        rows,
        key=lambda row: (row.get("price_eur") is None, row.get("price_eur") or 0),
    )
    shown = rows[:MAX_ROWS]
    print(f"\n{len(rows)} flights (showing {len(shown)}, cheapest first)\n")
    header = (
        f"{'#':<4} {'Destination':<22} {'IATA':<6} {'Price':<12} "
        f"{'Depart':<17} {'Return':<17} {'Airline':<7} {'Stops':<5} {'Max C':<6}"
    )
    print(header)
    print("-" * len(header))
    for index, row in enumerate(shown, 1):
        city = str(row.get("destination_city") or "-")
        country = str(row.get("destination_country_code") or "")
        dest = f"{city} {country}".strip()
        stops = row.get("outbound_stops")
        stops_text = "-" if stops is None else str(int(stops) if float(stops).is_integer() else stops)
        temp = row.get("temp_max_c")
        temp_text = "-" if temp is None else f"{temp:g}"
        print(
            f"{index:<4} {dest[:22]:<22} {str(row.get('destination_iata') or '-'):<6} "
            f"{format_price(row.get('price_eur'), row.get('currency')):<12} "
            f"{short_dt(row.get('departure_at')):<17} {short_dt(row.get('return_at')):<17} "
            f"{str(row.get('airline_code') or '-'):<7} {stops_text:<5} {temp_text:<6}"
        )

    if len(rows) > MAX_ROWS:
        print(f"\n... {len(rows) - MAX_ROWS} more not shown")


def main() -> int:
    print("Cosmos flight lookup")
    print("Type an origin city, then country name or country code (e.g. Zagreb / HR).\n")

    city = ask("Origin city: ")
    while not city:
        city = ask("Origin city: ")
    country = ask("Country (name or code): ")
    while not country:
        country = ask("Country (name or code): ")

    endpoint, account_key, database_name = cosmos_settings()
    client = CosmosClient(url=endpoint, credential=account_key)
    database = client.get_database_client(database_name)
    origins = database.get_container_client(ORIGINS_CONTAINER)
    flights = database.get_container_client(FLIGHTS_CONTAINER)
    print(f"\nConnected to {database_name} / {ORIGINS_CONTAINER}, {FLIGHTS_CONTAINER}")

    matches = find_origins(origins, city, country)
    origin = pick_origin(matches, country)
    if origin is None:
        suggestions = suggest_origins(origins, city)
        if suggestions:
            print("\nNo exact match. Similar origins:")
            for item in suggestions:
                print(
                    f"  - {item.get('city')}, {item.get('country')} "
                    f"({item.get('country_code')})  id={item.get('id')}"
                )
        else:
            print(f"\nNo origin found for city '{city}'.")
        return 1

    print_origin(origin)
    origin_id = str(origin.get("id") or "")
    rows = query_all(
        flights,
        "SELECT * FROM c WHERE c.origin_id = @origin_id",
        [{"name": "@origin_id", "value": origin_id}],
        partition_key=origin_id,
    )
    print_flights(rows)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nCancelled.")
        raise SystemExit(130)
