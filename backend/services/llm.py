"""Travel request extraction and validation.

Backend integration should call `parse_request`.

Signature:
    parse_request(
        user_text: str,
        form_fields: dict[str, Any] | None = None,
        *,
        reference_date: date | None = None,
        llm_client: LLMClient | None = None,
    ) -> ParseRequestResult

Arguments:
    user_text: Free-text travel request. Extracted only from this string.
    form_fields: Optional explicit form values. These are preserved.
                 If they conflict with the text, status is needs_input.
    reference_date: Date used to resolve relative phrases such as "next week".
                    Defaults to today. Tests should pass a fixed date.
    llm_client: Injectable model client. Tests pass a fake. Production should
                pass a configured client or rely on environment variables.
                A fake client is never used automatically.

Return shape (`ParseRequestResult`):
    status: "ready" | "needs_input" | "error"
    request: TripRequest when status is ready, otherwise null
    preferences: ExtractedPreferences (partial or complete)
    issues: Validation or model problems
    clarification_questions: Questions for the user when input is missing
                             or conflicting

LLM behaviour:
    One extraction attempt, then one repair attempt if the model output is
    malformed or schema-invalid. Missing user facts are not invented and are
    not retried. Fixture files are never read.
"""

from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path
from typing import Any, Protocol

from pydantic import ValidationError

from backend.models.trip_request import (
    ExtractedPreferences,
    ParseRequestResult,
    apply_explicit_text_facts,
    merge_preferences,
    parse_form_fields,
    validate_preferences,
)

EXTRACT_FUNCTION_NAME = "extract_trip_preferences"
MAX_MODEL_ATTEMPTS = 2
_ENV_PATH = Path(__file__).resolve().parents[2] / ".env"
_PLACEHOLDER_API_KEYS = frozenset(
    {
        "replace-with-your-key",
        "your-key",
        "changeme",
        "todo",
        "xxx",
        "none",
    }
)

EXTRACTION_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": EXTRACT_FUNCTION_NAME,
        "description": (
            "Extract travel preferences that the user explicitly stated. "
            "Leave a field null when the user did not state it."
        ),
        "parameters": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "origin_iata": {
                    "type": ["string", "null"],
                    "description": (
                        "3-letter IATA code only when the user wrote that code. "
                        "Do not invent a code for a city or airport name."
                    ),
                },
                "origin_text": {
                    "type": ["string", "null"],
                    "description": "Origin place name when no IATA code was given.",
                },
                "departure_date": {
                    "type": ["string", "null"],
                    "description": "ISO date YYYY-MM-DD, or null if not stated.",
                },
                "return_date": {
                    "type": ["string", "null"],
                    "description": "ISO date YYYY-MM-DD, or null if not stated.",
                },
                "duration_days": {
                    "type": ["integer", "null"],
                    "description": "Trip length in days only if the user stated one.",
                },
                "budget": {
                    "type": ["number", "null"],
                    "description": "Numeric budget only if the user stated one.",
                },
                "currency": {
                    "type": ["string", "null"],
                    "description": (
                        "3-letter currency code if the user stated one. "
                        "€ means EUR. £ means GBP. Null if no currency was stated."
                    ),
                },
                "moods": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Mood words the user stated, such as relaxing.",
                },
                "direct_flights_only": {
                    "type": ["boolean", "null"],
                    "description": "True or false only if the user stated a direct-flight requirement.",
                },
                "weather_preference": {
                    "type": ["string", "null"],
                    "description": (
                        "Weather preference such as warm. "
                        "'warm escape' or 'somewhere warm' is warm. Null if not stated."
                    ),
                },
            },
        },
    },
}


class LLMClient(Protocol):
    """Minimal function-calling client used by parse_request."""

    def complete_function_call(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        tool_choice: dict[str, Any] | None = None,
    ) -> str:
        """Return the chosen tool-call arguments as a JSON string."""


class LLMConfigurationError(RuntimeError):
    """Raised when a live client is requested but environment config is missing."""


class OpenAICompatibleClient:
    """Thin adapter around the OpenAI-compatible Chat Completions API."""

    client_kind = "openai_compatible"

    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str | None = None,
        api_version: str | None = None,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._base_url = base_url
        self._api_version = api_version

    def complete_function_call(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        tool_choice: dict[str, Any] | None = None,
    ) -> str:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise LLMConfigurationError(
                "The openai package is required for the live LLM adapter. "
                "Install project dependencies or inject llm_client."
            ) from exc

        client_kwargs: dict[str, Any] = {"api_key": self._api_key}
        if self._base_url:
            client_kwargs["base_url"] = self._base_url
        client = OpenAI(**client_kwargs)
        create_kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "tools": tools,
            "tool_choice": tool_choice
            or {
                "type": "function",
                "function": {"name": EXTRACT_FUNCTION_NAME},
            },
        }
        if self._api_version:
            create_kwargs["extra_query"] = {"api-version": self._api_version}

        response = client.chat.completions.create(**create_kwargs)
        return _tool_arguments_from_response(response)


class AzureOpenAIChatClient:
    """Versioned Azure OpenAI chat client.

    Matches Academy Day 9 ``AzureChatOpenAI`` settings: resource endpoint,
    API key, deployment name and API version. The Azure resource root is not
    used as a generic OpenAI base_url.
    """

    client_kind = "azure_openai"

    def __init__(
        self,
        api_key: str,
        azure_endpoint: str,
        deployment: str,
        api_version: str,
    ) -> None:
        self._api_key = api_key
        self._azure_endpoint = azure_endpoint.rstrip("/")
        self._model = deployment
        self._api_version = api_version

    def complete_function_call(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        tool_choice: dict[str, Any] | None = None,
    ) -> str:
        try:
            from openai import AzureOpenAI
        except ImportError as exc:
            raise LLMConfigurationError(
                "The openai package is required for the live LLM adapter. "
                "Install project dependencies or inject llm_client."
            ) from exc

        client = AzureOpenAI(
            api_key=self._api_key,
            azure_endpoint=self._azure_endpoint,
            api_version=self._api_version,
        )
        response = client.chat.completions.create(
            model=self._model,
            messages=messages,
            tools=tools,
            tool_choice=tool_choice
            or {
                "type": "function",
                "function": {"name": EXTRACT_FUNCTION_NAME},
            },
        )
        return _tool_arguments_from_response(response)


def _tool_arguments_from_response(response: Any) -> str:
    choice = response.choices[0]
    tool_calls = getattr(choice.message, "tool_calls", None) or []
    if not tool_calls:
        return ""
    return tool_calls[0].function.arguments or ""


def load_llm_environment(env_path: Path | None = None) -> None:
    """Load project `.env` without overriding explicit process environment values."""
    path = env_path or _ENV_PATH
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key or key in os.environ:
            continue
        os.environ[key] = value.strip().strip('"').strip("'")


def _usable_secret(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip().strip('"').strip("'")
    if not cleaned or cleaned.lower() in _PLACEHOLDER_API_KEYS:
        return None
    return cleaned


def create_llm_client_from_env() -> LLMClient:
    """Build a live client from environment variables. Never returns a fake client.

    Academy Azure OpenAI chat settings take precedence when present. A partial
    Azure configuration does not fall back to public OpenAI or a default model.
    """
    load_llm_environment()
    azure_client = _azure_client_from_env()
    if azure_client is not None:
        return azure_client

    api_key = _usable_secret(
        os.environ.get("LLM_API_KEY") or os.environ.get("OPENAI_API_KEY")
    )
    if not api_key:
        raise LLMConfigurationError(
            "Set LLM_API_KEY or OPENAI_API_KEY, or the Academy Azure chat "
            "variables AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_KEY, "
            "AZURE_OPENAI_DEPLOYMENT and AZURE_OPENAI_API_VERSION."
        )
    model = os.environ.get("LLM_MODEL") or os.environ.get("OPENAI_MODEL")
    if not model or not model.strip():
        raise LLMConfigurationError(
            "Set LLM_MODEL or OPENAI_MODEL. No default model is assumed."
        )
    base_url = os.environ.get("LLM_BASE_URL") or os.environ.get("OPENAI_BASE_URL")
    api_version = os.environ.get("LLM_API_VERSION")
    return OpenAICompatibleClient(
        api_key=api_key,
        model=model.strip(),
        base_url=base_url or None,
        api_version=api_version or None,
    )


def _azure_client_from_env() -> AzureOpenAIChatClient | None:
    names = (
        "AZURE_OPENAI_ENDPOINT",
        "AZURE_OPENAI_API_KEY",
        "AZURE_OPENAI_DEPLOYMENT",
        "AZURE_OPENAI_API_VERSION",
    )
    present = {name: _usable_secret(os.environ.get(name)) for name in names}
    if not any(present.values()):
        return None
    missing = [name for name, value in present.items() if not value]
    if missing:
        raise LLMConfigurationError(
            "Incomplete Academy Azure chat configuration. Missing usable "
            f"values for: {', '.join(missing)}. Public OpenAI is not used as a fallback."
        )
    return AzureOpenAIChatClient(
        api_key=present["AZURE_OPENAI_API_KEY"],
        azure_endpoint=present["AZURE_OPENAI_ENDPOINT"],
        deployment=present["AZURE_OPENAI_DEPLOYMENT"],
        api_version=present["AZURE_OPENAI_API_VERSION"],
    )


def parse_request(
    user_text: str,
    form_fields: dict[str, Any] | None = None,
    *,
    reference_date: date | None = None,
    llm_client: LLMClient | None = None,
) -> ParseRequestResult:
    """Extract, merge and validate a travel request.

    See the module docstring for the full contract.
    """
    today = reference_date or date.today()

    try:
        form_preferences = parse_form_fields(form_fields)
    except (ValueError, ValidationError) as exc:
        return ParseRequestResult(
            status="needs_input",
            preferences=ExtractedPreferences(),
            issues=[str(exc)],
            clarification_questions=[
                "Please check the form values. Dates should be YYYY-MM-DD, "
                "budget a positive number, and origin a 3-letter IATA code."
            ],
        )

    text = (user_text or "").strip()
    if text:
        client = llm_client
        if client is None:
            try:
                client = create_llm_client_from_env()
            except LLMConfigurationError as exc:
                return ParseRequestResult(
                    status="error",
                    preferences=form_preferences,
                    issues=[str(exc)],
                    clarification_questions=[],
                )
        extracted, model_error = _extract_with_retry(text, today, client)
        if model_error:
            return ParseRequestResult(
                status="error",
                preferences=form_preferences,
                issues=[model_error],
                clarification_questions=[],
            )
        extracted = apply_explicit_text_facts(extracted, text)
    else:
        extracted = ExtractedPreferences()

    merged, conflict_issues, conflict_questions = merge_preferences(
        extracted, form_preferences
    )
    request, validation_issues, validation_questions = validate_preferences(merged)
    issues = conflict_issues + validation_issues
    questions = conflict_questions + validation_questions

    if conflict_issues or request is None:
        return ParseRequestResult(
            status="needs_input",
            request=None,
            preferences=merged,
            issues=issues,
            clarification_questions=questions,
        )

    return ParseRequestResult(
        status="ready",
        request=request,
        preferences=merged,
        issues=[],
        clarification_questions=[],
    )


def _extract_with_retry(
    user_text: str,
    reference_date: date,
    llm_client: LLMClient,
) -> tuple[ExtractedPreferences | None, str | None]:
    messages = [
        {"role": "system", "content": _system_prompt(reference_date)},
        {"role": "user", "content": user_text},
    ]
    last_error = "The model returned invalid output."

    for attempt in range(MAX_MODEL_ATTEMPTS):
        try:
            raw_arguments = llm_client.complete_function_call(
                messages=messages,
                tools=[EXTRACTION_TOOL],
                tool_choice={
                    "type": "function",
                    "function": {"name": EXTRACT_FUNCTION_NAME},
                },
            )
        except Exception:
            last_error = "The model request failed."
            if attempt == 0:
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "The previous model call failed. Call "
                            f"{EXTRACT_FUNCTION_NAME} again with valid JSON. "
                            "Do not invent values the user did not provide."
                        ),
                    }
                )
                continue
            break

        preferences, parse_error = _preferences_from_tool_arguments(raw_arguments)
        if preferences is not None:
            return preferences, None

        last_error = parse_error or last_error
        if attempt == 0:
            messages.append(
                {
                    "role": "user",
                    "content": (
                        f"Your previous function call was invalid: {last_error} "
                        f"Call {EXTRACT_FUNCTION_NAME} again with JSON that matches "
                        "the schema. Do not invent values the user did not provide."
                    ),
                }
            )

    return None, (
        "The model returned invalid output twice. Please try again."
    )


def _preferences_from_tool_arguments(
    raw_arguments: str,
) -> tuple[ExtractedPreferences | None, str | None]:
    if raw_arguments is None or not str(raw_arguments).strip():
        return None, "The model did not return a function call."

    try:
        payload = json.loads(raw_arguments)
    except json.JSONDecodeError:
        return None, "The model output was not valid JSON."

    if not isinstance(payload, dict):
        return None, "The model output was not a JSON object."

    mapped = _map_extraction_payload(payload)
    try:
        return ExtractedPreferences.model_validate(mapped), None
    except ValidationError as exc:
        return None, f"The model output did not match the extraction schema: {exc.error_count()} error(s)."


def _map_extraction_payload(payload: dict[str, Any]) -> dict[str, Any]:
    mapped = {
        "origin": payload.get("origin_iata") or payload.get("origin"),
        "origin_text": payload.get("origin_text"),
        "departure_date": payload.get("departure_date"),
        "return_date": payload.get("return_date"),
        "duration_days": payload.get("duration_days"),
        "budget": payload.get("budget"),
        "currency": payload.get("currency"),
        "moods": payload.get("moods") or [],
        "direct_flights_only": payload.get("direct_flights_only"),
        "weather_preference": payload.get("weather_preference"),
    }
    return {key: value for key, value in mapped.items() if value is not None or key == "moods"}


def _system_prompt(reference_date: date) -> str:
    return (
        "You extract travel preferences from the user's message only.\n"
        f"Today's date is {reference_date.isoformat()}. Use it for relative dates.\n"
        f"Call the {EXTRACT_FUNCTION_NAME} function.\n"
        "Rules:\n"
        "- Extract only facts the user stated. Leave other fields null.\n"
        "- origin_iata: only when the user wrote an explicit 3-letter IATA code.\n"
        "- Never invent an airport or city code for a place name. Put the name in origin_text.\n"
        "- Do not use fixture data, default destinations, or assumed budgets.\n"
        "- currency: € means EUR. '400 EUR' and 'EUR 400' are EUR. Do not invent EUR without a cue.\n"
        "- moods: mood words such as relaxing. Do not put weather words in moods.\n"
        "- weather_preference: weather words such as warm. 'warm escape' is warm.\n"
        "- duration_days: only if the user stated a duration.\n"
        "- direct_flights_only: only if the user stated a direct-flight requirement.\n"
    )
