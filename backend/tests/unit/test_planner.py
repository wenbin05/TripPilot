from __future__ import annotations

from datetime import date, time
from pathlib import Path

import pytest

from trippilot.domain import (
    Interest,
    ItemKind,
    Money,
    Pace,
    TripRequest,
    ViolationCode,
)
from trippilot.providers import JsonMockTravelDataProvider
from trippilot.services import (
    PLANNER_ID,
    PlanningFailure,
    PlanningFailureCode,
    PlanningSuccess,
    plan_trip,
)

REPOSITORY_ROOT = Path(__file__).parents[3]
FIXTURE_PATH = REPOSITORY_ROOT / "data/mock/kingston-toronto-v1.json"


@pytest.fixture(scope="module")
def provider() -> JsonMockTravelDataProvider:
    return JsonMockTravelDataProvider(FIXTURE_PATH)


def request(
    *,
    end_date: date = date(2026, 8, 10),
    travellers: int = 1,
    budget: int = 100_000,
    interests: tuple[Interest, ...] = (Interest.ARTS_CULTURE, Interest.NATURE),
    pace: Pace = Pace.BALANCED,
    earliest: time = time(9),
    origin: str = "Kingston, Ontario",
    destination: str = "Toronto, Ontario",
) -> TripRequest:
    return TripRequest(
        origin=origin,
        destination=destination,
        start_date=date(2026, 8, 10),
        end_date=end_date,
        travellers=travellers,
        budget=Money(budget, "CAD"),
        interests=interests,
        pace=pace,
        earliest_activity_time=earliest,
        destination_timezone="America/Toronto",
    )


def success(result: object) -> PlanningSuccess:
    assert isinstance(result, PlanningSuccess)
    assert result.validation_report.is_valid
    return result


class ProviderOverride:
    def __init__(
        self, provider: JsonMockTravelDataProvider, **overrides: object
    ) -> None:
        self._provider = provider
        self.__dict__.update(overrides)

    def __getattr__(self, name: str) -> object:
        return getattr(self._provider, name)


def test_result_is_stable_across_repeated_runs(
    provider: JsonMockTravelDataProvider,
) -> None:
    trip = request()

    assert plan_trip(trip, provider) == plan_trip(trip, provider)


@pytest.mark.parametrize(
    ("pace", "expected_count"),
    [(Pace.RELAXED, 1), (Pace.BALANCED, 2), (Pace.PACKED, 3)],
)
def test_pace_changes_primary_activity_target(
    provider: JsonMockTravelDataProvider, pace: Pace, expected_count: int
) -> None:
    result = success(plan_trip(request(pace=pace), provider))

    assert (
        sum(item.kind is ItemKind.ACTIVITY for item in result.itinerary.scheduled_items)
        == expected_count
    )


def test_interest_match_is_ranked_before_unmatched_options(
    provider: JsonMockTravelDataProvider,
) -> None:
    result = success(
        plan_trip(request(interests=(Interest.NATURE,), pace=Pace.RELAXED), provider)
    )

    activity = next(
        item
        for item in result.itinerary.scheduled_items
        if item.kind is ItemKind.ACTIVITY
    )
    assert activity.source_record_id == "activity-island-walk"
    assert result.matched_interests == (Interest.NATURE,)


def test_per_person_pricing_is_normalized(
    provider: JsonMockTravelDataProvider,
) -> None:
    one = success(plan_trip(request(end_date=date(2026, 8, 11)), provider))
    two = success(
        plan_trip(request(end_date=date(2026, 8, 11), travellers=2), provider)
    )

    one_stay = one.itinerary.accommodation_stays[0]
    two_stay = two.itinerary.accommodation_stays[0]
    assert one_stay.source_record_id == "stay-harbour-hostel"
    assert one_stay.estimated_cost.amount_minor == 5_400
    assert two_stay.source_record_id == "stay-harbour-hostel"
    assert two_stay.estimated_cost.amount_minor == 10_800
    assert (
        two.itinerary.category_totals.transport.amount_minor
        == 2 * one.itinerary.category_totals.transport.amount_minor
    )


def test_per_group_per_stay_pricing_is_charged_once(
    provider: JsonMockTravelDataProvider,
) -> None:
    base_transfer = provider.get_transfer_estimate(
        "loc-toronto-terminal", "loc-civic-gallery"
    )
    assert base_transfer is not None
    synthetic = {
        ("loc-toronto-terminal", "loc-campus-lodge"): base_transfer.model_copy(
            update={
                "record_id": "transfer-terminal-lodge",
                "from_location_id": "loc-toronto-terminal",
                "to_location_id": "loc-campus-lodge",
                "duration_minutes": 10,
            }
        ),
        ("loc-campus-lodge", "loc-market-kitchen"): base_transfer.model_copy(
            update={
                "record_id": "transfer-lodge-market",
                "from_location_id": "loc-campus-lodge",
                "to_location_id": "loc-market-kitchen",
                "duration_minutes": 10,
            }
        ),
        ("loc-island-park", "loc-campus-lodge"): base_transfer.model_copy(
            update={
                "record_id": "transfer-island-lodge",
                "from_location_id": "loc-island-park",
                "to_location_id": "loc-campus-lodge",
                "duration_minutes": 10,
            }
        ),
        ("loc-campus-lodge", "loc-toronto-terminal"): base_transfer.model_copy(
            update={
                "record_id": "transfer-lodge-terminal",
                "from_location_id": "loc-campus-lodge",
                "to_location_id": "loc-toronto-terminal",
                "duration_minutes": 10,
            }
        ),
    }
    original_transfer = provider.get_transfer_estimate

    def transfer(start: str, end: str) -> object:
        return synthetic.get((start, end), original_transfer(start, end))

    result = success(
        plan_trip(
            request(end_date=date(2026, 8, 11), travellers=3),
            ProviderOverride(provider, get_transfer_estimate=transfer),
        )
    )

    stay = result.itinerary.accommodation_stays[0]
    assert stay.source_record_id == "stay-campus-lodge"
    assert stay.estimated_cost.amount_minor == 11_800
    assert stay.pricing.charged_travellers is None


def test_cost_categories_reconcile_exactly(
    provider: JsonMockTravelDataProvider,
) -> None:
    itinerary = success(plan_trip(request(), provider)).itinerary

    assert (
        sum(value.amount_minor for value in itinerary.category_totals.values())
        == itinerary.total_estimated_cost.amount_minor
    )
    assert itinerary.category_totals.transport.amount_minor == 6_400
    assert itinerary.category_totals.meal.amount_minor > 0


def test_exact_budget_equality_is_valid(
    provider: JsonMockTravelDataProvider,
) -> None:
    first = success(plan_trip(request(), provider))
    exact = first.itinerary.total_estimated_cost.amount_minor

    result = success(plan_trip(request(budget=exact), provider))

    assert result.itinerary.total_estimated_cost.amount_minor == exact


@pytest.mark.parametrize(
    ("budget_minor", "display"),
    [(1, "CAD 0.01"), (100, "CAD 1.00"), (123, "CAD 1.23")],
)
def test_impossible_budget_is_structured_failure(
    provider: JsonMockTravelDataProvider,
    budget_minor: int,
    display: str,
) -> None:
    result = plan_trip(request(budget=budget_minor), provider)

    assert isinstance(result, PlanningFailure)
    assert result.code is PlanningFailureCode.INSUFFICIENT_BUDGET
    assert result.relevant_constraints == (f"All-in budget: {display}",)
    assert result.fixture_snapshot_version == "2026-08-01.v1"
    assert result.planner_id == PLANNER_ID
    assert any(
        violation.code is ViolationCode.BUDGET_EXCEEDED
        for violation in result.validation_report.violations
    )


def test_budget_fallback_tries_cheaper_activity_before_failing(
    provider: JsonMockTravelDataProvider,
) -> None:
    result = success(
        plan_trip(
            request(
                budget=8_500,
                interests=(Interest.ARTS_CULTURE,),
                pace=Pace.RELAXED,
            ),
            provider,
        )
    )

    activity = next(
        item
        for item in result.itinerary.scheduled_items
        if item.kind is ItemKind.ACTIVITY
    )
    assert activity.source_record_id == "activity-island-walk"
    assert result.itinerary.total_estimated_cost.amount_minor <= 8_500


def test_late_earliest_start_is_respected(
    provider: JsonMockTravelDataProvider,
) -> None:
    result = success(
        plan_trip(
            request(
                earliest=time(16),
                interests=(Interest.NATURE,),
                pace=Pace.RELAXED,
            ),
            provider,
        )
    )

    activities = [
        item
        for item in result.itinerary.scheduled_items
        if item.kind is ItemKind.ACTIVITY
    ]
    assert activities
    assert all(item.window.start.time() >= time(16) for item in activities)


def test_unfittable_high_ranked_activity_uses_alternative(
    provider: JsonMockTravelDataProvider,
) -> None:
    result = success(
        plan_trip(
            request(
                earliest=time(16),
                interests=(Interest.ARTS_CULTURE, Interest.NATURE),
                pace=Pace.RELAXED,
            ),
            provider,
        )
    )

    activity_ids = {
        item.source_record_id
        for item in result.itinerary.scheduled_items
        if item.kind is ItemKind.ACTIVITY
    }
    assert activity_ids == {"activity-island-walk"}


def test_operating_hours_exclude_unavailable_top_choice(
    provider: JsonMockTravelDataProvider,
) -> None:
    original = provider.get_operating_windows

    def windows(record_id: str) -> tuple[object, ...]:
        if record_id == "activity-history":
            return ()
        return original(record_id)

    result = success(
        plan_trip(
            request(interests=(Interest.ARTS_CULTURE,), pace=Pace.RELAXED),
            ProviderOverride(provider, get_operating_windows=windows),
        )
    )

    activity = next(
        item
        for item in result.itinerary.scheduled_items
        if item.kind is ItemKind.ACTIVITY
    )
    assert activity.source_record_id == "activity-gallery"


def test_stable_provider_id_breaks_equal_candidate_tie(
    provider: JsonMockTravelDataProvider,
) -> None:
    gallery = provider.get_record("activity-gallery")
    assert gallery is not None
    first = gallery.model_copy(
        update={"record_id": "activity-aaa", "title": "First equal option"}
    )
    second = gallery.model_copy(
        update={"record_id": "activity-zzz", "title": "Second equal option"}
    )
    lunch = provider.get_record("meal-market-lunch")
    assert lunch is not None
    local_meal = lunch.model_copy(
        update={
            "record_id": "meal-gallery",
            "location_id": gallery.location_id,
            "title": "Gallery meal estimate",
        }
    )
    original_get = provider.get_record
    gallery_windows = provider.get_operating_windows("activity-gallery")

    def get_record(record_id: str) -> object:
        return {
            first.record_id: first,
            second.record_id: second,
            local_meal.record_id: local_meal,
        }.get(record_id, original_get(record_id))

    equal_provider = ProviderOverride(
        provider,
        list_activities=lambda destination_id: (second, first),
        list_meal_options=lambda destination_id: (local_meal,),
        get_record=get_record,
        get_operating_windows=lambda record_id: (
            gallery_windows
            if record_id in {first.record_id, second.record_id, local_meal.record_id}
            else provider.get_operating_windows(record_id)
        ),
        list_fees=lambda record_id: (),
    )
    result = success(
        plan_trip(
            request(interests=(Interest.ARTS_CULTURE,), pace=Pace.RELAXED),
            equal_provider,
        )
    )

    activity = next(
        item
        for item in result.itinerary.scheduled_items
        if item.kind is ItemKind.ACTIVITY
    )
    assert activity.source_record_id == "activity-aaa"


def test_missing_transport_is_structured_failure(
    provider: JsonMockTravelDataProvider,
) -> None:
    result = plan_trip(
        request(), ProviderOverride(provider, list_transport_options=lambda *args: ())
    )

    assert isinstance(result, PlanningFailure)
    assert result.code is PlanningFailureCode.NO_TRANSPORT_OPTION


def test_missing_accommodation_is_structured_failure(
    provider: JsonMockTravelDataProvider,
) -> None:
    result = plan_trip(
        request(end_date=date(2026, 8, 11)),
        ProviderOverride(
            provider, list_accommodation_options=lambda destination_id: ()
        ),
    )

    assert isinstance(result, PlanningFailure)
    assert result.code is PlanningFailureCode.NO_ACCOMMODATION_OPTION


def test_missing_transfer_estimates_cannot_create_a_plan(
    provider: JsonMockTravelDataProvider,
) -> None:
    result = plan_trip(
        request(),
        ProviderOverride(provider, get_transfer_estimate=lambda start, end: None),
    )

    assert isinstance(result, PlanningFailure)
    assert result.code is PlanningFailureCode.NO_FEASIBLE_ACTIVITY_SET
    assert "transfer estimates" in result.relevant_constraints


def test_provider_exception_becomes_incomplete_data_failure(
    provider: JsonMockTravelDataProvider,
) -> None:
    def broken(destination_id: str) -> tuple[object, ...]:
        raise RuntimeError("broken fixture adapter")

    result = plan_trip(request(), ProviderOverride(provider, list_activities=broken))

    assert isinstance(result, PlanningFailure)
    assert result.code is PlanningFailureCode.PROVIDER_DATA_INCOMPLETE
    assert "broken fixture adapter" not in result.explanation


def test_unsupported_destination_is_structured_failure(
    provider: JsonMockTravelDataProvider,
) -> None:
    result = plan_trip(request(destination="Ottawa, Ontario"), provider)

    assert isinstance(result, PlanningFailure)
    assert result.code is PlanningFailureCode.UNSUPPORTED_ROUTE
