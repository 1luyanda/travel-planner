"""Fill reconstructable holes in local normalized_destinations.json.

Offline: no .env and no API calls. Price is never imputed. Weather zeros stay.

Fill order:
    1. duration = outbound + return on the same row
    2. missing outbound/return from duration minus the other leg
    3. reverse origin/destination pair, with legs swapped
    4. other rows with the same origin and destination (prefer same stops)
    5. lat/lon/airport from the same destination airport IATA
    6. origin city/country from other local rows

Usage:
    python data_preparation/fill_missing_data.py
    python data_preparation/fill_missing_data.py mock_data
    python data_preparation/fill_missing_data.py Real_data/normalized_destinations.json
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

PROJECT_DIR = Path(__file__).resolve().parent.parent


def write_json(path: Path, payload: Any) -> None:
    compact = "Real_data" in path.parts
    text = json.dumps(
        payload,
        ensure_ascii=False,
        indent=None if compact else 2,
        separators=(",", ":") if compact else None,
    )
    path.write_text(text + "\n", encoding="utf-8")


DEFAULT_DIRS = (
    PROJECT_DIR / "mock_data",
    PROJECT_DIR / "Real_data",
)
ORIGIN_KEYS = ("city", "airport", "country_code", "country", "iata", "airport_iata")

DURATION_FIELDS = (
    "duration_minutes",
    "outbound_duration_minutes",
    "return_duration_minutes",
)


def is_blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def resolve_files(raw: str | None) -> list[Path]:
    if not raw:
        return [folder / "normalized_destinations.json" for folder in DEFAULT_DIRS]
    target = Path(raw)
    if not target.is_absolute():
        target = PROJECT_DIR / target
    if target.is_dir():
        return [target / "normalized_destinations.json"]
    return [target]


def merge_place(base: dict[str, Any] | None, donor: dict[str, Any] | None) -> dict[str, Any]:
    merged = dict(base or {})
    for key in ORIGIN_KEYS:
        if is_blank(merged.get(key)) and not is_blank((donor or {}).get(key)):
            merged[key] = donor[key]
    return merged


def origin_iata_of(item: dict[str, Any]) -> str:
    origin = item.get("origin") or {}
    flight = item.get("flight") or {}
    return str(origin.get("iata") or flight.get("origin_iata") or "").upper()


def place_from_origin(item: dict[str, Any]) -> dict[str, Any]:
    origin = dict(item.get("origin") or {})
    flight = item.get("flight") or {}
    iata = origin_iata_of(item)
    origin["iata"] = iata or origin.get("iata")
    origin["airport_iata"] = (
        origin.get("airport_iata")
        or flight.get("origin_airport_iata")
        or iata
        or None
    )
    return origin


def place_from_destination(item: dict[str, Any]) -> dict[str, Any]:
    dest = item.get("destination") or {}
    country = item.get("country") or {}
    flight = item.get("flight") or {}
    iata = str(flight.get("destination_iata") or "").upper()
    return {
        "city": dest.get("city"),
        "airport": dest.get("airport"),
        "country_code": dest.get("country_code") or country.get("alpha_2"),
        "country": country.get("common_name"),
        "iata": iata or None,
        "airport_iata": flight.get("destination_airport_iata") or iata or None,
    }


def origin_is_complete(origin: dict[str, Any] | None) -> bool:
    return bool(origin) and not is_blank(origin.get("city")) and not is_blank(
        origin.get("country")
    )


def catalog_places(destinations: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    by_iata: dict[str, dict[str, Any]] = {}
    for item in destinations:
        dest_place = place_from_destination(item)
        dest_iata = str(dest_place.get("iata") or "").upper()
        if dest_iata and dest_place.get("city"):
            by_iata[dest_iata] = merge_place(by_iata.get(dest_iata), dest_place)
        origin = place_from_origin(item)
        origin_iata = str(origin.get("iata") or "").upper()
        if origin_iata and origin_is_complete(origin):
            by_iata[origin_iata] = merge_place(by_iata.get(origin_iata), origin)
    return by_iata


def to_number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def as_minutes(value: float) -> int | float:
    if float(value).is_integer():
        return int(value)
    return round(value, 2)


def is_valid_duration(value: Any) -> bool:
    number = to_number(value)
    return number is not None and number > 0


def is_broken_duration(value: Any) -> bool:
    return not is_valid_duration(value)


def is_broken_price(value: Any) -> bool:
    number = to_number(value)
    return number is None or number <= 0


def coords_broken(lat: Any, lon: Any) -> bool:
    lat_n = to_number(lat)
    lon_n = to_number(lon)
    if lat_n is None or lon_n is None:
        return True
    return lat_n == 0 and lon_n == 0


def average_minutes(values: list[float]) -> int | float:
    mean = sum(values) / len(values)
    if all(value == int(value) for value in values):
        return int(round(mean))
    return round(mean, 2)


def flight_of(item: dict[str, Any]) -> dict[str, Any]:
    flight = item.get("flight")
    if not isinstance(flight, dict):
        flight = {}
        item["flight"] = flight
    return flight


def dest_of(item: dict[str, Any]) -> dict[str, Any]:
    dest = item.get("destination")
    if not isinstance(dest, dict):
        dest = {}
        item["destination"] = dest
    return dest


def route_key(item: dict[str, Any]) -> tuple[str, str]:
    flight = item.get("flight") or {}
    origin = (item.get("origin") or {}).get("iata") or flight.get("origin_iata")
    dest = flight.get("destination_iata")
    return (str(origin or "").upper(), str(dest or "").upper())


def stop_key(item: dict[str, Any]) -> tuple[Any, Any]:
    flight = item.get("flight") or {}
    return (flight.get("outbound_stops"), flight.get("return_stops"))


def reverse_stop_key(item: dict[str, Any]) -> tuple[Any, Any]:
    outbound, inbound = stop_key(item)
    return (inbound, outbound)


def airport_code(item: dict[str, Any]) -> str:
    flight = item.get("flight") or {}
    return str(flight.get("destination_airport_iata") or "").upper()


def set_if_broken(target: dict[str, Any], field: str, value: Any, stats: dict[str, int]) -> bool:
    if value is None or not is_broken_duration(target.get(field)):
        return False
    number = to_number(value)
    if number is None or number <= 0:
        return False
    target[field] = as_minutes(number)
    stats[field] += 1
    return True


def pick_duration(
    donors: list[dict[str, Any]],
    field: str,
    *,
    prefer_stops: tuple[Any, Any] | None = None,
    reverse_field: str | None = None,
    exclude_id: Any = None,
) -> float | None:
    usable: list[dict[str, Any]] = []
    for donor in donors:
        if exclude_id is not None and donor.get("id") == exclude_id:
            continue
        flight = donor.get("flight") or {}
        source_field = reverse_field or field
        if is_valid_duration(flight.get(source_field)):
            usable.append(donor)
    if not usable:
        return None
    if prefer_stops is not None:
        matched = [
            donor
            for donor in usable
            if (
                reverse_stop_key(donor) if reverse_field else stop_key(donor)
            )
            == prefer_stops
        ]
        if matched:
            usable = matched
    values = [
        to_number((donor.get("flight") or {}).get(reverse_field or field))
        for donor in usable
    ]
    numbers = [value for value in values if value is not None and value > 0]
    if not numbers:
        return None
    return average_minutes(numbers)


def fill_same_row(flight: dict[str, Any], stats: dict[str, int]) -> bool:
    changed = False
    outbound = to_number(flight.get("outbound_duration_minutes"))
    inbound = to_number(flight.get("return_duration_minutes"))
    total = to_number(flight.get("duration_minutes"))

    if is_broken_duration(flight.get("duration_minutes")):
        if outbound and outbound > 0 and inbound and inbound > 0:
            flight["duration_minutes"] = as_minutes(outbound + inbound)
            stats["duration_minutes"] += 1
            changed = True
            total = outbound + inbound

    if total and total > 0:
        if is_broken_duration(flight.get("outbound_duration_minutes")) and inbound and inbound > 0:
            remainder = total - inbound
            if remainder > 0:
                flight["outbound_duration_minutes"] = as_minutes(remainder)
                stats["outbound_duration_minutes"] += 1
                changed = True
        if is_broken_duration(flight.get("return_duration_minutes")) and outbound and outbound > 0:
            remainder = total - outbound
            if remainder > 0:
                flight["return_duration_minutes"] = as_minutes(remainder)
                stats["return_duration_minutes"] += 1
                changed = True
    return changed


def fill_from_donors(
    item: dict[str, Any],
    by_route: dict[tuple[str, str], list[dict[str, Any]]],
    stats: dict[str, int],
) -> bool:
    flight = flight_of(item)
    origin, dest = route_key(item)
    if not origin or not dest:
        return False
    changed = False
    item_id = item.get("id")
    prefer = stop_key(item)

    reverse_donors = by_route.get((dest, origin), [])
    same_donors = by_route.get((origin, dest), [])

    reverse_map = {
        "duration_minutes": ("duration_minutes", prefer),
        "outbound_duration_minutes": ("return_duration_minutes", prefer),
        "return_duration_minutes": ("outbound_duration_minutes", prefer),
    }
    for field, (source_field, stops) in reverse_map.items():
        if not is_broken_duration(flight.get(field)):
            continue
        value = pick_duration(
            reverse_donors,
            field,
            prefer_stops=stops,
            reverse_field=source_field,
            exclude_id=item_id,
        )
        changed = set_if_broken(flight, field, value, stats) or changed

    for field in DURATION_FIELDS:
        if not is_broken_duration(flight.get(field)):
            continue
        value = pick_duration(
            same_donors,
            field,
            prefer_stops=prefer,
            exclude_id=item_id,
        )
        changed = set_if_broken(flight, field, value, stats) or changed
    return changed


def build_airport_catalog(
    destinations: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    catalog: dict[str, dict[str, Any]] = {}
    for item in destinations:
        code = airport_code(item)
        dest = item.get("destination") or {}
        if not code or coords_broken(dest.get("latitude"), dest.get("longitude")):
            continue
        donor = catalog.setdefault(code, {})
        if donor.get("latitude") is None:
            donor["latitude"] = dest.get("latitude")
            donor["longitude"] = dest.get("longitude")
        if not donor.get("airport") and dest.get("airport"):
            donor["airport"] = dest.get("airport")
    return catalog


def fill_coords(
    item: dict[str, Any],
    catalog: dict[str, dict[str, Any]],
    stats: dict[str, int],
) -> bool:
    dest = dest_of(item)
    code = airport_code(item)
    donor = catalog.get(code)
    if not donor:
        return False
    changed = False
    if coords_broken(dest.get("latitude"), dest.get("longitude")):
        dest["latitude"] = donor["latitude"]
        dest["longitude"] = donor["longitude"]
        stats["coordinates"] += 1
        changed = True
    if not dest.get("airport") and donor.get("airport"):
        dest["airport"] = donor["airport"]
        stats["airport_name"] += 1
        changed = True
    return changed


def fill_origin(item: dict[str, Any], catalog: dict[str, dict[str, Any]], stats: dict[str, int]) -> bool:
    origin = place_from_origin(item)
    iata = str(origin.get("iata") or "").upper()
    if origin_is_complete(origin):
        item["origin"] = origin
        return False
    filled = merge_place(origin, catalog.get(iata))
    item["origin"] = filled
    if origin_is_complete(filled):
        stats["origin"] += 1
        return True
    return False


def still_broken(item: dict[str, Any]) -> list[str]:
    flight = item.get("flight") or {}
    dest = item.get("destination") or {}
    holes: list[str] = []
    if is_broken_price(flight.get("price")):
        holes.append("price")
    for field in DURATION_FIELDS:
        if is_broken_duration(flight.get(field)):
            holes.append(field)
    if coords_broken(dest.get("latitude"), dest.get("longitude")):
        holes.append("coordinates")
    if not origin_is_complete(item.get("origin")):
        holes.append("origin")
    return holes


def fill_file(json_path: Path) -> dict[str, int]:
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    destinations = payload.get("destinations") or []
    by_route: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for item in destinations:
        key = route_key(item)
        if key[0] and key[1]:
            by_route[key].append(item)

    airport_catalog = build_airport_catalog(destinations)
    origin_catalog = catalog_places(destinations)
    stats: dict[str, int] = defaultdict(int)
    changed = False
    unfinished: dict[str, int] = defaultdict(int)

    for item in destinations:
        flight = flight_of(item)
        if is_broken_price(flight.get("price")):
            if to_number(flight.get("price")) == 0:
                flight["price"] = None
                changed = True
            stats["price_left_empty"] += 1

        changed = fill_same_row(flight, stats) or changed
        changed = fill_from_donors(item, by_route, stats) or changed
        changed = fill_same_row(flight, stats) or changed
        changed = fill_coords(item, airport_catalog, stats) or changed
        changed = fill_origin(item, origin_catalog, stats) or changed
        for hole in still_broken(item):
            unfinished[hole] += 1

    if changed:
        write_json(json_path, payload)
    return {
        "rows": len(destinations),
        "wrote_json": int(changed),
        **stats,
        **{f"still_{name}": count for name, count in unfinished.items()},
    }


def print_stats(stats: dict[str, int]) -> None:
    labels = [
        ("rows", "rows"),
        ("duration_minutes", "filled duration_minutes"),
        ("outbound_duration_minutes", "filled outbound_duration_minutes"),
        ("return_duration_minutes", "filled return_duration_minutes"),
        ("coordinates", "filled lat/lon"),
        ("airport_name", "filled airport_name"),
        ("origin", "filled origin city/country"),
        ("price_left_empty", "prices left empty (not filled)"),
        ("still_price", "still missing price"),
        ("still_duration_minutes", "still missing duration_minutes"),
        ("still_outbound_duration_minutes", "still missing outbound_duration_minutes"),
        ("still_return_duration_minutes", "still missing return_duration_minutes"),
        ("still_coordinates", "still missing lat/lon"),
        ("still_origin", "still missing origin"),
    ]
    for key, label in labels:
        if key in stats:
            print(f"  {label}: {stats[key]}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fill reconstructable holes in local normalized_destinations.json."
    )
    parser.add_argument(
        "path",
        nargs="?",
        help="Folder or normalized_destinations.json (default: mock_data and Real_data)",
    )
    args = parser.parse_args()

    files = resolve_files(args.path)
    for json_path in files:
        if not json_path.exists():
            print(f"skip (missing): {json_path}")
            continue
        print(f"Filling {json_path} from local rows only ...")
        print_stats(fill_file(json_path))


if __name__ == "__main__":
    main()
