# Travel Planner frontend

React UI for Team 4's Travel Planner. The main planner flow calls FastAPI
`POST /api/recommend` and `POST /api/refine`. Origin autocomplete uses
`GET /api/origins`. `/api/flights` is only used to enrich map pins and photos;
it does not rank results. Fares are not live or bookable. Start the backend
first so the Vite `/api` proxy can reach `http://127.0.0.1:8000`.

## Run locally (Windows PowerShell)

```powershell
cd frontend
npm install
npm run dev
```

Open the URL shown by Vite, normally `http://localhost:5173`.

The landing page provides local registration, sign-in, and logout. Authentication
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
