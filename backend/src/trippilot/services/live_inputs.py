"""Strict optional user-input contracts, never represented as provider quotes."""

import re
from datetime import time
from typing import Annotated, Literal

from pydantic import AwareDatetime, Field, field_validator

from trippilot.domain.live_constraints import MAX_ESTIMATE_MINOR, TravelWindow
from trippilot.providers.geoapify import StrictRecord

MinorUnits = Annotated[int, Field(ge=0, le=MAX_ESTIMATE_MINOR)]


class TravelTimes(StrictRecord):
    arrival_time: time
    departure_time: time
    transfer_buffer_minutes: int = Field(default=60, ge=0, le=240)

    @field_validator("arrival_time", "departure_time", mode="before")
    @classmethod
    def local_clock(cls, value: object) -> time:
        if isinstance(value, str) and re.fullmatch(r"\d{2}:\d{2}(?::\d{2})?", value):
            value = time.fromisoformat(value)
        if not isinstance(value, time) or value.tzinfo is not None:
            raise ValueError("Use local wall-clock times without offsets")
        return value


class EnteredCosts(StrictRecord):
    transport: MinorUnits | None = None
    accommodation: MinorUnits | None = None
    activities: MinorUnits | None = None
    meals: MinorUnits | None = None
    fees_taxes: MinorUnits | None = None

    def values_in_order(self) -> tuple[int | None, ...]:
        return (
            self.transport,
            self.accommodation,
            self.activities,
            self.meals,
            self.fees_taxes,
        )


class BudgetEstimate(StrictRecord):
    basis: Literal["user_entered_all_travellers_whole_trip"] = (
        "user_entered_all_travellers_whole_trip"
    )
    currency: Literal["CAD", "USD"]
    budget_minor: MinorUnits
    categories: EnteredCosts
    status: Literal["incomplete", "within_entered_estimate", "over_entered_estimate"]
    known_subtotal_minor: int = Field(ge=0)
    estimated_total_minor: int | None = Field(ge=0)
    remaining_minor: int | None
    missing_categories: tuple[str, ...]


class TravelWindowResponse(StrictRecord):
    basis: Literal["user_entered"] = "user_entered"
    arrival: AwareDatetime
    departure: AwareDatetime
    available_from: AwareDatetime
    available_until: AwareDatetime
    transfer_buffer_minutes: int

    @classmethod
    def from_domain(cls, window: TravelWindow) -> TravelWindowResponse:
        return cls(
            arrival=window.arrival,
            departure=window.departure,
            available_from=window.available_from,
            available_until=window.available_until,
            transfer_buffer_minutes=window.buffer_minutes,
        )
