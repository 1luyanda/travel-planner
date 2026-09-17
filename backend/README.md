# Travel Planner Backend

FastAPI and Cosmos candidate retrieval live here, along with the AI request
parser, grounded explanations, and feedback interpretation.

The running application serves origins, raw Cosmos flight documents, prepared
unranked candidates, and the recommend/refine workflow. `parse_request`,
`rank_candidates`, `explain_ranked_trips`, and `interpret_feedback` are called
from `POST /api/recommend` and `POST /api/refine`. `/api/candidates` stays
unranked.

## Setup

1. Install dependencies:

   ```powershell
   python3.13.exe -m pip install -r requirements.txt
   ```

2. Copy `.env.example` to `.env` and configure Cosmos DB:

   - `COSMOS_CONNECTION_STRING` — the PRIMARY CONNECTION STRING.
   - `COSMOS_DATABASE=TravelPlaner` — spelling and case matter.
   - `API_AUTH_KEY` — a server-side key used by the Vite development proxy
     or production gateway. Generate it with
     `python -c "import secrets; print(secrets.token_urlsafe(32))"`.
   - `TRUSTED_HOSTS` — comma-separated host names accepted by the API.

   The backend uses the fixed `origins` and `flights` container names.

3. Start FastAPI:

   ```powershell
   python3.13.exe -m uvicorn backend.main:app --reload
   ```

API documentation is available at `http://localhost:8000/docs`.

## Endpoints

- `GET /api/health`
- `GET /api/origins?q=zag&country=HR`
- `GET /api/origins/{origin_id}`
- `GET /api/flights` — raw Cosmos flight documents for one origin partition
  (airline, coordinates, weather, and other stored fields).
  Required: `origin_id`. Optional: `departure_date`, `return_date`, `max_price`,
  `min_temp`, `country`. Does not accept `max_changeovers` or
  `max_duration_minutes`.
- `GET /api/candidates` — prepared, unranked `candidates` plus `rejected`
  reasons. Required: `origin_id`. Optional: `departure_date`, `return_date`,
  `max_price`, `min_temp`, `country`, `max_changeovers`, `max_duration_minutes`.
- `POST /api/recommend` — parse user text (and optional form fields), resolve
  origin IATA to a Cosmos origin, load candidates, rank them, and explain.
- `POST /api/refine` — interpret feedback against a saved `TripRequest`, then
  search and rank again. Explicit field changes (budget, direct flights) are
  applied. Intents such as cheaper/warmer are passed to Ivan's
  `preferences_from_intents` so ranking weights update.

Example requests:

```http
GET /api/flights?origin_id=zagreb-hr
GET /api/candidates?origin_id=zagreb-hr&max_price=300&max_changeovers=0
POST /api/recommend
POST /api/refine
```

Example recommend body:

```json
{
  "text": "From ZAG, 21–25 September 2026, under EUR 400, somewhere warm and relaxing."
}
```

Example refine body:

```json
{
  "text": "Cheaper",
  "request": {
    "origin": "ZAG",
    "departure_date": "2026-09-21",
    "return_date": "2026-09-25",
    "budget": 400,
    "currency": "EUR",
    "moods": ["relaxing"],
    "weather_preference": "warm"
  }
}
```

`ranking_preferences` is optional on both bodies. On refine, recognized
cheaper/warmer intents replace those weights using Ivan's presets. If the
feedback has no ranking intent, the supplied weights (or defaults) stay.

## Integration placeholders

- `POST /api/recommend` and `POST /api/refine` now call the AI functions, Cosmos,
  and ranking in one backend path.
- Origin IATA codes such as `ZAG` are resolved through Cosmos `city_iata` /
  `airports`. Unmatched or ambiguous codes return `needs_input`.
- Refine calls Ivan's `preferences_from_intents` for cheaper/warmer. Luyanda
  can still send `ranking_preferences` as the starting weights.
- Data and recommendation routes require the server-side `X-API-Key`
  configured through `API_AUTH_KEY`. The health endpoint remains public.
  The browser must not receive this key; local Vite and production gateways
  inject it server-side. User authentication with Microsoft Entra External ID
  is planned separately. Production rate limits should be enforced by the
  gateway and returned as `429 Too Many Requests`.

# AI request parser and explanations

Turns user text and optional form fields into a structured travel request, then
explains ranked destinations using only supplied facts.

These functions do not rank destinations or query Cosmos. FastAPI calls them
from `/api/recommend` and `/api/refine`.

## interpret_feedback

Call this when the user comments on an **existing** validated `TripRequest`.
The input request is not mutated. Explicit feedback updates are applied; the
initial parser's form-vs-text conflict rules are not used.

```python
from backend.services.feedback import interpret_feedback

result = interpret_feedback(
    "Cheaper",
    request,  # current TripRequest
    llm_client=create_llm_client_from_env(),
)
```

### Return shape

```python
result.status              # "ready" | "needs_input" | "error"
result.request             # snapshot of the input TripRequest
result.updated_request     # new TripRequest when ready, else None
result.intents             # semantic ranking/filter intents (no invented weights)
result.changes             # explicit field updates only
result.issues
result.clarification_questions
```

| Feedback | Validated result |
|---|---|
| Cheaper | Intent `stronger_price_preference`. Budget unchanged. |
| Warmer | Intent `prefer_warmer`. `weather_preference="warmer"`. No temperature number. |
| My budget is now EUR 300 | `budget=300`, `currency=EUR`. Other fields copied. |
| Direct flights only | `direct_flights_only=True`. Intent maps to ranking hard filter `max_changeovers`, not a weight. |

Ivan's `RankingPreferences` (`price_weight`, `weather_weight`, `changeovers_weight`, `duration_weight`) has no named mapping from these phrases to numeric weights. Intents record the related field name and leave the value unset.

## parse_request

```python
from datetime import date
from backend.services.llm import parse_request, create_llm_client_from_env

result = parse_request(
    "From ZAG, 21–25 September 2026, under EUR 400, somewhere warm and relaxing.",
    form_fields=None,
    reference_date=date.today(),
    llm_client=create_llm_client_from_env(),
)
```

`llm_client` is optional. If omitted and `user_text` is present, the function builds a live client from environment variables. It never falls back to the test fake client.

### Return shape

```python
result.status                    # "ready" | "needs_input" | "error"
result.request                   # TripRequest or None
result.preferences               # ExtractedPreferences (partial or complete)
result.issues                    # list[str]
result.clarification_questions   # list[str]
```

`TripRequest` fields: `origin`, `departure_date`, `return_date`, `duration_days`, `budget`, `currency`, `moods`, `direct_flights_only`, `weather_preference`.

`ready` requires origin IATA, departure date, return date, positive budget and currency. Mood, duration, direct-flight and weather are optional.

### Form fields

Optional keys: `origin`, `departure_date`, `return_date`, `duration_days`, `budget`, `currency`, `moods`, `direct_flights_only`, `weather_preference`.

Explicit form values are preserved. If they conflict with the message, `status` is `needs_input`.

## explain_ranked_trips

Call this **after** ranking. Pass the validated `TripRequest` and the ranked list in ranking order.

The ranking package is not imported by the AI functions. Any object with the
`RankedDestination` fields from ranking is accepted
(`destination_id`, `destination_iata`, `city`, `price_eur`, `changeover_count`,
`flight_duration_minutes`, `trip_duration_days`, `average_max_temperature_c`,
and the five scores). Wiring to Ivan's live ranking objects is still pending.

```python
from backend.services.explanations import explain_ranked_trips
from backend.services.llm import create_llm_client_from_env

result = explain_ranked_trips(
    request,                 # TripRequest from parse_request
    ranked,                  # list of RankedDestination-like objects
    llm_client=create_llm_client_from_env(),
    ranking_weights=None,    # optional dict actually used by ranking
)
```

### Return shape

```python
result.status          # "ok" | "error"
result.explanations    # list[DestinationExplanation] in the supplied ranking order
result.issues          # ignored unknown IDs, cross-destination evidence, model problems
```

Each explanation keeps the supplied scores and includes only evidence IDs that
belong to that `destination_id`. Factual numbers are rendered from the ranked
records, not from model prose.

### Example

Input ranked row (fields only):

```text
destination_id=ZAG-ROM-2026-09-18
city=Rome
price_eur=65
changeover_count=0
final_score=0.92
```

Example `ok` output:

```python
result.status == "ok"
result.explanations[0].destination_id == "ZAG-ROM-2026-09-18"
result.explanations[0].rank == 1
result.explanations[0].final_score == 0.92
result.explanations[0].evidence[0].code == "within_budget"
# summary contains the recorded 65 EUR price from the ranked object
```

### Failure behaviour

| Case | Result |
|---|---|
| Empty `ranked` list | `ok`, `explanations=[]`, model is **not** called |
| Missing LLM config when ranked items exist | `error`, `explanations=[]` |
| Invalid model JSON twice, or two request failures | `error`, `explanations=[]`, no invented text |
| Unknown `destination_id` | ignored, listed in `issues` |
| Evidence ID for another destination | ignored, listed in `issues` |
| Mood / cooler-weather claims not in the allowed list | dropped; mood is never treated as a destination quality |
| Budget vs price | compared only when the request currency is EUR |

Scores are relative ranking values, not confidence or match percentages.
`flight_duration_minutes` is documented by ranking as round-trip air time
(outbound plus return), not holiday length.

## Configuration

`create_llm_client_from_env()` loads the project-root `.env` and does not
override process environment values. Do not commit `.env`.

Academy Azure OpenAI chat (used when these four are set together):

- `AZURE_OPENAI_ENDPOINT` — Azure resource root, not a generic OpenAI base URL
- `AZURE_OPENAI_API_KEY`
- `AZURE_OPENAI_DEPLOYMENT` — chat deployment name
- `AZURE_OPENAI_API_VERSION`

A partial Azure set does not fall back to public OpenAI.

OpenAI-compatible alternative:

- `LLM_API_KEY` or `OPENAI_API_KEY`
- `LLM_MODEL` or `OPENAI_MODEL` (required on this path; no default model)
- `LLM_BASE_URL` or `OPENAI_BASE_URL` (optional)
- `LLM_API_VERSION` (optional)

Live checks need the `openai` package from `requirements.txt`.

## Local checks

```text
python -m pip install -r requirements.txt
python -m pytest tests/test_parse_request.py tests/test_explanations.py tests/test_llm_config.py tests/test_feedback.py tests/test_recommendations.py
python backend/scripts/live_llm_check.py
python backend/scripts/live_feedback_check.py
```
