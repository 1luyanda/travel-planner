"""Check whether normalized_destinations.json is usable ranking data.

Reads the local JSON only. No .env and no API calls.

A saved flight is OK if ranking fields are filled. Rain/temp/sunshine/stops
of 0 are real values. Blank rain, 0 euro price, 0-minute duration, or
latitude+longitude both 0 are not.

Usage:
    python data_preparation/check_missing_data.py
    python data_preparation/check_missing_data.py --drop-broken
    python data_preparation/check_missing_data.py mock_data
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

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


DEFAULT_JSON = PROJECT_DIR / "Real_data" / "normalized_destinations.json"

MUST_HAVE = (
    "id",
    "origin_city",
    "origin_country",
    "origin_iata",
    "city",
    "country",
    "destination_iata",
    "price_eur",
    "currency",
    "departure_at",
    "return_at",
    "duration_minutes",
    "temp_max_c",
    "temp_min_c",
    "rain_pct",
    "latitude",
    "longitude",
)

NICE_TO_HAVE = (
    "origin_country_code",
    "origin_airport_iata",
    "country_code",
    "destination_airport_iata",
    "airport_name",
    "outbound_duration_minutes",
    "return_duration_minutes",
    "airline_code",
    "flight_number",
    "sunshine_hours",
)

ZERO_IS_BAD = (
    "price_eur",
    "duration_minutes",
    "outbound_duration_minutes",
    "return_duration_minutes",
)

LABELS = {
    "id": "id",
    "origin_city": "origin city",
    "origin_country": "origin country",
    "origin_country_code": "origin country code",
    "origin_iata": "origin airport/city code",
    "origin_airport_iata": "origin airport code",
    "city": "destination city",
    "country": "destination country",
    "country_code": "destination country code",
    "destination_iata": "destination code",
    "destination_airport_iata": "destination airport code",
    "airport_name": "airport name",
    "price_eur": "price",
    "currency": "currency",
    "departure_at": "departure time",
    "return_at": "return time",
    "duration_minutes": "total flight minutes",
    "outbound_duration_minutes": "outbound minutes",
    "return_duration_minutes": "return minutes",
    "airline_code": "airline",
    "flight_number": "flight number",
    "temp_max_c": "max temperature",
    "temp_min_c": "min temperature",
    "rain_pct": "rain chance",
    "sunshine_hours": "sunshine hours",
    "latitude": "latitude",
    "longitude": "longitude",
}

SECTIONS = ("origin", "flight", "destination", "weather", "country")


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
        "flight_number": flight.get("flight_number"),
        "temp_max_c": weather.get("average_max_temperature_c"),
        "temp_min_c": weather.get("average_min_temperature_c"),
        "rain_pct": weather.get("average_precipitation_probability_percent"),
        "sunshine_hours": weather.get("average_sunshine_hours"),
        "latitude": dest.get("latitude"),
        "longitude": dest.get("longitude"),
    }


def is_blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    if isinstance(value, (list, dict, tuple, set)) and len(value) == 0:
        return True
    return False


def to_number(value: Any) -> float | None:
    if is_blank(value):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def problems_for(row: dict[str, Any]) -> list[tuple[str, str, str]]:
    """Return (field, severity, reason) tuples. severity is must or extra."""
    found: list[tuple[str, str, str]] = []
    for field in MUST_HAVE + NICE_TO_HAVE:
        severity = "must" if field in MUST_HAVE else "extra"
        label = LABELS.get(field, field)
        if is_blank(row.get(field)):
            found.append((field, severity, f"{label} is blank"))
        elif field in ZERO_IS_BAD and to_number(row.get(field)) == 0:
            found.append((field, severity, f"{label} is 0 (impossible)"))

    lat = to_number(row.get("latitude"))
    lon = to_number(row.get("longitude"))
    if lat == 0 and lon == 0:
        found.append(("latitude", "must", "latitude and longitude are both 0 (not a real place)"))
        found.append(("longitude", "must", "latitude and longitude are both 0 (not a real place)"))
    return found


def short(value: Any, width: int = 40) -> str:
    text = "" if is_blank(value) else str(value).replace("\n", " ")
    if len(text) > width:
        return text[: width - 1] + "…"
    return text


def configure_stdout() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")


def resolve_json(raw: Path) -> Path:
    if raw.is_dir():
        return raw / "normalized_destinations.json"
    return raw


def load_payload(path: Path) -> dict[str, Any]:
    print(f"Checking: {path}")
    print("Loading JSON (the Real_data file can take a minute)...")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SystemExit("normalized_destinations.json should be an object with a destinations list.")
    return payload


def count_daily_nulls(weather: dict[str, Any]) -> bool:
    daily = weather.get("daily") or {}
    for values in daily.values():
        if isinstance(values, list) and any(is_blank(item) for item in values):
            return True
    return False


def inspect(payload: dict[str, Any]) -> dict[str, Any]:
    destinations = payload.get("destinations") or []
    dropped = payload.get("errors") or []
    must_broken: list[dict[str, Any]] = []
    extra_only: list[dict[str, Any]] = []
    must_counts: Counter[str] = Counter()
    extra_counts: Counter[str] = Counter()
    missing_sections: Counter[str] = Counter()
    daily_null_rows = 0
    ids: list[str] = []

    for index, item in enumerate(destinations, start=1):
        row_id = str(item.get("id") or f"row-{index}")
        ids.append(row_id)
        for section in SECTIONS:
            if is_blank(item.get(section)):
                missing_sections[section] += 1
        if count_daily_nulls(item.get("weather") or {}):
            daily_null_rows += 1

        row = flatten(item)
        issues = problems_for(row)
        if not issues:
            continue
        must = [issue for issue in issues if issue[1] == "must"]
        extra = [issue for issue in issues if issue[1] == "extra"]
        record = {"id": row_id, "row": row, "must": must, "extra": extra}
        for field, _, _ in must:
            must_counts[field] += 1
        for field, _, _ in extra:
            extra_counts[field] += 1
        if must:
            must_broken.append(record)
        else:
            extra_only.append(record)

    return {
        "destinations": destinations,
        "dropped": dropped,
        "must_broken": must_broken,
        "extra_only": extra_only,
        "must_counts": must_counts,
        "extra_counts": extra_counts,
        "missing_sections": missing_sections,
        "daily_null_rows": daily_null_rows,
        "ids": ids,
    }


def print_reason_counts(title: str, counts: Counter[str], total: int) -> None:
    print(f"\n{title}")
    if not counts:
        print("  none")
        return
    for field, count in counts.most_common():
        label = LABELS.get(field, field)
        pct = (count / total * 100) if total else 0
        print(f"  {count:5}  {label} ({field})  {pct:.2f}% of saved flights")


def print_broken_rows(title: str, records: list[dict[str, Any]], *, key: str) -> None:
    print(f"\n{title} ({len(records)})")
    if not records:
        print("  none")
        return
    for item in records:
        row = item["row"]
        issues = item["must"] + item["extra"] if key == "must" else item[key]
        reasons = "; ".join(reason for _, _, reason in issues)
        origin = row.get("origin_city") or row.get("origin_iata") or "?"
        dest = row.get("city") or row.get("destination_iata") or "?"
        print(
            f"  {item['id']}: {origin} -> {dest}"
            f"  |  {reasons}"
        )


def print_dropped(dropped: list[dict[str, Any]]) -> None:
    print("\nRoutes the pipeline could not save")
    print(
        "These never entered normalized_destinations.json. "
        "They are extra destinations you do not have, not broken rows inside the file."
    )
    if not dropped:
        print("  none")
        return
    grouped: dict[str, list[str]] = {}
    for item in dropped:
        reason = short(item.get("error") or "unknown", 90)
        grouped.setdefault(reason, []).append(str(item.get("destination_iata") or "?"))
    print(f"  {len(dropped)} routes dropped")
    for reason, iatas in sorted(grouped.items(), key=lambda pair: -len(pair[1])):
        unique = sorted(set(iatas))
        sample = ", ".join(unique[:12])
        if len(unique) > 12:
            sample += ", …"
        print(f"  {len(iatas):4} routes ({len(unique)} codes: {sample})")
        print(f"       why: {reason}")


def drop_broken(path: Path, payload: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    drop_ids = {item["id"] for item in result["must_broken"]}
    if not drop_ids:
        print("\nNothing to drop. All saved flights already have required fields.")
        return result

    kept = []
    dropped_now = []
    for item in payload.get("destinations") or []:
        row_id = str(item.get("id") or "")
        if row_id in drop_ids:
            dropped_now.append(item)
        else:
            kept.append(item)

    errors = list(payload.get("errors") or [])
    for item in dropped_now:
        row = flatten(item)
        errors.append(
            {
                "destination_iata": row.get("destination_iata") or "unknown",
                "id": item.get("id"),
                "error": "Dropped: ranking weather/price/duration fields were blank.",
            }
        )
    payload["destinations"] = kept
    payload["errors"] = errors
    print(f"\nDropping {len(dropped_now)} broken flights from the JSON...")
    write_json(path, payload)
    return inspect(payload)


def print_report(path: Path, result: dict[str, Any]) -> int:
    total = len(result["destinations"])
    must_n = len(result["must_broken"])
    extra_n = len(result["extra_only"])
    usable = total - must_n
    dups = total - len(set(result["ids"]))

    print()
    print("=" * 64)
    if total == 0:
        print("VERDICT: EMPTY FILE")
        print("No saved flights. Ranking has nothing to use.")
        return 1
    if must_n:
        print("VERDICT: NOT READY")
        print(
            f"{must_n} of {total:,} saved flights are missing data ranking needs. "
            f"{usable:,} flights are usable."
        )
    else:
        print("VERDICT: READY")
        print(
            f"All {total:,} saved flights have the required ranking fields. "
            "0 rain/temp/sunshine is allowed."
        )
    print("=" * 64)

    print("\nSaved flights in this JSON (the file the team should use)")
    print(f"  saved:          {total:,}")
    print(f"  usable:         {usable:,}")
    print(f"  broken:         {must_n:,}  (these fail the check)")
    print(f"  optional gaps:  {extra_n:,}  (only airline/sunshine etc; ranking can still run)")
    print(f"  duplicate ids:  {dups:,}")

    print("\nHow to read values")
    print("  blank rain/temp         = bad (Open-Meteo gave no number)")
    print("  rain 0 or sunshine 0    = fine (dry or dark forecast)")
    print("  price 0 or duration 0   = bad (not a real ticket)")
    print("  latitude and longitude both 0 = bad (placeholder, not a city)")

    print_reason_counts("Required fields that are blank or impossible", result["must_counts"], total)
    print_broken_rows("Broken flights (fix or drop these)", result["must_broken"], key="must")

    print_reason_counts("Optional fields that are blank", result["extra_counts"], total)
    if extra_n and extra_n <= 20:
        print_broken_rows("Flights with only optional gaps", result["extra_only"], key="extra")
    elif extra_n:
        print(f"\n{extra_n} flights have only optional gaps (not listed).")

    if result["missing_sections"]:
        print("\nWhole JSON blocks missing on a flight")
        for section, count in result["missing_sections"].most_common():
            print(f"  {count:5}  missing `{section}`")

    if result["daily_null_rows"]:
        print("\nDaily forecast arrays")
        print(
            f"  {result['daily_null_rows']:,} flights still have weather.daily "
            "with a null day. Ranking and Cosmos use averages only, not that array."
        )

    print_dropped(result["dropped"])
    print()
    if must_n:
        print("FAIL: some saved flights are not good ranking data.")
        return 1
    print("OK: saved flights are good ranking data.")
    if result["dropped"]:
        print("Note: some other routes never made it into the file (see dropped list).")
    return 0


def main(argv: Iterable[str] | None = None) -> int:
    configure_stdout()
    parser = argparse.ArgumentParser(
        description="Check whether normalized_destinations.json is good ranking data."
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=str(DEFAULT_JSON),
        help="JSON file or folder that contains it (default: Real_data/normalized_destinations.json)",
    )
    parser.add_argument(
        "--drop-broken",
        action="store_true",
        help="Remove the broken saved flights from the JSON.",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    target = Path(args.path)
    if not target.is_absolute():
        target = PROJECT_DIR / target
    json_path = resolve_json(target)
    if not json_path.exists():
        print(f"File not found: {json_path}", file=sys.stderr)
        print("Pass a path to normalized_destinations.json", file=sys.stderr)
        return 2

    payload = load_payload(json_path)
    result = inspect(payload)
    exit_code = print_report(json_path, result)
    if args.drop_broken and result["must_broken"]:
        result = drop_broken(json_path, payload, result)
        print("\nAfter dropping broken flights:")
        exit_code = print_report(json_path, result)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
