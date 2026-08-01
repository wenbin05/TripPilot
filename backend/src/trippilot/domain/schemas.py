"""Strict Pydantic boundary schemas for Milestone 1 domain inputs."""

from __future__ import annotations

from datetime import UTC, date, datetime, time
from typing import Annotated, Literal, Self
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from .models import (
    AccommodationStay,
    CostBreakdown,
    ExplicitFee,
    Interest,
    ItemKind,
    Itinerary,
    Money,
    NonBlockingMarker,
    Pace,
    Pricing,
    PricingBasis,
    ScheduledItem,
    TimeWindow,
    TransportRole,
    TripRequest,
)

NonEmptyString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
CurrencyCode = Literal["CAD", "USD"]


class StrictSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class MoneySchema(StrictSchema):
    amount_minor: int = Field(ge=0)
    currency: CurrencyCode

    def to_domain(self) -> Money:
        return Money(self.amount_minor, self.currency)


class TimeWindowSchema(StrictSchema):
    start: datetime
    end: datetime

    @field_validator("start", "end")
    @classmethod
    def require_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamp must be timezone-aware")
        return value

    @model_validator(mode="after")
    def require_positive_duration(self) -> Self:
        if self.end.astimezone(UTC) <= self.start.astimezone(UTC):
            raise ValueError("time window must have positive duration")
        return self

    def to_domain(self) -> TimeWindow:
        return TimeWindow(self.start, self.end)


class PricingSchema(StrictSchema):
    basis: PricingBasis
    unit_price: MoneySchema
    charged_travellers: int | None = Field(default=None, ge=1, le=10)

    def to_domain(self) -> Pricing:
        return Pricing(self.basis, self.unit_price.to_domain(), self.charged_travellers)


class TripRequestSchema(StrictSchema):
    origin: NonEmptyString
    destination: NonEmptyString
    start_date: date
    end_date: date
    travellers: int = Field(ge=1, le=10)
    budget: MoneySchema
    interests: tuple[Interest, ...] = Field(min_length=1)
    pace: Pace
    earliest_activity_time: time
    destination_timezone: NonEmptyString

    @field_validator("earliest_activity_time")
    @classmethod
    def require_local_wall_clock(cls, value: time) -> time:
        if value.tzinfo is not None:
            raise ValueError("earliest activity time must be a local wall-clock time")
        return value

    @field_validator("destination_timezone")
    @classmethod
    def require_iana_timezone(cls, value: str) -> str:
        try:
            return ZoneInfo(value).key
        except (ZoneInfoNotFoundError, ValueError) as error:
            raise ValueError("destination timezone must be an IANA name") from error

    @model_validator(mode="after")
    def validate_request_constraints(self) -> Self:
        if self.origin.casefold() == self.destination.casefold():
            raise ValueError("origin and destination must differ")
        trip_days = (self.end_date - self.start_date).days + 1
        if not 1 <= trip_days <= 4:
            raise ValueError("inclusive trip length must be between one and four days")
        if self.budget.amount_minor <= 0:
            raise ValueError("budget must be positive")
        return self

    def to_domain(self) -> TripRequest:
        return TripRequest(
            origin=self.origin,
            destination=self.destination,
            start_date=self.start_date,
            end_date=self.end_date,
            travellers=self.travellers,
            budget=self.budget.to_domain(),
            interests=self.interests,
            pace=self.pace,
            earliest_activity_time=self.earliest_activity_time,
            destination_timezone=self.destination_timezone,
        )


class ScheduledItemSchema(StrictSchema):
    item_id: NonEmptyString
    title: NonEmptyString
    kind: ItemKind
    window: TimeWindowSchema
    location_id: NonEmptyString | None
    estimated_cost: MoneySchema
    source_record_id: NonEmptyString | None
    pricing: PricingSchema
    transport_role: TransportRole | None = None

    def to_domain(self) -> ScheduledItem:
        return ScheduledItem(
            item_id=self.item_id,
            title=self.title,
            kind=self.kind,
            window=self.window.to_domain(),
            location_id=self.location_id,
            estimated_cost=self.estimated_cost.to_domain(),
            source_record_id=self.source_record_id,
            pricing=self.pricing.to_domain(),
            transport_role=self.transport_role,
        )


class AccommodationStaySchema(StrictSchema):
    stay_id: NonEmptyString
    title: NonEmptyString
    check_in: datetime
    check_out: datetime
    number_of_nights: int = Field(ge=1, le=4)
    location_id: NonEmptyString | None
    estimated_cost: MoneySchema
    source_record_id: NonEmptyString | None
    pricing: PricingSchema

    @field_validator("check_in", "check_out")
    @classmethod
    def require_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamp must be timezone-aware")
        return value

    @model_validator(mode="after")
    def require_ordered_stay(self) -> Self:
        if self.check_out.astimezone(UTC) <= self.check_in.astimezone(UTC):
            raise ValueError("check-out must be after check-in")
        return self

    def to_domain(self) -> AccommodationStay:
        return AccommodationStay(
            stay_id=self.stay_id,
            title=self.title,
            check_in=self.check_in,
            check_out=self.check_out,
            number_of_nights=self.number_of_nights,
            location_id=self.location_id,
            estimated_cost=self.estimated_cost.to_domain(),
            source_record_id=self.source_record_id,
            pricing=self.pricing.to_domain(),
        )


class ExplicitFeeSchema(StrictSchema):
    fee_id: NonEmptyString
    title: NonEmptyString
    cost: MoneySchema

    def to_domain(self) -> ExplicitFee:
        return ExplicitFee(self.fee_id, self.title, self.cost.to_domain())


class CostBreakdownSchema(StrictSchema):
    transport: MoneySchema
    accommodation: MoneySchema
    activity: MoneySchema
    meal: MoneySchema
    fees_taxes: MoneySchema

    def to_domain(self) -> CostBreakdown:
        return CostBreakdown(
            transport=self.transport.to_domain(),
            accommodation=self.accommodation.to_domain(),
            activity=self.activity.to_domain(),
            meal=self.meal.to_domain(),
            fees_taxes=self.fees_taxes.to_domain(),
        )


class NonBlockingMarkerSchema(StrictSchema):
    marker_id: NonEmptyString
    title: NonEmptyString
    start: datetime
    end: datetime

    @field_validator("start", "end")
    @classmethod
    def require_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamp must be timezone-aware")
        return value

    @model_validator(mode="after")
    def reject_negative_duration(self) -> Self:
        if self.end.astimezone(UTC) < self.start.astimezone(UTC):
            raise ValueError("marker duration cannot be negative")
        return self

    def to_domain(self) -> NonBlockingMarker:
        return NonBlockingMarker(
            marker_id=self.marker_id,
            title=self.title,
            window=TimeWindow(self.start, self.end),
        )


class ItinerarySchema(StrictSchema):
    scheduled_items: tuple[ScheduledItemSchema, ...]
    accommodation_stays: tuple[AccommodationStaySchema, ...]
    explicit_fees: tuple[ExplicitFeeSchema, ...]
    category_totals: CostBreakdownSchema
    total_estimated_cost: MoneySchema
    non_blocking_markers: tuple[NonBlockingMarkerSchema, ...] = ()

    def to_domain(self) -> Itinerary:
        return Itinerary(
            scheduled_items=tuple(item.to_domain() for item in self.scheduled_items),
            accommodation_stays=tuple(
                stay.to_domain() for stay in self.accommodation_stays
            ),
            explicit_fees=tuple(fee.to_domain() for fee in self.explicit_fees),
            category_totals=self.category_totals.to_domain(),
            total_estimated_cost=self.total_estimated_cost.to_domain(),
            non_blocking_markers=tuple(
                marker.to_domain() for marker in self.non_blocking_markers
            ),
        )
