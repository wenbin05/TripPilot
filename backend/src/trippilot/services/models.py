"""Structured outcomes from the deterministic planning service."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from trippilot.domain import Interest, Itinerary, ValidationReport


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
