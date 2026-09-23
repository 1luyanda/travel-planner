"""Google Places (New) lookup for destination activities.

The API key stays in the backend process. It is never logged or returned.
Nearby searches do not log coordinates, and place content is not cached.
"""

from __future__ import annotations

import math
import os
import re
from collections.abc import Awaitable, Callable, Mapping, Sequence
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
from dotenv import load_dotenv

from backend.contracts.activities import (
    ActivitiesRequest,
    ActivitiesResponse,
    ActivityItem,
    ActivityPhoto,
    NearbyActivitiesRequest,
    NearbyActivitiesResponse,
    NearbyActivityItem,
    PhotoAttribution,
    SearchCenter,
)

PLACES_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
PLACES_NEARBY_URL = "https://places.googleapis.com/v1/places:searchNearby"
FIELD_MASK = (
    "places.id,"
    "places.displayName,"
    "places.formattedAddress,"
    "places.types,"
    "places.businessStatus,"
    "places.rating,"
    "places.userRatingCount,"
    "places.priceLevel,"
    "places.editorialSummary,"
    "places.location"
)
NEARBY_FIELD_MASK = (
    "places.id,"
    "places.displayName,"
    "places.formattedAddress,"
    "places.types,"
    "places.businessStatus,"
    "places.rating,"
    "places.userRatingCount,"
    "places.location,"
    "places.googleMapsUri,"
    "places.photos.name,"
    "places.photos.authorAttributions,"
    "places.photos.googleMapsUri,"
    "places.editorialSummary"
)
LOCALITY_FIELD_MASK = "places.location,places.displayName"
PHOTO_NAME_RE = re.compile(r"^places/[A-Za-z0-9_-]{1,255}/photos/[A-Za-z0-9_-]{1,900}$")
MAX_PHOTO_BYTES = 2_000_000
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
HttpGet = Callable[..., Awaitable[Any]]


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
        http_get: HttpGet | None = None,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        cleaned = api_key.strip()
        if not cleaned:
            raise PlacesConfigurationError(
                "Activity data is temporarily unavailable."
            )
        self._api_key = cleaned
        self._http_post = http_post
        self._http_get = http_get
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

    async def search_nearby(self, request: NearbyActivitiesRequest) -> NearbyActivitiesResponse:
        """Nearby Search (New) around an explicit coordinate or a typed city."""

        if request.latitude is not None and request.longitude is not None:
            center = (request.latitude, request.longitude)
        else:
            center = await self._resolve_locality(request.city or "", request.country_code)
            if center is None:
                return NearbyActivitiesResponse(
                    status="ready",
                    city=request.city,
                    radius_meters=request.radius_meters,
                    search_center=None,
                    activities=[],
                    issues=["No matching city location was found."],
                )

        latitude, longitude = center
        places = await self._search_nearby(
            latitude=latitude,
            longitude=longitude,
            radius_meters=request.radius_meters,
            limit=request.limit,
            included_types=request.included_types,
            region_code=request.country_code,
        )
        collected: list[NearbyActivityItem] = []
        seen_ids: set[str] = set()
        for place in places:
            item = normalize_nearby_place(place)
            if item is None or item.place_id in seen_ids:
                continue
            seen_ids.add(item.place_id)
            collected.append(item)
            if len(collected) >= request.limit:
                break
        return NearbyActivitiesResponse(
            status="ready",
            city=request.city,
            radius_meters=request.radius_meters,
            search_center=SearchCenter(latitude=latitude, longitude=longitude),
            activities=collected,
            issues=[],
        )

    async def fetch_photo(self, name: str, *, max_height_px: int) -> tuple[bytes, str]:
        """Load one photo without persisting it or exposing the API key."""

        if not PHOTO_NAME_RE.fullmatch(name):
            raise PlacesUnavailableError("Activity photo is unavailable.")
        media_url = f"https://places.googleapis.com/v1/{name}/media"
        try:
            meta = await self._get(
                media_url,
                params={"maxHeightPx": max_height_px, "skipHttpRedirect": "true"},
                headers={
                    "X-Goog-Api-Key": self._api_key,
                    "X-Goog-FieldMask": "photoUri",
                },
            )
        except httpx.HTTPError as error:
            raise PlacesUnavailableError("Activity photo is unavailable.") from error
        if getattr(meta, "status_code", 0) != 200:
            raise PlacesUnavailableError("Activity photo is unavailable.")
        try:
            payload = meta.json()
        except Exception as error:
            raise PlacesUnavailableError("Activity photo is unavailable.") from error
        photo_uri = payload.get("photoUri") if isinstance(payload, Mapping) else None
        if not isinstance(photo_uri, str) or self._api_key in photo_uri:
            raise PlacesUnavailableError("Activity photo is unavailable.")
        safe_uri = _safe_google_image_uri(photo_uri)
        if safe_uri is None:
            raise PlacesUnavailableError("Activity photo is unavailable.")
        try:
            image = await self._get(safe_uri, params=None, headers={})
        except httpx.HTTPError as error:
            raise PlacesUnavailableError("Activity photo is unavailable.") from error
        if getattr(image, "status_code", 0) != 200:
            raise PlacesUnavailableError("Activity photo is unavailable.")
        content_type = _image_content_type(getattr(image, "headers", {}) or {})
        body = getattr(image, "content", b"")
        if not isinstance(body, (bytes, bytearray)) or not body or len(body) > MAX_PHOTO_BYTES:
            raise PlacesUnavailableError("Activity photo is unavailable.")
        if content_type is None:
            raise PlacesUnavailableError("Activity photo is unavailable.")
        return bytes(body), content_type

    async def _resolve_locality(
        self,
        city: str,
        country_code: str | None,
    ) -> tuple[float, float] | None:
        text_query = f"{city}, {country_code}" if country_code else city
        payload = {
            "textQuery": text_query,
            "pageSize": 1,
            "includedType": "locality",
        }
        data = await self._request(PLACES_SEARCH_URL, payload, LOCALITY_FIELD_MASK)
        places = data.get("places") if isinstance(data, Mapping) else None
        if not isinstance(places, list):
            return None
        for place in places:
            if not isinstance(place, Mapping):
                continue
            latitude, longitude = _coordinates(place.get("location"))
            if latitude is not None and longitude is not None:
                return latitude, longitude
        return None

    async def _search_nearby(
        self,
        *,
        latitude: float,
        longitude: float,
        radius_meters: int,
        limit: int,
        included_types: Sequence[str],
        region_code: str | None,
    ) -> list[Any]:
        payload: dict[str, Any] = {
            "includedTypes": list(included_types),
            "maxResultCount": limit,
            "locationRestriction": {
                "circle": {
                    "center": {"latitude": latitude, "longitude": longitude},
                    "radius": float(radius_meters),
                }
            },
        }
        if region_code:
            payload["regionCode"] = region_code
        data = await self._request(PLACES_NEARBY_URL, payload, NEARBY_FIELD_MASK)
        places = data.get("places") if isinstance(data, Mapping) else None
        return places if isinstance(places, list) else []

    async def _search_text(self, text_query: str, *, page_size: int) -> list[ActivityItem]:
        payload = {
            "textQuery": text_query,
            "pageSize": page_size,
        }
        data = await self._request(PLACES_SEARCH_URL, payload, FIELD_MASK)
        places = data.get("places") if isinstance(data, Mapping) else None
        if not isinstance(places, list):
            return []

        items: list[ActivityItem] = []
        for place in places:
            item = normalize_place(place)
            if item is not None:
                items.append(item)
        return items

    async def _request(
        self,
        url: str,
        payload: dict[str, Any],
        field_mask: str,
    ) -> Mapping[str, Any]:
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": self._api_key,
            "X-Goog-FieldMask": field_mask,
        }
        try:
            response = await self._post(url, payload, headers)
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
        if not isinstance(data, Mapping):
            raise PlacesUnavailableError("Activity data is temporarily unavailable.")
        return data

    async def _post(self, url: str, payload: dict[str, Any], headers: dict[str, str]) -> Any:
        if self._http_post is not None:
            return await self._http_post(
                url,
                json=payload,
                headers=headers,
                timeout=self._timeout_seconds,
            )
        async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
            return await client.post(url, json=payload, headers=headers)

    async def _get(
        self,
        url: str,
        *,
        params: dict[str, Any] | None,
        headers: dict[str, str],
    ) -> Any:
        if self._http_get is not None:
            return await self._http_get(
                url,
                params=params,
                headers=headers,
                timeout=self._timeout_seconds,
            )
        async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
            return await client.get(url, params=params, headers=headers)


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
    description, language_code = editorial_description(place)
    latitude, longitude = _coordinates(place.get("location"))
    return ActivityItem(
        place_id=place_id,
        name=name,
        types=_string_list(place.get("types")),
        address=_optional_str(place.get("formattedAddress")),
        rating=_optional_float(place.get("rating")),
        user_ratings_total=_optional_int(place.get("userRatingCount")),
        business_status=business_status,
        price_level=_optional_str(place.get("priceLevel")),
        description=description,
        description_language_code=language_code,
        latitude=latitude,
        longitude=longitude,
    )


def editorial_description(place: Mapping[str, Any]) -> tuple[str | None, str | None]:
    """Copy Google's editorial text unchanged. Do not invent a substitute."""
    summary = place.get("editorialSummary")
    if not isinstance(summary, Mapping):
        return None, None
    text = summary.get("text")
    if not isinstance(text, str) or not text.strip():
        return None, None
    return text, _optional_str(summary.get("languageCode"))


def normalize_nearby_place(place: Any) -> NearbyActivityItem | None:
    if not isinstance(place, Mapping):
        return None
    place_id = str(place.get("id") or "").strip()
    name = _place_name(place.get("displayName"))
    if not place_id or not name:
        return None
    business_status = _optional_str(place.get("businessStatus"))
    if business_status == CLOSED_PERMANENTLY:
        return None
    latitude, longitude = _coordinates(place.get("location"))
    description, language_code = editorial_description(place)
    return NearbyActivityItem(
        place_id=place_id,
        name=name,
        types=_string_list(place.get("types")),
        address=_optional_str(place.get("formattedAddress")),
        rating=_optional_float(place.get("rating")),
        user_ratings_total=_optional_int(place.get("userRatingCount")),
        business_status=business_status,
        latitude=latitude,
        longitude=longitude,
        google_maps_uri=_safe_maps_uri(place.get("googleMapsUri")),
        photo=_first_photo(place.get("photos")),
        description=description,
        description_language_code=language_code,
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


def _coordinates(value: Any) -> tuple[float | None, float | None]:
    if not isinstance(value, Mapping):
        return None, None
    latitude = _optional_float(value.get("latitude"))
    longitude = _optional_float(value.get("longitude"))
    if latitude is None or longitude is None:
        return None, None
    if not math.isfinite(latitude) or not math.isfinite(longitude):
        return None, None
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        return None, None
    return latitude, longitude


def _first_photo(value: Any) -> ActivityPhoto | None:
    if not isinstance(value, list):
        return None
    for item in value:
        if not isinstance(item, Mapping):
            continue
        name = _optional_str(item.get("name"))
        if name is None or PHOTO_NAME_RE.fullmatch(name) is None:
            continue
        return ActivityPhoto(
            name=name,
            author_attributions=_photo_attributions(item.get("authorAttributions")),
            google_maps_uri=_safe_maps_uri(item.get("googleMapsUri")),
        )
    return None


def _photo_attributions(value: Any) -> list[PhotoAttribution]:
    if not isinstance(value, list):
        return []
    authors: list[PhotoAttribution] = []
    for item in value:
        if not isinstance(item, Mapping):
            continue
        display_name = _optional_str(item.get("displayName"))
        uri = _safe_https_uri(item.get("uri"))
        photo_uri = _safe_google_image_uri(item.get("photoUri"))
        if not display_name and uri is None and photo_uri is None:
            continue
        authors.append(
            PhotoAttribution(display_name=display_name, uri=uri, photo_uri=photo_uri)
        )
    return authors


def _safe_https_uri(value: Any) -> str | None:
    text = _optional_str(value)
    if text is None:
        return None
    parsed = urlparse(text)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not host or parsed.username or parsed.password:
        return None
    return text


def _safe_maps_uri(value: Any) -> str | None:
    text = _safe_https_uri(value)
    if text is None:
        return None
    parsed = urlparse(text)
    host = (parsed.hostname or "").lower()
    if host in {"maps.google.com", "maps.app.goo.gl"}:
        return text
    if host in {"www.google.com", "google.com"} and parsed.path.startswith("/maps"):
        return text
    return None


def _safe_google_image_uri(value: Any) -> str | None:
    text = _safe_https_uri(value)
    if text is None:
        return None
    host = (urlparse(text).hostname or "").lower()
    if host == "googleusercontent.com" or host.endswith(".googleusercontent.com"):
        return text
    if host == "ggpht.com" or host.endswith(".ggpht.com"):
        return text
    return None


def _image_content_type(headers: Mapping[str, Any]) -> str | None:
    raw = headers.get("content-type") or headers.get("Content-Type")
    if not isinstance(raw, str):
        return None
    media_type = raw.split(";", 1)[0].strip().lower()
    if media_type.startswith("image/"):
        return media_type
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
