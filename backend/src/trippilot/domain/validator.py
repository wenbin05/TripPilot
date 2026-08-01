"""Pure deterministic validation for normalized TripPilot domain objects."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .models import (
    Currency,
    Interest,
    ItemKind,
    Itinerary,
    Money,
    NonBlockingMarker,
    OperatingWindow,
    Pricing,
    PricingBasis,
    ProviderSnapshot,
    ScheduledItem,
    TransferRequirement,
    TransportRole,
    TripRequest,
    ValidationReport,
    Violation,
    ViolationCode,
)


def _violation(code: str, message: str, *affected_ids: str) -> Violation:
    return Violation(
        code=ViolationCode(code), message=message, affected_ids=tuple(affected_ids)
    )


def _is_aware(value: datetime) -> bool:
    return value.tzinfo is not None and value.utcoffset() is not None


def _instant(value: datetime) -> datetime:
    return value.astimezone(UTC)


def _sorted_items(items: Iterable[ScheduledItem]) -> list[ScheduledItem]:
    return sorted(items, key=lambda item: (item.item_id, item.title))


def _valid_window(item: ScheduledItem) -> bool:
    return (
        _is_aware(item.window.start)
        and _is_aware(item.window.end)
        and _instant(item.window.end) > _instant(item.window.start)
    )


def _valid_marker(marker: NonBlockingMarker) -> bool:
    return (
        _is_aware(marker.window.start)
        and _is_aware(marker.window.end)
        and _instant(marker.window.end) >= _instant(marker.window.start)
    )


def _money_values(
    request: TripRequest, itinerary: Itinerary
) -> list[tuple[str, Money]]:
    values = [("budget", request.budget), ("total", itinerary.total_estimated_cost)]
    values.extend(
        (f"category:{name}", value)
        for name, value in zip(
            ("transport", "accommodation", "activity", "meal", "fees_taxes"),
            itinerary.category_totals.values(),
            strict=True,
        )
    )
    values.extend(
        (item.item_id, item.estimated_cost) for item in itinerary.scheduled_items
    )
    values.extend(
        (stay.stay_id, stay.estimated_cost) for stay in itinerary.accommodation_stays
    )
    values.extend((fee.fee_id, fee.cost) for fee in itinerary.explicit_fees)
    values.extend(
        (f"pricing:{item.item_id}", item.pricing.unit_price)
        for item in itinerary.scheduled_items
    )
    values.extend(
        (f"pricing:{stay.stay_id}", stay.pricing.unit_price)
        for stay in itinerary.accommodation_stays
    )
    return values


def _pricing_is_consistent(pricing: Pricing, cost: Money, travellers: int) -> bool:
    if pricing.basis not in {PricingBasis.PER_PERSON, PricingBasis.PER_GROUP}:
        return False
    if pricing.charged_travellers is not None and (
        isinstance(pricing.charged_travellers, bool)
        or not isinstance(pricing.charged_travellers, int)
        or pricing.charged_travellers <= 0
    ):
        return False
    if pricing.basis is PricingBasis.PER_PERSON:
        return (
            pricing.charged_travellers == travellers
            and pricing.unit_price.amount_minor * travellers == cost.amount_minor
        )
    return pricing.charged_travellers in (None, 1) and (
        pricing.unit_price.amount_minor == cost.amount_minor
    )


def _inside_any_operating_window(
    item: ScheduledItem, windows: tuple[OperatingWindow, ...]
) -> bool:
    matching = (
        entry.window for entry in windows if entry.record_id == item.source_record_id
    )
    return any(
        _is_aware(window.start)
        and _is_aware(window.end)
        and _instant(window.start) <= _instant(item.window.start)
        and _instant(item.window.end) <= _instant(window.end)
        for window in matching
    )


def _required_transfer_minutes(
    first: ScheduledItem,
    second: ScheduledItem,
    requirements: tuple[TransferRequirement, ...],
) -> int | None:
    for requirement in requirements:
        if (
            requirement.from_location_id == first.location_id
            and requirement.to_location_id == second.location_id
        ):
            return requirement.minimum_minutes
    return None


def validate_itinerary(
    request: TripRequest,
    itinerary: Itinerary,
    provider_snapshot: ProviderSnapshot | None = None,
) -> ValidationReport:
    """Return every detected violation in a stable, phase-defined order."""

    violations: list[Violation] = []

    # Phase 1: request structure and provider references.
    if not request.origin.strip():
        violations.append(
            _violation("ORIGIN_REQUIRED", "Origin is required.", "origin")
        )
    if not request.destination.strip():
        violations.append(
            _violation(
                "DESTINATION_REQUIRED", "Destination is required.", "destination"
            )
        )
    if request.origin.strip().casefold() == request.destination.strip().casefold() and (
        request.origin.strip()
    ):
        violations.append(
            _violation(
                "ORIGIN_DESTINATION_SAME",
                "Origin and destination must differ.",
                "origin",
                "destination",
            )
        )

    trip_days = (request.end_date - request.start_date).days + 1
    if not 1 <= trip_days <= 4:
        violations.append(
            _violation(
                "TRIP_LENGTH_OUT_OF_RANGE",
                "Inclusive trip length must be between one and four days.",
                "start_date",
                "end_date",
            )
        )
    if (
        isinstance(request.travellers, bool)
        or not isinstance(request.travellers, int)
        or not 1 <= request.travellers <= 10
    ):
        violations.append(
            _violation(
                "INVALID_TRAVELLER_COUNT",
                "Traveller count must be between 1 and 10.",
                "travellers",
            )
        )
    if request.budget.amount_minor <= 0:
        violations.append(
            _violation("INVALID_BUDGET", "Budget must be positive.", "budget")
        )
    if request.budget.currency not in {currency.value for currency in Currency}:
        violations.append(
            _violation(
                "UNSUPPORTED_CURRENCY",
                "The request currency must be CAD or USD.",
                "budget",
            )
        )
    supported_interests = {interest.value for interest in Interest}
    if not request.interests or not any(
        str(interest) in supported_interests for interest in request.interests
    ):
        violations.append(
            _violation(
                "INTEREST_REQUIRED",
                "At least one supported interest is required.",
                "interests",
            )
        )

    missing_boundary_roles = tuple(
        role.value
        for role in (TransportRole.INBOUND, TransportRole.OUTBOUND)
        if not any(
            item.kind is ItemKind.TRANSPORT and item.transport_role is role
            for item in itinerary.scheduled_items
        )
    )
    if missing_boundary_roles:
        violations.append(
            _violation(
                "MISSING_BOUNDARY_TRANSPORT",
                "Itinerary requires inbound and outbound boundary transport.",
                *missing_boundary_roles,
            )
        )

    destination_zone: ZoneInfo | None
    try:
        destination_zone = ZoneInfo(request.destination_timezone)
    except ZoneInfoNotFoundError, ValueError:
        destination_zone = None
        violations.append(
            _violation(
                "INVALID_TIMEZONE",
                "Destination timezone must be a valid IANA timezone name.",
                "destination_timezone",
            )
        )

    if provider_snapshot is not None:
        referenced = [
            (item.item_id, item.source_record_id) for item in itinerary.scheduled_items
        ] + [
            (stay.stay_id, stay.source_record_id)
            for stay in itinerary.accommodation_stays
        ]
        for item_id, record_id in sorted(referenced, key=lambda value: value[0]):
            if record_id is None or record_id not in provider_snapshot.record_ids:
                violations.append(
                    _violation(
                        "RECORD_NOT_FOUND",
                        "Selected item does not reference a valid provider record.",
                        item_id,
                    )
                )

    # Phase 2: time-window and trip-envelope checks.
    valid_items: list[ScheduledItem] = []
    envelope_start: datetime | None = None
    envelope_end: datetime | None = None
    if destination_zone is not None:
        envelope_start = datetime.combine(
            request.start_date, time.min, destination_zone
        )
        envelope_end = datetime.combine(
            request.end_date + timedelta(days=1), time.min, destination_zone
        )

    for item in _sorted_items(itinerary.scheduled_items):
        if not _valid_window(item):
            violations.append(
                _violation(
                    "INVALID_TIME_WINDOW",
                    "Scheduled items require aware timestamps and positive duration.",
                    item.item_id,
                )
            )
            continue
        valid_items.append(item)
        if (
            envelope_start is not None
            and envelope_end is not None
            and (
                _instant(item.window.start) < _instant(envelope_start)
                or _instant(item.window.end) > _instant(envelope_end)
            )
        ):
            violations.append(
                _violation(
                    "ITEM_OUTSIDE_TRIP",
                    "Scheduled item falls outside the destination-local trip dates.",
                    item.item_id,
                )
            )

    for marker in sorted(
        itinerary.non_blocking_markers, key=lambda value: value.marker_id
    ):
        if not _valid_marker(marker):
            violations.append(
                _violation(
                    "INVALID_TIME_WINDOW",
                    "Non-blocking markers require aware, non-negative time windows.",
                    marker.marker_id,
                )
            )
            continue
        if (
            envelope_start is not None
            and envelope_end is not None
            and (
                _instant(marker.window.start) < _instant(envelope_start)
                or _instant(marker.window.end) > _instant(envelope_end)
            )
        ):
            violations.append(
                _violation(
                    "ITEM_OUTSIDE_TRIP",
                    "Non-blocking marker falls outside the destination-local "
                    "trip dates.",
                    marker.marker_id,
                )
            )

    for stay in sorted(itinerary.accommodation_stays, key=lambda value: value.stay_id):
        valid_stay = (
            _is_aware(stay.check_in)
            and _is_aware(stay.check_out)
            and _instant(stay.check_out) > _instant(stay.check_in)
        )
        if valid_stay and destination_zone is not None:
            expected_nights = (
                stay.check_out.astimezone(destination_zone).date()
                - stay.check_in.astimezone(destination_zone).date()
            ).days
            valid_stay = (
                not isinstance(stay.number_of_nights, bool)
                and isinstance(stay.number_of_nights, int)
                and stay.number_of_nights == expected_nights
                and stay.number_of_nights > 0
            )
        if valid_stay and envelope_start is not None and envelope_end is not None:
            valid_stay = _instant(stay.check_in) >= _instant(
                envelope_start
            ) and _instant(stay.check_out) <= _instant(envelope_end)
        if not valid_stay:
            violations.append(
                _violation(
                    "INVALID_ACCOMMODATION_STAY",
                    "Accommodation dates must be ordered, aware, within the trip, "
                    "and match the destination-local number of nights.",
                    stay.stay_id,
                )
            )

    # Phase 3: scheduled-item chronology and availability.
    chronological = sorted(
        valid_items,
        key=lambda item: (
            _instant(item.window.start),
            _instant(item.window.end),
            item.item_id,
        ),
    )
    for index, first in enumerate(chronological):
        for second in chronological[index + 1 :]:
            if _instant(second.window.start) >= _instant(first.window.end):
                break
            violations.append(
                _violation(
                    "ITEM_OVERLAP",
                    "Time-blocking scheduled items overlap.",
                    first.item_id,
                    second.item_id,
                )
            )

    for item in chronological:
        if item.kind is ItemKind.ACTIVITY:
            local_start = (
                item.window.start.astimezone(destination_zone)
                if destination_zone is not None
                else item.window.start
            )
            if (
                local_start.timetz().replace(tzinfo=None)
                < request.earliest_activity_time
            ):
                violations.append(
                    _violation(
                        "ACTIVITY_TOO_EARLY",
                        "Activity starts before the permitted local time.",
                        item.item_id,
                    )
                )
            has_operating_windows = provider_snapshot is not None and any(
                entry.record_id == item.source_record_id
                for entry in provider_snapshot.operating_windows
            )
            if has_operating_windows and not _inside_any_operating_window(
                item, provider_snapshot.operating_windows
            ):
                violations.append(
                    _violation(
                        "OUTSIDE_OPERATING_WINDOW",
                        "Activity is not contained in a supplied operating window.",
                        item.item_id,
                    )
                )

    located_items = [item for item in chronological if item.location_id is not None]
    for first, second in zip(located_items, located_items[1:], strict=False):
        if first.location_id == second.location_id or provider_snapshot is None:
            continue
        required = _required_transfer_minutes(
            first, second, provider_snapshot.transfer_requirements
        )
        if required is not None:
            available = _instant(second.window.start) - _instant(first.window.end)
            if available < timedelta(minutes=required):
                violations.append(
                    _violation(
                        "INSUFFICIENT_TRANSFER_TIME",
                        "Gap between consecutive locations is shorter than required.",
                        first.item_id,
                        second.item_id,
                    )
                )

    inbound_ends = [
        item.window.end
        for item in chronological
        if item.kind is ItemKind.TRANSPORT
        and item.transport_role is TransportRole.INBOUND
    ]
    outbound_starts = [
        item.window.start
        for item in chronological
        if item.kind is ItemKind.TRANSPORT
        and item.transport_role is TransportRole.OUTBOUND
    ]
    usable_start = max((_instant(value) for value in inbound_ends), default=None)
    usable_end = min((_instant(value) for value in outbound_starts), default=None)
    if (
        usable_start is not None
        and usable_end is not None
        and usable_start > usable_end
    ):
        boundary_ids = tuple(
            item.item_id
            for item in chronological
            if item.kind is ItemKind.TRANSPORT
            and item.transport_role in {TransportRole.INBOUND, TransportRole.OUTBOUND}
        )
        violations.append(
            _violation(
                "ARRIVAL_DEPARTURE_CONFLICT",
                "Arrival completion must not be after departure start.",
                *boundary_ids,
            )
        )
    for item in chronological:
        is_boundary = item.kind is ItemKind.TRANSPORT and item.transport_role in {
            TransportRole.INBOUND,
            TransportRole.OUTBOUND,
        }
        if is_boundary:
            continue
        if (
            usable_start is not None and _instant(item.window.start) < usable_start
        ) or (usable_end is not None and _instant(item.window.end) > usable_end):
            violations.append(
                _violation(
                    "ARRIVAL_DEPARTURE_CONFLICT",
                    "Scheduled item falls outside the arrival/departure usable window.",
                    item.item_id,
                )
            )

    # Phase 4: money currency, sign, and traveller pricing.
    money_values = _money_values(request, itinerary)
    for value_id, money in sorted(money_values, key=lambda value: value[0]):
        if money.amount_minor < 0:
            violations.append(
                _violation("NEGATIVE_COST", "Costs cannot be negative.", value_id)
            )
        if money.currency != request.budget.currency:
            violations.append(
                _violation(
                    "CURRENCY_MISMATCH",
                    "All monetary values must use the request currency.",
                    value_id,
                )
            )

    priced = [
        (item.item_id, item.pricing, item.estimated_cost)
        for item in itinerary.scheduled_items
    ] + [
        (stay.stay_id, stay.pricing, stay.estimated_cost)
        for stay in itinerary.accommodation_stays
    ]
    for item_id, pricing, cost in sorted(priced, key=lambda value: value[0]):
        if not _pricing_is_consistent(pricing, cost, request.travellers):
            violations.append(
                _violation(
                    "PRICING_INCONSISTENT",
                    "Traveller-dependent pricing does not match the declared basis.",
                    item_id,
                )
            )

    # Phase 5: exact arithmetic and all-in budget.
    currency = request.budget.currency
    expected = {
        "transport": sum(
            item.estimated_cost.amount_minor
            for item in itinerary.scheduled_items
            if item.kind is ItemKind.TRANSPORT
        ),
        "accommodation": sum(
            stay.estimated_cost.amount_minor for stay in itinerary.accommodation_stays
        ),
        "activity": sum(
            item.estimated_cost.amount_minor
            for item in itinerary.scheduled_items
            if item.kind is ItemKind.ACTIVITY
        ),
        "meal": sum(
            item.estimated_cost.amount_minor
            for item in itinerary.scheduled_items
            if item.kind is ItemKind.MEAL
        ),
        "fees_taxes": sum(fee.cost.amount_minor for fee in itinerary.explicit_fees),
    }
    reported_values = itinerary.category_totals.values()
    reported = dict(
        zip(
            ("transport", "accommodation", "activity", "meal", "fees_taxes"),
            (value.amount_minor for value in reported_values),
            strict=True,
        )
    )
    itemized_total = sum(expected.values())
    reported_category_total = sum(reported.values())
    if (
        expected != reported
        or itemized_total != itinerary.total_estimated_cost.amount_minor
        or reported_category_total != itinerary.total_estimated_cost.amount_minor
    ):
        violations.append(
            _violation(
                "TOTAL_MISMATCH",
                "Itemized costs, category totals, fees, and all-in total must "
                "agree exactly.",
                "total_estimated_cost",
            )
        )
    if (
        itinerary.total_estimated_cost.currency == currency
        and itinerary.total_estimated_cost.amount_minor > request.budget.amount_minor
    ):
        violations.append(
            _violation(
                "BUDGET_EXCEEDED",
                "All-in estimated total exceeds the request budget.",
                "total_estimated_cost",
            )
        )

    return ValidationReport(violations=tuple(violations))
