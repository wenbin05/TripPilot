"""Canonical context construction for the optional coordinator experiment."""

from __future__ import annotations

import secrets
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from zoneinfo import ZoneInfo

from pydantic import ValidationError

from trippilot.domain import Interest, ItemKind, TripRequest
from trippilot.providers import (
    AccommodationOptionRecord,
    ActivityRecord,
    TransportMode,
    TransportOptionRecord,
    TravelDataProvider,
)

from .coordinator_schemas import (
    AccommodationStyleTag,
    ActivityInterestCounts,
    CandidateSummary,
    CoordinatorContext,
    CoordinatorTransportModeTag,
    DaypartActivityCounts,
)
from .models import CandidateSet, CanonicalCandidate

FIXED_RANKER_ID = "trippilot-fixed-ranker-v1"


class CoordinatorContextBuildFailureCode(StrEnum):
    INSUFFICIENT_CANDIDATES = "INSUFFICIENT_CANDIDATES"
    INVALID_CANDIDATE_ID = "INVALID_CANDIDATE_ID"
    INCOMPLETE_CANONICAL_DATA = "INCOMPLETE_CANONICAL_DATA"
    INVALID_DERIVED_METRICS = "INVALID_DERIVED_METRICS"


class CoordinatorSelectionFact(StrEnum):
    LOWEST_ESTIMATED_COST = "lowest_estimated_cost"
    LARGEST_BUDGET_BUFFER = "largest_budget_buffer"
    FEWEST_ACTIVITIES = "fewest_activities"
    MOST_ACTIVITIES = "most_activities"
    GREATEST_ACTIVITY_VARIETY = "greatest_activity_variety"
    SHORTEST_TRANSFER_TIME = "shortest_transfer_time"
    GREATEST_INTEREST_COVERAGE = "greatest_interest_coverage"
    MOST_DAYTIME_ACTIVITIES = "most_daytime_activities"
    MOST_EVENING_ACTIVITIES = "most_evening_activities"


@dataclass(frozen=True, slots=True)
class CoordinatorContextBuildFailure:
    code: CoordinatorContextBuildFailureCode


@dataclass(frozen=True, slots=True)
class CoordinatorCandidateBinding:
    candidate_id: str
    candidate: CanonicalCandidate


@dataclass(frozen=True, slots=True)
class BoundCoordinatorContext:
    context: CoordinatorContext
    bindings: tuple[CoordinatorCandidateBinding, ...]

    def resolve(self, candidate_id: str) -> CanonicalCandidate | None:
        return next(
            (
                binding.candidate
                for binding in self.bindings
                if binding.candidate_id == candidate_id
            ),
            None,
        )


CoordinatorContextBuildResult = BoundCoordinatorContext | CoordinatorContextBuildFailure
CandidateIdFactory = Callable[[], str]


def _request_scoped_candidate_id() -> str:
    return f"candidate_{secrets.token_urlsafe(18)}"


def build_coordinator_context(
    request: TripRequest,
    candidate_set: CandidateSet,
    provider: TravelDataProvider,
    *,
    preference_notes: str | None,
    candidate_id_factory: CandidateIdFactory = _request_scoped_candidate_id,
) -> CoordinatorContextBuildResult:
    """Bind opaque IDs and derive one closed context from canonical records."""

    if len(candidate_set.candidates) < 2:
        return CoordinatorContextBuildFailure(
            CoordinatorContextBuildFailureCode.INSUFFICIENT_CANDIDATES
        )

    bindings: list[CoordinatorCandidateBinding] = []
    summaries: list[CandidateSummary] = []
    seen_ids: set[str] = set()
    for candidate in candidate_set.candidates:
        candidate_id = candidate_id_factory()
        if candidate_id in seen_ids:
            return CoordinatorContextBuildFailure(
                CoordinatorContextBuildFailureCode.INVALID_CANDIDATE_ID
            )
        summary = _candidate_summary(request, candidate, provider, candidate_id)
        if isinstance(summary, CoordinatorContextBuildFailure):
            return summary
        seen_ids.add(candidate_id)
        bindings.append(CoordinatorCandidateBinding(candidate_id, candidate))
        summaries.append(summary)

    try:
        context = CoordinatorContext(
            contract_version="coordinator-context-v1",
            interests=request.interests,
            pace=request.pace,
            preference_notes=preference_notes,
            candidates=tuple(summaries),
        )
    except ValidationError, ValueError, TypeError:
        return CoordinatorContextBuildFailure(
            CoordinatorContextBuildFailureCode.INVALID_DERIVED_METRICS
        )
    return BoundCoordinatorContext(context, tuple(bindings))


def derive_selection_facts(
    selected_candidate_id: str, context: CoordinatorContext
) -> tuple[CoordinatorSelectionFact, ...]:
    """Return only facts that are strict canonical optima in this candidate set."""

    selected = next(
        (
            candidate
            for candidate in context.candidates
            if candidate.candidate_id == selected_candidate_id
        ),
        None,
    )
    if selected is None:
        return ()

    facts: list[CoordinatorSelectionFact] = []
    comparisons = (
        (
            CoordinatorSelectionFact.LOWEST_ESTIMATED_COST,
            selected.total_estimated_cost_minor,
            tuple(
                candidate.total_estimated_cost_minor for candidate in context.candidates
            ),
            min,
        ),
        (
            CoordinatorSelectionFact.LARGEST_BUDGET_BUFFER,
            selected.remaining_budget_minor,
            tuple(candidate.remaining_budget_minor for candidate in context.candidates),
            max,
        ),
        (
            CoordinatorSelectionFact.FEWEST_ACTIVITIES,
            selected.primary_activity_count,
            tuple(candidate.primary_activity_count for candidate in context.candidates),
            min,
        ),
        (
            CoordinatorSelectionFact.MOST_ACTIVITIES,
            selected.primary_activity_count,
            tuple(candidate.primary_activity_count for candidate in context.candidates),
            max,
        ),
        (
            CoordinatorSelectionFact.GREATEST_ACTIVITY_VARIETY,
            selected.distinct_primary_activity_count,
            tuple(
                candidate.distinct_primary_activity_count
                for candidate in context.candidates
            ),
            max,
        ),
        (
            CoordinatorSelectionFact.SHORTEST_TRANSFER_TIME,
            selected.total_transfer_minutes,
            tuple(candidate.total_transfer_minutes for candidate in context.candidates),
            min,
        ),
        (
            CoordinatorSelectionFact.GREATEST_INTEREST_COVERAGE,
            selected.requested_interest_coverage_count,
            tuple(
                candidate.requested_interest_coverage_count
                for candidate in context.candidates
            ),
            max,
        ),
        (
            CoordinatorSelectionFact.MOST_DAYTIME_ACTIVITIES,
            selected.daypart_activity_counts.morning
            + selected.daypart_activity_counts.afternoon,
            tuple(
                candidate.daypart_activity_counts.morning
                + candidate.daypart_activity_counts.afternoon
                for candidate in context.candidates
            ),
            max,
        ),
        (
            CoordinatorSelectionFact.MOST_EVENING_ACTIVITIES,
            selected.daypart_activity_counts.evening,
            tuple(
                candidate.daypart_activity_counts.evening
                for candidate in context.candidates
            ),
            max,
        ),
    )
    for fact, selected_value, values, optimum in comparisons:
        if selected_value == optimum(values) and len(set(values)) > 1:
            facts.append(fact)
    return tuple(facts)


def _candidate_summary(
    request: TripRequest,
    candidate: CanonicalCandidate,
    provider: TravelDataProvider,
    candidate_id: str,
) -> CandidateSummary | CoordinatorContextBuildFailure:
    activities = tuple(
        item
        for item in candidate.itinerary.scheduled_items
        if item.kind is ItemKind.ACTIVITY
    )
    interest_counts = {interest: 0 for interest in Interest}
    activity_source_ids: list[str] = []
    dayparts = [0, 0, 0]
    zone = ZoneInfo(request.destination_timezone)

    for item in activities:
        record = _canonical_record(candidate, provider, item.source_record_id)
        if not isinstance(record, ActivityRecord):
            return CoordinatorContextBuildFailure(
                CoordinatorContextBuildFailureCode.INCOMPLETE_CANONICAL_DATA
            )
        activity_source_ids.append(record.record_id)
        for interest in record.interests:
            interest_counts[interest] += 1
        hour = item.window.start.astimezone(zone).hour
        dayparts[0 if hour < 12 else 1 if hour < 18 else 2] += 1

    accommodation_styles: set[AccommodationStyleTag] = set()
    for stay in candidate.itinerary.accommodation_stays:
        record = _canonical_record(candidate, provider, stay.source_record_id)
        if not isinstance(record, AccommodationOptionRecord):
            return CoordinatorContextBuildFailure(
                CoordinatorContextBuildFailureCode.INCOMPLETE_CANONICAL_DATA
            )
        for tag in record.tags:
            if tag == AccommodationStyleTag.QUIET:
                accommodation_styles.add(AccommodationStyleTag.QUIET)
            elif tag == AccommodationStyleTag.SOCIAL:
                accommodation_styles.add(AccommodationStyleTag.SOCIAL)

    transport_modes: set[CoordinatorTransportModeTag] = set()
    for item in candidate.itinerary.scheduled_items:
        if item.kind is not ItemKind.TRANSPORT:
            continue
        record = _canonical_record(candidate, provider, item.source_record_id)
        if not isinstance(record, TransportOptionRecord):
            return CoordinatorContextBuildFailure(
                CoordinatorContextBuildFailureCode.INCOMPLETE_CANONICAL_DATA
            )
        transport_modes.add(
            CoordinatorTransportModeTag.COACH
            if record.mode is TransportMode.COACH
            else CoordinatorTransportModeTag.TRAIN
        )

    primary_count = len(activities)
    total_cost = candidate.itinerary.total_estimated_cost.amount_minor
    try:
        return CandidateSummary(
            contract_version="candidate-summary-v1",
            candidate_id=candidate_id,
            total_estimated_cost_minor=total_cost,
            remaining_budget_minor=request.budget.amount_minor - total_cost,
            primary_activity_count=primary_count,
            distinct_primary_activity_count=len(set(activity_source_ids)),
            total_transfer_minutes=sum(
                requirement.minimum_minutes
                for requirement in candidate.provider_snapshot.transfer_requirements
            ),
            activity_interest_counts=ActivityInterestCounts(
                food=interest_counts[Interest.FOOD],
                arts_culture=interest_counts[Interest.ARTS_CULTURE],
                nature=interest_counts[Interest.NATURE],
                history=interest_counts[Interest.HISTORY],
                nightlife=interest_counts[Interest.NIGHTLIFE],
                shopping=interest_counts[Interest.SHOPPING],
                sports=interest_counts[Interest.SPORTS],
                student_budget=interest_counts[Interest.STUDENT_BUDGET],
            ),
            requested_interest_coverage_count=sum(
                interest_counts[interest] > 0 for interest in request.interests
            ),
            daypart_activity_counts=DaypartActivityCounts(
                morning=dayparts[0], afternoon=dayparts[1], evening=dayparts[2]
            ),
            accommodation_style_tags=tuple(
                tag for tag in AccommodationStyleTag if tag in accommodation_styles
            ),
            transport_mode_tags=tuple(
                tag for tag in CoordinatorTransportModeTag if tag in transport_modes
            ),
        )
    except ValidationError, ValueError, TypeError:
        return CoordinatorContextBuildFailure(
            CoordinatorContextBuildFailureCode.INVALID_DERIVED_METRICS
        )


def _canonical_record(
    candidate: CanonicalCandidate,
    provider: TravelDataProvider,
    record_id: str | None,
) -> object | None:
    if record_id is None or record_id not in candidate.provider_snapshot.record_ids:
        return None
    try:
        return provider.get_record(record_id)
    except Exception:
        return None
