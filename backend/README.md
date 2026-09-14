# AI request parser

Turns user text and optional form fields into a structured travel request.

This component does not rank destinations, call travel providers, or expose HTTP routes.

## Function the backend owner should call

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

## Return shape

```python
result.status                    # "ready" | "needs_input" | "error"
result.request                   # TripRequest or None
result.preferences               # ExtractedPreferences (partial or complete)
result.issues                    # list[str]
result.clarification_questions   # list[str]
```

`TripRequest` fields: `origin`, `departure_date`, `return_date`, `duration_days`, `budget`, `currency`, `moods`, `direct_flights_only`, `weather_preference`.

`ready` requires origin IATA, departure date, return date, positive budget and currency. Mood, duration, direct-flight and weather are optional.

## Form fields

Optional keys: `origin`, `departure_date`, `return_date`, `duration_days`, `budget`, `currency`, `moods`, `direct_flights_only`, `weather_preference`.

Explicit form values are preserved. If they conflict with the message, `status` is `needs_input`.

## Configuration

Copy `.env.example` to `.env`. Proposed variable names:

- `LLM_API_KEY` or `OPENAI_API_KEY`
- `LLM_MODEL` or `OPENAI_MODEL`
- `LLM_BASE_URL` or `OPENAI_BASE_URL` (optional)
- `LLM_API_VERSION` (optional)

Do not commit `.env`.

## Local checks

```text
python -m pip install -r requirements.txt
python -m pytest tests/test_parse_request.py
```
