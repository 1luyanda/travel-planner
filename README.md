# Team 4 Travel Planner

React frontend plus a FastAPI backend. The UI filters and ranks destinations in the browser. FastAPI reads the authoritative mock file at `mock_data/normalized_destinations.json`.

# Getting Started

Run the API and the UI in two PowerShell terminals.

## Terminal 1: backend

```powershell
cd backend
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

## Terminal 2: frontend

```powershell
cd frontend
npm install
npm run dev
```

Open the URL shown by Vite, normally `http://localhost:5173`.

# Build and Test

Frontend production build:

```powershell
cd frontend
npm run build
```

Backend checks:

- `http://127.0.0.1:8000/api/health`
- `http://127.0.0.1:8000/api/destinations`

# Contribute

Keep `mock_data/` unchanged unless you are updating the mock-data pipeline. Destination ranking and filters stay in the frontend.
