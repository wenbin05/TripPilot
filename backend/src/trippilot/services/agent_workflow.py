"""Offline action/observation loop; no hosted model or public API wiring."""

from __future__ import annotations

import json
import math
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal, Protocol, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from trippilot.domain import (
    Interest,
    Pace,
    TripRequest,
    ViolationCode,
    validate_itinerary,
)

from .coordinator_context import BoundCoordinatorContext
from .coordinator_schemas import CandidateSummary
from .models import CanonicalCandidate

MAX_STEPS = 5
MAX_TOOLS = 4
MAX_ACTION_BYTES = 2_048
ActionName = Literal["inspect_candidate", "validate_candidate", "finish"]
ErrorCode = Literal[
    "INVALID_ACTION",
    "UNKNOWN_CANDIDATE",
    "VALIDATION_REQUIRED",
    "VALIDATION_FAILED",
    "ADAPTER_FAILED",
    "TOOL_FAILED",
    "DEADLINE_EXCEEDED",
    "STEP_LIMIT",
    "TOOL_LIMIT",
]


class WorkflowSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class AgentAction(WorkflowSchema):
    action: ActionName
    candidate_id: str = Field(pattern=r"^candidate_[A-Za-z0-9_-]{1,64}$")


class ToolObservation(WorkflowSchema):
    action: ActionName
    candidate_id: str = Field(pattern=r"^candidate_[A-Za-z0-9_-]{1,64}$")
    summary: CandidateSummary | None = None
    valid: bool | None = None
    violations: tuple[ViolationCode, ...] = ()

    @model_validator(mode="after")
    def consistent_payload(self) -> Self:
        if self.action == "inspect_candidate":
            if (
                self.summary is None
                or self.summary.candidate_id != self.candidate_id
                or self.valid is not None
                or self.violations
            ):
                raise ValueError("invalid inspection observation")
        elif self.action != "validate_candidate" or (
            self.summary is not None
            or self.valid is None
            or self.valid == bool(self.violations)
        ):
            raise ValueError("invalid validation observation")
        return self


class AgentState(WorkflowSchema):
    contract_version: Literal["agent-state-v1"] = "agent-state-v1"
    candidate_ids: tuple[str, ...] = Field(min_length=2, max_length=5)
    interests: tuple[Interest, ...]
    pace: Pace
    preference_notes: str | None = Field(max_length=300)
    observations: tuple[ToolObservation, ...] = Field(default=(), max_length=4)
    feedback: ErrorCode | None = None


class AgentAdapter(Protocol):
    def next_action(self, state: AgentState, *, deadline_monotonic: float) -> str:
        """Return one JSON action; honor the supplied absolute deadline."""
        ...


@dataclass(frozen=True, slots=True)
class AgentRunResult:
    status: Literal["selected", "fallback", "failure"]
    candidate: CanonicalCandidate | None
    code: ErrorCode | None
    steps: int
    tool_calls: int
    invalid_actions: int


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


def _reject_constant(value: str) -> object:
    raise ValueError("non-finite JSON")


def parse_agent_action(raw: object) -> AgentAction | None:
    if not isinstance(raw, str) or len(raw) > MAX_ACTION_BYTES:
        return None
    try:
        if len(raw.encode("utf-8")) > MAX_ACTION_BYTES:
            return None
        json.loads(
            raw, object_pairs_hook=_unique_object, parse_constant=_reject_constant
        )
        return AgentAction.model_validate_json(raw)
    except ValueError, TypeError, RecursionError:
        return None


def _validate(request: TripRequest, candidate: CanonicalCandidate) -> bool:
    return validate_itinerary(
        request, candidate.itinerary, candidate.provider_snapshot
    ).is_valid


def _execute_tool(
    action: AgentAction, request: TripRequest, bound: BoundCoordinatorContext
) -> ToolObservation:
    candidate = bound.resolve(action.candidate_id)
    if candidate is None:
        raise ValueError("unknown candidate")
    if action.action == "inspect_candidate":
        summary = next(
            item
            for item in bound.context.candidates
            if item.candidate_id == action.candidate_id
        )
        return ToolObservation(
            action=action.action, candidate_id=action.candidate_id, summary=summary
        )
    report = validate_itinerary(
        request, candidate.itinerary, candidate.provider_snapshot
    )
    return ToolObservation(
        action=action.action,
        candidate_id=action.candidate_id,
        valid=report.is_valid,
        violations=tuple(dict.fromkeys(item.code for item in report.violations)),
    )


def run_agent_workflow(
    request: TripRequest,
    bound: BoundCoordinatorContext,
    adapter: AgentAdapter,
    *,
    deadline_monotonic: float,
    monotonic: Callable[[], float] = time.monotonic,
) -> AgentRunResult:
    """Consume bounded actions with one repair and freshly validated fallback."""
    if not math.isfinite(deadline_monotonic):
        raise ValueError("deadline must be finite")
    state = AgentState(
        candidate_ids=tuple(item.candidate_id for item in bound.context.candidates),
        interests=bound.context.interests,
        pace=bound.context.pace,
        preference_notes=bound.context.preference_notes,
    )
    steps = tool_calls = invalid_actions = 0

    def stop(code: ErrorCode) -> AgentRunResult:
        candidate = bound.resolve(state.candidate_ids[0])
        try:
            valid = candidate is not None and _validate(request, candidate)
        except Exception:
            valid = False
        return AgentRunResult(
            "fallback" if valid else "failure",
            candidate if valid else None,
            code,
            steps,
            tool_calls,
            invalid_actions,
        )

    for _ in range(MAX_STEPS):
        if monotonic() >= deadline_monotonic:
            return stop("DEADLINE_EXCEEDED")
        steps += 1
        try:
            raw = adapter.next_action(state, deadline_monotonic=deadline_monotonic)
        except Exception:
            return stop("ADAPTER_FAILED")
        if monotonic() >= deadline_monotonic:
            return stop("DEADLINE_EXCEEDED")
        action = parse_agent_action(raw)
        error: ErrorCode | None = None
        if action is None:
            error = "INVALID_ACTION"
        elif action.candidate_id not in state.candidate_ids:
            error = "UNKNOWN_CANDIDATE"
        elif action.action == "finish" and not any(
            item.candidate_id == action.candidate_id and item.valid is True
            for item in state.observations
        ):
            error = "VALIDATION_REQUIRED"
        if error is not None:
            invalid_actions += 1
            if invalid_actions > 1:
                return stop(error)
            state = state.model_copy(update={"feedback": error})
            continue
        assert action is not None
        if action.action == "finish":
            candidate = bound.resolve(action.candidate_id)
            try:
                valid = candidate is not None and _validate(request, candidate)
            except Exception:
                return stop("TOOL_FAILED")
            if monotonic() >= deadline_monotonic:
                return stop("DEADLINE_EXCEEDED")
            if not valid:
                return stop("VALIDATION_FAILED")
            return AgentRunResult(
                "selected", candidate, None, steps, tool_calls, invalid_actions
            )
        if tool_calls >= MAX_TOOLS:
            return stop("TOOL_LIMIT")
        tool_calls += 1
        try:
            observation = _execute_tool(action, request, bound)
        except Exception:
            return stop("TOOL_FAILED")
        if monotonic() >= deadline_monotonic:
            return stop("DEADLINE_EXCEEDED")
        state = state.model_copy(
            update={
                "observations": (*state.observations, observation),
                "feedback": None,
            }
        )
    return stop("STEP_LIMIT")
