"""Deterministic checks over explicitly user-supplied live-trip estimates."""

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

COST_CATEGORIES = ("transport", "accommodation", "activities", "meals", "fees_taxes")
MAX_ESTIMATE_MINOR = 1_000_000_000_000


@dataclass(frozen=True)
class TravelWindow:
    arrival: datetime
    departure: datetime
    available_from: datetime
    available_until: datetime
    buffer_minutes: int


class InvalidTravelWindow(ValueError):
    pass


def _resolve_local(day: date, clock: time, zone: ZoneInfo) -> datetime:
    if clock.tzinfo is not None:
        raise InvalidTravelWindow("Use destination-local clock times without offsets.")
    naive = datetime.combine(day, clock)
    candidates = {
        naive.replace(tzinfo=zone, fold=fold).astimezone(UTC)
        for fold in (0, 1)
        if naive.replace(tzinfo=zone, fold=fold)
        .astimezone(UTC)
        .astimezone(zone)
        .replace(tzinfo=None)
        == naive
    }
    if len(candidates) != 1:
        raise InvalidTravelWindow(
            "A travel time is ambiguous or nonexistent during a clock change. "
            "Choose an unambiguous local time."
        )
    return candidates.pop().astimezone(zone)


def resolve_travel_window(
    start: date,
    end: date,
    arrival: time,
    departure: time,
    timezone: str,
    buffer_minutes: int,
) -> TravelWindow:
    if (
        not 1 <= (end - start).days + 1 <= 4
        or type(buffer_minutes) is not int
        or not 0 <= buffer_minutes <= 240
    ):
        raise InvalidTravelWindow("Invalid travel-window bounds.")
    zone = ZoneInfo(timezone)
    arrived = _resolve_local(start, arrival, zone)
    departing = _resolve_local(end, departure, zone)
    ready = arrived.astimezone(UTC) + timedelta(minutes=buffer_minutes)
    finish = departing.astimezone(UTC) - timedelta(minutes=buffer_minutes)
    if ready >= finish:
        raise InvalidTravelWindow(
            "Arrival must precede departure with time left after both transfer buffers."
        )
    return TravelWindow(
        arrived,
        departing,
        ready.astimezone(zone),
        finish.astimezone(zone),
        buffer_minutes,
    )


@dataclass(frozen=True)
class EstimateCheck:
    status: Literal["incomplete", "within_entered_estimate", "over_entered_estimate"]
    known_subtotal_minor: int
    estimated_total_minor: int | None
    remaining_minor: int | None
    missing_categories: tuple[str, ...]


def check_entered_estimates(
    values: tuple[int | None, ...],
    budget_minor: int,
) -> EstimateCheck:
    if (
        len(values) != len(COST_CATEGORIES)
        or type(budget_minor) is not int
        or not 0 < budget_minor <= MAX_ESTIMATE_MINOR
    ):
        raise ValueError("Invalid estimate budget")
    if any(
        v is not None and (type(v) is not int or not 0 <= v <= MAX_ESTIMATE_MINOR)
        for v in values
    ):
        raise ValueError("Estimates must be non-negative integer minor units")
    missing = tuple(
        k for k, v in zip(COST_CATEGORIES, values, strict=True) if v is None
    )
    subtotal = sum(v for v in values if v is not None)
    status = (
        "over_entered_estimate"
        if subtotal > budget_minor
        else "incomplete"
        if missing
        else "within_entered_estimate"
    )
    return EstimateCheck(
        status,
        subtotal,
        None if missing else subtotal,
        None if missing else budget_minor - subtotal,
        missing,
    )
