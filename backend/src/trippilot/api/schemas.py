"""Strict public HTTP request and response schemas."""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Annotated, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    StringConstraints,
    field_validator,
    model_validator,
)

from trippilot.domain import (
    Interest,
    ItemKind,
    Money,
    Pace,
    PricingBasis,
    Severity,
    TransportRole,
    TripRequest,
    ViolationCode,
)
from trippilot.services import PlanningFailureCode

PublicLabel = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
]
CurrencyCode = Literal["CAD", "USD"]


class ApiSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class TripPlanRequest(ApiSchema):
    origin: PublicLabel
    destination: PublicLabel
    start_date: date
    end_date: date
    travellers: StrictInt = Field(ge=1, le=10)
    total_budget_minor: StrictInt = Field(gt=0)
    currency: CurrencyCode
    interests: tuple[Interest, ...] = Field(min_length=1, max_length=8)
    pace: Pace
    earliest_activity_time: time

    @field_validator("earliest_activity_time")
    @classmethod
    def require_local_wall_clock(cls, value: time) -> time:
        if value.tzinfo is not None:
            raise ValueError("earliest activity time must be a local wall-clock time")
        return value

    @model_validator(mode="after")
    def validate_request_shape(self) -> Self:
        if self.origin.casefold() == self.destination.casefold():
            raise ValueError("origin and destination must differ")
        trip_days = (self.end_date - self.start_date).days + 1
        if not 1 <= trip_days <= 4:
            raise ValueError("inclusive trip length must be between one and four days")
        return self

    def to_domain(self, destination_timezone: str) -> TripRequest:
        return TripRequest(
            origin=self.origin,
            destination=self.destination,
            start_date=self.start_date,
            end_date=self.end_date,
            travellers=self.travellers,
            budget=Money(self.total_budget_minor, self.currency),
            interests=self.interests,
            pace=self.pace,
            earliest_activity_time=self.earliest_activity_time,
            destination_timezone=destination_timezone,
        )


class MoneyResponse(ApiSchema):
    amount_minor: int = Field(ge=0)
    currency: CurrencyCode


class TimeWindowResponse(ApiSchema):
    start: datetime
    end: datetime


class PricingResponse(ApiSchema):
    basis: PricingBasis
    unit_price: MoneyResponse
    charged_travellers: int | None = None


class ScheduledItemResponse(ApiSchema):
    item_id: str
    title: str
    kind: ItemKind
    window: TimeWindowResponse
    location_id: str | None
    location_label: PublicLabel | None
    estimated_cost: MoneyResponse
    source_record_id: str | None
    pricing: PricingResponse
    transport_role: TransportRole | None


class AccommodationStayResponse(ApiSchema):
    stay_id: str
    title: str
    check_in: datetime
    check_out: datetime
    number_of_nights: int
    location_id: str | None
    location_label: PublicLabel | None
    estimated_cost: MoneyResponse
    source_record_id: str | None
    pricing: PricingResponse


class ExplicitFeeResponse(ApiSchema):
    fee_id: str
    title: str
    cost: MoneyResponse


class NonBlockingMarkerResponse(ApiSchema):
    marker_id: str
    title: str
    window: TimeWindowResponse


class ProposedItineraryResponse(ApiSchema):
    scheduled_items: tuple[ScheduledItemResponse, ...]
    accommodation_stays: tuple[AccommodationStayResponse, ...]
    explicit_fees: tuple[ExplicitFeeResponse, ...]
    non_blocking_markers: tuple[NonBlockingMarkerResponse, ...]


class CostBreakdownResponse(ApiSchema):
    transport: MoneyResponse
    accommodation: MoneyResponse
    activity: MoneyResponse
    meal: MoneyResponse
    fees_taxes: MoneyResponse
    total_estimated_cost: MoneyResponse


class ViolationResponse(ApiSchema):
    code: ViolationCode
    message: str
    affected_ids: tuple[str, ...]
    severity: Severity


class ValidationReportResponse(ApiSchema):
    is_valid: bool
    violations: tuple[ViolationResponse, ...]


class NormalizedRequestResponse(ApiSchema):
    origin: str
    destination: str
    start_date: date
    end_date: date
    travellers: int
    budget: MoneyResponse
    interests: tuple[Interest, ...]
    pace: Pace
    earliest_activity_time: time
    destination_timezone: str | None


class PlanningSuccessResponse(ApiSchema):
    status: Literal["success"]
    request: NormalizedRequestResponse
    proposed_itinerary: ProposedItineraryResponse
    cost_breakdown: CostBreakdownResponse
    validation_report: ValidationReportResponse
    matched_interests: tuple[Interest, ...]
    planning_rationale: tuple[str, ...] = Field(min_length=1)
    assumptions: tuple[str, ...]
    warnings: tuple[str, ...]
    fixture_snapshot_version: str
    planner_id: str
    disclosures: tuple[str, ...] = Field(min_length=2)


class PlanningFailureResponse(ApiSchema):
    status: Literal["planning_failure"]
    request: NormalizedRequestResponse
    failure_code: PlanningFailureCode
    explanation: str
    relevant_constraints: tuple[str, ...]
    validation_report: ValidationReportResponse
    assumptions: tuple[str, ...]
    warnings: tuple[str, ...]
    fixture_snapshot_version: str | None
    planner_id: str
    disclosures: tuple[str, ...] = Field(min_length=2)


PlanResponse = Annotated[
    PlanningSuccessResponse | PlanningFailureResponse, Field(discriminator="status")
]


class HealthResponse(ApiSchema):
    status: Literal["healthy"]
    service: Literal["trippilot-api"]


class RequestErrorDetail(ApiSchema):
    location: tuple[str | int, ...]
    message: str


class RequestErrorResponse(ApiSchema):
    status: Literal["error"]
    error_code: Literal["REQUEST_VALIDATION_ERROR"]
    explanation: str
    details: tuple[RequestErrorDetail, ...]


class InternalErrorResponse(ApiSchema):
    status: Literal["error"]
    error_code: Literal["INTERNAL_ERROR"]
    explanation: str
