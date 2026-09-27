"""Live place-backed drafts, kept distinct from complete validated itineraries."""

from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime
from typing import Literal, Self

from pydantic import AwareDatetime, Field, model_validator

from trippilot.domain import TripRequest
from trippilot.domain.live_constraints import InvalidTravelWindow, resolve_travel_window
from trippilot.domain.live_draft import schedule_draft
from trippilot.providers.geoapify import (
    CATEGORIES,
    City,
    LivePlacesProvider,
    Place,
    StrictRecord,
)

from .live_inputs import BudgetEstimate, TravelTimes, TravelWindowResponse


class LiveStop(StrictRecord):
    place: Place
    day: date
    start: AwareDatetime
    end: AwareDatetime
    walking_minutes_from_previous: int | None = Field(ge=1)
    visit_duration_basis: Literal["estimated_60_minutes"] = "estimated_60_minutes"
    opening_hours_status: Literal["unverified"] = "unverified"
    price_minor: None = None

    @model_validator(mode="after")
    def positive_duration(self) -> Self:
        if (
            self.end <= self.start
            or self.start.date() != self.day
            or self.end.date() != self.day
        ):
            raise ValueError("Invalid stop window")
        return self


class LiveDraft(StrictRecord):
    status: Literal[
        "draft",
        "unavailable",
        "ambiguous_destination",
        "no_places",
        "invalid_window",
        "budget_exceeded",
    ]
    city: City | None = None
    destination_choices: tuple[str, ...] = Field(default=(), max_length=5)
    stops: tuple[LiveStop, ...] = Field(default=(), max_length=8)
    retrieved_at: AwareDatetime | None = None
    budget_status: Literal["not_verified"] = "not_verified"
    all_in_total_minor: None = None
    budget_estimate: BudgetEstimate | None = None
    travel_window: TravelWindowResponse | None = None
    notice: str
    missing: tuple[str, ...] = (
        "Arrival and departure times and fares",
        "Accommodation availability and prices",
        "Activity and meal prices, fees and taxes",
        "Date-specific opening hours",
    )
    attribution: Literal["Geoapify · © OpenStreetMap contributors (ODbL)"] = (
        "Geoapify · © OpenStreetMap contributors (ODbL)"
    )

    @model_validator(mode="after")
    def consistent_status(self) -> Self:
        if self.status == "draft":
            if not self.city or not self.stops or not self.retrieved_at:
                raise ValueError("A draft requires dated source-backed stops")
            ids = [stop.place.place_id for stop in self.stops]
            if len(set(ids)) != len(ids):
                raise ValueError("Repeated place")
        elif self.stops:
            raise ValueError("Failed drafts cannot contain stops")
        return self


class LocalAllowance:
    """Local single-process guard, NOT an account-wide billing guarantee."""

    def __init__(self) -> None:
        self.lock = asyncio.Lock()
        self.day = datetime.now(UTC).date()
        self.attempts = 0

    def reserve(self) -> bool:
        today = datetime.now(UTC).date()
        if today != self.day:
            self.day, self.attempts = today, 0
        if self.attempts >= 20:
            return False
        self.attempts += 1
        return True


async def build_live_draft(
    request: TripRequest,
    provider: LivePlacesProvider,
    *,
    travel_times: TravelTimes | None = None,
) -> LiveDraft:
    cities = await provider.cities(request.destination)
    if len(cities) != 1:
        return LiveDraft(
            status="ambiguous_destination",
            destination_choices=tuple(c.name for c in cities),
            notice="Enter a specific city, province/state and country, then try again.",
        )
    city = cities[0]
    window = None
    if travel_times is not None:
        try:
            window = resolve_travel_window(
                request.start_date,
                request.end_date,
                travel_times.arrival_time,
                travel_times.departure_time,
                city.timezone,
                travel_times.transfer_buffer_minutes,
            )
        except InvalidTravelWindow as error:
            return LiveDraft(status="invalid_window", city=city, notice=str(error))
    # Up to three category calls, interleaved for variety rather than letting
    # the first interest consume the entire eight-place candidate allowance.
    categories = tuple(dict.fromkeys(CATEGORIES[i.value] for i in request.interests))[
        :3
    ]
    groups = [await provider.places(city, category) for category in categories]
    selected: dict[str, Place] = {}
    for rank in range(20):
        for group in groups:
            if rank < len(group) and len(selected) < 8:
                place = group[rank]
                selected.setdefault(place.place_id, place)
    places = tuple(selected.values())
    if not places:
        return LiveDraft(
            status="no_places",
            city=city,
            notice=(
                "No named places found within 5 km of the city centre "
                "for these interests."
            ),
        )
    matrix = await provider.matrix(places)
    stops = schedule_draft(
        request.start_date,
        request.end_date,
        request.earliest_activity_time,
        city.timezone,
        {"relaxed": 2, "balanced": 3, "packed": 4}[request.pace.value],
        tuple(
            tuple(None if cell is None else cell.time for cell in row)
            for row in matrix.sources_to_targets
        ),
        window=window,
    )
    if not stops:
        return LiveDraft(
            status="no_places",
            city=city,
            travel_window=TravelWindowResponse.from_domain(window) if window else None,
            notice=(
                "No 60-minute visits fit the daytime activity window after travel "
                "buffers and your earliest start. Adjust the times or dates."
            ),
        )
    return LiveDraft(
        status="draft",
        city=city,
        retrieved_at=datetime.now(UTC),
        travel_window=TravelWindowResponse.from_domain(window) if window else None,
        stops=tuple(
            LiveStop(
                place=places[s.place_index],
                day=s.day,
                start=s.start,
                end=s.end,
                walking_minutes_from_previous=s.walk_minutes,
            )
            for s in stops
        ),
        notice=(
            "Live places and estimated walking routes; this is an incomplete draft, "
            "not a validated all-in trip. Visits are estimated at 60 minutes, with "
            "30-minute breaks. The 09:00–18:00 daytime envelope is constrained by "
            "your earliest start and any entered arrival/departure transfer buffers. "
            "Without travel times it assumes you are already in the city. "
            "Up to eight unique places and the first three "
            "interest categories are considered; some days may be sparse or empty. "
            "No claim of affordability, opening hours, accessibility or availability. "
            "Nothing has been booked. Verify before purchase."
        ),
        missing=(
            ("Provider-confirmed transport schedules and transfer durations",)
            if window
            else ("Arrival and departure times and fares",)
        )
        + (
            "Provider-confirmed accommodation availability and prices",
            "Provider-confirmed activity and meal prices, fees and taxes",
            "Date-specific opening hours",
        ),
    )
