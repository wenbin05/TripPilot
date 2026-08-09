"""Explicit dependency wiring for the local API application."""

from __future__ import annotations

import os
from collections.abc import Callable
from functools import lru_cache
from pathlib import Path

from trippilot.domain import TripRequest
from trippilot.providers import JsonMockTravelDataProvider, TravelDataProvider
from trippilot.services import (
    COORDINATOR_MODEL,
    CandidateEnumerationResult,
    CoordinatorAdapter,
    NotConfiguredCoordinatorAdapter,
    OpenAICoordinatorAdapter,
    OpenAICoordinatorConfig,
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


def get_coordinator_adapter() -> CoordinatorAdapter:
    """Return the one explicitly configured hosted adapter or safe fallback."""

    if os.getenv("TRIPPILOT_COORDINATOR_ENABLED", "").strip().casefold() != "true":
        return NotConfiguredCoordinatorAdapter()
    api_key = os.getenv("TRIPPILOT_OPENAI_API_KEY", "")
    model = os.getenv("TRIPPILOT_COORDINATOR_MODEL", "")
    try:
        config = OpenAICoordinatorConfig(api_key=api_key, model=model)
    except ValueError:
        return NotConfiguredCoordinatorAdapter()
    if model != COORDINATOR_MODEL:
        return NotConfiguredCoordinatorAdapter()
    return OpenAICoordinatorAdapter(config)
