from __future__ import annotations

import json
from dataclasses import replace
from datetime import date, time
from pathlib import Path

import pytest

from trippilot.domain import Interest, Money, Pace, TripRequest, validate_itinerary
from trippilot.providers import JsonMockTravelDataProvider
from trippilot.services import (
    BoundCoordinatorContext,
    CandidateSet,
    build_coordinator_context,
    enumerate_trip_candidates,
)
from trippilot.services.agent_workflow import (
    AgentState,
    parse_agent_action,
    run_agent_workflow,
)


@pytest.fixture(scope="module")
def context() -> tuple[TripRequest, BoundCoordinatorContext]:
    trip = TripRequest(
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
    provider = JsonMockTravelDataProvider(
        Path(__file__).parents[3] / "data/mock/kingston-toronto-v1.json"
    )
    candidates = enumerate_trip_candidates(trip, provider)
    assert isinstance(candidates, CandidateSet)
    ids = iter(f"candidate_{i}" for i in range(5))
    bound = build_coordinator_context(
        trip,
        candidates,
        provider,
        preference_notes="Prefer shorter transfers",
        candidate_id_factory=lambda: next(ids),
    )
    assert isinstance(bound, BoundCoordinatorContext)
    return trip, bound


def action(name: str, candidate_id: str = "candidate_0") -> str:
    return json.dumps({"action": name, "candidate_id": candidate_id})


class ScriptedAdapter:
    def __init__(self, actions: list[str]) -> None:
        self.actions = iter(actions)
        self.states: list[AgentState] = []

    def next_action(self, state: AgentState, *, deadline_monotonic: float) -> str:
        assert deadline_monotonic == 10
        self.states.append(state)
        return next(self.actions)


def test_tool_observations_drive_a_validated_selection(context):
    trip, bound = context
    adapter = ScriptedAdapter(
        [
            action("inspect_candidate", "candidate_1"),
            action("validate_candidate", "candidate_1"),
            action("finish", "candidate_1"),
        ]
    )
    result = run_agent_workflow(
        trip, bound, adapter, deadline_monotonic=10, monotonic=lambda: 0
    )
    assert result.status == "selected"
    assert result.candidate == bound.resolve("candidate_1")
    assert result.steps == 3 and result.tool_calls == 2
    assert adapter.states[0].observations == ()
    assert adapter.states[1].observations[0].summary is not None
    assert adapter.states[2].observations[1].valid is True
    assert result.candidate is not None
    assert validate_itinerary(
        trip, result.candidate.itinerary, result.candidate.provider_snapshot
    ).is_valid


@pytest.mark.parametrize(
    "raw",
    [
        "not json",
        "x" * 2049,
        "\ud800",
        "[]",
        '{"action":"finish","action":"inspect_candidate","candidate_id":"candidate_0"}',
        '{"action":"finish","candidate_id":"candidate_0","x":NaN}',
        '{"action":"finish","candidate_id":1}',
        '{"action":"finish","candidate_id":"candidate_0","total":0}',
        action("shell"),
        action("finish", "../../secret"),
    ],
)
def test_parser_rejects_unsafe_actions(raw):
    assert parse_agent_action(raw) is None


@pytest.mark.parametrize(
    ("first", "code"),
    [
        ("not json", "INVALID_ACTION"),
        (action("inspect_candidate", "candidate_foreign"), "UNKNOWN_CANDIDATE"),
        (action("finish"), "VALIDATION_REQUIRED"),
    ],
)
def test_one_error_can_recover_but_two_stop(context, first, code):
    trip, bound = context
    adapter = ScriptedAdapter([first, action("validate_candidate"), action("finish")])
    result = run_agent_workflow(
        trip, bound, adapter, deadline_monotonic=10, monotonic=lambda: 0
    )
    assert result.status == "selected" and result.invalid_actions == 1
    assert adapter.states[1].feedback == code
    result = run_agent_workflow(
        trip,
        bound,
        ScriptedAdapter([first, first]),
        deadline_monotonic=10,
        monotonic=lambda: 0,
    )
    assert result.status == "fallback" and result.code == code
    assert result.invalid_actions == 2


def test_validation_does_not_authorize_another_candidate(context):
    trip, bound = context
    result = run_agent_workflow(
        trip,
        bound,
        ScriptedAdapter(
            [
                action("validate_candidate"),
                action("finish", "candidate_1"),
                action("finish", "candidate_1"),
            ]
        ),
        deadline_monotonic=10,
        monotonic=lambda: 0,
    )
    assert result.status == "fallback" and result.code == "VALIDATION_REQUIRED"


def test_tool_and_step_limits(context):
    trip, bound = context
    result = run_agent_workflow(
        trip,
        bound,
        ScriptedAdapter([action("inspect_candidate")] * 6),
        deadline_monotonic=10,
        monotonic=lambda: 0,
    )
    assert result.code == "TOOL_LIMIT" and result.tool_calls == 4
    result = run_agent_workflow(
        trip,
        bound,
        ScriptedAdapter(
            ["bad"] + [action("inspect_candidate")] * 4 + [action("finish")]
        ),
        deadline_monotonic=10,
        monotonic=lambda: 0,
    )
    assert result.code == "STEP_LIMIT" and result.steps == 5
    result = run_agent_workflow(
        trip,
        bound,
        ScriptedAdapter(
            [action("inspect_candidate")] * 4
            + [action("finish"), action("inspect_candidate")]
        ),
        deadline_monotonic=10,
        monotonic=lambda: 0,
    )
    assert result.code == "STEP_LIMIT" and result.steps == 5


@pytest.mark.parametrize("deadline", [float("nan"), float("inf")])
def test_deadline_must_be_finite(context, deadline):
    trip, bound = context
    with pytest.raises(ValueError, match="finite"):
        run_agent_workflow(
            trip, bound, ScriptedAdapter([]), deadline_monotonic=deadline
        )


def test_finish_revalidates_even_after_successful_tool(context, monkeypatch):
    trip, bound = context
    monkeypatch.setattr(
        "trippilot.services.agent_workflow._validate", lambda *args: False
    )
    result = run_agent_workflow(
        trip,
        bound,
        ScriptedAdapter([action("validate_candidate"), action("finish")]),
        deadline_monotonic=10,
        monotonic=lambda: 0,
    )
    assert result.code == "VALIDATION_FAILED"
    assert result.status == "failure" and result.candidate is None


def test_adapter_failure_is_sanitized_and_fallback_is_revalidated(context):
    trip, bound = context
    result = run_agent_workflow(
        trip,
        bound,
        ScriptedAdapter([]),
        deadline_monotonic=10,
        monotonic=lambda: 0,
    )
    assert result.status == "fallback" and result.code == "ADAPTER_FAILED"
    changed = replace(trip, budget=Money(1, "CAD"))
    result = run_agent_workflow(
        changed,
        bound,
        ScriptedAdapter([]),
        deadline_monotonic=10,
        monotonic=lambda: 0,
    )
    assert result.status == "failure" and result.candidate is None


@pytest.mark.parametrize("ticks", [(10,), (0, 10), (0, 0, 10)])
def test_deadline_before_after_adapter_and_after_tool(context, ticks):
    trip, bound = context
    clock = iter(ticks)
    result = run_agent_workflow(
        trip,
        bound,
        ScriptedAdapter([action("validate_candidate")]),
        deadline_monotonic=10,
        monotonic=lambda: next(clock),
    )
    assert result.status == "fallback" and result.code == "DEADLINE_EXCEEDED"


def test_tool_failure_does_not_leak_exception(context, monkeypatch):
    trip, bound = context

    def broken(*args):
        raise RuntimeError("secret-canary")

    monkeypatch.setattr("trippilot.services.agent_workflow._execute_tool", broken)
    result = run_agent_workflow(
        trip,
        bound,
        ScriptedAdapter([action("inspect_candidate")]),
        deadline_monotonic=10,
        monotonic=lambda: 0,
    )
    assert result.code == "TOOL_FAILED"
    assert "secret-canary" not in repr(result)
