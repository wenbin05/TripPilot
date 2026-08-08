from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from trippilot.domain import Interest, ItemKind, Money, Pace, TripRequest
from trippilot.providers import JsonMockTravelDataProvider
from trippilot.services import (
    BoundCoordinatorContext,
    CandidateSet,
    CoordinatorContextBuildFailure,
    CoordinatorContextBuildFailureCode,
    CoordinatorSelectionFact,
    build_coordinator_context,
    derive_selection_facts,
    enumerate_trip_candidates,
)

REPOSITORY_ROOT = Path(__file__).parents[3]
FIXTURE_PATH = REPOSITORY_ROOT / "data/mock/kingston-toronto-v1.json"


def request() -> TripRequest:
    from datetime import date, time

    return TripRequest(
        origin="Kingston, Ontario",
        destination="Toronto, Ontario",
        start_date=date(2026, 8, 10),
        end_date=date(2026, 8, 11),
        travellers=1,
        budget=Money(100_000, "CAD"),
        interests=(Interest.ARTS_CULTURE, Interest.NATURE),
        pace=Pace.BALANCED,
        earliest_activity_time=time(9),
        destination_timezone="America/Toronto",
    )


def candidates(trip: TripRequest, provider: JsonMockTravelDataProvider) -> CandidateSet:
    result = enumerate_trip_candidates(trip, provider)
    assert isinstance(result, CandidateSet)
    assert len(result.candidates) >= 2
    return result


def sequential_ids() -> object:
    values = iter(("candidate_A", "candidate_B", "candidate_C", "candidate_D"))
    return lambda: next(values)


def test_builds_closed_canonical_context_and_request_local_bindings() -> None:
    provider = JsonMockTravelDataProvider(FIXTURE_PATH)
    trip = request()
    candidate_set = candidates(trip, provider)

    result = build_coordinator_context(
        trip,
        candidate_set,
        provider,
        preference_notes="Prefer varied daytime activities",
        candidate_id_factory=sequential_ids(),  # type: ignore[arg-type]
    )

    assert isinstance(result, BoundCoordinatorContext)
    assert result.context.preference_notes == "Prefer varied daytime activities"
    assert len(result.bindings) == len(candidate_set.candidates)
    assert result.resolve("candidate_A") == candidate_set.candidates[0]
    assert result.resolve("unknown") is None
    for summary, binding in zip(
        result.context.candidates, result.bindings, strict=True
    ):
        activities = tuple(
            item
            for item in binding.candidate.itinerary.scheduled_items
            if item.kind is ItemKind.ACTIVITY
        )
        assert summary.candidate_id == binding.candidate_id
        assert summary.primary_activity_count == len(activities)
        assert summary.distinct_primary_activity_count == len(
            {item.source_record_id for item in activities}
        )
        assert (
            summary.total_estimated_cost_minor + summary.remaining_budget_minor
            == trip.budget.amount_minor
        )
        assert summary.transport_mode_tags


def test_generated_ids_are_ascii_bounded_and_change_between_requests() -> None:
    provider = JsonMockTravelDataProvider(FIXTURE_PATH)
    trip = request()
    candidate_set = candidates(trip, provider)

    first = build_coordinator_context(
        trip, candidate_set, provider, preference_notes=None
    )
    second = build_coordinator_context(
        trip, candidate_set, provider, preference_notes=None
    )

    assert isinstance(first, BoundCoordinatorContext)
    assert isinstance(second, BoundCoordinatorContext)
    first_ids = {binding.candidate_id for binding in first.bindings}
    second_ids = {binding.candidate_id for binding in second.bindings}
    assert first_ids.isdisjoint(second_ids)
    assert all(value.isascii() and len(value) <= 64 for value in first_ids)


def test_selection_facts_are_only_strict_canonical_optima() -> None:
    provider = JsonMockTravelDataProvider(FIXTURE_PATH)
    trip = request()
    result = build_coordinator_context(
        trip,
        candidates(trip, provider),
        provider,
        preference_notes=None,
        candidate_id_factory=sequential_ids(),  # type: ignore[arg-type]
    )
    assert isinstance(result, BoundCoordinatorContext)

    facts = derive_selection_facts("candidate_A", result.context)
    assert facts
    selected = result.context.candidates[0]
    candidates_in_context = result.context.candidates
    checks = {
        CoordinatorSelectionFact.LOWEST_ESTIMATED_COST: (
            selected.total_estimated_cost_minor,
            tuple(value.total_estimated_cost_minor for value in candidates_in_context),
            min,
        ),
        CoordinatorSelectionFact.LARGEST_BUDGET_BUFFER: (
            selected.remaining_budget_minor,
            tuple(value.remaining_budget_minor for value in candidates_in_context),
            max,
        ),
        CoordinatorSelectionFact.FEWEST_ACTIVITIES: (
            selected.primary_activity_count,
            tuple(value.primary_activity_count for value in candidates_in_context),
            min,
        ),
        CoordinatorSelectionFact.MOST_ACTIVITIES: (
            selected.primary_activity_count,
            tuple(value.primary_activity_count for value in candidates_in_context),
            max,
        ),
        CoordinatorSelectionFact.GREATEST_ACTIVITY_VARIETY: (
            selected.distinct_primary_activity_count,
            tuple(
                value.distinct_primary_activity_count for value in candidates_in_context
            ),
            max,
        ),
        CoordinatorSelectionFact.SHORTEST_TRANSFER_TIME: (
            selected.total_transfer_minutes,
            tuple(value.total_transfer_minutes for value in candidates_in_context),
            min,
        ),
        CoordinatorSelectionFact.GREATEST_INTEREST_COVERAGE: (
            selected.requested_interest_coverage_count,
            tuple(
                value.requested_interest_coverage_count
                for value in candidates_in_context
            ),
            max,
        ),
        CoordinatorSelectionFact.MOST_DAYTIME_ACTIVITIES: (
            selected.daypart_activity_counts.morning
            + selected.daypart_activity_counts.afternoon,
            tuple(
                value.daypart_activity_counts.morning
                + value.daypart_activity_counts.afternoon
                for value in candidates_in_context
            ),
            max,
        ),
        CoordinatorSelectionFact.MOST_EVENING_ACTIVITIES: (
            selected.daypart_activity_counts.evening,
            tuple(
                value.daypart_activity_counts.evening for value in candidates_in_context
            ),
            max,
        ),
    }
    for fact in facts:
        selected_value, values, optimum = checks[fact]
        assert selected_value == optimum(values)
        assert len(set(values)) > 1
    assert derive_selection_facts("unknown", result.context) == ()


def test_rejects_insufficient_candidates_and_duplicate_or_invalid_ids() -> None:
    provider = JsonMockTravelDataProvider(FIXTURE_PATH)
    trip = request()
    candidate_set = candidates(trip, provider)
    one = replace(candidate_set, candidates=(candidate_set.candidates[0],))

    assert build_coordinator_context(
        trip, one, provider, preference_notes=None
    ) == CoordinatorContextBuildFailure(
        CoordinatorContextBuildFailureCode.INSUFFICIENT_CANDIDATES
    )
    assert build_coordinator_context(
        trip,
        candidate_set,
        provider,
        preference_notes=None,
        candidate_id_factory=lambda: "duplicate",
    ) == CoordinatorContextBuildFailure(
        CoordinatorContextBuildFailureCode.INVALID_CANDIDATE_ID
    )
    assert build_coordinator_context(
        trip,
        candidate_set,
        provider,
        preference_notes=None,
        candidate_id_factory=lambda: "not valid",
    ) == CoordinatorContextBuildFailure(
        CoordinatorContextBuildFailureCode.INVALID_DERIVED_METRICS
    )


def test_fails_closed_when_canonical_source_record_is_missing() -> None:
    provider = JsonMockTravelDataProvider(FIXTURE_PATH)
    trip = request()
    candidate_set = candidates(trip, provider)
    first = candidate_set.candidates[0]
    activity = next(
        item
        for item in first.itinerary.scheduled_items
        if item.kind is ItemKind.ACTIVITY
    )
    broken_snapshot = replace(
        first.provider_snapshot,
        record_ids=first.provider_snapshot.record_ids - {activity.source_record_id},
    )
    broken = replace(
        candidate_set,
        candidates=(replace(first, provider_snapshot=broken_snapshot),)
        + candidate_set.candidates[1:],
    )

    assert build_coordinator_context(
        trip,
        broken,
        provider,
        preference_notes=None,
        candidate_id_factory=sequential_ids(),  # type: ignore[arg-type]
    ) == CoordinatorContextBuildFailure(
        CoordinatorContextBuildFailureCode.INCOMPLETE_CANONICAL_DATA
    )
