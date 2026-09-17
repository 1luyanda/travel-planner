# Travel Planner frontend

React UI for Team 4's Travel Planner. It searches stored Cosmos snapshots through FastAPI (`/api/origins`, `/api/candidates`, `/api/flights`) and ranks results in the browser. Fares are not live or bookable. Start the backend first so the Vite `/api` proxy can reach `http://127.0.0.1:8000`.

## Run locally (Windows PowerShell)

```powershell
cd frontend
npm install
npm run dev
```

Open the URL shown by Vite, normally `http://localhost:5173`.

The landing page provides local registration, sign-in, and logout. Authentication
uses credentials-inclusive requests and an HttpOnly cookie; the frontend never
stores a password or session token in localStorage.

## Build

```powershell
cd frontend
npm install
npm run build
```

## Notes

- Choose a stored origin city before searching. `origin_id` values such as `zagreb-hr` are not IATA codes.
- Ranking runs once in the browser because `/api/candidates` is unranked.
- Missing optional fields stay unavailable; map pins require valid destination coordinates from flight documents.
