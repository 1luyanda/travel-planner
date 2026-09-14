# Travel Planner frontend

React UI for Team 4's Travel Planner. It fetches `/api/destinations` from FastAPI and ranks destinations in the browser. Start the backend first so the Vite `/api` proxy can reach `http://127.0.0.1:8000`.

## Run locally (Windows PowerShell)

```powershell
cd frontend
npm install
npm run dev
```

Open the URL shown by Vite, normally `http://localhost:5173`.

## Build

```powershell
cd frontend
npm install
npm run build
```

## Notes

- Destination cards use the normalized mock data, not hardcoded city lists.
- Filters and ranking run entirely in the browser.
- Ranking weights are shown in the refinement panel and change when you choose Cheaper, Warmer, Direct flights, or Shorter travel.
