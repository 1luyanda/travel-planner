"""Proposed TripRequest contract for the Travel Planner.

This module is the AI-owned request contract until the team agrees a shared
schema. It is intentionally separate from provider fixtures.

`ExtractedPreferences` holds whatever the user (and optional form) supplied,
including incomplete values.

`TripRequest` is only built after validation succeeds. The MVP requires an
explicit origin IATA code, departure date, return date, positive budget and
currency before status becomes `ready`.

Moods are free-text labels from the user. They do not need to appear in
travel fixtures.

Duration is optional. It is never derived from fixture metadata or invented
when the user omitted it.

Proposed team alignment:
- Origin is a 3-letter IATA code. Unresolved place names stay in
  `origin_text` and trigger clarification instead of a guessed code.
- `direct_flights_only` and `weather_preference` are optional constraints.
- Currency is a 3-letter code such as EUR. No default currency is assumed.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

ParseStatus = Literal["ready", "needs_input", "error"]

FORM_FIELD_NAMES = (
    "origin",
    "departure_date",
    "return_date",
    "duration_days",
    "budget",
    "currency",
    "moods",
    "direct_flights_only",
    "weather_preference",
)

IATA_CODE_PATTERN = r"^[A-Za-z]{3}$"
CURRENCY_PATTERN = r"^[A-Za-z]{3}$"
_MONTH_NAME = (
    r"(?:January|February|March|April|May|June|July|August|September|"
    r"October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)"
)
_DATE_TOKEN = re.compile(
    r"("
    r"\d{4}-\d{2}-\d{2}"
    r"|[0-9]{1,2}\s+" + _MONTH_NAME + r"[a-z]*\.?,?\s+[0-9]{4}"
    r"|" + _MONTH_NAME + r"[a-z]*\.?,?\s+[0-9]{1,2},?\s+[0-9]{4}"
    r"|[0-9]{1,2}[./-][0-9]{1,2}[./-][0-9]{4}"
    r"|[0-9]{1,2}[./-][0-9]{1,2}\.?(?![./-]?\d)"
    r")",
    re.IGNORECASE,
)
_RANGE_GAP = re.compile(r"^[\s.]*\b(?:until|till|to)\b[\s.]*$", re.IGNORECASE)
_DASH_GAP = re.compile(r"^[\s.]*[-–—][\s.]*$")
_STATED_RANGE = re.compile(
    r"(?is)^(?:from\s+)?(.+?)\s+(?:until|till|to)\s+(.+)$"
)
_PLANNER_SECTION_PREFIXES = (
    "the planner asked:",
    "initial form selections:",
)
WARM_WEATHER_EQUIVALENTS = frozenset(
    {
        "warm",
        "warmer",
        "hot",
        "hotter",
        "sunny",
        "sunnier",
        "sunshine",
        "more sunshine",
        "more sunny",
        "less rain",
        "less rainy",
        "drier",
    }
)
COOL_WEATHER_EQUIVALENTS = frozenset(
    {
        "cool",
        "cooler",
        "cold",
        "colder",
        "chilly",
        "rain",
        "rainy",
        "rainier",
        "more rain",
        "more rainy",
        "wetter",
        "less sunshine",
        "cloudy",
        "cloudier",
    }
)
CURRENCY_ALIASES = {
    "€": "EUR",
    "EURO": "EUR",
    "EUROS": "EUR",
    "£": "GBP",
    "POUND": "GBP",
    "POUNDS": "GBP",
    "$": "USD",
    "DOLLAR": "USD",
    "DOLLARS": "USD",
}
_AUTHORITATIVE_ANSWER = re.compile(
    r"Authoritative answer(?:[^\n]*):\s*([^\n]+)",
    re.IGNORECASE,
)
_AMOUNT_CURRENCY = re.compile(
    r"\b(EUR|USD|GBP)\s*(\d+(?:[.,]\d+)?)|(\d+(?:[.,]\d+)?)\s*(EUR|USD|GBP)\b",
    re.IGNORECASE,
)
_EURO_AMOUNT = re.compile(r"€\s*(\d+(?:[.,]\d+)?)|(\d+(?:[.,]\d+)?)\s*€")
_DOLLAR_AMOUNT = re.compile(r"\$\s*(\d+(?:[.,]\d+)?)|(\d+(?:[.,]\d+)?)\s*\$")
_POUND_AMOUNT = re.compile(r"£\s*(\d+(?:[.,]\d+)?)|(\d+(?:[.,]\d+)?)\s*£")
_STANDALONE_CURRENCY = re.compile(r"\b(EUR|USD|GBP)\b", re.IGNORECASE)
_ISO_DATE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
_YEAR_LIKE = re.compile(r"^20[2-9]\d$")
_LEFT_NEGATION = re.compile(
    r"(?i)(?:\b(?:not|no|never|without|avoid|except)\b|n't)\s+(?:\w+\s+){0,3}$"
)
_WARM_WORD = re.compile(
    r"\b(warm|warmer|hot|hotter|sunny|sunnier)\b",
    re.IGNORECASE,
)
_COOL_WORD = re.compile(
    r"\b(cool|cooler|cold|colder|chilly)\b",
    re.IGNORECASE,
)


def canonical_currency(value: str | None) -> str | None:
    """Map explicit currency symbols and names onto a 3-letter code."""
    if value is None:
        return None
    cleaned = str(value).strip()
    if not cleaned:
        return None
    if cleaned in CURRENCY_ALIASES:
        return CURRENCY_ALIASES[cleaned]
    upper = cleaned.upper()
    if upper in CURRENCY_ALIASES:
        return CURRENCY_ALIASES[upper]
    if re.fullmatch(CURRENCY_PATTERN, cleaned):
        return upper
    return None


def canonical_weather_preference(value: str | None) -> str | None:
    """Map equivalent weather words onto one parser value.

    ``warm`` and ``warmer`` are the same preference. Ranking still treats the
    stored string as a label, not a temperature.
    """
    if value is None:
        return None
    cleaned = str(value).strip().lower()
    if not cleaned:
        return None
    if cleaned in WARM_WEATHER_EQUIVALENTS or any(
        phrase in cleaned
        for phrase in (
            "less rain",
            "less rainy",
            "more sunshine",
            "more sunny",
            "sunnier",
            "drier",
        )
    ):
        return "warm"
    if cleaned in COOL_WEATHER_EQUIVALENTS or any(
        phrase in cleaned
        for phrase in (
            "more rain",
            "more rainy",
            "rainier",
            "wetter",
            "less sunshine",
            "cloudy",
            "cloudier",
        )
    ):
        return "cool"
    return cleaned


class ExtractedPreferences(BaseModel):
    """Incomplete or complete preferences collected from text and/or form fields."""

    origin: str | None = Field(
        default=None,
        description="Explicit 3-letter origin IATA code. Never invented from a place name.",
    )
    origin_text: str | None = Field(
        default=None,
        max_length=200,
        description="Origin place name when the user did not give an IATA code.",
    )
    departure_date: date | None = None
    return_date: date | None = None
    duration_days: int | None = Field(
        default=None,
        description="Trip length in days only when the user supplied one.",
    )
    budget: float | None = None
    currency: str | None = None
    moods: list[str] = Field(default_factory=list, max_length=10)
    direct_flights_only: bool | None = None
    weather_preference: str | None = Field(default=None, max_length=100)

    @field_validator("origin")
    @classmethod
    def _uppercase_origin(cls, value: str | None) -> str | None:
        return value.upper() if value else value

    @field_validator("currency")
    @classmethod
    def _canonical_currency(cls, value: str | None) -> str | None:
        if value is None or str(value).strip() == "":
            return None
        return canonical_currency(value) or str(value).strip().upper()

    @field_validator("moods")
    @classmethod
    def _clean_moods(cls, value: list[str]) -> list[str]:
        cleaned = [item.strip() for item in value if item and str(item).strip()]
        if any(len(item) > 50 for item in cleaned):
            raise ValueError("Each mood must be 50 characters or fewer.")
        return cleaned

    @field_validator("origin_text")
    @classmethod
    def _strip_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @field_validator("departure_date", "return_date", mode="before")
    @classmethod
    def _coerce_explicit_date(cls, value: Any) -> date | None:
        if value is None or isinstance(value, date):
            return value
        return _coerce_date(value, "date")

    @field_validator("weather_preference")
    @classmethod
    def _canonical_weather_preference(cls, value: str | None) -> str | None:
        return canonical_weather_preference(value)


class TripRequest(BaseModel):
    """Validated travel request ready for ranking and destination search."""

    origin: str = Field(description="3-letter origin IATA code.")
    departure_date: date
    return_date: date
    duration_days: int | None = Field(default=None, gt=0, le=60)
    budget: float = Field(gt=0, le=1_000_000)
    currency: str
    moods: list[str] = Field(default_factory=list, max_length=10)
    direct_flights_only: bool | None = None
    weather_preference: str | None = Field(default=None, max_length=100)

    @field_validator("origin")
    @classmethod
    def _uppercase_origin(cls, value: str) -> str:
        return value.upper()

    @field_validator("currency")
    @classmethod
    def _canonical_currency(cls, value: str) -> str:
        return canonical_currency(value) or value.upper()

    @field_validator("moods")
    @classmethod
    def _validate_moods(cls, value: list[str]) -> list[str]:
        cleaned = [item.strip() for item in value if item and str(item).strip()]
        if any(len(item) > 50 for item in cleaned):
            raise ValueError("Each mood must be 50 characters or fewer.")
        return cleaned


class ParseRequestResult(BaseModel):
    """Result returned to the backend integration owner."""

    status: ParseStatus
    request: TripRequest | None = None
    preferences: ExtractedPreferences | None = None
    issues: list[str] = Field(default_factory=list)
    clarification_questions: list[str] = Field(default_factory=list)


def parse_form_fields(
    form_fields: dict[str, Any] | None,
    *,
    reference_date: date | None = None,
) -> ExtractedPreferences:
    """Coerce optional frontend form values into ExtractedPreferences."""
    if not form_fields:
        return ExtractedPreferences()

    raw: dict[str, Any] = {}
    for name in FORM_FIELD_NAMES:
        if name not in form_fields:
            continue
        value = form_fields[name]
        if value is None or value == "":
            continue
        raw[name] = value

    if "moods" in raw:
        raw["moods"] = _coerce_moods(raw["moods"])
    if "departure_date" in raw:
        raw["departure_date"] = _coerce_date(
            raw["departure_date"], "departure_date", reference_date
        )
    if "return_date" in raw:
        raw["return_date"] = _coerce_date(
            raw["return_date"], "return_date", reference_date
        )
    if "budget" in raw:
        raw["budget"] = _coerce_number(raw["budget"], "budget")
    if "duration_days" in raw:
        raw["duration_days"] = _coerce_int(raw["duration_days"], "duration_days")
    if "direct_flights_only" in raw:
        raw["direct_flights_only"] = _coerce_bool(
            raw["direct_flights_only"], "direct_flights_only"
        )
    if "origin" in raw and isinstance(raw["origin"], str):
        raw["origin"] = raw["origin"].strip()
    if "currency" in raw and isinstance(raw["currency"], str):
        raw["currency"] = raw["currency"].strip()

    return ExtractedPreferences.model_validate(raw)


def apply_explicit_text_facts(
    preferences: ExtractedPreferences,
    user_text: str,
) -> ExtractedPreferences:
    """Fill missing currency, budget, and weather from explicit wording.

    Does not invent EUR, a budget, or weather when the text has no cue.
    An authoritative clarification answer overrides earlier values for fields
    it actually states. Conflicting currencies or amounts are left unset.
    """
    text = user_text or ""
    answer = _latest_authoritative_answer(text)
    updates: dict[str, Any] = {}

    if answer:
        if not _conflicting_currencies(answer):
            currency = _currency_from_answer(answer)
            if currency:
                updates["currency"] = currency
        if not _conflicting_budgets(answer):
            budget = _budget_from_answer(answer)
            if budget is not None:
                updates["budget"] = budget
        updates.update(_dates_from_text(answer))
        if _weather_mentioned(answer):
            updates["weather_preference"] = weather_from_text(answer)

    if "currency" not in updates and preferences.currency is None:
        currency = currency_from_text(text)
        if currency:
            updates["currency"] = currency
    if "budget" not in updates and preferences.budget is None:
        budget = budget_from_text(text)
        if budget is not None:
            updates["budget"] = budget
    if "weather_preference" not in updates and preferences.weather_preference is None:
        weather = weather_from_text(text)
        if weather:
            updates["weather_preference"] = weather

    if not updates:
        return preferences
    return preferences.model_copy(update=updates)


def currency_from_text(text: str) -> str | None:
    answer = _latest_authoritative_answer(text)
    if answer:
        if _conflicting_currencies(answer):
            return None
        from_answer = _currency_from_answer(answer)
        if from_answer:
            return from_answer
        if _conflicting_currencies(text):
            return None
    if _conflicting_currencies(text):
        return None
    return _currency_tokens(text)


def budget_from_text(text: str) -> float | None:
    answer = _latest_authoritative_answer(text)
    if answer:
        if _conflicting_budgets(answer):
            return None
        amount = _budget_from_answer(answer)
        if amount is not None:
            return amount
    if _conflicting_budgets(text):
        return None
    return _single_budget_amount(text)


def weather_from_text(text: str) -> str | None:
    warm = bool(_unnegated_matches(_WARM_WORD, text))
    cool = bool(_unnegated_matches(_COOL_WORD, text))
    if warm and not cool:
        return "warm"
    if cool and not warm:
        return "cool"
    return None


def _weather_mentioned(text: str) -> bool:
    return bool(_WARM_WORD.search(text or "") or _COOL_WORD.search(text or ""))


def _unnegated_matches(pattern: re.Pattern[str], text: str) -> list[str]:
    hits: list[str] = []
    source = text or ""
    for match in pattern.finditer(source):
        before = source[max(0, match.start() - 40) : match.start()]
        if _LEFT_NEGATION.search(before):
            continue
        hits.append(match.group(0).lower())
    return hits


def _latest_authoritative_answer(text: str) -> str | None:
    matches = list(_AUTHORITATIVE_ANSWER.finditer(text or ""))
    if matches:
        return matches[-1].group(1).strip()
    return None


def _currency_from_answer(answer: str) -> str | None:
    return canonical_currency(answer) or _currency_tokens(answer) or _standalone_currency(answer)


def _standalone_currency(text: str) -> str | None:
    codes = _currency_codes_in(text)
    if len(codes) == 1:
        return next(iter(codes))
    return None


def _currency_codes_in(text: str) -> set[str]:
    return {match.group(1).upper() for match in _STANDALONE_CURRENCY.finditer(text or "")}


def _currency_tokens(text: str) -> str | None:
    codes = _currencies_stated(text)
    if len(codes) == 1:
        return next(iter(codes))
    return None


def _currencies_stated(text: str) -> set[str]:
    found: set[str] = set()
    source = text or ""
    if "€" in source:
        found.add("EUR")
    if "£" in source:
        found.add("GBP")
    if _DOLLAR_AMOUNT.search(source):
        found.add("USD")
    for match in _AMOUNT_CURRENCY.finditer(source):
        found.add((match.group(1) or match.group(4)).upper())
    word = re.search(r"\b(euros?|pounds?|dollars?)\b", source, re.IGNORECASE)
    if word:
        aliased = canonical_currency(word.group(1))
        if aliased:
            found.add(aliased)
    return found


def _conflicting_currencies(text: str) -> bool:
    return len(_currencies_stated(text)) > 1


def _budget_from_answer(answer: str) -> float | None:
    stripped = _ISO_DATE.sub(" ", answer or "")
    amounts = _amounts_in_text(stripped)
    if len(amounts) == 1:
        return amounts[0]
    if len(amounts) > 1:
        return None
    match = re.search(r"\b(\d{2,5}(?:[.,]\d+)?)\b", stripped)
    if not match:
        return None
    raw = match.group(1)
    if _YEAR_LIKE.fullmatch(raw):
        return None
    try:
        return float(raw.replace(",", "."))
    except ValueError:
        return None


def _single_budget_amount(text: str) -> float | None:
    amounts = _amounts_in_text(text)
    if len(amounts) == 1:
        return amounts[0]
    return None


def _conflicting_budgets(text: str) -> bool:
    return len(_amounts_in_text(text)) > 1


def _amounts_in_text(text: str) -> list[float]:
    values: list[float] = []
    source = text or ""
    for pattern in (_EURO_AMOUNT, _AMOUNT_CURRENCY, _DOLLAR_AMOUNT, _POUND_AMOUNT):
        for match in pattern.finditer(source):
            raw = next((group for group in match.groups() if group and re.search(r"\d", group)), None)
            if raw is None:
                continue
            try:
                number = float(raw.replace(",", "."))
            except ValueError:
                continue
            if number not in values:
                values.append(number)
    return values


def _dates_from_text(text: str) -> dict[str, date]:
    found: list[date] = []
    for raw in _ISO_DATE.findall(text or ""):
        try:
            parsed = date.fromisoformat(raw)
        except ValueError:
            continue
        if parsed not in found:
            found.append(parsed)
    if not found:
        return {}
    if len(found) >= 2:
        return {"departure_date": found[0], "return_date": found[1]}
    if re.search(r"\breturn\b", text or "", re.IGNORECASE) and not re.search(
        r"\bdepart", text or "", re.IGNORECASE
    ):
        return {"return_date": found[0]}
    return {"departure_date": found[0]}


def merge_preferences(
    extracted: ExtractedPreferences,
    form: ExtractedPreferences,
) -> tuple[ExtractedPreferences, list[str], list[str]]:
    """Preserve explicit form values. Record conflicts instead of overwriting."""
    merged = extracted.model_dump()
    issues: list[str] = []
    questions: list[str] = []

    comparable_fields = (
        "origin",
        "departure_date",
        "return_date",
        "duration_days",
        "budget",
        "currency",
        "direct_flights_only",
        "weather_preference",
    )

    for field_name in comparable_fields:
        form_value = getattr(form, field_name)
        extracted_value = merged.get(field_name)
        if form_value is None:
            continue
        if _has_extracted_value(field_name, extracted_value) and not _values_equal(
            extracted_value, form_value, field_name=field_name
        ):
            issues.append(
                f"The form and the message disagree about {field_name.replace('_', ' ')}."
            )
            questions.append(
                f"The form has {field_name.replace('_', ' ')} {form_value!s} "
                f"but the message has {extracted_value!s}. Which should we use?"
            )
            continue
        merged[field_name] = form_value

    if form.moods:
        if extracted.moods and _normalise_moods(extracted.moods) != _normalise_moods(
            form.moods
        ):
            issues.append("The form and the message disagree about moods.")
            questions.append(
                f"The form moods are {form.moods} but the message moods are "
                f"{extracted.moods}. Which moods should we use?"
            )
        else:
            merged["moods"] = form.moods

    if form.origin_text and not merged.get("origin_text"):
        merged["origin_text"] = form.origin_text

    return ExtractedPreferences.model_validate(merged), issues, questions


def validate_preferences(
    preferences: ExtractedPreferences,
) -> tuple[TripRequest | None, list[str], list[str]]:
    """Validate merged preferences. Missing or invalid user values need input."""
    issues: list[str] = []
    questions: list[str] = []

    origin = preferences.origin
    if preferences.origin_text and not origin:
        issues.append(
            "Origin was given as a place name, not an IATA code."
        )
        questions.append(
            f"Please provide the 3-letter IATA code for {preferences.origin_text}. "
            "A code will not be invented from the place name."
        )
    elif origin and not _matches(IATA_CODE_PATTERN, origin):
        issues.append("Origin must be a 3-letter IATA code.")
        questions.append(
            "What is your origin airport or city IATA code (for example ZAG)?"
        )
        origin = None
    elif not origin:
        issues.append("Origin is missing.")
        questions.append(
            "What is your origin airport or city IATA code (for example ZAG)?"
        )

    if preferences.departure_date is None:
        issues.append("Departure date is missing.")
        questions.append(
            "What is your departure date? For example: 12.10, 12/10/2026, "
            "or 2026-10-12."
        )
    if preferences.return_date is None:
        issues.append("Return date is missing.")
        questions.append(
            "What is your return date? For example: 16.10, 16/10/2026, "
            "or 2026-10-16."
        )
    if (
        preferences.departure_date is not None
        and preferences.return_date is not None
        and preferences.return_date < preferences.departure_date
    ):
        issues.append("Return date is before departure date.")
        questions.append("Return date must be on or after the departure date. Please confirm both dates.")

    if preferences.duration_days is not None and preferences.duration_days <= 0:
        issues.append("Duration must be a positive number of days.")
        questions.append("How many days is the trip? Duration must be greater than zero.")

    budget = preferences.budget
    if budget is None:
        issues.append("Budget is missing.")
        questions.append("What is your maximum budget?")
    elif budget <= 0:
        issues.append("Budget must be a positive number.")
        questions.append("What is your maximum budget? It must be greater than zero.")
        budget = None

    currency = preferences.currency
    if currency is None:
        issues.append("Currency is missing.")
        questions.append("What currency is the budget in (for example EUR)?")
    elif not _matches(CURRENCY_PATTERN, currency):
        issues.append("Currency must be a 3-letter code.")
        questions.append("What currency is the budget in (for example EUR)?")
        currency = None

    blocking_invalid = any(
        item
        in {
            "Return date is before departure date.",
            "Budget must be a positive number.",
            "Duration must be a positive number of days.",
            "Origin must be a 3-letter IATA code.",
            "Currency must be a 3-letter code.",
        }
        for item in issues
    )

    missing_required = any(
        (
            origin is None,
            preferences.departure_date is None,
            preferences.return_date is None,
            budget is None,
            currency is None,
        )
    )

    if (
        missing_required
        or blocking_invalid
        or (preferences.return_date and preferences.departure_date
            and preferences.return_date < preferences.departure_date)
    ):
        return None, issues, questions

    request = TripRequest(
        origin=origin,
        departure_date=preferences.departure_date,
        return_date=preferences.return_date,
        duration_days=preferences.duration_days,
        budget=budget,
        currency=currency,
        moods=preferences.moods,
        direct_flights_only=preferences.direct_flights_only,
        weather_preference=preferences.weather_preference,
    )
    return request, [], []


def _has_extracted_value(field_name: str, value: Any) -> bool:
    if field_name == "moods":
        return bool(value)
    return value is not None


def _values_equal(left: Any, right: Any, field_name: str | None = None) -> bool:
    if field_name == "weather_preference":
        left_weather = canonical_weather_preference(left)
        right_weather = canonical_weather_preference(right)
        if left_weather is not None and right_weather is not None:
            return left_weather == right_weather
    if isinstance(left, float) or isinstance(right, float):
        try:
            return float(left) == float(right)
        except (TypeError, ValueError):
            return False
    if isinstance(left, str) and isinstance(right, str):
        return left.strip().upper() == right.strip().upper()
    return left == right


def _normalise_moods(moods: list[str]) -> list[str]:
    return sorted(mood.strip().lower() for mood in moods if mood.strip())


def _matches(pattern: str, value: str) -> bool:
    return re.fullmatch(pattern, value) is not None


def _coerce_moods(value: Any) -> list[str]:
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    raise ValueError("moods must be a list or a comma-separated string.")


def _user_authored_text(text: str) -> str:
    """Keep original request and answers; drop planner example dates."""
    if not text:
        return ""
    lowered = text.lower()
    if "the planner asked:" not in lowered and "original request:" not in lowered:
        return text
    kept: list[str] = []
    for part in re.split(r"\n\s*\n", text):
        first_line = part.strip().split("\n", 1)[0].strip().lower()
        if any(first_line.startswith(prefix) for prefix in _PLANNER_SECTION_PREFIXES):
            continue
        kept.append(part)
    return "\n\n".join(kept)


def dates_from_text(
    text: str,
    reference_date: date | None = None,
) -> list[date]:
    """Parse explicit calendar dates from user-authored text, in order."""
    found: list[date] = []
    for token in _DATE_TOKEN.findall(_user_authored_text(text)):
        try:
            parsed = _coerce_date(token, "date", reference_date)
        except ValueError:
            continue
        if parsed not in found:
            found.append(parsed)
    return found


def range_dates_from_text(
    text: str,
    reference_date: date | None = None,
) -> tuple[date, date] | None:
    """Return (departure, return) when the text has from/until or a date dash range."""
    authored = _user_authored_text(text)
    spans: list[tuple[int, int, date]] = []
    for match in _DATE_TOKEN.finditer(authored):
        try:
            parsed = _coerce_date(match.group(1), "date", reference_date)
        except ValueError:
            continue
        spans.append((match.start(), match.end(), parsed))
    for index in range(len(spans) - 1):
        gap = authored[spans[index][1] : spans[index + 1][0]]
        if _RANGE_GAP.fullmatch(gap) or _DASH_GAP.fullmatch(gap):
            return spans[index][2], spans[index + 1][2]
    return None


def split_stated_date_range(value: Any) -> tuple[Any, Any]:
    """Split a single string such as '10.10. until 16.10.' into two date tokens."""
    if not isinstance(value, str):
        return value, None
    match = _STATED_RANGE.match(value.strip())
    if not match:
        return value, None
    start = match.group(1).strip(" .")
    end = match.group(2).strip(" .")
    if not start or not end:
        return value, None
    return start, end


def fill_missing_dates(
    preferences: ExtractedPreferences,
    user_text: str,
    *,
    reference_date: date | None = None,
) -> ExtractedPreferences:
    """Fill blank dates from the message. Do not override model or form values.

    A from/until (or to/till/dash) range fills both missing ends. Otherwise a
    single date is departure and a second date is return. If return is still
    missing and the user stated duration_days, return is departure plus that
    duration. Duration itself is never invented.
    """
    found = dates_from_text(user_text, reference_date)
    pair = range_dates_from_text(user_text, reference_date)
    updates: dict[str, Any] = {}
    departure = preferences.departure_date

    if pair is not None:
        start, end = pair
        if departure is None:
            departure = start
            updates["departure_date"] = start
        if preferences.return_date is None:
            updates["return_date"] = end
    else:
        if departure is None and found:
            departure = found[0]
            updates["departure_date"] = departure
        if preferences.return_date is None:
            later = [item for item in found if item != departure]
            if later:
                updates["return_date"] = later[0]
            elif departure is not None and preferences.duration_days:
                updates["return_date"] = departure + timedelta(
                    days=preferences.duration_days
                )
    if not updates:
        return preferences
    return preferences.model_copy(update=updates)


def _coerce_date(
    value: Any,
    field_name: str,
    reference_date: date | None = None,
) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        cleaned = value.strip().rstrip(".;")
        try:
            return date.fromisoformat(cleaned)
        except ValueError:
            pass

        # Accept explicit calendar dates in common written forms. Relative
        # expressions such as "next weekend" remain intentionally unsupported.
        normalized = re.sub(r"\s+", " ", cleaned.replace(",", "")).strip()
        normalized = normalized.rstrip(".;")
        for pattern in ("%d %B %Y", "%d %b %Y", "%B %d %Y", "%b %d %Y"):
            try:
                return datetime.strptime(normalized, pattern).date()
            except ValueError:
                continue

        match = re.fullmatch(r"(\d{1,2})[./-](\d{1,2})[./-](\d{4})", normalized)
        if match:
            first, second, year = (int(part) for part in match.groups())
            if first <= 12 and second <= 12:
                raise ValueError(
                    f"{field_name} is ambiguous. Use a month name or YYYY-MM-DD."
                )
            day, month = (first, second) if first > 12 else (second, first)
            try:
                return date(year, month, day)
            except ValueError as exc:
                raise ValueError(f"{field_name} is not a valid calendar date.") from exc

        short_match = re.fullmatch(r"(\d{1,2})[./-](\d{1,2})", normalized)
        if short_match:
            day, month = (int(part) for part in short_match.groups())
            today = reference_date or date.today()
            try:
                candidate = date(today.year, month, day)
            except ValueError as exc:
                raise ValueError(f"{field_name} is not a valid calendar date.") from exc
            if candidate < today:
                candidate = date(today.year + 1, month, day)
            return candidate

    raise ValueError(
        f"{field_name} must be an explicit calendar date such as "
        "YYYY-MM-DD, 18 September 2026, or September 18 2026."
    )


def _coerce_number(value: Any, field_name: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be a number.")
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be a number.") from exc


def _coerce_int(value: Any, field_name: str) -> int:
    number = _coerce_number(value, field_name)
    if int(number) != number:
        raise ValueError(f"{field_name} must be a whole number of days.")
    return int(number)


def _coerce_bool(value: Any, field_name: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalised = value.strip().lower()
        if normalised in {"true", "yes", "1"}:
            return True
        if normalised in {"false", "no", "0"}:
            return False
    raise ValueError(f"{field_name} must be true or false.")
