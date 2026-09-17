# Team 4 Travel Planner

React frontend plus a Cosmos-backed FastAPI backend. Candidate retrieval,
origins, and raw flight documents come from Cosmos DB. Request parsing,
ranking, and explanations live in Python packages; see
[backend/README.md](backend/README.md) for what is wired into HTTP routes
today.

Data pull, filter, and Cosmos load live in
[data_preparation/](data_preparation/README.md). `.env` stays at the repo
root. Do not commit secrets.

# Getting Started

Run the API and the UI in two terminals. Copy `.env.example` to `.env` and
set `COSMOS_CONNECTION_STRING`, `COSMOS_DATABASE`, and a generated
`API_AUTH_KEY` plus a generated `AUTH_SESSION_SECRET` before starting the
backend. The Vite development proxy injects the API key server-side; do not
expose it in a `VITE_` frontend variable.

Create a Cosmos `users` container with partition key `/email_normalized` and a
unique key on `/email_normalized` before using registration. Local
authentication stores only Argon2id password hashes and uses short-lived
signed HttpOnly cookies.

## Terminal 1: backend

Install dependencies from the repo root, then start FastAPI:

```powershell
python3.13.exe -m pip install -r requirements.txt
python3.13.exe -m uvicorn backend.main:app --reload
```

API docs: `http://localhost:8000/docs`

## Terminal 2: frontend

```powershell
cd frontend
npm install
npm run dev
```

Open the URL shown by Vite, normally `http://localhost:5173`. The Vite dev
server proxies `/api` to `http://127.0.0.1:8000`.

# Build and Test

Frontend production build and unit tests:

```powershell
cd frontend
npm test
npm run build
```

Backend checks:

- `http://127.0.0.1:8000/api/health`
- `http://127.0.0.1:8000/docs`

```powershell
python -m pytest
```

Current HTTP routes include `/api/origins`, `/api/flights`, and
`/api/candidates`. There is no `/api/destinations` mock-file endpoint.

# Contribute

Keep Cosmos credentials and other secrets in `.env`. Data ingestion stays in
`data_preparation/`. Backend route and parser details are in
`backend/README.md`.
