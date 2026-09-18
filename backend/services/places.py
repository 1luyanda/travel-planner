"""Google Places (New) lookup for destination activities.

The API key stays in the backend process. It is never logged or returned.
"""

from __future__ import annotations

import os
from collections.abc import Awaitable, Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

from backend.contracts.activities import (
    ActivitiesRequest,
    ActivitiesResponse,
    ActivityItem,
)

PLACES_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
FIELD_MASK = (
    "places.id,"
    "places.displayName,"
    "places.formattedAddress,"
    "places.types,"
    "places.businessStatus,"
    "places.rating,"
    "places.userRatingCount,"
    "places.priceLevel"
)
CLOSED_PERMANENTLY = "CLOSED_PERMANENTLY"
DEFAULT_TIMEOUT_SECONDS = 20.0
_ENV_PATH = Path(__file__).resolve().parents[2] / ".env"
_PLACEHOLDER_API_KEYS = frozenset(
    {
        "replace-with-your-key",
        "your-key",
        "changeme",
        "todo",
        "xxx",
        "none",
    }
)
MOOD_SEARCH_PHRASES: dict[str, tuple[str, ...]] = {
    "cultural": ("museums", "historical landmarks"),
    "relaxing": ("parks", "spas", "beaches"),
    "outdoors": ("parks", "hiking", "outdoor attractions"),
}

HttpPost = Callable[..., Awaitable[Any]]


class PlacesConfigurationError(RuntimeError):
    """Raised when Google Places is not configured."""


class PlacesUnavailableError(RuntimeError):
    """Raised when Google Places cannot be queried safely."""


class PlacesService:
    """Text Search (New) client that returns verified activity items."""

    def __init__(
        self,
        api_key: str,
        *,
        http_post: HttpPost | None = None,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        cleaned = api_key.strip()
        if not cleaned:
            raise PlacesConfigurationError(
                "Activity data is temporarily unavailable."
            )
        self._api_key = cleaned
        self._http_post = http_post
        self._timeout_seconds = timeout_seconds

    @classmethod
    def from_env(cls) -> PlacesService:
        load_dotenv(_ENV_PATH, override=False)
        key = _usable_secret(os.getenv("GOOGLE_PLACES_API_KEY"))
        if key is None:
            raise PlacesConfigurationError(
                "Activity data is temporarily unavailable."
            )
        return cls(key)

    async def search(self, request: ActivitiesRequest) -> ActivitiesResponse:
        queries = build_text_queries(request.city, request.country_code, request.moods)
        collected: list[ActivityItem] = []
        seen_ids: set[str] = set()

        for query in queries:
            for item in await self._search_text(query, page_size=request.limit):
                if item.place_id in seen_ids:
                    continue
                seen_ids.add(item.place_id)
                collected.append(item)
                if len(collected) >= request.limit:
                    return _ready_response(request, collected)
        return _ready_response(request, collected)

    async def _search_text(self, text_query: str, *, page_size: int) -> list[ActivityItem]:
        payload = {
            "textQuery": text_query,
            "pageSize": page_size,
        }
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": self._api_key,
            "X-Goog-FieldMask": FIELD_MASK,
        }
        try:
            response = await self._post(payload, headers)
        except httpx.HTTPError as error:
            raise PlacesUnavailableError(
                "Activity data is temporarily unavailable."
            ) from error

        if getattr(response, "status_code", 0) != 200:
            raise PlacesUnavailableError(
                "Activity data is temporarily unavailable."
            )

        try:
            data = response.json()
        except Exception as error:
            raise PlacesUnavailableError(
                "Activity data is temporarily unavailable."
            ) from error

        places = data.get("places") if isinstance(data, Mapping) else None
        if not isinstance(places, list):
            return []

        items: list[ActivityItem] = []
        for place in places:
            item = normalize_place(place)
            if item is not None:
                items.append(item)
        return items

    async def _post(self, payload: dict[str, Any], headers: dict[str, str]) -> Any:
        if self._http_post is not None:
            return await self._http_post(
                PLACES_SEARCH_URL,
                json=payload,
                headers=headers,
                timeout=self._timeout_seconds,
            )
        async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
            return await client.post(
                PLACES_SEARCH_URL,
                json=payload,
                headers=headers,
            )


def build_text_queries(
    city: str,
    country_code: str | None,
    moods: Sequence[str],
) -> list[str]:
    location = f"{city}, {country_code}" if country_code else city
    if not moods:
        return [f"tourist attractions in {location}"]

    phrases: list[str] = []
    seen: set[str] = set()
    for mood in moods:
        key = mood.strip().lower()
        mapped = MOOD_SEARCH_PHRASES.get(key, (f"{key} attractions",))
        for phrase in mapped:
            if phrase in seen:
                continue
            seen.add(phrase)
            phrases.append(phrase)
    return [f"{phrase} in {location}" for phrase in phrases]


def normalize_place(place: Any) -> ActivityItem | None:
    if not isinstance(place, Mapping):
        return None
    place_id = str(place.get("id") or "").strip()
    name = _place_name(place.get("displayName"))
    if not place_id or not name:
        return None
    business_status = _optional_str(place.get("businessStatus"))
    if business_status == CLOSED_PERMANENTLY:
        return None
    return ActivityItem(
        place_id=place_id,
        name=name,
        types=_string_list(place.get("types")),
        address=_optional_str(place.get("formattedAddress")),
        rating=_optional_float(place.get("rating")),
        user_ratings_total=_optional_int(place.get("userRatingCount")),
        business_status=business_status,
        price_level=_optional_str(place.get("priceLevel")),
    )


def _ready_response(
    request: ActivitiesRequest,
    activities: list[ActivityItem],
) -> ActivitiesResponse:
    return ActivitiesResponse(
        status="ready",
        city=request.city,
        destination_id=request.destination_id,
        activities=activities,
        issues=[],
    )


def _usable_secret(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip().strip('"').strip("'")
    if not cleaned or cleaned.lower() in _PLACEHOLDER_API_KEYS:
        return None
    return cleaned


def _place_name(display_name: Any) -> str | None:
    if isinstance(display_name, Mapping):
        return _optional_str(display_name.get("text"))
    return _optional_str(display_name)


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    items: list[str] = []
    for item in value:
        text = _optional_str(item)
        if text:
            items.append(text)
    return items
