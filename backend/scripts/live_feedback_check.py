"""Bounded live checks for interpret_feedback. Never uses FakeLLMClient.

Run from the repo root:

    python backend/scripts/live_feedback_check.py

Cases:
    D. Cheaper — stronger price intent, budget stays 400 EUR
    E. Warmer — warmer intent, no invented temperature
    F. My budget is now EUR 300 — explicit budget update
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.models.trip_request import TripRequest
from backend.services.feedback import interpret_feedback
from backend.services.llm import (
    LLMConfigurationError,
    create_llm_client_from_env,
    load_llm_environment,
)

BASE_REQUEST = TripRequest(
    origin="ZAG",
    departure_date=date(2026, 9, 21),
    return_date=date(2026, 9, 25),
    budget=400,
    currency="EUR",
    moods=["relaxing"],
    weather_preference="warm",
)


def _snapshot() -> TripRequest:
    return BASE_REQUEST.model_copy(deep=True)


def main() -> int:
    load_llm_environment()
    try:
        client = create_llm_client_from_env()
    except LLMConfigurationError as exc:
        print("LIVE FEEDBACK CHECKS: NOT RUN")
        print(str(exc))
        return 2

    print("LIVE FEEDBACK CHECKS: using configured live client")
    print(f"client_kind={getattr(client, 'client_kind', type(client).__name__)}")
    print(f"model_or_deployment_configured={bool(getattr(client, '_model', None))}")
    print(f"azure_endpoint_configured={bool(getattr(client, '_azure_endpoint', None))}")
    print(f"api_version_configured={bool(getattr(client, '_api_version', None))}")

    failures: list[str] = []
    original = _snapshot()

    print("\nCASE D: cheaper")
    cheaper = interpret_feedback("Cheaper", original, llm_client=client)
    cheaper_checks = {
        "status_ready": cheaper.status == "ready",
        "budget_unchanged": cheaper.updated_request is not None
        and cheaper.updated_request.budget == 400,
        "currency_unchanged": cheaper.updated_request is not None
        and cheaper.updated_request.currency == "EUR",
        "price_intent": any(
            item.code == "stronger_price_preference" for item in cheaper.intents
        ),
        "original_untouched": original.budget == 400,
    }
    print(f"status={cheaper.status}")
    print(
        "sanitized_updated=",
        None
        if cheaper.updated_request is None
        else cheaper.updated_request.model_dump(mode="json"),
    )
    print("intent_codes=", [item.code for item in cheaper.intents])
    print("change_fields=", [item.field for item in cheaper.changes])
    print("checks=", cheaper_checks)
    cheaper_pass = all(cheaper_checks.values())
    print(f"result={'PASS' if cheaper_pass else 'FAIL'}")
    if not cheaper_pass:
        failures.append("D")
        if cheaper.status == "error":
            print("CASE E: NOT RUN (case D error)")
            print("CASE F: NOT RUN (case D error)")
            print("LIVE FEEDBACK CHECKS: FAIL")
            return 1

    print("\nCASE E: warmer")
    warmer_original = _snapshot()
    warmer = interpret_feedback("Warmer", warmer_original, llm_client=client)
    weather = (
        warmer.updated_request.weather_preference if warmer.updated_request else None
    )
    warmer_checks = {
        "status_ready": warmer.status == "ready",
        "warmer_intent": any(item.code == "prefer_warmer" for item in warmer.intents),
        "budget_unchanged": warmer.updated_request is not None
        and warmer.updated_request.budget == 400,
        "no_numeric_weather": weather is None or not str(weather).replace(".", "", 1).isdigit(),
        "original_weather_untouched": warmer_original.weather_preference == "warm",
    }
    print(f"status={warmer.status}")
    print("weather_preference=", weather)
    print("intent_codes=", [item.code for item in warmer.intents])
    print("checks=", warmer_checks)
    warmer_pass = all(warmer_checks.values())
    print(f"result={'PASS' if warmer_pass else 'FAIL'}")
    if not warmer_pass:
        failures.append("E")

    print("\nCASE F: explicit budget update")
    budget_original = _snapshot()
    budgeted = interpret_feedback(
        "My budget is now EUR 300",
        budget_original,
        llm_client=client,
    )
    budget_checks = {
        "status_ready": budgeted.status == "ready",
        "budget_300": budgeted.updated_request is not None
        and budgeted.updated_request.budget == 300,
        "currency_eur": budgeted.updated_request is not None
        and budgeted.updated_request.currency == "EUR",
        "origin_preserved": budgeted.updated_request is not None
        and budgeted.updated_request.origin == "ZAG",
        "original_untouched": budget_original.budget == 400,
    }
    print(f"status={budgeted.status}")
    print(
        "sanitized_updated=",
        None
        if budgeted.updated_request is None
        else {
            "origin": budgeted.updated_request.origin,
            "budget": budgeted.updated_request.budget,
            "currency": budgeted.updated_request.currency,
            "moods": budgeted.updated_request.moods,
        },
    )
    print("change_fields=", [item.field for item in budgeted.changes])
    print("checks=", budget_checks)
    budget_pass = all(budget_checks.values())
    print(f"result={'PASS' if budget_pass else 'FAIL'}")
    if not budget_pass:
        failures.append("F")

    if failures:
        print("LIVE FEEDBACK CHECKS: FAIL")
        return 1
    print("\nLIVE FEEDBACK CHECKS: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
