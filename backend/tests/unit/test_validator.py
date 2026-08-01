from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo

import pytest

from trippilot.domain import (
    AccommodationStay,
    CostBreakdown,
    ExplicitFee,
    Interest,
    ItemKind,
    Itinerary,
    Money,
    NonBlockingMarker,
    OperatingWindow,
    Pace,
    Pricing,
    PricingBasis,
    ProviderSnapshot,
    ScheduledItem,
    TimeWindow,
    TransferRequirement,
    TransportRole,
    TripRequest,
    validate_itinerary,
)

ZONE = ZoneInfo("America/Toronto")


def dt(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 8, day, hour, minute, tzinfo=ZONE)


def money(amount: int, currency: str = "CAD") -> Money:
    return Money(amount, currency)


def group_price(amount: int, currency: str = "CAD") -> Pricing:
    return Pricing(PricingBasis.PER_GROUP, money(amount, currency))


def item(
    item_id: str,
    kind: ItemKind,
    start: datetime,
    end: datetime,
    cost: int,
    record_id: str,
    location_id: str,
    *,
    transport_role: TransportRole | None = None,
    pricing: Pricing | None = None,
    currency: str = "CAD",
) -> ScheduledItem:
    return ScheduledItem(
        item_id=item_id,
        title=item_id,
        kind=kind,
        window=TimeWindow(start, end),
        location_id=location_id,
        estimated_cost=money(cost, currency),
        source_record_id=record_id,
        pricing=pricing or group_price(cost, currency),
        transport_role=transport_role,
    )


def request(**changes: object) -> TripRequest:
    value = TripRequest(
        origin="Toronto",
        destination="Montreal",
        start_date=date(2026, 8, 10),
        end_date=date(2026, 8, 11),
        travellers=2,
        budget=money(100_000),
        interests=(Interest.ARTS_CULTURE, Interest.FOOD),
        pace=Pace.BALANCED,
        earliest_activity_time=time(9),
        destination_timezone="America/Toronto",
    )
    return replace(value, **changes)


def empty_itinerary(currency: str = "CAD") -> Itinerary:
    zero = money(0, currency)
    return Itinerary((), (), (), CostBreakdown(zero, zero, zero, zero, zero), zero)


def representative() -> tuple[TripRequest, Itinerary, ProviderSnapshot]:
    inbound = item(
        "inbound",
        ItemKind.TRANSPORT,
        dt(10, 8),
        dt(10, 10),
        20_000,
        "transport-in",
        "station",
        transport_role=TransportRole.INBOUND,
        pricing=Pricing(PricingBasis.PER_PERSON, money(10_000), 2),
    )
    museum = item(
        "museum",
        ItemKind.ACTIVITY,
        dt(10, 10, 30),
        dt(10, 12),
        4_000,
        "activity-museum",
        "museum",
        pricing=Pricing(PricingBasis.PER_PERSON, money(2_000), 2),
    )
    lunch = item(
        "lunch",
        ItemKind.MEAL,
        dt(10, 12, 30),
        dt(10, 13, 30),
        6_000,
        "meal-lunch",
        "restaurant",
        pricing=Pricing(PricingBasis.PER_PERSON, money(3_000), 2),
    )
    evening = item(
        "evening",
        ItemKind.ACTIVITY,
        dt(10, 18),
        dt(10, 20),
        0,
        "activity-evening",
        "venue",
    )
    outbound = item(
        "outbound",
        ItemKind.TRANSPORT,
        dt(11, 18),
        dt(11, 20),
        20_000,
        "transport-out",
        "station",
        transport_role=TransportRole.OUTBOUND,
        pricing=Pricing(PricingBasis.PER_PERSON, money(10_000), 2),
    )
    stay = AccommodationStay(
        stay_id="hotel",
        title="Mock hotel",
        check_in=dt(10, 15),
        check_out=dt(11, 11),
        number_of_nights=1,
        location_id="hotel",
        estimated_cost=money(25_000),
        source_record_id="hotel-1",
        pricing=group_price(25_000),
    )
    fee = ExplicitFee("tax", "Explicit tax", money(1_000))
    itinerary = Itinerary(
        scheduled_items=(inbound, museum, lunch, evening, outbound),
        accommodation_stays=(stay,),
        explicit_fees=(fee,),
        category_totals=CostBreakdown(
            transport=money(40_000),
            accommodation=money(25_000),
            activity=money(4_000),
            meal=money(6_000),
            fees_taxes=money(1_000),
        ),
        total_estimated_cost=money(76_000),
    )
    snapshot = ProviderSnapshot(
        record_ids=frozenset(
            {
                "transport-in",
                "activity-museum",
                "meal-lunch",
                "activity-evening",
                "transport-out",
                "hotel-1",
            }
        ),
        operating_windows=(
            OperatingWindow("activity-museum", TimeWindow(dt(10, 10), dt(10, 17))),
            OperatingWindow("activity-evening", TimeWindow(dt(10, 17), dt(10, 22))),
        ),
        transfer_requirements=(
            TransferRequirement("station", "museum", 30),
            TransferRequirement("museum", "restaurant", 30),
            TransferRequirement("restaurant", "venue", 30),
            TransferRequirement("venue", "station", 30),
        ),
    )
    return request(), itinerary, snapshot


def codes(report: object) -> list[str]:
    return [violation.code for violation in report.violations]


def test_fully_valid_representative_itinerary() -> None:
    trip_request, itinerary, snapshot = representative()

    report = validate_itinerary(trip_request, itinerary, snapshot)

    assert report.is_valid
    assert report.violations == ()


@pytest.mark.parametrize(
    ("start", "end"),
    [
        (date(2026, 8, 10), date(2026, 8, 10)),
        (date(2026, 8, 10), date(2026, 8, 13)),
    ],
)
def test_one_and_four_day_trip_boundaries_are_valid(start: date, end: date) -> None:
    report = validate_itinerary(
        request(start_date=start, end_date=end), empty_itinerary()
    )

    assert "TRIP_LENGTH_OUT_OF_RANGE" not in codes(report)


def test_five_day_trip_is_rejected() -> None:
    report = validate_itinerary(request(end_date=date(2026, 8, 14)), empty_itinerary())

    assert "TRIP_LENGTH_OUT_OF_RANGE" in codes(report)


def test_missing_boundary_transport_is_rejected() -> None:
    report = validate_itinerary(request(), empty_itinerary())

    violation = next(
        entry
        for entry in report.violations
        if entry.code == "MISSING_BOUNDARY_TRANSPORT"
    )
    assert violation.affected_ids == ("inbound", "outbound")


def test_adjacent_half_open_intervals_do_not_overlap() -> None:
    first = item("a", ItemKind.MEAL, dt(10, 10), dt(10, 11), 0, "a", "same")
    second = item("b", ItemKind.MEAL, dt(10, 11), dt(10, 12), 0, "b", "same")
    itinerary = replace(empty_itinerary(), scheduled_items=(first, second))

    assert "ITEM_OVERLAP" not in codes(validate_itinerary(request(), itinerary))


def test_genuinely_overlapping_items_are_reported() -> None:
    first = item("a", ItemKind.MEAL, dt(10, 10), dt(10, 11), 0, "a", "same")
    second = item("b", ItemKind.MEAL, dt(10, 10, 59), dt(10, 12), 0, "b", "same")
    itinerary = replace(empty_itinerary(), scheduled_items=(first, second))

    assert "ITEM_OVERLAP" in codes(validate_itinerary(request(), itinerary))


def test_accommodation_can_overlap_evening_activity() -> None:
    trip_request, itinerary, snapshot = representative()

    report = validate_itinerary(trip_request, itinerary, snapshot)

    assert "ITEM_OVERLAP" not in codes(report)


def test_zero_duration_non_blocking_marker_is_valid_and_does_not_overlap() -> None:
    trip_request, itinerary, snapshot = representative()
    marker = NonBlockingMarker(
        "checkpoint",
        "Informational checkpoint",
        TimeWindow(dt(10, 11), dt(10, 11)),
    )
    itinerary = replace(itinerary, non_blocking_markers=(marker,))

    report = validate_itinerary(trip_request, itinerary, snapshot)

    assert report.is_valid


def test_earliest_start_equality_is_valid() -> None:
    activity = item(
        "activity", ItemKind.ACTIVITY, dt(10, 9), dt(10, 10), 0, "a", "venue"
    )
    itinerary = replace(empty_itinerary(), scheduled_items=(activity,))

    assert "ACTIVITY_TOO_EARLY" not in codes(validate_itinerary(request(), itinerary))


def test_activity_before_earliest_start_is_invalid() -> None:
    activity = item(
        "activity", ItemKind.ACTIVITY, dt(10, 8, 59), dt(10, 10), 0, "a", "venue"
    )
    itinerary = replace(empty_itinerary(), scheduled_items=(activity,))

    assert "ACTIVITY_TOO_EARLY" in codes(validate_itinerary(request(), itinerary))


def test_exact_budget_equality_is_valid() -> None:
    trip_request, itinerary, snapshot = representative()
    trip_request = replace(trip_request, budget=money(76_000))

    assert validate_itinerary(trip_request, itinerary, snapshot).is_valid


def test_over_budget_total_is_invalid() -> None:
    trip_request, itinerary, snapshot = representative()
    trip_request = replace(trip_request, budget=money(75_999))

    assert "BUDGET_EXCEEDED" in codes(
        validate_itinerary(trip_request, itinerary, snapshot)
    )


def test_total_arithmetic_mismatch_is_invalid() -> None:
    trip_request, itinerary, snapshot = representative()
    itinerary = replace(itinerary, total_estimated_cost=money(76_001))

    report = validate_itinerary(trip_request, itinerary, snapshot)

    assert codes(report).count("TOTAL_MISMATCH") == 1


def test_currency_mismatch_is_invalid() -> None:
    trip_request, itinerary, snapshot = representative()
    bad_fee = replace(itinerary.explicit_fees[0], cost=money(1_000, "USD"))
    itinerary = replace(itinerary, explicit_fees=(bad_fee,))

    assert "CURRENCY_MISMATCH" in codes(
        validate_itinerary(trip_request, itinerary, snapshot)
    )


@pytest.mark.parametrize("kind", list(ItemKind))
def test_zero_duration_scheduled_item_is_rejected(kind: ItemKind) -> None:
    scheduled_item = item(
        "zero-duration", kind, dt(10, 10), dt(10, 10), 0, "record", "venue"
    )
    itinerary = replace(empty_itinerary(), scheduled_items=(scheduled_item,))

    assert "INVALID_TIME_WINDOW" in codes(validate_itinerary(request(), itinerary))


def test_naive_datetime_is_rejected() -> None:
    activity = item(
        "activity",
        ItemKind.ACTIVITY,
        datetime(2026, 8, 10, 10),
        datetime(2026, 8, 10, 11),
        0,
        "a",
        "venue",
    )
    itinerary = replace(empty_itinerary(), scheduled_items=(activity,))

    assert "INVALID_TIME_WINDOW" in codes(validate_itinerary(request(), itinerary))


def test_dst_fold_uses_absolute_time_for_positive_duration() -> None:
    new_york = ZoneInfo("America/New_York")
    start = datetime(2026, 11, 1, 1, 30, tzinfo=new_york, fold=0)
    end = datetime(2026, 11, 1, 1, 15, tzinfo=new_york, fold=1)
    activity = item(
        "dst-activity",
        ItemKind.ACTIVITY,
        start,
        end,
        0,
        "dst-record",
        "venue",
    )
    itinerary = replace(empty_itinerary(), scheduled_items=(activity,))
    trip_request = request(
        start_date=date(2026, 11, 1),
        end_date=date(2026, 11, 1),
        earliest_activity_time=time(1),
        destination_timezone="America/New_York",
    )

    assert "INVALID_TIME_WINDOW" not in codes(
        validate_itinerary(trip_request, itinerary)
    )


def test_dst_fold_adjacent_absolute_intervals_do_not_overlap() -> None:
    new_york = ZoneInfo("America/New_York")
    first = item(
        "first",
        ItemKind.MEAL,
        datetime(2026, 11, 1, 1, 30, tzinfo=new_york, fold=0),
        datetime(2026, 11, 1, 1, 15, tzinfo=new_york, fold=1),
        0,
        "first",
        "same",
    )
    second = item(
        "second",
        ItemKind.MEAL,
        datetime(2026, 11, 1, 1, 15, tzinfo=new_york, fold=1),
        datetime(2026, 11, 1, 1, 45, tzinfo=new_york, fold=1),
        0,
        "second",
        "same",
    )
    itinerary = replace(empty_itinerary(), scheduled_items=(first, second))
    trip_request = request(
        start_date=date(2026, 11, 1),
        end_date=date(2026, 11, 1),
        destination_timezone="America/New_York",
    )

    assert "ITEM_OVERLAP" not in codes(validate_itinerary(trip_request, itinerary))


def test_item_outside_trip_dates_is_invalid() -> None:
    meal = item("meal", ItemKind.MEAL, dt(12, 10), dt(12, 11), 0, "m", "cafe")
    itinerary = replace(empty_itinerary(), scheduled_items=(meal,))

    assert "ITEM_OUTSIDE_TRIP" in codes(validate_itinerary(request(), itinerary))


def test_trip_envelope_uses_destination_timezone_for_other_offset_timestamps() -> None:
    meal = item(
        "midnight-meal",
        ItemKind.MEAL,
        datetime(2026, 8, 10, 4, tzinfo=UTC),
        datetime(2026, 8, 10, 5, tzinfo=UTC),
        0,
        "meal",
        "cafe",
    )
    itinerary = replace(empty_itinerary(), scheduled_items=(meal,))

    assert "ITEM_OUTSIDE_TRIP" not in codes(
        validate_itinerary(request(end_date=date(2026, 8, 10)), itinerary)
    )


def test_insufficient_transfer_time_is_invalid() -> None:
    first = item("a", ItemKind.MEAL, dt(10, 10), dt(10, 11), 0, "a", "west")
    second = item("b", ItemKind.MEAL, dt(10, 11, 15), dt(10, 12), 0, "b", "east")
    itinerary = replace(empty_itinerary(), scheduled_items=(first, second))
    snapshot = ProviderSnapshot(
        frozenset({"a", "b"}),
        transfer_requirements=(TransferRequirement("west", "east", 30),),
    )

    assert "INSUFFICIENT_TRANSFER_TIME" in codes(
        validate_itinerary(request(), itinerary, snapshot)
    )


def test_transfer_check_uses_consecutive_located_items() -> None:
    first = item("a", ItemKind.MEAL, dt(10, 10), dt(10, 11), 0, "a", "west")
    unlocated = item(
        "note-like-item",
        ItemKind.MEAL,
        dt(10, 11),
        dt(10, 11, 15),
        0,
        "middle",
        "temporary",
    )
    unlocated = replace(unlocated, location_id=None)
    second = item("b", ItemKind.MEAL, dt(10, 11, 15), dt(10, 12), 0, "b", "east")
    itinerary = replace(empty_itinerary(), scheduled_items=(first, unlocated, second))
    snapshot = ProviderSnapshot(
        frozenset({"a", "middle", "b"}),
        transfer_requirements=(TransferRequirement("west", "east", 30),),
    )

    assert "INSUFFICIENT_TRANSFER_TIME" in codes(
        validate_itinerary(request(), itinerary, snapshot)
    )


def test_activity_outside_operating_hours_is_invalid() -> None:
    activity = item(
        "activity", ItemKind.ACTIVITY, dt(10, 18), dt(10, 19), 0, "a", "venue"
    )
    itinerary = replace(empty_itinerary(), scheduled_items=(activity,))
    snapshot = ProviderSnapshot(
        frozenset({"a"}),
        operating_windows=(OperatingWindow("a", TimeWindow(dt(10, 9), dt(10, 17))),),
    )

    assert "OUTSIDE_OPERATING_WINDOW" in codes(
        validate_itinerary(request(), itinerary, snapshot)
    )


@pytest.mark.parametrize(
    ("start", "end"),
    [(dt(10, 9, 59), dt(10, 11)), (dt(11, 17), dt(11, 18, 1))],
)
def test_arrival_or_departure_conflict_is_invalid(
    start: datetime, end: datetime
) -> None:
    inbound = item(
        "inbound",
        ItemKind.TRANSPORT,
        dt(10, 8),
        dt(10, 10),
        0,
        "in",
        "station",
        transport_role=TransportRole.INBOUND,
    )
    activity = item("activity", ItemKind.ACTIVITY, start, end, 0, "a", "venue")
    outbound = item(
        "outbound",
        ItemKind.TRANSPORT,
        dt(11, 18),
        dt(11, 20),
        0,
        "out",
        "station",
        transport_role=TransportRole.OUTBOUND,
    )
    itinerary = replace(
        empty_itinerary(), scheduled_items=(inbound, activity, outbound)
    )

    assert "ARRIVAL_DEPARTURE_CONFLICT" in codes(
        validate_itinerary(request(), itinerary)
    )


@pytest.mark.parametrize(
    ("check_in", "check_out"),
    [(dt(10, 15), dt(10, 14)), (dt(9, 15), dt(10, 11))],
)
def test_invalid_accommodation_stay(check_in: datetime, check_out: datetime) -> None:
    stay = AccommodationStay(
        "bad-stay",
        "Bad stay",
        check_in,
        check_out,
        1,
        "hotel",
        money(0),
        "hotel",
        group_price(0),
    )
    itinerary = replace(empty_itinerary(), accommodation_stays=(stay,))

    assert "INVALID_ACCOMMODATION_STAY" in codes(
        validate_itinerary(request(), itinerary)
    )


def test_accommodation_nights_use_destination_local_dates() -> None:
    stay = AccommodationStay(
        "bad-nights",
        "Bad nights",
        dt(10, 15),
        dt(11, 11),
        2,
        "hotel",
        money(0),
        "hotel",
        group_price(0),
    )
    itinerary = replace(empty_itinerary(), accommodation_stays=(stay,))

    assert "INVALID_ACCOMMODATION_STAY" in codes(
        validate_itinerary(request(), itinerary)
    )


@pytest.mark.parametrize(
    ("changes", "expected_code"),
    [
        ({"origin": ""}, "ORIGIN_REQUIRED"),
        ({"destination": ""}, "DESTINATION_REQUIRED"),
        ({"destination": "Toronto"}, "ORIGIN_DESTINATION_SAME"),
        ({"travellers": 0}, "INVALID_TRAVELLER_COUNT"),
        ({"travellers": True}, "INVALID_TRAVELLER_COUNT"),
        ({"budget": money(0)}, "INVALID_BUDGET"),
        ({"budget": money(100, "EUR")}, "UNSUPPORTED_CURRENCY"),
        ({"interests": ()}, "INTEREST_REQUIRED"),
    ],
)
def test_request_rules(changes: dict[str, object], expected_code: str) -> None:
    assert expected_code in codes(
        validate_itinerary(request(**changes), empty_itinerary())
    )


@pytest.mark.parametrize("travellers", [1, 10])
def test_traveller_count_boundaries_are_valid(travellers: int) -> None:
    assert "INVALID_TRAVELLER_COUNT" not in codes(
        validate_itinerary(request(travellers=travellers), empty_itinerary())
    )


def test_traveller_dependent_pricing_must_reconcile() -> None:
    meal = item(
        "meal",
        ItemKind.MEAL,
        dt(10, 10),
        dt(10, 11),
        6_000,
        "meal",
        "cafe",
        pricing=Pricing(PricingBasis.PER_PERSON, money(3_000), 1),
    )
    itinerary = Itinerary(
        (meal,),
        (),
        (),
        CostBreakdown(money(0), money(0), money(0), money(6_000), money(0)),
        money(6_000),
    )

    assert "PRICING_INCONSISTENT" in codes(validate_itinerary(request(), itinerary))


def test_boolean_charged_traveller_count_is_not_valid_pricing() -> None:
    meal = item(
        "meal",
        ItemKind.MEAL,
        dt(10, 10),
        dt(10, 11),
        3_000,
        "meal",
        "cafe",
        pricing=Pricing(PricingBasis.PER_PERSON, money(3_000), True),
    )
    itinerary = Itinerary(
        (meal,),
        (),
        (),
        CostBreakdown(money(0), money(0), money(0), money(3_000), money(0)),
        money(3_000),
    )

    assert "PRICING_INCONSISTENT" in codes(
        validate_itinerary(request(travellers=1), itinerary)
    )


def test_missing_provider_record_is_invalid() -> None:
    meal = item("meal", ItemKind.MEAL, dt(10, 10), dt(10, 11), 0, "missing", "cafe")
    itinerary = replace(empty_itinerary(), scheduled_items=(meal,))

    assert "RECORD_NOT_FOUND" in codes(
        validate_itinerary(request(), itinerary, ProviderSnapshot(frozenset()))
    )


def test_stable_violation_ordering() -> None:
    activity = item(
        "activity",
        ItemKind.ACTIVITY,
        dt(12, 8),
        dt(12, 8),
        0,
        "missing",
        "venue",
    )
    itinerary = replace(
        empty_itinerary("USD"),
        scheduled_items=(activity,),
        total_estimated_cost=money(1, "USD"),
    )
    trip_request = request(
        destination="Toronto",
        end_date=date(2026, 8, 14),
        travellers=11,
        budget=money(0, "EUR"),
        interests=(),
    )

    report = validate_itinerary(trip_request, itinerary, ProviderSnapshot(frozenset()))

    assert codes(report) == [
        "ORIGIN_DESTINATION_SAME",
        "TRIP_LENGTH_OUT_OF_RANGE",
        "INVALID_TRAVELLER_COUNT",
        "INVALID_BUDGET",
        "UNSUPPORTED_CURRENCY",
        "INTEREST_REQUIRED",
        "MISSING_BOUNDARY_TRANSPORT",
        "RECORD_NOT_FOUND",
        "INVALID_TIME_WINDOW",
        "CURRENCY_MISMATCH",
        "CURRENCY_MISMATCH",
        "CURRENCY_MISMATCH",
        "CURRENCY_MISMATCH",
        "CURRENCY_MISMATCH",
        "CURRENCY_MISMATCH",
        "CURRENCY_MISMATCH",
        "CURRENCY_MISMATCH",
        "TOTAL_MISMATCH",
    ]


def test_repeated_validation_is_identical() -> None:
    trip_request, itinerary, snapshot = representative()
    broken = replace(
        itinerary,
        scheduled_items=(
            *itinerary.scheduled_items,
            item(
                "overlap",
                ItemKind.ACTIVITY,
                dt(10, 11),
                dt(10, 13),
                0,
                "activity-overlap",
                "other",
            ),
        ),
    )
    snapshot = replace(
        snapshot,
        record_ids=snapshot.record_ids | {"activity-overlap"},
        operating_windows=(
            *snapshot.operating_windows,
            OperatingWindow("activity-overlap", TimeWindow(dt(10, 9), dt(10, 17))),
        ),
    )

    assert validate_itinerary(trip_request, broken, snapshot) == validate_itinerary(
        trip_request, broken, snapshot
    )


@pytest.mark.parametrize("amount", [-1, 1.5, True])
def test_money_rejects_negative_or_non_integer_minor_units(amount: object) -> None:
    expected_error = ValueError if amount == -1 else TypeError

    with pytest.raises(expected_error):
        Money(amount, "CAD")  # type: ignore[arg-type]
