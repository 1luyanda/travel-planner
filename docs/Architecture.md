# Architecture

[Documentation index](README.md)

## Components

| Component | Responsibility |
|---|---|
| `frontend/src` | React UI, browser navigation, map interactions, request state, and HTTP clients |
| `frontend/vite.config.js` | Local development API proxy and server-side API-key injection |
| `backend/api` | FastAPI routes and HTTP error mapping |
| `backend/contracts`, `backend/models` | Pydantic request, response, and persistence models |
| `backend/services` | Recommendation orchestration, accounts, saved items, hotels, Places, and LLM operations |
| `backend/data` | Retrieval adapter between services and the repository |
| `backend/repositories/cosmos.py` | Async Cosmos queries and saved-item writes |
| `ranking` | Storage-independent validation, hard constraints, scoring, and preference policy |
| `tests`, frontend test files | Automated behavioral checks with fixtures and mocks |

## Planner request flow

```text
React -> Vite /api proxy -> FastAPI authentication and route
  -> parse text/form or interpret refinement
  -> resolve origin IATA in Cosmos
  -> retrieve and validate flight candidates
  -> add eligible nearby-date candidates when needed
  -> deterministic ranking -> top five
  -> grounded explanations and hotel-ID enrichment
  -> response -> React cards and destination map
```

`/api/candidates` stops at preparation and remains unranked. `/api/flights` returns allowlisted stored flight data. The planner uses the flights included in recommend/refine responses for display rather than fetching `/api/flights` after each search.

The client carries the validated trip request and effective ranking preferences into refinement. The backend does not store a durable conversation. RecommendationService has a process-local explanation cache capped at 64 entries; refinements may reuse summaries/evidence while rebuilding scores and ranks. This is not a shared persistent cache.

## Independent detail services

Opening trip details loads stored hotels by the resolved hotel destination ID and activities from Google Places. Hotel resolution failures leave flight recommendations usable with an issue and null hotel IDs. Explore uses a separate nearby activity endpoint with a city or coordinates. Liked activities and saved flights are persisted under the authenticated user.

React Leaflet supplies destination, hotel, and activity map interactions. Valid coordinates are required for markers. External maps/photos and Places are separate from stored flight and hotel retrieval.

## Process lifecycle and boundaries

FastAPI startup loads settings, initializes a Cosmos repository and shared services, and creates the LLM client when configured. Shutdown closes database and LLM clients. The application does not create Cosmos containers.

The checked-in Vite proxy is a development integration. A frontend build produces static assets; this repository does not provide a production gateway, infrastructure deployment, or scheduled ingestion service.

Sources: [application](../backend/main.py), [recommendation service](../backend/services/recommendations.py), [candidate service](../backend/services/candidates.py), [frontend application](../frontend/src/App.jsx).
