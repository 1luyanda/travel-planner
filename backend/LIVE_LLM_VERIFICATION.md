# Live LLM verification

Recorded 2026-09-15. No API keys, tokens or connection strings are included.

## Current step

Step 3: configure and verify the Travel Planner’s live LLM using Academy AI-day chat settings.

Overall: **complete**. Live cases A–C **PASS**. Targeted unit tests **PASS**. Changes remain uncommitted.

## Configuration source (sanitized)

| Item | Finding |
|---|---|
| Source file | `SNyamfu/AI/Day9_Tasks/.env` |
| Adjacent working client | `SNyamfu/AI/Day9_Tasks/config.py` (`AzureChatOpenAI`) |
| Endpoint style | Azure resource root (not `/openai/v1`, not public OpenAI) |
| Copied variable names | `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_DEPLOYMENT`, `AZURE_OPENAI_API_VERSION` |
| Not copied | embedding deployment / embedding keys |
| Destination | project-root `.env` (gitignored, untracked) |
| Client selected | `AzureOpenAI` via `AzureOpenAIChatClient` (`client_kind=azure_openai`) |
| Mixed credentials | Azure four-set takes precedence; incomplete Azure does not fall back to public OpenAI |

## Live cases (this step)

Interpreter: `.\.venv\Scripts\python.exe backend/scripts/live_llm_check.py`

| Case | Result |
|---|---|
| A. Complete request | **PASS** |
| B. Incomplete request (`I want something relaxing.`) | **PASS** |
| C. Grounded explanation with sample ranked objects | **PASS** |

Sanitized outcomes:

- A: `status=ready`; origin `ZAG`; dates `2026-09-21` to `2026-09-25`; budget `400.0`; currency `EUR`
- B: `status=needs_input`; mood `relaxing` retained; origin/dates/budget still missing; clarification questions present
- C: `status=ok`; sample destination IDs and scores preserved; evidence scoped to those IDs; summaries used supplied facts (including 65 EUR / 189 EUR)

No fake client was used for A–C.

## Unit tests executed (this step)

```text
python -m pytest tests/test_parse_request.py tests/test_explanations.py tests/test_llm_config.py -v
```

27 passed in 0.27s (12 parser, 11 explanation, 4 config). These use fake clients or local temp `.env` files, not the live model.

## How to re-run

```text
.\.venv\Scripts\python.exe backend/scripts/live_llm_check.py
.\.venv\Scripts\python.exe -m pytest tests/test_parse_request.py tests/test_explanations.py tests/test_llm_config.py -v
```
