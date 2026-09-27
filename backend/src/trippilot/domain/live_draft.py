"""Pure provisional scheduling. Never claims price/opening-hour feasibility."""

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from math import ceil
from zoneinfo import ZoneInfo

from .live_constraints import TravelWindow


@dataclass(frozen=True)
class DraftStop:
    place_index: int
    day: date
    start: datetime
    end: datetime
    walk_minutes: int | None


def schedule_draft(
    start_date: date,
    end_date: date,
    earliest: time,
    timezone: str,
    daily_target: int,
    travel_seconds: tuple[tuple[float | None, ...], ...],
    window: TravelWindow | None = None,
) -> tuple[DraftStop, ...]:
    """No repeated places; reserve actual route time + 30-minute breaks.

    Each stop has a clearly estimated 60-minute visit. No cross-day travel is
    inferred. A missing/long walking leg is not replaced with a guessed duration.
    """
    days = (end_date - start_date).days + 1
    size = len(travel_seconds)
    if not 1 <= days <= 4 or not 1 <= daily_target <= 4 or not 1 <= size <= 8:
        raise ValueError("Invalid draft bounds")
    if earliest.tzinfo is not None or any(len(row) != size for row in travel_seconds):
        raise ValueError("Invalid draft inputs")
    zone = ZoneInfo(timezone)
    remaining = list(range(size))
    stops: list[DraftStop] = []
    for offset in range(days):
        day = start_date + timedelta(days=offset)
        local_start = datetime.combine(day, max(earliest, time(9)), zone)
        cursor = local_start.astimezone(UTC)
        # Reject nonexistent local start times instead of silently shifting them.
        if cursor.astimezone(zone).replace(tzinfo=None) != local_start.replace(
            tzinfo=None
        ):
            raise ValueError("Nonexistent local time")
        limit = datetime.combine(day, time(18), zone).astimezone(UTC)
        if window is not None:
            cursor = max(cursor, window.available_from.astimezone(UTC))
            limit = min(limit, window.available_until.astimezone(UTC))
        previous: int | None = None
        # Spread limited candidates across every requested day before adding density.
        target = min(daily_target, ceil(len(remaining) / (days - offset)))
        for _ in range(target):
            eligible = [
                index
                for index in remaining
                if previous is None
                or (
                    (seconds := travel_seconds[previous][index]) is not None
                    and 0 <= seconds <= 2700
                )
            ]
            if not eligible:
                break
            chosen = min(
                eligible,
                key=lambda i: (
                    0 if previous is None else travel_seconds[previous][i] or 0,
                    i,
                ),
            )
            seconds = None if previous is None else travel_seconds[previous][chosen]
            minutes = None if seconds is None else max(1, ceil(seconds / 60))
            begin = cursor + timedelta(minutes=minutes or 0)
            end = begin + timedelta(minutes=60)
            if end > limit:
                break
            stops.append(
                DraftStop(
                    chosen, day, begin.astimezone(zone), end.astimezone(zone), minutes
                )
            )
            remaining.remove(chosen)
            previous = chosen
            cursor = end + timedelta(minutes=30)
    return tuple(stops)
