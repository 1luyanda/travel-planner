# Testing and troubleshooting

[Documentation index](README.md)

## Automated checks

From the repository root with Python dependencies installed:

```powershell
.\.venv\Scripts\python.exe -m pytest
```

`pytest.ini` sets the repository on the Python path and discovers `tests/`. The suite includes ranking/policy, parsing, explanation, refinement, flexible-date, integration-boundary, hotel, Places, authentication, security, and saved-flight checks. Fixtures and fake/mocked clients exercise behavior without proving live service availability.

Frontend checks:

```powershell
cd frontend
npm test
npm run build
```

`npm test` runs Vitest once. Most tests use the Node environment; DOM interaction tests use jsdom, including mocked map interactions. The build produces static assets and does not provision an API gateway.

This documentation change was reviewed against source and checked for local links and route coverage. Application test results are not claimed by these pages.

## Optional live checks

The repository contains `backend/scripts/live_llm_check.py` and `backend/scripts/live_feedback_check.py`. They use configured live LLM services; they are separate from routine documentation validation and were not run to create this documentation. See the existing [live verification notes](../backend/LIVE_LLM_VERIFICATION.md) for their intended use.

## Troubleshooting

| Symptom | Check |
|---|---|
| Backend fails on import/startup | Required Cosmos variables, valid environment/number/boolean settings, installed root dependencies, and configured identity secret |
| `/api/health` succeeds but searches fail | Health does not test Cosmos data, LLM credentials, or Places; inspect the failing operation |
| 401 on a protected route | Direct API calls need `X-API-Key`; browser calls should go through Vite with matching root `API_AUTH_KEY` |
| 401 on saved items or `/auth/me` | Log in again; check cookie host, expiry, and credentials-inclusive requests |
| Login does not persist locally | Use a consistent frontend hostname; local HTTP requires `AUTH_COOKIE_SECURE=false` |
| Account lookup fails after secret change | Identity hashes depend on the session secret; changing it is not a transparent account migration |
| 503 for stored data | Check connection/database/container configuration and access; confirm expected partition design |
| Planner returns `needs_input` | Read clarification questions; supply origin IATA, dates, positive budget, and explicit currency; confirm unique stored origin match |
| Empty or fewer results | Check data for that origin/dates, budget and direct-flight constraints, invalid-record rejection reasons, and query limits |
| Unexpected dates | Inspect flexible-date flags and actual/requested dates; fallback can shift each date by up to seven days |
| Blank explanations | Inspect issues and LLM configuration; ranked results can survive explanation failure |
| Partial Azure LLM settings | Supply all four Azure variables; partial configuration does not use the alternative provider |
| Activities or photos fail | Check backend Places key and provider response; photos also require a valid resource name |
| No hotel details | Use `hotel_destination_id`, not the flight ID; check ambiguity, missing stored data, and browser-local saved metadata |
| Saved flight is unavailable | The current offer is absent; the retained snapshot is historical data |
| `/docs` behaves unexpectedly | Port 8000 exposes FastAPI docs outside production; frontend `/docs` redirects to planner; repository Markdown is local files |
| Invalid Host / CORS behavior | Review `TRUSTED_HOSTS` and `FRONTEND_ORIGINS` for the actual host and origin |

Sources: [pytest configuration](../pytest.ini), [frontend scripts](../frontend/package.json), [API routes](../backend/api/routes.py), [startup](../backend/main.py).
