"""Structured outcomes from the deterministic planning service."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from trippilot.domain import (
    Interest,
    Itinerary,
    ProviderSnapshot,
    ValidationReport,
)


class PlanningFailureCode(StrEnum):
    """Stable expected-failure codes returned instead of raising exceptions."""

    INVALID_REQUEST = "INVALID_REQUEST"
    NO_TRANSPORT_OPTION = "NO_TRANSPORT_OPTION"
    NO_ACCOMMODATION_OPTION = "NO_ACCOMMODATION_OPTION"
    NO_FEASIBLE_ACTIVITY_SET = "NO_FEASIBLE_ACTIVITY_SET"
    INSUFFICIENT_BUDGET = "INSUFFICIENT_BUDGET"
    NO_VALID_ITINERARY = "NO_VALID_ITINERARY"
    UNSUPPORTED_ROUTE = "UNSUPPORTED_ROUTE"
    PROVIDER_DATA_INCOMPLETE = "PROVIDER_DATA_INCOMPLETE"


@dataclass(frozen=True, slots=True)
class PlanningSuccess:
    itinerary: Itinerary
    validation_report: ValidationReport
    fixture_snapshot_version: str
    planner_id: str
    matched_interests: tuple[Interest, ...]
    assumptions: tuple[str, ...]
    disclosures: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PlanningFailure:
    code: PlanningFailureCode
    explanation: str
    validation_report: ValidationReport
    relevant_constraints: tuple[str, ...]
    fixture_snapshot_version: str | None
    planner_id: str
    assumptions: tuple[str, ...]
    disclosures: tuple[str, ...]


PlanningResult = PlanningSuccess | PlanningFailure


@dataclass(frozen=True, slots=True)
class CanonicalCandidate:
    """One canonical proposal plus the exact snapshot used to validate it."""

    itinerary: Itinerary
    provider_snapshot: ProviderSnapshot
    validation_report: ValidationReport
    matched_interests: tuple[Interest, ...]

    def __post_init__(self) -> None:
        if not self.validation_report.is_valid:
            raise ValueError("canonical candidates must be validator-clean")


@dataclass(frozen=True, slots=True)
class CandidateSet:
    """Bounded, ordered canonical proposals for one normalized request."""

    candidates: tuple[CanonicalCandidate, ...]
    fixture_snapshot_version: str
    generator_id: str
    assumptions: tuple[str, ...]
    disclosures: tuple[str, ...]

    def __post_init__(self) -> None:
        if not 1 <= len(self.candidates) <= 5:
            raise ValueError("candidate sets must contain between one and five items")
        if any(
            candidate == existing
            for index, candidate in enumerate(self.candidates)
            for existing in self.candidates[:index]
        ):
            raise ValueError("candidate sets cannot contain exact duplicates")
        if not self.fixture_snapshot_version or not self.generator_id:
            raise ValueError("candidate-set metadata cannot be empty")


CandidateEnumerationResult = CandidateSet | PlanningFailure
