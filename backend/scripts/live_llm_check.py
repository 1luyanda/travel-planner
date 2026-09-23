"""Manual live LLM checks. Never uses FakeLLMClient.

Run from the repo root after filling `.env`:

    python backend/scripts/live_llm_check.py

Exits 0 if all live cases pass, 2 if configuration is missing (NOT RUN),
1 if a live case fails.
"""

from __future__ import annotations

import asyncio
import sys
from datetime import date
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.models.trip_request import TripRequest
from backend.services.explanations import explain_ranked_trips
from backend.services.llm import (
    LLMConfigurationError,
    create_llm_client_from_env,
    load_llm_environment,
    parse_request,
)

REFERENCE_DATE = date(2026, 9, 15)
COMPLETE_TEXT = (
    "From ZAG, 21–25 September 2026, under EUR 400, somewhere warm and relaxing."
)
INCOMPLETE_TEXT = "I want something relaxing."
ROME_ID = "SAMPLE-ZAG-ROM-2026-09-21"
LISBON_ID = "SAMPLE-ZAG-LIS-2026-09-21"


def _ranked(destination_id: str, city: str, **overrides) -> SimpleNamespace:
    values = {
        "destination_id": destination_id,
        "destination_iata": "FCO" if "ROM" in destination_id else "LIS",
        "city": city,
        "price_eur": 65,
        "changeover_count": 0,
        "flight_duration_minutes": 170,
        "trip_duration_days": 4,
        "average_max_temperature_c": 27.8,
        "price_score": 1.0,
        "weather_score": 0.8,
        "stops_score": 1.0,
        "duration_score": 0.9,
        "final_score": 0.92,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


async def main() -> int:
    load_llm_environment()
    try:
        client = create_llm_client_from_env()
    except LLMConfigurationError as exc:
        print("LIVE CHECKS: NOT RUN")
        print(str(exc))
        print("Missing usable Azure chat values for: AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_KEY, AZURE_OPENAI_DEPLOYMENT, AZURE_OPENAI_API_VERSION")
        print("Or OpenAI-compatible: LLM_API_KEY or OPENAI_API_KEY, plus LLM_MODEL or OPENAI_MODEL")
        print("Create a project-root .env from .env.example. Process environment is not overridden.")
        return 2

    print("LIVE CHECKS: using configured live client")
    print(f"client_kind={getattr(client, 'client_kind', type(client).__name__)}")
    print(f"model_or_deployment_configured={bool(getattr(client, '_model', None))}")
    print(f"azure_endpoint_configured={bool(getattr(client, '_azure_endpoint', None))}")
    print(f"api_version_configured={bool(getattr(client, '_api_version', None))}")

    try:
        return await _run_live_cases(client)
    finally:
        await client.aclose()


async def _run_live_cases(client) -> int:
    failures: list[str] = []

    complete = await parse_request(
        COMPLETE_TEXT,
        reference_date=REFERENCE_DATE,
        llm_client=client,
    )
    print("\nCASE A: complete request")
    print(f"status={complete.status}")
    if complete.request is None:
        failures.append("A: expected ready request")
        print("result=FAIL expected request")
    else:
        checks = {
            "status_ready": complete.status == "ready",
            "origin": complete.request.origin == "ZAG",
            "departure": str(complete.request.departure_date) == "2026-09-21",
            "return": str(complete.request.return_date) == "2026-09-25",
            "budget": complete.request.budget == 400,
            "currency": complete.request.currency == "EUR",
        }
        print("sanitized_request=", complete.request.model_dump(mode="json"))
        print("checks=", checks)
        if not all(checks.values()):
            failures.append("A: field checks failed")
            print("result=FAIL")
        else:
            print("result=PASS")

    if complete.status == "error":
        print("Stopping remaining live cases after case A error to avoid repeating a failed request.")
        print("\nLIVE CHECKS: FAIL")
        for item in failures:
            print("-", item)
        return 1

    incomplete = await parse_request(
        INCOMPLETE_TEXT,
        reference_date=REFERENCE_DATE,
        llm_client=client,
    )
    print("\nCASE B: incomplete request")
    print(f"status={incomplete.status}")
    prefs = incomplete.preferences
    checks_b = {
        "status_needs_input": incomplete.status == "needs_input",
        "mood_retained": bool(prefs and "relaxing" in [m.lower() for m in prefs.moods]),
        "origin_missing": prefs is not None and prefs.origin is None,
        "dates_missing": prefs is not None
        and prefs.departure_date is None
        and prefs.return_date is None,
        "budget_missing": prefs is not None and prefs.budget is None,
        "has_questions": bool(incomplete.clarification_questions),
    }
    print("sanitized_preferences=", prefs.model_dump(mode="json") if prefs else None)
    print("clarification_questions=", incomplete.clarification_questions)
    print("checks=", checks_b)
    if not all(checks_b.values()):
        failures.append("B: incomplete-request checks failed")
        print("result=FAIL")
    else:
        print("result=PASS")

    request = TripRequest(
        origin="ZAG",
        departure_date=date(2026, 9, 21),
        return_date=date(2026, 9, 25),
        budget=400,
        currency="EUR",
        moods=["relaxing"],
        weather_preference="warm",
    )
    ranked = [
        _ranked(ROME_ID, "Rome", price_eur=65, final_score=0.92),
        _ranked(LISBON_ID, "Lisbon", price_eur=189, final_score=0.70),
    ]
    explained = await explain_ranked_trips(request, ranked, llm_client=client)
    print("\nCASE C: grounded explanation (sample ranked objects, not Cosmos)")
    print(f"status={explained.status}")
    ids = [item.destination_id for item in explained.explanations]
    scores = [item.final_score for item in explained.explanations]
    evidence_ok = all(
        all(ref.destination_id == item.destination_id for ref in item.evidence)
        for item in explained.explanations
    )
    summaries_use_facts = any(
        "65" in item.summary or "189" in item.summary for item in explained.explanations
    )
    checks_c = {
        "status_ok": explained.status == "ok",
        "ids_preserved": ids == [ROME_ID, LISBON_ID],
        "scores_preserved": scores == [0.92, 0.70],
        "evidence_scoped": evidence_ok,
        "summaries_use_supplied_facts": summaries_use_facts,
    }
    print(
        "sanitized_explanations=",
        [
            {
                "destination_id": item.destination_id,
                "rank": item.rank,
                "final_score": item.final_score,
                "evidence_codes": [ref.code for ref in item.evidence],
                "summary": item.summary,
            }
            for item in explained.explanations
        ],
    )
    print("issues=", explained.issues)
    print("checks=", checks_c)
    if not all(checks_c.values()):
        failures.append("C: explanation checks failed")
        print("result=FAIL")
    else:
        print("result=PASS")

    if failures:
        print("\nLIVE CHECKS: FAIL")
        for item in failures:
            print("-", item)
        return 1
    print("\nLIVE CHECKS: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
