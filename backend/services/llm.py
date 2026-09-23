"""Travel request extraction and validation.

Backend integration should call `parse_request`.

Signature:
    await parse_request(
        user_text: str,
        form_fields: dict[str, Any] | None = None,
        *,
        reference_date: date | None = None,
        llm_client: LLMClient | None = None,
    ) -> ParseRequestResult

Arguments:
    user_text: Free-text travel request. Extracted only from this string.
    form_fields: Optional explicit form values. These fill fields the
                 message did not set. If both set a field, the message wins.
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

LLM behaviour:
    One extraction attempt, then one repair attempt if the model output is
    malformed or schema-invalid. Missing user facts are not invented and are
    not retried. Fixture files are never read.
"""

from __future__ import annotations

import asyncio
import json
import os
from datetime import date
from pathlib import Path
from typing import Any, Protocol

from pydantic import ValidationError

from backend.models.trip_request import (
    ExtractedPreferences,
    ParseRequestResult,
    _coerce_date,
    apply_explicit_text_facts,
    fill_missing_dates,
    merge_preferences,
    parse_form_fields,
    split_stated_date_range,
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
                    "description": (
                        "An explicit calendar date in any common written format, "
                        "including yearless dates such as 12.10 or 12/10. Copy "
                        "those as written; do not return null because the year "
                        "is missing. Examples: 2026-09-18, 18/09/2026, 12.10, "
                        "or September 18 2026. Do not resolve relative dates "
                        "such as next weekend; return null for those. A phrase "
                        "like 'from 10.10. until 16.10.' is two explicit dates, "
                        "not a relative date."
                    ),
                },
                "return_date": {
                    "type": ["string", "null"],
                    "description": (
                        "An explicit calendar date in any common written format, "
                        "including yearless dates such as 16.10 or 16/10. Copy "
                        "those as written; do not return null because the year "
                        "is missing. Do not resolve relative dates such as next "
                        "weekend; return null for those. 'until 16.10.' and "
                        "'to 16.10' are explicit return dates; copy them even "
                        "when they end with a period."
                    ),
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
                        "Weather meaning only: use warm for warmer or hotter "
                        "temperature requests, including 'warm escape'; use cool "
                        "for cooler or colder temperature requests; otherwise null. "
                        "Do not use warm/cool for sunshine or rain."
                    ),
                },
            },
        },
    },
}


class LLMClient(Protocol):
    """Minimal function-calling client used by parse_request."""

    async def complete_function_call(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        tool_choice: dict[str, Any] | None = None,
    ) -> str:
        """Return the chosen tool-call arguments as a JSON string."""

    async def aclose(self) -> None:
        """Release the shared SDK client for this worker, if one was created."""


class LLMConfigurationError(RuntimeError):
    """Raised when a live client is requested but environment config is missing."""


def _missing_openai_package(exc: ImportError) -> LLMConfigurationError:
    return LLMConfigurationError(
        "The openai package is required for the live LLM adapter. "
        "Install project dependencies or inject llm_client."
    )


async def _aclose_sdk(client: Any) -> None:
    if client is None:
        return
    closer = getattr(client, "close", None)
    if closer is None:
        return
    result = closer()
    if asyncio.iscoroutine(result):
        await result


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
        self._sdk: Any = None
        self._init_lock: asyncio.Lock | None = None

    async def _sdk_client(self) -> Any:
        if self._sdk is not None:
            return self._sdk
        if self._init_lock is None:
            self._init_lock = asyncio.Lock()
        async with self._init_lock:
            if self._sdk is None:
                try:
                    from openai import AsyncOpenAI
                except ImportError as exc:
                    raise _missing_openai_package(exc) from exc
                client_kwargs: dict[str, Any] = {"api_key": self._api_key}
                if self._base_url:
                    client_kwargs["base_url"] = self._base_url
                self._sdk = AsyncOpenAI(**client_kwargs)
        return self._sdk

    async def complete_function_call(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        tool_choice: dict[str, Any] | None = None,
    ) -> str:
        client = await self._sdk_client()
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

        response = await client.chat.completions.create(**create_kwargs)
        return _tool_arguments_from_response(response)

    async def aclose(self) -> None:
        client = self._sdk
        self._sdk = None
        await _aclose_sdk(client)


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
        self._sdk: Any = None
        self._init_lock: asyncio.Lock | None = None

    async def _sdk_client(self) -> Any:
        if self._sdk is not None:
            return self._sdk
        if self._init_lock is None:
            self._init_lock = asyncio.Lock()
        async with self._init_lock:
            if self._sdk is None:
                try:
                    from openai import AsyncAzureOpenAI
                except ImportError as exc:
                    raise _missing_openai_package(exc) from exc
                self._sdk = AsyncAzureOpenAI(
                    api_key=self._api_key,
                    azure_endpoint=self._azure_endpoint,
                    api_version=self._api_version,
                )
        return self._sdk

    async def complete_function_call(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        tool_choice: dict[str, Any] | None = None,
    ) -> str:
        client = await self._sdk_client()
        response = await client.chat.completions.create(
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

    async def aclose(self) -> None:
        client = self._sdk
        self._sdk = None
        await _aclose_sdk(client)


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


async def parse_request(
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
        form_preferences = parse_form_fields(
            form_fields,
            reference_date=today,
        )
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
        owned_client = None
        try:
            client = llm_client
            if client is None:
                try:
                    owned_client = create_llm_client_from_env()
                except LLMConfigurationError as exc:
                    return ParseRequestResult(
                        status="error",
                        preferences=form_preferences,
                        issues=[str(exc)],
                        clarification_questions=[],
                    )
                client = owned_client
            extracted, model_error = await _extract_with_retry(text, today, client)
            if model_error:
                return ParseRequestResult(
                    status="error",
                    preferences=form_preferences,
                    issues=[model_error],
                    clarification_questions=[],
                )
            extracted = apply_explicit_text_facts(extracted, text)
        finally:
            if owned_client is not None:
                await owned_client.aclose()
    else:
        extracted = ExtractedPreferences()

    merged, conflict_issues, conflict_questions = merge_preferences(
        extracted, form_preferences
    )
    merged = fill_missing_dates(merged, text, reference_date=today)
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


async def _extract_with_retry(
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
            raw_arguments = await llm_client.complete_function_call(
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

        preferences, parse_error = _preferences_from_tool_arguments(
            raw_arguments,
            reference_date=reference_date,
        )
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
    *,
    reference_date: date | None = None,
) -> tuple[ExtractedPreferences | None, str | None]:
    if raw_arguments is None or not str(raw_arguments).strip():
        return None, "The model did not return a function call."

    try:
        payload = json.loads(raw_arguments)
    except json.JSONDecodeError:
        return None, "The model output was not valid JSON."

    if not isinstance(payload, dict):
        return None, "The model output was not a JSON object."

    try:
        mapped = _map_extraction_payload(payload, reference_date=reference_date)
        return ExtractedPreferences.model_validate(mapped), None
    except ValidationError as exc:
        # An ambiguous or unsupported date is missing information, not a
        # reason to fail the whole request. Let validation ask for that date.
        recoverable = dict(mapped)
        recovered_date = False
        for error in exc.errors():
            location = error.get("loc") or ()
            field_name = location[0] if location else None
            if field_name in {"departure_date", "return_date"}:
                recoverable[field_name] = None
                recovered_date = True
        if recovered_date:
            return ExtractedPreferences.model_validate(recoverable), None
        return None, f"The model output did not match the extraction schema: {exc.error_count()} error(s)."
    except ValueError as exc:
        return None, str(exc)


def _map_extraction_payload(
    payload: dict[str, Any],
    *,
    reference_date: date | None = None,
) -> dict[str, Any]:
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
    if mapped.get("return_date") in (None, ""):
        start, end = split_stated_date_range(mapped.get("departure_date"))
        if end:
            mapped["departure_date"] = start
            mapped["return_date"] = end
    for field_name in ("departure_date", "return_date"):
        if mapped.get(field_name) is not None:
            try:
                mapped[field_name] = _coerce_date(
                    mapped[field_name],
                    field_name,
                    reference_date,
                )
            except ValueError:
                # Keep the rest of the extracted request and let normal
                # validation ask the user to clarify this date.
                mapped[field_name] = None
    return {key: value for key, value in mapped.items() if value is not None or key == "moods"}


def _system_prompt(reference_date: date) -> str:
    return (
        "You extract travel preferences from the user's message only.\n"
        f"Today's date is {reference_date.isoformat()}. Use it only to "
        "validate explicit dates; do not resolve relative dates.\n"
        f"Call the {EXTRACT_FUNCTION_NAME} function.\n"
        "Rules:\n"
        "- Extract only facts the user stated. Leave other fields null.\n"
        "- origin_iata: only when the user wrote an explicit 3-letter IATA code.\n"
        "- Never invent an airport or city code for a place name. Put the name in origin_text.\n"
        "- Do not use fixture data, default destinations, or assumed budgets.\n"
        "- currency: € means EUR. '400 EUR' and 'EUR 400' are EUR. Do not invent EUR without a cue.\n"
        "- moods: mood words such as relaxing. Do not put weather words in moods.\n"
        "- weather_preference: canonicalize warmer/hotter temperature requests "
        "to warm and cooler/colder temperature requests to cool. 'warm escape' "
        "is warm. Do not treat sunshine or rain as temperature.\n"
        "- Do not treat rain or sunshine as a mood.\n"
        "- Accept explicit calendar dates in common formats, including "
        "yearless dates such as 12.10, 12.10., or 12/10. Copy those as written, "
        "including a trailing period after the month. The backend adds the year. "
        "Leave relative dates such as 'next weekend' null.\n"
        "- from/until, from/to, and '10.10. until 16.10.' are two explicit dates: "
        "put the first in departure_date and the second in return_date. Do not "
        "leave return_date null in that case.\n"
        "- If the user gave only one explicit date, put it in departure_date "
        "and leave return_date null unless a second date or duration was stated.\n"
        "- duration_days: only if the user stated a duration.\n"
        "- direct_flights_only: only if the user stated a direct-flight requirement.\n"
    )
