"""Storage-independent models and preparation for destination ranking.

``prepare_ranking_records`` validates already-loaded nested or flat dictionaries.
Data-access code can supply these from a database, Parquet, files or an API.
``prepare_ranking_data`` is a JSON/CSV compatibility adapter for local use.
The ranking algorithm consumes only the prepared models.
"""

from __future__ import annotations

import csv
import json
import math
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Public models: these are the types that the ranking developer works with.
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RankingCandidate:
    """One destination that has passed validation and hard constraints.

    ``frozen=True`` prevents ranking code from accidentally changing input data.
    ``slots=True`` makes the model lightweight and catches misspelled attributes.
    Optional values use ``None`` when the source did not provide that feature;
    the loader never invents a numeric replacement.
    """

    # Stable identity fields, also useful as deterministic sorting tie-breakers.
    destination_id: str
    destination_iata: str
    city: str

    # Core flight features. Currency is absent because price is guaranteed EUR.
    price_eur: float
    changeover_count: int
    # Round-trip total: outbound duration plus return duration.
    flight_duration_minutes: int
    trip_duration_days: int

    # Weather features remain separate so ranking can apply different user
    # preferences (for example, warmer versus drier) without reloading data.
    average_max_temperature_c: float
    average_min_temperature_c: float | None
    precipitation_probability_percent: float
    sunshine_hours: float | None
    max_wind_speed_kmh: float | None

    # This is optional because the current normalized data may not contain the
    # distance between the destination airport and its associated city.
    airport_distance_km: float | None

    # Cosmos currently omits freshness; it does not affect MVP scores.
    flight_retrieved_at: datetime | None = None
    weather_retrieved_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class RankedDestination:
    """Six component scores; legacy weather_score represents temperature."""

    destination_id: str
    destination_iata: str
    city: str
    price_eur: float
    changeover_count: int
    # Round-trip total: outbound duration plus return duration.
    flight_duration_minutes: int
    trip_duration_days: int
    average_max_temperature_c: float
    price_score: float
    weather_score: float
    stops_score: float
    duration_score: float
    final_score: float
    precipitation_score: float = 0.0
    sunshine_score: float = 0.0
    temperature_direction: str = "higher_is_better"


@dataclass(frozen=True, slots=True)
class RankingConstraints:
    """Hard requirements applied before ranking, not user preferences.

    A hard requirement removes a candidate. A preference such as "cheaper is
    better" belongs in the ranking weights and must not be added here.
    """

    max_price_eur: float | None = None
    max_changeovers: int | None = None
    max_flight_duration_minutes: int | None = None

    def __post_init__(self) -> None:
        if self.max_price_eur is not None and self.max_price_eur < 0:
            raise ValueError("max_price_eur cannot be negative")
        if self.max_changeovers is not None and self.max_changeovers < 0:
            raise ValueError("max_changeovers cannot be negative")
        if (
            self.max_flight_duration_minutes is not None
            and self.max_flight_duration_minutes < 0
        ):
            raise ValueError("max_flight_duration_minutes cannot be negative")


@dataclass(frozen=True, slots=True)
class Rejection:
    """Machine-readable rejection code plus a message useful for logs."""

    code: str
    message: str


@dataclass(frozen=True, slots=True)
class RejectedCandidate:
    """A source record that could not be handed to the ranking algorithm."""

    destination_id: str | None
    destination_iata: str | None
    reasons: tuple[Rejection, ...]


@dataclass(frozen=True, slots=True)
class CandidatePreparationResult:
    """The complete hand-off from the data layer to ranking.

    Ranking uses ``candidates``. The backend or logs can inspect ``rejected`` to
    explain why a source destination was excluded.
    """

    candidates: tuple[RankingCandidate, ...]
    rejected: tuple[RejectedCandidate, ...]


class RankingDataError(ValueError):
    """Raised when the input file itself cannot be interpreted."""


def prepare_ranking_data(
    source_path: str | Path,
    constraints: RankingConstraints | None = None,
) -> CandidatePreparationResult:
    """Compatibility adapter: read JSON/CSV and delegate to record preparation."""

    return prepare_ranking_records(_read_records(Path(source_path)), constraints)


def prepare_ranking_records(
    records: Iterable[dict[str, Any]],
    constraints: RankingConstraints | None = None,
) -> CandidatePreparationResult:
    """Validate loaded records and apply hard constraints, without storage I/O.

    Invalid records are returned in ``rejected`` instead of being silently
    discarded. Candidate order is deterministic and does not imply rank.
    Both nested provider records and flat ranking-ready records are accepted.
    """

    active_constraints = constraints or RankingConstraints()
    candidates: list[RankingCandidate] = []
    rejected: list[RejectedCandidate] = []

    # Convert each raw dictionary into the shared model.
    # One bad destination does not prevent other valid destinations from being
    # ranked; instead, the bad destination receives a structured rejection.
    for record in records:
        try:
            if not isinstance(record, dict):
                raise ValueError("Destination record must be a dictionary")
            candidate = _to_candidate(record)
        except (KeyError, TypeError, ValueError) as error:
            rejected.append(
                RejectedCandidate(
                    destination_id=_text_or_none(
                        _first(record, "id", "destination_id")
                    ),
                    destination_iata=_text_or_none(
                        _first(
                            record,
                            "flight.destination_airport_iata",
                            "flight.destination_iata",
                            "destination_iata",
                        )
                    ),
                    reasons=(Rejection("invalid_data", str(error)),),
                )
            )
            continue

        # Apply only mandatory request constraints after type and range
        # validation. Ranking preferences are deliberately not applied here.
        reasons = _constraint_rejections(candidate, active_constraints)
        if reasons:
            rejected.append(
                RejectedCandidate(
                    destination_id=candidate.destination_id,
                    destination_iata=candidate.destination_iata,
                    reasons=tuple(reasons),
                )
            )
        else:
            candidates.append(candidate)

    # Sources may change record order. Sorting by stable identifiers makes the
    # hand-off deterministic before any ranking score is calculated.
    candidates.sort(
        key=lambda candidate: (
            candidate.destination_iata,
            candidate.destination_id,
        )
    )
    rejected.sort(
        key=lambda item: (
            item.destination_iata or "",
            item.destination_id or "",
        )
    )
    return CandidatePreparationResult(
        candidates=tuple(candidates),
        rejected=tuple(rejected),
    )


def _read_records(path: Path) -> list[dict[str, Any]]:
    """Turn a supported file into a list of raw destination dictionaries."""

    suffix = path.suffix.lower()
    if suffix == ".json":
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            raise RankingDataError(f"Invalid JSON: {error}") from error

        # Accept both common JSON layouts:
        #   [{...}, {...}]
        #   {"generated_at": "...", "destinations": [{...}, {...}]}
        if isinstance(payload, list):
            records = payload
        elif isinstance(payload, dict) and isinstance(
            payload.get("destinations"), list
        ):
            records = payload["destinations"]
        else:
            raise RankingDataError(
                "JSON must be a list or contain a 'destinations' list"
            )
    elif suffix == ".csv":
        # utf-8-sig also accepts normal UTF-8 while safely removing a BOM often
        # added by Excel. DictReader maps each CSV row to a field-name dictionary.
        with path.open("r", encoding="utf-8-sig", newline="") as csv_file:
            records = list(csv.DictReader(csv_file))
    else:
        raise RankingDataError("Only .json and .csv input files are supported")

    return records


def _to_candidate(record: dict[str, Any]) -> RankingCandidate:
    """Map a nested or flat record to one validated ranking candidate.

    Lookups support provider field names and ranking-ready aliases.
    That keeps source field mappings out of the ranking algorithm.
    """

    destination_id = _required_text(record, "id", "destination_id")
    destination_iata = _required_text(
        record,
        "flight.destination_airport_iata",
        "destination_airport_iata",
        "destination_airport",
        "flight.destination_iata",
        "destination_iata",
    ).upper()
    if len(destination_iata) != 3 or not destination_iata.isalpha():
        raise ValueError("destination_iata must be a three-letter IATA code")

    price_eur = _price_eur(record)
    if price_eur <= 0:
        raise ValueError("price_eur must be greater than zero")

    # Ranking-ready records provide totals; provider records provide two legs.
    supplied_changeovers = _first(record, "changeover_count")
    if supplied_changeovers not in (None, ""):
        changeovers = _whole_number(supplied_changeovers, "changeover_count")
    else:
        outbound = _required_int(record, "flight.outbound_stops", "outbound_stops")
        inbound = _required_int(record, "flight.return_stops", "return_stops")
        changeovers = outbound + inbound
    if changeovers < 0:
        raise ValueError("changeover_count cannot be negative")

    supplied_duration = _first(record, "flight_duration_minutes", "duration_minutes")
    if supplied_duration is not None:
        duration = _whole_number(supplied_duration, "flight_duration_minutes")
    else:
        outbound_duration = _required_int(
            record, "flight.outbound_duration_minutes", "outbound_duration_minutes"
        )
        return_duration = _required_int(
            record, "flight.return_duration_minutes", "return_duration_minutes"
        )
        duration = outbound_duration + return_duration
    if duration <= 0:
        raise ValueError("flight_duration_minutes must be greater than zero")

    max_temperature = _required_float(
        record,
        "weather.average_max_temperature_c",
        "average_max_temperature_c",
        "temp_max_c",
    )
    min_temperature = _optional_float(
        record,
        "weather.average_min_temperature_c",
        "average_min_temperature_c",
        "temp_min_c",
    )
    for name, temperature in (
        ("average_max_temperature_c", max_temperature),
        ("average_min_temperature_c", min_temperature),
    ):
        if temperature is not None and not -100 <= temperature <= 70:
            raise ValueError(f"{name} is outside the valid Celsius range")

    precipitation = _required_float(
        record,
        "weather.average_precipitation_probability_percent",
        "precipitation_probability_percent",
        "rain_pct",
    )
    if not 0 <= precipitation <= 100:
        raise ValueError("precipitation_probability_percent must be between 0 and 100")

    # Constructing this dataclass is the actual boundary: after this point the
    # ranking developer uses attributes rather than raw record fields.
    return RankingCandidate(
        destination_id=destination_id,
        destination_iata=destination_iata,
        city=_required_text(
            record,
            "destination.city",
            "destination_city",
            "city",
        ),
        price_eur=price_eur,
        changeover_count=changeovers,
        flight_duration_minutes=duration,
        trip_duration_days=_trip_duration_days(record),
        average_max_temperature_c=max_temperature,
        average_min_temperature_c=min_temperature,
        precipitation_probability_percent=precipitation,
        sunshine_hours=_optional_float(
            record, "weather.average_sunshine_hours", "sunshine_hours"
        ),
        max_wind_speed_kmh=_optional_float(
            record,
            "weather.average_max_wind_speed_kmh",
            "max_wind_speed_kmh",
        ),
        airport_distance_km=_optional_float(
            record,
            "destination.airport_distance_km",
            "destination.airport_distance_from_city_km",
            "airport_distance_km",
        ),
        flight_retrieved_at=_optional_datetime(
            record, "flight.retrieved_at", "flight_retrieved_at"
        ),
        weather_retrieved_at=_optional_datetime(
            record, "weather.retrieved_at", "weather_retrieved_at"
        ),
    )


def _price_eur(record: dict[str, Any]) -> float:
    """Read a pre-normalized EUR price or verify that a raw price is in EUR."""

    normalized_price = _first(record, "price_eur")
    if normalized_price not in (None, ""):
        return _finite_float(normalized_price, "price_eur")

    currency = _required_text(record, "flight.currency", "currency").upper()
    if currency != "EUR":
        raise ValueError(
            f"price has unsupported currency {currency!r}; convert it to EUR first"
        )
    return _required_float(record, "flight.price", "price")


def _trip_duration_days(record: dict[str, Any]) -> int:
    """Read supplied trip days or derive them from departure/return dates."""

    supplied_days = _first(record, "trip_duration_days")
    if supplied_days not in (None, ""):
        days = _whole_number(supplied_days, "trip_duration_days")
    else:
        departure = _required_datetime(record, "flight.departure_at", "departure_at")
        return_time = _required_datetime(record, "flight.return_at", "return_at")
        if return_time < departure:
            raise ValueError("return_at cannot be before departure_at")
        days = (return_time.date() - departure.date()).days
    if days < 0:
        raise ValueError("trip_duration_days cannot be negative")
    return days


def _constraint_rejections(
    candidate: RankingCandidate,
    constraints: RankingConstraints,
) -> list[Rejection]:
    """Return every hard-constraint failure for an otherwise valid candidate."""

    reasons: list[Rejection] = []
    if (
        constraints.max_price_eur is not None
        and candidate.price_eur > constraints.max_price_eur
    ):
        reasons.append(
            Rejection(
                "over_budget",
                f"Price {candidate.price_eur:.2f} EUR exceeds "
                f"{constraints.max_price_eur:.2f} EUR",
            )
        )
    if (
        constraints.max_changeovers is not None
        and candidate.changeover_count > constraints.max_changeovers
    ):
        reasons.append(
            Rejection(
                "too_many_changeovers",
                f"Candidate has {candidate.changeover_count} changeovers; "
                f"maximum allowed is {constraints.max_changeovers}",
            )
        )
    if (
        constraints.max_flight_duration_minutes is not None
        and candidate.flight_duration_minutes > constraints.max_flight_duration_minutes
    ):
        reasons.append(
            Rejection(
                "flight_too_long",
                f"Flight duration {candidate.flight_duration_minutes} minutes "
                f"exceeds {constraints.max_flight_duration_minutes} minutes",
            )
        )
    return reasons


# ---------------------------------------------------------------------------
# Private parsing helpers. Their leading underscore means they are internal to
# this module; other project code should call prepare_ranking_records instead.
# ---------------------------------------------------------------------------


def _nested(record: dict[str, Any], path: str) -> Any:
    """Resolve a dotted path such as ``weather.average_max_temperature_c``."""

    value: Any = record
    for part in path.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


def _first(record: dict[str, Any], *paths: str) -> Any:
    """Return the first populated field among nested and flat aliases."""

    for path in paths:
        value = _nested(record, path)
        if value not in (None, ""):
            return value
    return None


def _required_text(record: dict[str, Any], *paths: str) -> str:
    value = _first(record, *paths)
    if value is None:
        raise ValueError(f"Missing required field: {paths[0]}")
    text = str(value).strip()
    if not text:
        raise ValueError(f"Field {paths[0]} cannot be empty")
    return text


def _finite_float(value: Any, field_name: str) -> float:
    """Convert numeric strings/numbers while rejecting NaN and infinity."""

    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError(f"{field_name} must be numeric") from error
    if not math.isfinite(number):
        raise ValueError(f"{field_name} must be finite")
    return number


def _whole_number(value: Any, field_name: str) -> int:
    """Convert values such as 2 or '2', but reject fractional values."""

    number = _finite_float(value, field_name)
    if not number.is_integer():
        raise ValueError(f"{field_name} must be a whole number")
    return int(number)


def _required_float(record: dict[str, Any], *paths: str) -> float:
    value = _first(record, *paths)
    if value is None:
        raise ValueError(f"Missing required field: {paths[0]}")
    return _finite_float(value, paths[0])


def _optional_float(record: dict[str, Any], *paths: str) -> float | None:
    value = _first(record, *paths)
    if value is None:
        return None
    return _finite_float(value, paths[0])


def _required_int(record: dict[str, Any], *paths: str) -> int:
    value = _first(record, *paths)
    if value is None:
        raise ValueError(f"Missing required field: {paths[0]}")
    return _whole_number(value, paths[0])


def _required_datetime(record: dict[str, Any], *paths: str) -> datetime:
    """Parse an ISO-8601 timestamp and ensure that it has a timezone."""

    value = _first(record, *paths)
    if value is None:
        raise ValueError(f"Missing required field: {paths[0]}")
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{paths[0]} must be an ISO-8601 timestamp") from error
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _optional_datetime(
    record: dict[str, Any],
    *paths: str,
) -> datetime | None:
    """Parse an optional ISO-8601 timestamp without inventing freshness."""

    value = _first(record, *paths)
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{paths[0]} must be an ISO-8601 timestamp") from error
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _text_or_none(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return str(value)
