from __future__ import annotations

import hashlib
import json
import socket
from datetime import date, time
from itertools import combinations
from pathlib import Path

import pytest

import trippilot.services.planner as planner_module
from trippilot.domain import (
    Interest,
    ItemKind,
    Money,
    Pace,
    TripRequest,
    validate_itinerary,
)
from trippilot.providers import (
    ActivityRecord,
    JsonMockTravelDataProvider,
    LocationRecord,
)
from trippilot.services import (
    CANDIDATE_GENERATOR_ID,
    CandidateSet,
    CanonicalCandidate,
    PlanningFailure,
    PlanningFailureCode,
    PlanningSuccess,
    enumerate_trip_candidates,
    plan_trip,
)

REPOSITORY_ROOT = Path(__file__).parents[3]
FIXTURE_PATH = REPOSITORY_ROOT / "data/mock/kingston-toronto-v1.json"


@pytest.fixture(scope="module")
def provider() -> JsonMockTravelDataProvider:
    return JsonMockTravelDataProvider(FIXTURE_PATH)


def request(
    *,
    end_date: date = date(2026, 8, 11),
    travellers: int = 1,
    budget: int = 100_000,
    interests: tuple[Interest, ...] = (
        Interest.ARTS_CULTURE,
        Interest.HISTORY,
        Interest.STUDENT_BUDGET,
    ),
    pace: Pace = Pace.BALANCED,
    earliest: time = time(9),
    destination: str = "Toronto, Ontario",
) -> TripRequest:
    return TripRequest(
        origin="Kingston, Ontario",
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


def candidate_set(result: object) -> CandidateSet:
    assert isinstance(result, CandidateSet)
    return result


class ProviderOverride:
    def __init__(
        self, provider: JsonMockTravelDataProvider, **overrides: object
    ) -> None:
        self._provider = provider
        self.__dict__.update(overrides)

    def __getattr__(self, name: str) -> object:
        return getattr(self._provider, name)


def activity_signature(candidate: CanonicalCandidate) -> tuple[str, ...]:
    itinerary = candidate.itinerary
    return tuple(
        item.source_record_id or ""
        for item in itinerary.scheduled_items
        if item.kind is ItemKind.ACTIVITY
    )


def interest_counts(
    candidate: CanonicalCandidate, provider: JsonMockTravelDataProvider
) -> tuple[int, ...]:
    counts = {interest: 0 for interest in Interest}
    itinerary = candidate.itinerary
    for item in itinerary.scheduled_items:
        if item.kind is not ItemKind.ACTIVITY or item.source_record_id is None:
            continue
        record = provider.get_record(item.source_record_id)
        assert isinstance(record, ActivityRecord)
        for interest in record.interests:
            counts[interest] += 1
    return tuple(counts[interest] for interest in Interest)


def transfer_minutes(candidate: CanonicalCandidate) -> int:
    snapshot = candidate.provider_snapshot
    return sum(value.minimum_minutes for value in snapshot.transfer_requirements)


def assert_pairwise_materiality(
    trip: TripRequest,
    result: CandidateSet,
    provider: JsonMockTravelDataProvider,
) -> None:
    cost_threshold = min(500, (trip.budget.amount_minor * 5 + 99) // 100)
    for left, right in combinations(result.candidates, 2):
        assert activity_signature(left) != activity_signature(right)
        cost_delta = abs(
            left.itinerary.total_estimated_cost.amount_minor
            - right.itinerary.total_estimated_cost.amount_minor
        )
        assert (
            cost_delta >= cost_threshold
            or abs(transfer_minutes(left) - transfer_minutes(right)) >= 15
            or len(activity_signature(left)) != len(activity_signature(right))
            or interest_counts(left, provider) != interest_counts(right, provider)
        )


def candidate_metric_digest(
    result: CandidateSet, provider: JsonMockTravelDataProvider
) -> str:
    payload = [
        {
            "activities": activity_signature(candidate),
            "cost": candidate.itinerary.total_estimated_cost.amount_minor,
            "interest_counts": interest_counts(candidate, provider),
            "transfer": transfer_minutes(candidate),
        }
        for candidate in result.candidates
    ]
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def test_enumeration_is_deterministic_and_preserves_standard_selection(
    provider: JsonMockTravelDataProvider,
) -> None:
    trip = request()

    first = candidate_set(enumerate_trip_candidates(trip, provider))
    assert first == enumerate_trip_candidates(trip, provider)
    assert first.generator_id == CANDIDATE_GENERATOR_ID
    assert 1 <= len(first.candidates) <= 5

    standard = plan_trip(trip, provider)
    assert isinstance(standard, PlanningSuccess)
    assert first.candidates[0].itinerary == standard.itinerary
    assert first.candidates[0].matched_interests == standard.matched_interests
    assert first.assumptions == standard.assumptions
    assert first.disclosures == standard.disclosures


@pytest.mark.parametrize("limit", [False, 0, 1, 6, 2.0, 2.5, "2", None])
def test_candidate_limit_rejects_values_outside_coordinator_bounds(
    provider: JsonMockTravelDataProvider, limit: object
) -> None:
    with pytest.raises(ValueError, match="between two and five"):
        enumerate_trip_candidates(request(), provider, limit=limit)  # type: ignore[arg-type]


def test_every_candidate_is_canonical_clean_and_reconciled(
    provider: JsonMockTravelDataProvider,
) -> None:
    trip = request(end_date=date(2026, 8, 13), travellers=2, pace=Pace.PACKED)
    result = candidate_set(enumerate_trip_candidates(trip, provider))

    for candidate in result.candidates:
        itinerary = candidate.itinerary
        assert validate_itinerary(trip, itinerary, candidate.provider_snapshot).is_valid
        assert itinerary.total_estimated_cost.amount_minor <= trip.budget.amount_minor
        assert (
            sum(value.amount_minor for value in itinerary.category_totals.values())
            == itinerary.total_estimated_cost.amount_minor
        )
        for item in itinerary.scheduled_items:
            assert item.source_record_id in candidate.provider_snapshot.record_ids
            assert provider.get_record(item.source_record_id or "") is not None
            if item.location_id is not None:
                assert isinstance(provider.get_record(item.location_id), LocationRecord)
        for stay in itinerary.accommodation_stays:
            assert stay.source_record_id in candidate.provider_snapshot.record_ids
            assert provider.get_record(stay.source_record_id or "") is not None
            if stay.location_id is not None:
                assert isinstance(provider.get_record(stay.location_id), LocationRecord)


def test_retained_candidates_are_pairwise_materially_different(
    provider: JsonMockTravelDataProvider,
) -> None:
    trip = request(end_date=date(2026, 8, 13), pace=Pace.PACKED)
    result = candidate_set(enumerate_trip_candidates(trip, provider))
    assert len(result.candidates) == 5
    assert_pairwise_materiality(trip, result, provider)


FROZEN_DIVERSITY_CASES = (
    request(
        pace=Pace.BALANCED,
        interests=(Interest.ARTS_CULTURE, Interest.NATURE),
        end_date=date(2026, 8, 10),
    ),
    request(
        pace=Pace.BALANCED,
        interests=(Interest.HISTORY, Interest.NIGHTLIFE),
        end_date=date(2026, 8, 10),
    ),
    request(
        pace=Pace.PACKED,
        interests=(Interest.FOOD, Interest.STUDENT_BUDGET),
        travellers=2,
        end_date=date(2026, 8, 10),
    ),
    request(
        pace=Pace.RELAXED,
        interests=(Interest.SPORTS, Interest.SHOPPING),
        earliest=time(13),
    ),
    request(),
    request(
        pace=Pace.PACKED,
        interests=(Interest.HISTORY, Interest.NIGHTLIFE),
        travellers=2,
        budget=35_000,
    ),
    request(
        pace=Pace.RELAXED,
        interests=(Interest.FOOD, Interest.STUDENT_BUDGET),
        end_date=date(2026, 8, 13),
    ),
    request(
        interests=(Interest.ARTS_CULTURE, Interest.NATURE),
        travellers=2,
        budget=120_000,
        earliest=time(13),
        end_date=date(2026, 8, 13),
    ),
)

FROZEN_DIVERSITY_DIGESTS = (
    "608a3fd26e94b3dfbb3ff7bfc81f52c68cb89579592a0b21a35b6122142364b7",
    "13f8fb66a50d9e8ca0e71b2371ceace416a6985ae832850e527d84efde946eca",
    "9b05b75d4067c92dfe680128a7caa6eafe2ccb86d01731530fdf9eefeb39a1c6",
    "93107201e2547343833eb9d19bcf0b07a290813dedc4541f07e7c291aeb7a28d",
    "8ae06fd0a48d416c443dda27d8da2f0dd120b4dc6f800608464dd54cc1eade29",
    "33b11a5705e7dc1a5b2fca34d79dddd941a5124dbd13fd64d9ba1dbb51e2c221",
    "9163b7b09be690ceeb9cc1d1c903ae8141804a6dcfade3a4838612445804e2af",
    "53debe0db8074f124ce23ec8d7e5bf24446de6373bcc2faa56058eb2ae6245b6",
)


@pytest.mark.parametrize(
    ("trip", "expected_digest"),
    tuple(zip(FROZEN_DIVERSITY_CASES, FROZEN_DIVERSITY_DIGESTS, strict=True)),
)
def test_frozen_request_meets_candidate_diversity_prerequisite(
    provider: JsonMockTravelDataProvider,
    trip: TripRequest,
    expected_digest: str,
) -> None:
    result = candidate_set(enumerate_trip_candidates(trip, provider))

    assert 2 <= len(result.candidates) <= 5
    assert result.fixture_snapshot_version == "2026-08-01.v1"
    assert result == enumerate_trip_candidates(trip, provider)
    standard = plan_trip(trip, provider)
    assert isinstance(standard, PlanningSuccess)
    assert result.candidates[0].itinerary == standard.itinerary
    assert_pairwise_materiality(trip, result, provider)
    assert candidate_metric_digest(result, provider) == expected_digest
    for candidate in result.candidates:
        assert validate_itinerary(
            trip, candidate.itinerary, candidate.provider_snapshot
        ).is_valid
        assert (
            sum(
                value.amount_minor
                for value in candidate.itinerary.category_totals.values()
            )
            == candidate.itinerary.total_estimated_cost.amount_minor
            <= trip.budget.amount_minor
        )


def test_zero_candidate_result_preserves_structured_failure(
    provider: JsonMockTravelDataProvider,
) -> None:
    result = enumerate_trip_candidates(request(budget=1), provider)

    assert isinstance(result, PlanningFailure)
    assert result.code is PlanningFailureCode.INSUFFICIENT_BUDGET
    assert result == plan_trip(request(budget=1), provider)


def test_one_material_candidate_is_returned_without_padding(
    provider: JsonMockTravelDataProvider,
) -> None:
    trip = request(
        end_date=date(2026, 8, 10),
        pace=Pace.RELAXED,
        interests=(Interest.ARTS_CULTURE, Interest.NATURE),
    )

    result = candidate_set(enumerate_trip_candidates(trip, provider))

    assert len(result.candidates) == 1
    standard = plan_trip(trip, provider)
    assert isinstance(standard, PlanningSuccess)
    assert result.candidates[0].itinerary == standard.itinerary


def test_unsupported_route_preserves_structured_failure(
    provider: JsonMockTravelDataProvider,
) -> None:
    result = enumerate_trip_candidates(request(destination="Ottawa, Ontario"), provider)

    assert isinstance(result, PlanningFailure)
    assert result.code is PlanningFailureCode.UNSUPPORTED_ROUTE
    assert result == plan_trip(request(destination="Ottawa, Ontario"), provider)


def test_provider_record_order_does_not_change_candidate_set(
    provider: JsonMockTravelDataProvider,
) -> None:
    reversed_provider = ProviderOverride(
        provider,
        list_transport_options=lambda *args: tuple(
            reversed(provider.list_transport_options(*args))
        ),
        list_accommodation_options=lambda *args: tuple(
            reversed(provider.list_accommodation_options(*args))
        ),
        list_activities=lambda *args: tuple(reversed(provider.list_activities(*args))),
        list_meal_options=lambda *args: tuple(
            reversed(provider.list_meal_options(*args))
        ),
        get_operating_windows=lambda *args: tuple(
            reversed(provider.get_operating_windows(*args))
        ),
        list_fees=lambda *args: tuple(reversed(provider.list_fees(*args))),
    )
    trip = request(end_date=date(2026, 8, 13), pace=Pace.PACKED)

    assert enumerate_trip_candidates(
        trip, reversed_provider
    ) == enumerate_trip_candidates(trip, provider)


def test_enumeration_preserves_search_caps(
    provider: JsonMockTravelDataProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    schedule_calls = 0
    candidate_calls = 0
    original_schedule = planner_module._schedule_sequence
    original_best = planner_module._best_agenda
    original_candidate = planner_module._candidate

    def counted_schedule(*args: object, **kwargs: object) -> object:
        nonlocal schedule_calls
        schedule_calls += 1
        return original_schedule(*args, **kwargs)  # type: ignore[arg-type]

    def checked_best(*args: object, **kwargs: object) -> object:
        before = schedule_calls
        result = original_best(*args, **kwargs)  # type: ignore[arg-type]
        assert schedule_calls - before <= planner_module.MAX_AGENDA_VARIANTS_PER_DAY
        return result

    def counted_candidate(*args: object, **kwargs: object) -> object:
        nonlocal candidate_calls
        candidate_calls += 1
        return original_candidate(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(planner_module, "_schedule_sequence", counted_schedule)
    monkeypatch.setattr(planner_module, "_best_agenda", checked_best)
    monkeypatch.setattr(planner_module, "_candidate", counted_candidate)
    trip = request(end_date=date(2026, 8, 13), pace=Pace.PACKED)

    result = candidate_set(enumerate_trip_candidates(trip, provider))

    assert len(result.candidates) == 5
    assert candidate_calls <= (
        planner_module.MAX_CANDIDATE_COMBINATIONS
        * len(planner_module._daily_target_profiles(trip))
        * 2
    )


def test_enumeration_uses_no_network(
    provider: JsonMockTravelDataProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    def reject_network(*args: object, **kwargs: object) -> None:
        raise AssertionError("network access is forbidden")

    monkeypatch.setattr(socket, "socket", reject_network)

    assert isinstance(enumerate_trip_candidates(request(), provider), CandidateSet)


def test_provider_failure_does_not_log_or_return_sensitive_canary(
    provider: JsonMockTravelDataProvider,
    caplog: pytest.LogCaptureFixture,
) -> None:
    canary = "SECRET-CANARY /private/provider.json"

    def broken(*args: object) -> object:
        raise RuntimeError(canary)

    result = enumerate_trip_candidates(
        request(), ProviderOverride(provider, list_activities=broken)
    )

    assert isinstance(result, PlanningFailure)
    assert result.code is PlanningFailureCode.PROVIDER_DATA_INCOMPLETE
    assert canary not in result.explanation
    assert canary not in caplog.text
