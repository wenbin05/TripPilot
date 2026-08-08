"""Explicit dependency wiring for the local API application."""

from __future__ import annotations

from collections.abc import Callable
from functools import lru_cache
from pathlib import Path

from trippilot.domain import TripRequest
from trippilot.providers import JsonMockTravelDataProvider, TravelDataProvider
from trippilot.services import (
    CandidateEnumerationResult,
    PlanningResult,
    enumerate_trip_candidates,
    plan_trip,
)

Planner = Callable[[TripRequest, TravelDataProvider], PlanningResult]
CandidateEnumerator = Callable[
    [TripRequest, TravelDataProvider], CandidateEnumerationResult
]

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_FIXTURE_PATH = REPOSITORY_ROOT / "data/mock/kingston-toronto-v1.json"


@lru_cache(maxsize=1)
def get_provider() -> JsonMockTravelDataProvider:
    """Load and validate the immutable mock snapshot once per process."""

    return JsonMockTravelDataProvider(DEFAULT_FIXTURE_PATH)


def get_planner() -> Planner:
    """Return the replaceable deterministic planning implementation."""

    return plan_trip


def get_candidate_enumerator() -> CandidateEnumerator:
    """Return the replaceable deterministic candidate implementation."""

    return enumerate_trip_candidates
