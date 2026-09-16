"""Fetch memorable city photos from Pexels into normalized_destinations.json.

Writes photo_url and photo_url_small onto each nested destination object.
Cosmos is loaded from that JSON with load_to_cosmos.py (not from this script).

Usage:
    python data_preparation/load_city_photos.py Real_data
    python data_preparation/load_to_cosmos.py Real_data --origins-only
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from azure.cosmos import CosmosClient, exceptions

from load_to_cosmos import (
    ENV_FILE,
    ORIGINS_CONTAINER,
    PROJECT_DIR,
    copy_photo_fields,
    cosmos_settings,
    load_dotenv,
    strip_extra_photo_fields,
    text,
)

PEXELS_SEARCH_URL = "https://api.pexels.com/v1/search"
USER_AGENT = "team-4-travel-planner/1.0"
HTTP_TIMEOUT_SECONDS = 25
PEXELS_KEY_COUNT = 10
RATE_LIMIT_SLEEP_SECONDS = 5400  # 1.5 hours after every key is exhausted

# Extra search terms so Pexels returns a landmark / skyline, not a random hotel.
LANDMARK_HINTS: dict[str, str] = {
    "amsterdam": "canals",
    "antalya": "old town harbor",
    "athens": "Acropolis",
    "baku": "Flame Towers",
    "bangkok": "temples Grand Palace",
    "barcelona": "Sagrada Familia",
    "beijing": "Forbidden City",
    "berlin": "Brandenburg Gate",
    "budapest": "Parliament",
    "cairo": "pyramids",
    "copenhagen": "Nyhavn",
    "denpasar (bali)": "Bali temple rice terrace",
    "dubai": "Burj Khalifa skyline",
    "dublin": "Ha'penny Bridge",
    "edinburgh": "castle",
    "florence": "Duomo",
    "guangzhou": "Canton Tower skyline",
    "istanbul": "Hagia Sophia",
    "krakow": "main square",
    "lisbon": "Belem Tower tram",
    "london|gb": "Big Ben Thames",
    "madrid": "Plaza Mayor",
    "marrakech": "Jemaa el-Fnaa",
    "milan": "Duomo",
    "moscow": "Red Square Saint Basil",
    "munich": "Marienplatz",
    "naples": "Mount Vesuvius waterfront",
    "new york": "Manhattan skyline",
    "nice": "Promenade des Anglais",
    "oslo": "opera house",
    "paris": "Eiffel Tower",
    "phuket": "beach island",
    "porto": "Ribeira Douro",
    "prague": "Charles Bridge",
    "rome": "Colosseum",
    "saint petersburg": "Hermitage Palace Square",
    "shanghai": "Pudong skyline",
    "sharjah": "mosque waterfront",
    "split": "Diocletian Palace",
    "stockholm": "Gamla Stan",
    "sydney": "Opera House",
    "tashkent": "city square",
    "tbilisi": "old town",
    "tirana": "Skanderbeg Square",
    "tokyo": "skyline Mount Fuji",
    "valencia": "City of Arts",
    "venice": "Grand Canal",
    "vienna": "St Stephen Cathedral",
    "warsaw": "old town",
    "yerevan": "cascade",
    "zagreb": "Ban Jelacic Square",
}

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(line_buffering=True)


def _clean_secret(value: str | None) -> str:
    return (value or "").strip().strip('"').strip("'")


PEXELS_KEY_NAME_RE = re.compile(r"^PEXELS_API_KEY_?(\d+)$", re.IGNORECASE)
PEXELS_KEYS_LIST_RE = re.compile(r"^PEXELS_API_KEYS$", re.IGNORECASE)
PEXELS_KEY_BARE_RE = re.compile(r"^PEXELS_API_KEY$", re.IGNORECASE)


def pexels_keys() -> list[str]:
    """Read every Pexels key from .env, including PEXELS_API_KEY2 and PEXELS_API_KEY_2."""
    numbered: list[tuple[int, str]] = []
    seen: set[str] = set()

    def add(raw: str | None, order: int) -> None:
        key = _clean_secret(raw)
        if key and key not in seen:
            seen.add(key)
            numbered.append((order, key))

    if not ENV_FILE.exists():
        raise SystemExit(f"Missing {ENV_FILE}. Add PEXELS_API_KEY there.")

    names: list[str] = []
    for raw_line in ENV_FILE.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        name = name.strip()
        if PEXELS_KEYS_LIST_RE.match(name):
            for offset, part in enumerate(_clean_secret(value).split(",")):
                add(part, offset + 1)
                if _clean_secret(part):
                    names.append(name)
            continue
        if PEXELS_KEY_BARE_RE.match(name):
            add(value, 1)
            if _clean_secret(value):
                names.append(name)
            continue
        match = PEXELS_KEY_NAME_RE.match(name)
        if match:
            add(value, int(match.group(1)))
            if _clean_secret(value):
                names.append(name)

    numbered.sort(key=lambda pair: pair[0])
    found = [key for _, key in numbered]
    if not found:
        raise SystemExit(
            "No Pexels keys found. Use PEXELS_API_KEY, PEXELS_API_KEY2, "
            "PEXELS_API_KEY_2, ..."
        )
    print(f"  loaded {len(found)} Pexels key(s) from {', '.join(names)}")
    return found


class PexelsKeys:
    def __init__(self, keys: list[str], on_all_limited=None) -> None:
        self.keys = keys
        self.index = 0
        self.limited: set[int] = set()
        self.dead: set[int] = set()
        self.on_all_limited = on_all_limited

    def current(self) -> str:
        return self.keys[self.index]

    def label(self) -> str:
        return f"key {self.index + 1}/{len(self.keys)}"

    def _usable(self, index: int) -> bool:
        return index not in self.limited and index not in self.dead

    def _switch_to_next(self) -> bool:
        for step in range(1, len(self.keys) + 1):
            candidate = (self.index + step) % len(self.keys)
            if self._usable(candidate):
                self.index = candidate
                print(f"  switching to Pexels {self.label()}")
                return True
        return False

    def mark_unauthorized(self) -> None:
        print(f"  Pexels {self.label()} rejected (401). Skipping it.")
        self.dead.add(self.index)
        if not self._switch_to_next():
            raise SystemExit("Every Pexels API key was rejected (401). Check .env.")

    def mark_limited(self) -> None:
        print(f"  Pexels {self.label()} hit the rate limit.")
        self.limited.add(self.index)
        if self._switch_to_next():
            return
        if self.on_all_limited:
            self.on_all_limited()
        print(
            f"  All {len(self.keys)} Pexels keys are rate-limited. "
            "Sleeping 1.5 hours, then retrying."
        )
        time.sleep(RATE_LIMIT_SLEEP_SECONDS)
        self.limited.clear()
        if not self._switch_to_next():
            self.index = 0
        print(f"  resumed with Pexels {self.label()}")


def search_name(city: str) -> str:
    cleaned = re.sub(r"[()]", " ", city)
    return re.sub(r"\s+", " ", cleaned).strip()


def landmark_hint(city: str, country_code: str) -> str | None:
    code = country_code.lower()
    keyed = LANDMARK_HINTS.get(f"{city.casefold()}|{code}")
    if keyed:
        return keyed
    return LANDMARK_HINTS.get(city.casefold())


def photo_queries(city: str, country: str, country_code: str) -> list[str]:
    name = search_name(city)
    country_name = country or country_code
    hint = landmark_hint(city, country_code)
    queries: list[str] = []
    if hint:
        queries.append(f"{name} {country_name} {hint}")
    queries.append(f"{name} {country_name} landmark cityscape")
    queries.append(f"{name} {country_name}")
    seen: set[str] = set()
    unique: list[str] = []
    for query in queries:
        key = query.casefold()
        if key in seen:
            continue
        seen.add(key)
        unique.append(query)
    return unique


def pexels_search(api_key: str, query: str) -> dict[str, Any]:
    params = urllib.parse.urlencode(
        {
            "query": query,
            "per_page": 8,
            "orientation": "landscape",
        }
    )
    request = urllib.request.Request(
        f"{PEXELS_SEARCH_URL}?{params}",
        headers={
            "Authorization": api_key,
            "User-Agent": USER_AGENT,
        },
    )
    with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        return {}
    return payload


def pick_photo(photos: list[dict[str, Any]], city: str) -> dict[str, Any] | None:
    if not photos:
        return None
    needle = search_name(city).casefold()
    named = [
        photo
        for photo in photos
        if needle and needle in str(photo.get("alt") or "").casefold()
    ]
    return (named or photos)[0]


def photo_fields(photo: dict[str, Any]) -> dict[str, Any]:
    src = photo.get("src") or {}
    return {
        "photo_url": src.get("landscape") or src.get("large") or src.get("original"),
        "photo_url_small": src.get("medium") or src.get("small"),
    }


def fetch_city_photo(
    keys: PexelsKeys, city: str, country: str, country_code: str
) -> tuple[dict[str, Any] | None, int]:
    used = 0
    for query in photo_queries(city, country, country_code):
        used += 1
        while True:
            try:
                payload = pexels_search(keys.current(), query)
                break
            except urllib.error.HTTPError as error:
                if error.code == 401:
                    keys.mark_unauthorized()
                    continue
                if error.code == 429:
                    keys.mark_limited()
                    continue
                print(f"  Pexels HTTP {error.code} for {city}: {query}")
                payload = {}
                break
            except urllib.error.URLError as error:
                print(f"  Pexels network error for {city}: {error.reason}")
                payload = {}
                break
        photo = pick_photo(list(payload.get("photos") or []), city)
        if photo:
            return photo_fields(photo), used
    return None, used


def resolve_json(raw: str | None) -> Path:
    target = Path(raw or "Real_data")
    if not target.is_absolute():
        target = PROJECT_DIR / target
    if target.is_dir():
        return target / "normalized_destinations.json"
    return target


def place_key(item: dict[str, Any]) -> tuple[str, str] | None:
    dest = item.get("destination") or {}
    country = item.get("country") or {}
    city = text(dest.get("city"))
    if not city:
        return None
    country_code = (text(dest.get("country_code") or country.get("alpha_2")) or "XX").upper()
    return city.casefold(), country_code


def unique_places(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[tuple[str, str], dict[str, Any]] = {}
    order: list[tuple[str, str]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        key = place_key(item)
        if key is None:
            continue
        dest = item.get("destination") or {}
        country = item.get("country") or {}
        bucket = buckets.get(key)
        if bucket is None:
            bucket = {
                "key": key,
                "city": text(dest.get("city")),
                "country": text(country.get("common_name")),
                "country_code": key[1],
                "flight_count": 0,
                "photos": copy_photo_fields(dest),
            }
            buckets[key] = bucket
            order.append(key)
        bucket["flight_count"] += 1
        if not bucket["photos"]:
            bucket["photos"] = copy_photo_fields(dest)
        if text(country.get("common_name")) and not bucket["country"]:
            bucket["country"] = text(country.get("common_name"))
    order.sort(key=lambda key: (-buckets[key]["flight_count"], key[0]))
    return [buckets[key] for key in order]


def photos_from_container(container) -> dict[tuple[str, str], dict[str, Any]]:
    rows = container.query_items(
        query=(
            "SELECT c.city, c.country_code, c.photo_url, c.photo_url_small FROM c "
            "WHERE IS_DEFINED(c.photo_url) AND c.photo_url != null"
        ),
        enable_cross_partition_query=True,
    )
    found: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        city = text(row.get("city"))
        code = (text(row.get("country_code")) or "XX").upper()
        fields = copy_photo_fields(row)
        if city and fields.get("photo_url"):
            found[(city.casefold(), code)] = fields
    return found


def photos_from_cosmos() -> dict[tuple[str, str], dict[str, Any]]:
    endpoint, account_key, database_name = cosmos_settings()
    client = CosmosClient(url=endpoint, credential=account_key)
    database = client.get_database_client(database_name)
    found: dict[tuple[str, str], dict[str, Any]] = {}
    # origins is the real store. leftover "destinations" is only a one-time copy.
    for name in (ORIGINS_CONTAINER, "destinations"):
        try:
            imported = photos_from_container(database.get_container_client(name))
        except exceptions.CosmosHttpResponseError:
            continue
        for key, fields in imported.items():
            found.setdefault(key, fields)
    return found


def apply_photos(
    items: list[dict[str, Any]], photos: dict[tuple[str, str], dict[str, Any]]
) -> int:
    updated = 0
    for item in items:
        if not isinstance(item, dict):
            continue
        key = place_key(item)
        if key is None:
            continue
        fields = photos.get(key)
        if not fields:
            continue
        dest = item.setdefault("destination", {})
        dest.update(copy_photo_fields(fields))
        strip_extra_photo_fields(dest)
        updated += 1
    return updated


def write_normalized_json(path: Path, payload: dict[str, Any]) -> None:
    for item in payload.get("destinations") or []:
        if isinstance(item, dict):
            dest = item.get("destination")
            if isinstance(dest, dict):
                strip_extra_photo_fields(dest)
    print(f"Writing {path}...")
    path.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Write Pexels city photo URLs into normalized_destinations.json."
    )
    parser.add_argument(
        "path",
        nargs="?",
        default="Real_data",
        help="JSON file or folder (default: Real_data).",
    )
    parser.add_argument(
        "--max-photos",
        type=int,
        default=None,
        help="Max new Pexels lookups this run (default: all missing photos).",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.35,
        help="Seconds to wait between Pexels calls (default: 0.35).",
    )
    parser.add_argument(
        "--from-cosmos",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Copy existing Cosmos photo URLs into the JSON first (default: true).",
    )
    args = parser.parse_args(argv)

    json_path = resolve_json(args.path)
    if not json_path.exists():
        raise SystemExit(f"Missing {json_path}")
    print(f"Reading {json_path}...")
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SystemExit(f"{json_path} should be an object with a destinations list.")
    items = payload.get("destinations") or []
    places = unique_places(items)
    print(f"Unique destination cities: {len(places):,}  rows: {len(items):,}")

    photos: dict[tuple[str, str], dict[str, Any]] = {}
    for place in places:
        if place["photos"].get("photo_url"):
            photos[place["key"]] = place["photos"]
    print(f"  already in JSON: {len(photos):,}")

    if args.from_cosmos:
        print("Copying photo URLs already in Cosmos...")
        imported = 0
        for key, fields in photos_from_cosmos().items():
            if key in photos:
                continue
            photos[key] = fields
            imported += 1
        print(f"  imported from Cosmos: {imported:,}")

    missing = [place for place in places if place["key"] not in photos]
    photos_done = 0
    photos_failed = 0
    pexels_calls = 0
    if missing and args.max_photos != 0:
        load_dotenv(ENV_FILE)

        def save_progress() -> None:
            apply_photos(items, photos)
            write_normalized_json(json_path, payload)
            print("  saved JSON before 1.5 hour wait")

        keys = PexelsKeys(pexels_keys(), on_all_limited=save_progress)
        print(
            f"Fetching Pexels photos for {len(missing):,} cities "
            f"with {len(keys.keys)} API keys..."
        )
        for place in missing:
            if args.max_photos is not None and photos_done >= args.max_photos:
                unused = sum(
                    1
                    for i in range(len(keys.keys))
                    if i not in keys.limited and i not in keys.dead
                )
                print(
                    f"Reached --max-photos {args.max_photos} (that cap stops the run, "
                    f"not the API keys). {unused} key(s) still unused. "
                    "Rerun without --max-photos to keep filling."
                )
                break
            fields, used = fetch_city_photo(
                keys,
                place["city"] or "",
                place["country"] or "",
                place["country_code"],
            )
            pexels_calls += used
            if fields and fields.get("photo_url"):
                photos[place["key"]] = fields
                photos_done += 1
                if photos_done % 10 == 0:
                    print(f"  photo {photos_done}: {place['city']}, {place['country']}")
                if photos_done % 25 == 0:
                    apply_photos(items, photos)
                    write_normalized_json(json_path, payload)
            else:
                photos_failed += 1
                print(f"  no photo: {place['city']}, {place['country']}")
            time.sleep(max(args.delay, 0))
    elif not missing:
        print("Every unique city already has a photo URL.")
    else:
        print("Skipping Pexels (--max-photos 0).")

    updated_rows = apply_photos(items, photos)
    cities_with_photos = sum(1 for place in places if place["key"] in photos)
    write_normalized_json(json_path, payload)
    print(
        f"Done. {cities_with_photos:,} cities with photos  "
        f"{updated_rows:,} JSON rows updated  "
        f"{photos_done:,} new Pexels photos  {photos_failed:,} missed  "
        f"{pexels_calls:,} Pexels calls"
    )
    print("Push to Cosmos with: python data_preparation/load_to_cosmos.py Real_data --origins-only")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nCancelled.")
        raise SystemExit(130)
