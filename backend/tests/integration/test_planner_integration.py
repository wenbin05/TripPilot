from __future__ import annotations

import socket
from datetime import UTC, date, datetime, time
from heapq import heappop, heappush
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from trippilot.domain import (
    Interest,
    ItemKind,
    Money,
    Pace,
    PricingBasis,
    TripRequest,
)
from trippilot.providers import (
    FixtureSnapshot,
    JsonMockTravelDataProvider,
    TransferEstimateRecord,
)
from trippilot.services import PlanningSuccess, plan_trip

REPOSITORY_ROOT = Path(__file__).parents[3]
FIXTURE_PATH = REPOSITORY_ROOT / "data/mock/kingston-toronto-v1.json"


def request(end_date: date, *, travellers: int = 1) -> TripRequest:
    return TripRequest(
        origin="Kingston, Ontario",
        destination="Toronto, Ontario",
        start_date=date(2026, 8, 10),
        end_date=end_date,
        travellers=travellers,
        budget=Money(250_000, "CAD"),
        interests=(Interest.ARTS_CULTURE, Interest.NATURE, Interest.STUDENT_BUDGET),
        pace=Pace.BALANCED,
        earliest_activity_time=time(9),
        destination_timezone="America/Toronto",
    )


@pytest.mark.parametrize(
    ("end_date", "expected_nights"),
    [
        (date(2026, 8, 10), 0),
        (date(2026, 8, 11), 1),
        (date(2026, 8, 13), 3),
    ],
)
def test_representative_trip_lengths_are_complete_and_valid(
    end_date: date, expected_nights: int
) -> None:
    provider = JsonMockTravelDataProvider(FIXTURE_PATH)
    result = plan_trip(request(end_date), provider)

    assert isinstance(result, PlanningSuccess)
    assert result.validation_report.is_valid
    assert (
        sum(stay.number_of_nights for stay in result.itinerary.accommodation_stays)
        == expected_nights
    )
    assert (
        sum(item.kind is ItemKind.MEAL for item in result.itinerary.scheduled_items)
        == expected_nights + 1
    )


def test_success_has_no_overlap_and_respects_arrival_departure_boundaries() -> None:
    provider = JsonMockTravelDataProvider(FIXTURE_PATH)
    result = plan_trip(request(date(2026, 8, 11)), provider)

    assert isinstance(result, PlanningSuccess)
    items = result.itinerary.scheduled_items
    chronological = sorted(items, key=lambda item: item.window.start.astimezone(UTC))
    assert all(
        first.window.end.astimezone(UTC) <= second.window.start.astimezone(UTC)
        for first, second in zip(chronological, chronological[1:], strict=False)
    )
    inbound = next(item for item in items if item.transport_role == "inbound")
    outbound = next(item for item in items if item.transport_role == "outbound")
    non_boundary = [item for item in items if item.transport_role is None]
    assert all(item.window.start >= inbound.window.end for item in non_boundary)
    assert all(item.window.end <= outbound.window.start for item in non_boundary)


def test_accommodation_occupancy_can_overlap_scheduled_activity() -> None:
    provider = JsonMockTravelDataProvider(FIXTURE_PATH)
    result = plan_trip(request(date(2026, 8, 11)), provider)

    assert isinstance(result, PlanningSuccess)
    stay = result.itinerary.accommodation_stays[0]
    assert any(
        item.kind is ItemKind.ACTIVITY
        and item.window.start < stay.check_out
        and stay.check_in < item.window.end
        for item in result.itinerary.scheduled_items
    )
    assert result.validation_report.is_valid


def test_every_activity_and_meal_is_inside_provider_operating_hours() -> None:
    provider = JsonMockTravelDataProvider(FIXTURE_PATH)
    result = plan_trip(request(date(2026, 8, 13)), provider)

    assert isinstance(result, PlanningSuccess)
    zone = ZoneInfo("America/Toronto")
    selected = [
        item
        for item in result.itinerary.scheduled_items
        if item.kind in {ItemKind.ACTIVITY, ItemKind.MEAL}
    ]
    for item in selected:
        local_day = item.window.start.astimezone(zone).date()
        windows = provider.get_operating_windows(item.source_record_id or "")
        assert any(
            local_day.weekday() in window.weekdays
            and datetime.combine(local_day, window.local_start_time, zone)
            <= item.window.start
            and item.window.end
            <= datetime.combine(local_day, window.local_end_time, zone)
            for window in windows
        )


def test_every_location_change_reserves_shortest_provider_transfer_gap() -> None:
    provider = JsonMockTravelDataProvider(FIXTURE_PATH)
    snapshot = FixtureSnapshot.model_validate_json(FIXTURE_PATH.read_text("utf-8"))
    graph: dict[str, list[tuple[str, int]]] = {}
    for record in snapshot.records:
        if isinstance(record, TransferEstimateRecord):
            graph.setdefault(record.from_location_id, []).append(
                (record.to_location_id, record.duration_minutes)
            )

    def shortest(start: str, end: str) -> int | None:
        if start == end:
            return 0
        queue = [(0, start)]
        best = {start: 0}
        while queue:
            minutes, location = heappop(queue)
            if location == end:
                return minutes
            if minutes != best[location]:
                continue
            for next_location, duration in graph.get(location, []):
                candidate = minutes + duration
                if candidate < best.get(next_location, candidate + 1):
                    best[next_location] = candidate
                    heappush(queue, (candidate, next_location))
        return None

    result = plan_trip(request(date(2026, 8, 13)), provider)

    assert isinstance(result, PlanningSuccess)
    items = sorted(
        result.itinerary.scheduled_items,
        key=lambda item: item.window.start.astimezone(UTC),
    )
    for first, second in zip(items, items[1:], strict=False):
        assert first.location_id is not None
        assert second.location_id is not None
        required = shortest(first.location_id, second.location_id)
        assert required is not None
        gap_minutes = int(
            (
                second.window.start.astimezone(UTC) - first.window.end.astimezone(UTC)
            ).total_seconds()
            // 60
        )
        assert gap_minutes >= required


def test_attached_fees_are_complete_and_use_traveller_pricing() -> None:
    provider = JsonMockTravelDataProvider(FIXTURE_PATH)
    trip = request(date(2026, 8, 10), travellers=2)
    trip = TripRequest(
        origin=trip.origin,
        destination=trip.destination,
        start_date=trip.start_date,
        end_date=trip.end_date,
        travellers=trip.travellers,
        budget=trip.budget,
        interests=trip.interests,
        pace=Pace.PACKED,
        earliest_activity_time=trip.earliest_activity_time,
        destination_timezone=trip.destination_timezone,
    )
    result = plan_trip(trip, provider)

    assert isinstance(result, PlanningSuccess)
    selected_ids = [
        item.source_record_id for item in result.itinerary.scheduled_items
    ] + [stay.source_record_id for stay in result.itinerary.accommodation_stays]
    expected = 0
    for record_id in selected_ids:
        for fee in provider.list_fees(record_id or ""):
            multiplier = (
                trip.travellers if fee.price.basis is PricingBasis.PER_PERSON else 1
            )
            expected += fee.price.amount_minor * multiplier
    assert (
        sum(fee.cost.amount_minor for fee in result.itinerary.explicit_fees) == expected
    )
    assert result.itinerary.category_totals.fees_taxes.amount_minor == expected


def test_planning_uses_no_network_or_secrets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def reject_network(*args: object, **kwargs: object) -> None:
        raise AssertionError("network access is forbidden")

    monkeypatch.setattr(socket, "socket", reject_network)
    provider = JsonMockTravelDataProvider(FIXTURE_PATH)

    result = plan_trip(request(date(2026, 8, 10)), provider)

    assert isinstance(result, PlanningSuccess)
    assert result.disclosures
