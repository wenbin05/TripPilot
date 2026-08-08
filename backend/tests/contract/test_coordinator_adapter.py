from __future__ import annotations

import socket

import pytest

from trippilot.domain import Interest, Pace
from trippilot.services.coordinator_adapter import (
    CoordinatorAdapter,
    CoordinatorAdapterFailure,
    CoordinatorAdapterFailureCode,
    CoordinatorAdapterResult,
    CoordinatorAdapterSuccess,
)
from trippilot.services.coordinator_schemas import (
    ActivityInterestCounts,
    CandidateSummary,
    CoordinatorContext,
    CoordinatorDecision,
    CoordinatorRetryCode,
    CoordinatorRetryFeedback,
    CoordinatorTransportModeTag,
    DaypartActivityCounts,
)


def summary(candidate_id: str, cost: int) -> CandidateSummary:
    return CandidateSummary(
        contract_version="candidate-summary-v1",
        candidate_id=candidate_id,
        total_estimated_cost_minor=cost,
        remaining_budget_minor=10_000 - cost,
        primary_activity_count=1,
        distinct_primary_activity_count=1,
        total_transfer_minutes=30,
        activity_interest_counts=ActivityInterestCounts(
            food=0,
            arts_culture=1,
            nature=0,
            history=0,
            nightlife=0,
            shopping=0,
            sports=0,
            student_budget=0,
        ),
        requested_interest_coverage_count=1,
        daypart_activity_counts=DaypartActivityCounts(
            morning=1, afternoon=0, evening=0
        ),
        accommodation_style_tags=(),
        transport_mode_tags=(CoordinatorTransportModeTag.COACH,),
    )


def context() -> CoordinatorContext:
    return CoordinatorContext(
        contract_version="coordinator-context-v1",
        interests=(Interest.ARTS_CULTURE,),
        pace=Pace.RELAXED,
        preference_notes=None,
        candidates=(summary("candidate_A", 1_000), summary("candidate_B", 1_500)),
    )


def decision() -> CoordinatorDecision:
    return CoordinatorDecision(
        contract_version="coordinator-decision-v1",
        status="selection",
        selected_candidate_id="candidate_A",
        interpreted_preference_tags=(),
        prioritized_interests=(),
        abstention_reason=None,
    )


class StubAdapter:
    def __init__(self, result: CoordinatorAdapterResult) -> None:
        self.result = result
        self.received: (
            tuple[CoordinatorContext, float, CoordinatorRetryFeedback | None] | None
        ) = None

    def decide(
        self,
        value: CoordinatorContext,
        *,
        deadline_monotonic: float,
        retry_feedback: CoordinatorRetryFeedback | None = None,
    ) -> CoordinatorAdapterResult:
        self.received = (value, deadline_monotonic, retry_feedback)
        return self.result


def test_sdk_neutral_stub_satisfies_runtime_protocol() -> None:
    adapter = StubAdapter(CoordinatorAdapterSuccess(decision()))

    assert isinstance(adapter, CoordinatorAdapter)
    assert adapter.decide(context(), deadline_monotonic=123.5) == (
        CoordinatorAdapterSuccess(decision())
    )
    assert adapter.received == (context(), 123.5, None)


@pytest.mark.parametrize("code", tuple(CoordinatorAdapterFailureCode))
def test_adapter_failures_contain_only_stable_codes(
    code: CoordinatorAdapterFailureCode,
) -> None:
    failure = CoordinatorAdapterFailure(code)

    assert not hasattr(failure, "message")
    assert not hasattr(failure, "raw_output")
    assert failure.allows_retry is (
        code is CoordinatorAdapterFailureCode.OUTPUT_INVALID
    )


def test_retry_feedback_contains_no_raw_provider_content() -> None:
    feedback = CoordinatorRetryFeedback(
        contract_version="coordinator-retry-v1",
        code=CoordinatorRetryCode.OUTPUT_SCHEMA_INVALID,
        candidate_ids=("candidate_A", "candidate_B"),
    )
    adapter = StubAdapter(CoordinatorAdapterSuccess(decision()))

    adapter.decide(context(), deadline_monotonic=321.0, retry_feedback=feedback)

    assert adapter.received == (context(), 321.0, feedback)
    assert "prompt" not in feedback.model_dump()
    assert "raw_output" not in feedback.model_dump()


def test_protocol_and_stub_use_no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def reject_network(*args: object, **kwargs: object) -> None:
        raise AssertionError("network access is forbidden")

    monkeypatch.setattr(socket, "socket", reject_network)
    adapter = StubAdapter(
        CoordinatorAdapterFailure(CoordinatorAdapterFailureCode.NOT_CONFIGURED)
    )

    assert adapter.decide(context(), deadline_monotonic=1.0) == (
        CoordinatorAdapterFailure(CoordinatorAdapterFailureCode.NOT_CONFIGURED)
    )
