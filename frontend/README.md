# Travel Planner frontend

React UI for Team 4's Travel Planner. The main planner flow calls FastAPI
`POST /api/recommend` and `POST /api/refine`. Origin autocomplete uses
`GET /api/origins`. Recommend and refine already include flight display fields
for map pins. `/api/flights` remains available but is not called after search.
Fares are not live or bookable. Start the backend
first so the Vite `/api` proxy can reach `http://127.0.0.1:8000`.

## Run locally (Windows PowerShell)

```powershell
cd frontend
npm install
npm run dev
```

Open the URL shown by Vite, normally `http://localhost:5173`.

The landing page links to dedicated Log in and Sign up pages. Authentication
uses credentials-inclusive requests and an HttpOnly cookie; the frontend never
stores a password or session token in localStorage. Saved flights are stored
on the backend for the signed-in user and are not kept in localStorage.

## Build

```powershell
cd frontend
npm install
npm run build
```

## Notes

- Selected Trip Details loads `GET /api/hotels?destination_id=<id>&limit=5`
  and shows Hotels above Activities, using the same stacked-card styling.
  The recommendation adapter preserves the backend's `hotel_destination_id`
  as `hotelDestinationId`; selection and display enrichment retain it unchanged.
  No hotel IDs are reconstructed and no hotel requests run for shortlist cards.
  Requests run on opening details or changing the hotel destination, with
  cancellation and stale-response protection on switching or closing. Ordinary
  rerenders and switching between offers with the same hotel ID do not refetch;
  reopening details refreshes the data. Errors have a Retry button and leave
  the rest of Trip Details usable. A missing ID or empty response shows an
  empty-state message. Older saved-flight responses without this ID use that
  same empty state.
- Hotels keep backend order. Distances are rounded to two decimals for display
  and described as approximate straight-line distances. Stars and safe HTTP(S)
  official website links appear only when supplied; links open in a new tab.
  Only display fields and coordinates are retained from the hotel response.
  There are no hotel booking links/buttons, prices or availability.
- Hotels and Activities have keyboard-accessible toggle buttons with
  `aria-expanded` and `aria-controls`. Hotels starts expanded and Activities
  collapsed. Content stays mounted while hidden, so toggling preserves data,
  errors and hotel markers and does not trigger a fetch.
- Valid hotel coordinates produce small bed-icon markers alongside existing
  destination pins. Hotel identity uses `osm_id`, falling back to a combination
  of name and coordinates. Clicking a hotel card or marker selects both, pans
  at the current zoom, and opens the hotel popup. Selecting another trip or
  closing details clears hotel selection; switching hotel destinations replaces
  the markers. Missing locations remain listed but cannot pan/create markers.
  Existing destination pins and Show all destinations retain their behavior.
- DOM interaction tests use the development-only `jsdom` dependency and a
  Leaflet adapter mock to verify selection, pan requests, and popup behavior.

- Natural-language parsing, ranking, and explanations run in the planner service.
- Origin autocomplete is optional. A 3-letter IATA code in the prompt or a
  selected origin is sent as `form_fields.origin`.
- Missing dates, budget, or currency are returned as `needs_input` with
  `clarification_questions`.
- Missing optional fields stay unavailable; map pins require valid destination
  coordinates from flight documents.
- Saved uses `GET/POST/DELETE /api/saved-flights`. It is independent of the
  current shortlist and filters, and does not show Explore chat or the
  composer. Only flight IDs are stored; details come from the flights
  container.
