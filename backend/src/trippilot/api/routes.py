"""HTTP routes and translation for deterministic trip planning."""

from __future__ import annotations

from typing import Annotated, cast

from fastapi import APIRouter, Depends

from trippilot.domain import Money, Pricing, TripRequest, ValidationReport
from trippilot.providers import LocationRecord, TravelDataProvider
from trippilot.services import PlanningFailure, PlanningFailureCode, PlanningSuccess

from .dependencies import Planner, get_planner, get_provider
from .schemas import (
    AccommodationStayResponse,
    CostBreakdownResponse,
    CurrencyCode,
    ExplicitFeeResponse,
    HealthResponse,
    InternalErrorResponse,
    MoneyResponse,
    NonBlockingMarkerResponse,
    NormalizedRequestResponse,
    PlanningFailureResponse,
    PlanningSuccessResponse,
    PlanResponse,
    PricingResponse,
    ProposedItineraryResponse,
    RequestErrorResponse,
    ScheduledItemResponse,
    TimeWindowResponse,
    TripPlanRequest,
    ValidationReportResponse,
    ViolationResponse,
)

router = APIRouter()
ProviderDependency = Annotated[TravelDataProvider, Depends(get_provider)]
PlannerDependency = Annotated[Planner, Depends(get_planner)]

PLANNING_RATIONALE = (
    "The bounded deterministic planner selected a validator-clean proposal using "
    "mock provider records, requested interests, estimated cost, transfer time, "
    "and stable record identifiers.",
)


def _money(value: Money) -> MoneyResponse:
    return MoneyResponse(
        amount_minor=value.amount_minor,
        currency=cast(CurrencyCode, value.currency),
    )


def _pricing(value: Pricing) -> PricingResponse:
    return PricingResponse(
        basis=value.basis,
        unit_price=_money(value.unit_price),
        charged_travellers=value.charged_travellers,
    )


def _request(
    value: TripRequest, destination_timezone: str | None
) -> NormalizedRequestResponse:
    return NormalizedRequestResponse(
        origin=value.origin,
        destination=value.destination,
        start_date=value.start_date,
        end_date=value.end_date,
        travellers=value.travellers,
        budget=_money(value.budget),
        interests=value.interests,
        pace=value.pace,
        earliest_activity_time=value.earliest_activity_time,
        destination_timezone=destination_timezone,
    )


def _report(value: ValidationReport) -> ValidationReportResponse:
    return ValidationReportResponse(
        is_valid=value.is_valid,
        violations=tuple(
            ViolationResponse(
                code=violation.code,
                message=violation.message,
                affected_ids=violation.affected_ids,
                severity=violation.severity,
            )
            for violation in value.violations
        ),
    )


def _disclosures(values: tuple[str, ...]) -> tuple[str, ...]:
    combined = " ".join(values).casefold()
    if "mock" not in combined or "nothing has been booked" not in combined:
        raise RuntimeError("planner result omitted required public disclosures")
    return values


def _location_label(
    provider: TravelDataProvider, location_id: str | None
) -> str | None:
    if location_id is None:
        return None
    record = provider.get_record(location_id)
    if not isinstance(record, LocationRecord):
        raise RuntimeError("itinerary referenced a non-canonical location")
    return record.name


def _success(
    request: TripRequest,
    result: PlanningSuccess,
    provider: TravelDataProvider,
) -> PlanningSuccessResponse:
    if not result.validation_report.is_valid:
        raise RuntimeError("planner returned an invalid result as successful")
    itinerary = result.itinerary
    return PlanningSuccessResponse(
        status="success",
        request=_request(request, request.destination_timezone),
        proposed_itinerary=ProposedItineraryResponse(
            scheduled_items=tuple(
                ScheduledItemResponse(
                    item_id=item.item_id,
                    title=item.title,
                    kind=item.kind,
                    window=TimeWindowResponse(
                        start=item.window.start, end=item.window.end
                    ),
                    location_id=item.location_id,
                    location_label=_location_label(provider, item.location_id),
                    estimated_cost=_money(item.estimated_cost),
                    source_record_id=item.source_record_id,
                    pricing=_pricing(item.pricing),
                    transport_role=item.transport_role,
                )
                for item in itinerary.scheduled_items
            ),
            accommodation_stays=tuple(
                AccommodationStayResponse(
                    stay_id=stay.stay_id,
                    title=stay.title,
                    check_in=stay.check_in,
                    check_out=stay.check_out,
                    number_of_nights=stay.number_of_nights,
                    location_id=stay.location_id,
                    location_label=_location_label(provider, stay.location_id),
                    estimated_cost=_money(stay.estimated_cost),
                    source_record_id=stay.source_record_id,
                    pricing=_pricing(stay.pricing),
                )
                for stay in itinerary.accommodation_stays
            ),
            explicit_fees=tuple(
                ExplicitFeeResponse(
                    fee_id=fee.fee_id,
                    title=fee.title,
                    cost=_money(fee.cost),
                )
                for fee in itinerary.explicit_fees
            ),
            non_blocking_markers=tuple(
                NonBlockingMarkerResponse(
                    marker_id=marker.marker_id,
                    title=marker.title,
                    window=TimeWindowResponse(
                        start=marker.window.start, end=marker.window.end
                    ),
                )
                for marker in itinerary.non_blocking_markers
            ),
        ),
        cost_breakdown=CostBreakdownResponse(
            transport=_money(itinerary.category_totals.transport),
            accommodation=_money(itinerary.category_totals.accommodation),
            activity=_money(itinerary.category_totals.activity),
            meal=_money(itinerary.category_totals.meal),
            fees_taxes=_money(itinerary.category_totals.fees_taxes),
            total_estimated_cost=_money(itinerary.total_estimated_cost),
        ),
        validation_report=_report(result.validation_report),
        matched_interests=result.matched_interests,
        planning_rationale=PLANNING_RATIONALE,
        assumptions=result.assumptions,
        warnings=(),
        fixture_snapshot_version=result.fixture_snapshot_version,
        planner_id=result.planner_id,
        disclosures=_disclosures(result.disclosures),
    )


def _failure(request: TripRequest, result: PlanningFailure) -> PlanningFailureResponse:
    explanation = result.explanation
    if result.code is PlanningFailureCode.PROVIDER_DATA_INCOMPLETE:
        explanation = "The mock provider data could not be used safely."
    return PlanningFailureResponse(
        status="planning_failure",
        request=_request(
            request,
            None
            if result.code is PlanningFailureCode.UNSUPPORTED_ROUTE
            or request.destination_timezone == "UTC"
            else request.destination_timezone,
        ),
        failure_code=result.code,
        explanation=explanation,
        relevant_constraints=result.relevant_constraints,
        validation_report=_report(result.validation_report),
        assumptions=result.assumptions,
        warnings=(),
        fixture_snapshot_version=result.fixture_snapshot_version,
        planner_id=result.planner_id,
        disclosures=_disclosures(result.disclosures),
    )


@router.get("/health", response_model=HealthResponse, tags=["health"])
def health() -> HealthResponse:
    return HealthResponse(status="healthy", service="trippilot-api")


@router.post(
    "/api/v1/itineraries/plan",
    response_model=PlanResponse,
    tags=["itineraries"],
    summary="Create a proposed itinerary from the offline mock snapshot",
    responses={
        422: {"model": RequestErrorResponse},
        500: {"model": InternalErrorResponse},
    },
)
def plan_itinerary(
    body: TripPlanRequest,
    provider: ProviderDependency,
    planner: PlannerDependency,
) -> PlanResponse:
    try:
        destination = provider.get_destination(body.destination)
    except Exception:  # Let the planner translate provider-boundary failures.
        destination = None
    destination_timezone = destination.timezone if destination is not None else "UTC"
    request = body.to_domain(destination_timezone)
    result = planner(request, provider)
    if isinstance(result, PlanningSuccess):
        return _success(request, result, provider)
    return _failure(request, result)
