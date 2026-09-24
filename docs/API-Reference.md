# API reference

[Documentation index](README.md)

Paths below are relative to the API host, normally `http://127.0.0.1:8000`. All `/api` routes except health require `X-API-Key`. Vite inserts it for local browser traffic. Routes marked Session additionally require the signed authentication cookie. JSON is used except for photo bytes and 204 responses.

## Route inventory

| Method | Path | Session | Input and behavior |
|---|---|---|---|
| GET | `/api/health` | No | Public; returns `{"status":"ok"}` |
| POST | `/api/auth/register` | No | `email`, `password`, `display_name`; 201, user wrapper and cookie |
| POST | `/api/auth/login` | No | `email`, `password`; user wrapper and cookie |
| POST | `/api/auth/logout` | No | Clears cookie; 204 |
| GET | `/api/auth/me` | Yes | Returns user object, without a `user` wrapper |
| GET | `/api/origins` | No | Required `q` (1-100 characters), optional `country`; origin array |
| GET | `/api/origins/{origin_id}` | No | One origin; 404 if absent |
| GET | `/api/flights` | No | Stored, allowlisted flight fields for an origin |
| GET | `/api/candidates` | No | Validated unranked candidates, flights, rejection reasons, and date metadata |
| POST | `/api/recommend` | No | Parse, retrieve, rank, and explain |
| POST | `/api/refine` | No | Apply feedback to a supplied request and rerun search |
| GET | `/api/hotels` | No | Required hotel `destination_id`; optional `limit`, default 5, range 1-20 |
| POST | `/api/activities` | No | City activity search |
| POST | `/api/activities/nearby` | No | Nearby activity search by city or coordinates |
| GET | `/api/activities/photo` | No | Required Places photo `name`; `max_height_px` defaults to 400, range 1-480; image bytes |
| GET | `/api/saved-flights` | Yes | Saved flight `items` |
| POST | `/api/saved-flights` | Yes | `{ "flight_id": "<stored-flight-id>" }`; saved item |
| DELETE | `/api/saved-flights/{flight_id}` | Yes | Remove saved item; 204 |
| GET | `/api/saved-activities` | Yes | Saved activity `items` |
| POST | `/api/saved-activities` | Yes | Activity snapshot plus city context; saved item |
| DELETE | `/api/saved-activities/{place_id}` | Yes | Remove liked activity; 204 |

## Flight and candidate query parameters

Both endpoints require `origin_id` (3-150 characters). They accept optional ISO `departure_date`, `return_date`, `max_price` (greater than 0, at most 1,000,000), `min_temp` (-100 to 100), and two-character `country`. `limit` defaults to 100 and accepts 1-200.

Only `/api/candidates` defines `max_changeovers` (0-20) and `max_duration_minutes` (1-10,080). `/api/flights` does not apply those constraints or flexible-date fallback. Retrieval limits bound the pool before ranking; these routes are not paginated exports of the full database.

## Recommend and refine

Example recommend body (illustrative; results depend on stored dates and origin):

```json
{
  "text": "Somewhere warm and relaxing",
  "form_fields": {
    "origin": "ZAG",
    "departure_date": "2026-10-12",
    "return_date": "2026-10-16",
    "budget": 400,
    "currency": "EUR"
  }
}
```

`text` defaults to empty and is limited to 4,000 characters. `form_fields` accepts up to 20 entries; recognized fields are `origin`, `departure_date`, `return_date`, `duration_days`, `budget`, `currency`, `moods`, `direct_flights_only`, and `weather_preference`.

Refine requires nonempty `text` (at most 2,000 characters) and a `request` matching TripRequest. Send the previous effective request; after a refinement use `updated_request`. Both endpoints accept `ranking_preferences`. Filter-only recommend calls can set `preserve_ranking_preferences: true` with the current preferences.

Response `status` is `ready`, `needs_input`, or `error`, independently of HTTP success. Inspect `issues` and `clarification_questions`. Other fields include `request`, `updated_request`, `preferences`, `origin`, `origin_id`, `recommendations`, `flights`, `rejected`, `intents`, `changes`, `ranking_preferences`, and date fallback counts/flags. Ready responses can have no recommendations.

Each recommendation contains its flight-offer `destination_id`, rank, component and final scores, summary/evidence, date metadata, and nullable `hotel_destination_id`. Use the latter for hotels. See [Ranking and recommendations](Ranking-and-Recommendations.md).

## Activities and hotels

City activities require `city`, with optional `country_code`, `destination_id`, `moods`, and `limit` (default 8, range 1-20). The response has `status`, `city`, `destination_id`, `activities`, and `issues`.

Nearby search requires a nonblank city or both `latitude` and `longitude`. Coordinates take precedence when supplied. `radius_meters` defaults to 5,000 (range 1-50,000); `limit` defaults to 10 (range 1-20). `included_types` accepts up to five entries from `tourist_attraction`, `museum`, `park`, `art_gallery`, and `historical_landmark`; an empty list uses all five. The response includes search center, radius, issues, activities, and Google Maps attribution.

Photo names must pass the service's Places resource-name pattern. Photos are streamed with `Cache-Control: no-store` and `X-Content-Type-Options: nosniff`.

Hotels return destination identity, reference coordinates, attribution, `hotel_count`, `returned_count`, and the ordered `hotels` array. Entries include name, OSM ID, optional stars, coordinates, distance in kilometers, and optional address/website/booking URL metadata. The frontend does not expose a hotel booking flow.

## Saved-item bodies

Saved-flight writes accept a stored flight ID, not a user ID or client flight snapshot. Saved-activity writes accept an `activity` object (at least `place_id` and `name`), required `city`, and optional `country_code` and `destination_id`. The backend stores the supplied typed activity snapshot without re-querying Places. Saved reads return `items`; flight items include availability and a flight snapshot.

## Error handling

| Status | Typical meaning |
|---|---|
| 400 | Invalid Content-Length, or rejected Host header |
| 401 | Missing/invalid API key, credentials, or required session |
| 404 | Missing origin, hotel destination, or flight being saved |
| 409 | Registration email already exists |
| 413 | Declared request length exceeds configured maximum |
| 422 | Request contract validation, including invalid photo names |
| 503 | Unconfigured authentication or unavailable storage/provider service |

Production disables generated OpenAPI pages. In development, `/docs` and `/openapi.json` provide the full Pydantic schemas. The frontend handles 429 responses, but no application rate limiter is implemented here.

Sources: [data routes](../backend/api/routes.py), [auth routes](../backend/api/auth.py), [recommendation contracts](../backend/contracts/recommendations.py), [activity contracts](../backend/contracts/activities.py), [saved activity contract](../backend/contracts/saved_activities.py).
