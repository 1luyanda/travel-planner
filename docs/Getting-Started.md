# Getting started

[Documentation index](README.md)

## Prerequisites

Use Python with the dependencies in the root `requirements.txt`, Node.js/npm compatible with the frontend dependencies, and access to a populated Cosmos database. The existing project setup uses Python 3.13. There is no checked-in container provisioning or data loading workflow in this checkout.

Cosmos data is required for searches. An LLM configuration is needed for natural-language parsing, feedback, and generated explanations. Google Places configuration is needed for activities. See [Configuration](Configuration.md) and [Data and persistence](Data-and-Persistence.md).

## Configure the repository

From the repository root, copy the example only if `.env` does not already exist:

```powershell
if (-not (Test-Path -LiteralPath .env)) { Copy-Item -LiteralPath .env.example -Destination .env }
```

Set `COSMOS_CONNECTION_STRING`, `COSMOS_DATABASE`, `API_AUTH_KEY`, and a separate `AUTH_SESSION_SECRET`. Set `AUTH_COOKIE_SECURE=false` for local HTTP. Generate each secret separately with:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Keep secrets in local configuration. Do not put server keys in variables prefixed `VITE_`.

## Start the backend

Run from the repository root. If an environment already exists, use it instead of creating another:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --reload
```

The API normally runs at `http://127.0.0.1:8000`. Its public health route is `/api/health`; interactive API documentation is `/docs` in development and test environments. Health returns `{"status":"ok"}` and is not a comprehensive provider readiness check.

## Start the frontend

In a second terminal, from the repository root:

```powershell
cd frontend
npm install
npm run dev
```

Open the URL printed by Vite, normally `http://localhost:5173`. Vite forwards `/api` to `http://127.0.0.1:8000` and inserts `X-API-Key` from the root environment in its Node process. Browser requests do not supply that secret.

Use the frontend host consistently for cookie-based login. If Vite selects a different port, check `FRONTEND_ORIGINS` for any direct cross-origin API access. Restart processes after changing configuration.

## Verify the setup

Open the landing page, enter the planner, and search using an origin and dates represented in your Cosmos data. Supply a budget and currency. Missing required information should produce clarification questions. Register or log in to save a flight and use Explore.

For API calls directly to port 8000, protected routes need `X-API-Key`; saved-item routes also need the session cookie. See [API reference](API-Reference.md). For build and test commands, see [Testing and troubleshooting](Testing-and-Troubleshooting.md).

Sources: [dependency manifest](../requirements.txt), [Vite configuration](../frontend/vite.config.js), [application startup](../backend/main.py).
