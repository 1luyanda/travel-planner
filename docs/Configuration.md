# Configuration

[Documentation index](README.md)

Backend settings load `.env` without overriding existing process variables and are cached in-process. The LLM loader reads the project-root `.env`; Vite uses the repository root as its environment directory. Restart after changes.

## Application settings

| Variable | Default or requirement |
|---|---|
| `COSMOS_CONNECTION_STRING` | Required Cosmos connection string |
| `COSMOS_DATABASE` | Required database name; the project documentation uses `TravelPlaner` |
| `API_AUTH_KEY` | Required to use protected routes; enforced at startup in production |
| `API_AUTH_KEY_PREVIOUS` | Optional second accepted key for rotation |
| `AUTH_SESSION_SECRET` | Required for cookie authentication; production requires at least 32 characters |
| `APP_ENV` | `development`; allowed values: `development`, `test`, `production` |
| `FRONTEND_ORIGINS` | Comma-separated; `http://localhost:5173` |
| `TRUSTED_HOSTS` | Comma-separated; `localhost,127.0.0.1,testserver` |
| `MAX_REQUEST_BYTES` | Positive integer; `65536`, checked against Content-Length |
| `AUTH_SESSION_TTL_SECONDS` | Positive integer; `3600` |
| `AUTH_COOKIE_SECURE` | False outside production; true in production, where false is rejected |
| `COSMOS_USERS_CONTAINER` | `users` |
| `COSMOS_USER_FLIGHTS_CONTAINER` | `user-flights` |
| `COSMOS_USER_ACTIVITIES_CONTAINER` | `user-activities` |
| `COSMOS_HOTELS_CONTAINER` | `hotels` |
| `GOOGLE_PLACES_API_KEY` | Required by the activity and photo services |

`origins` and `flights` container names are fixed. The session cookie name is `travel_planner_session`; the current environment loader does not expose a cookie-name override. Flexible-date window and shortlist constants are code settings, not environment variables.

Production mode disables `/docs`, `/redoc`, and `/openapi.json`. It validates keys, the session secret, secure cookies, and nonempty origin/host lists. The default origin/host lists still apply if variables are omitted; production mode does not provision a gateway or hosting environment.

## LLM settings

The Azure path takes precedence if any usable Azure setting is present. All four must then be supplied:

- `AZURE_OPENAI_ENDPOINT`
- `AZURE_OPENAI_API_KEY`
- `AZURE_OPENAI_DEPLOYMENT`
- `AZURE_OPENAI_API_VERSION`

A partial Azure configuration is an error and does not fall back to another provider.

The alternative client accepts `LLM_API_KEY` or `OPENAI_API_KEY`, and requires `LLM_MODEL` or `OPENAI_MODEL`. It optionally accepts `LLM_BASE_URL` or `OPENAI_BASE_URL`, and `LLM_API_VERSION`. No default model or fake production client is selected.

Startup catches LLM configuration errors so other services can initialize. This does not make natural-language operations available without valid LLM configuration. Complete form-only parsing can avoid model extraction; explanations still need the configured client unless reusable text is available.

The session secret also keys stored identity hashes. Changing it invalidates sessions and changes email lookup hashes; there is no account migration mechanism in this checkout. See [Security](Security.md).

Sources: [settings](../backend/config.py), [LLM client and parser](../backend/services/llm.py), [Places service](../backend/services/places.py), [startup](../backend/main.py).
