from __future__ import annotations

import json
from http import HTTPStatus

import pytest

from trippilot.domain import Interest, Pace
from trippilot.services import (
    COORDINATOR_MODEL,
    MAX_OUTPUT_TOKENS,
    OPENAI_RESPONSES_URL,
    ActivityInterestCounts,
    CandidateSummary,
    CoordinatorAdapterFailure,
    CoordinatorAdapterFailureCode,
    CoordinatorAdapterSuccess,
    CoordinatorContext,
    CoordinatorRetryCode,
    CoordinatorRetryFeedback,
    CoordinatorTransportModeTag,
    DaypartActivityCounts,
    OpenAICoordinatorAdapter,
    OpenAICoordinatorConfig,
)


def _summary(candidate_id: str, cost: int) -> CandidateSummary:
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


def _context() -> CoordinatorContext:
    return CoordinatorContext(
        contract_version="coordinator-context-v1",
        interests=(Interest.ARTS_CULTURE,),
        pace=Pace.BALANCED,
        preference_notes="Prefer the less expensive proposal",
        candidates=(_summary("candidate_A", 1_000), _summary("candidate_B", 1_500)),
    )


def _provider_response(output: str) -> bytes:
    return json.dumps(
        {
            "status": "completed",
            "model": "gpt-5.6-terra-2026-08-01",
            "usage": {"input_tokens": 120, "output_tokens": 40, "total_tokens": 160},
            "output": [
                {
                    "type": "message",
                    "content": [{"type": "output_text", "text": output}],
                }
            ],
        }
    ).encode()


def _decision(candidate_id: str = "candidate_A") -> str:
    return json.dumps(
        {
            "contract_version": "coordinator-decision-v1",
            "status": "selection",
            "selected_candidate_id": candidate_id,
            "interpreted_preference_tags": ["lower_cost"],
            "prioritized_interests": [],
            "abstention_reason": None,
        }
    )


def test_adapter_sends_one_bounded_tool_free_structured_request() -> None:
    captured: dict[str, object] = {}

    def post(
        url: str, headers: object, body: bytes, timeout: float
    ) -> tuple[int, bytes]:
        captured.update(url=url, headers=headers, body=body, timeout=timeout)
        return HTTPStatus.OK, _provider_response(_decision())

    adapter = OpenAICoordinatorAdapter(
        OpenAICoordinatorConfig(api_key="test-secret"),
        http_post=post,  # type: ignore[arg-type]
        monotonic=lambda: 10.0,
    )

    result = adapter.decide(_context(), deadline_monotonic=15.0)

    assert isinstance(result, CoordinatorAdapterSuccess)
    assert result.decision.selected_candidate_id == "candidate_A"
    assert result.metadata is not None
    assert result.metadata.returned_model == "gpt-5.6-terra-2026-08-01"
    assert result.metadata.input_tokens == 120
    assert result.metadata.output_tokens == 40
    assert result.metadata.estimated_cost_micro_usd == 720
    assert captured["url"] == OPENAI_RESPONSES_URL
    assert captured["timeout"] == 5.0
    payload = json.loads(captured["body"])  # type: ignore[arg-type]
    assert payload["model"] == COORDINATOR_MODEL
    assert payload["reasoning"] == {"effort": "low"}
    assert payload["max_output_tokens"] == MAX_OUTPUT_TOKENS
    assert payload["store"] is False
    assert payload["tools"] == []
    assert payload["text"]["format"]["strict"] is True
    assert "test-secret" not in captured["body"].decode()  # type: ignore[union-attr]


def test_retry_request_contains_only_stable_feedback() -> None:
    bodies: list[bytes] = []

    def post(
        _url: str, _headers: object, body: bytes, _timeout: float
    ) -> tuple[int, bytes]:
        bodies.append(body)
        return HTTPStatus.OK, _provider_response(_decision())

    adapter = OpenAICoordinatorAdapter(
        OpenAICoordinatorConfig(api_key="test-secret"),
        http_post=post,  # type: ignore[arg-type]
        monotonic=lambda: 1.0,
    )
    feedback = CoordinatorRetryFeedback(
        contract_version="coordinator-retry-v1",
        code=CoordinatorRetryCode.OUTPUT_SCHEMA_INVALID,
        candidate_ids=("candidate_A", "candidate_B"),
    )

    adapter.decide(_context(), deadline_monotonic=2.0, retry_feedback=feedback)

    request_text = bodies[0].decode()
    assert "coordinator-retry-v1" in request_text
    assert "raw_output" not in request_text
    assert "prompt" not in request_text


@pytest.mark.parametrize(
    ("status", "body", "expected"),
    [
        (
            HTTPStatus.TOO_MANY_REQUESTS,
            b"private provider detail",
            CoordinatorAdapterFailureCode.RATE_LIMITED,
        ),
        (
            HTTPStatus.INTERNAL_SERVER_ERROR,
            b"private provider detail",
            CoordinatorAdapterFailureCode.PROVIDER_ERROR,
        ),
        (
            HTTPStatus.OK,
            b"not-json",
            CoordinatorAdapterFailureCode.OUTPUT_INVALID,
        ),
        (
            HTTPStatus.OK,
            json.dumps(
                {
                    "status": "completed",
                    "model": "gpt-5.6-terra",
                    "usage": {"input_tokens": 120, "output_tokens": 10},
                    "output": [
                        {
                            "type": "message",
                            "content": [{"type": "refusal", "refusal": "private"}],
                        }
                    ],
                }
            ).encode(),
            CoordinatorAdapterFailureCode.REFUSAL,
        ),
    ],
)
def test_provider_failures_return_stable_codes_only(
    status: int, body: bytes, expected: CoordinatorAdapterFailureCode
) -> None:
    adapter = OpenAICoordinatorAdapter(
        OpenAICoordinatorConfig(api_key="test-secret"),
        http_post=lambda *_args: (status, body),
        monotonic=lambda: 1.0,
    )

    result = adapter.decide(_context(), deadline_monotonic=2.0)

    assert isinstance(result, CoordinatorAdapterFailure)
    assert result.code is expected
    if expected is CoordinatorAdapterFailureCode.REFUSAL:
        assert result.metadata is not None
        assert result.metadata.input_tokens == 120
    assert not hasattr(result, "message")


def test_expired_deadline_stops_before_transport() -> None:
    called = False

    def post(*_args: object) -> tuple[int, bytes]:
        nonlocal called
        called = True
        return HTTPStatus.OK, _provider_response(_decision())

    adapter = OpenAICoordinatorAdapter(
        OpenAICoordinatorConfig(api_key="test-secret"),
        http_post=post,  # type: ignore[arg-type]
        monotonic=lambda: 2.0,
    )

    assert adapter.decide(_context(), deadline_monotonic=2.0) == (
        CoordinatorAdapterFailure(CoordinatorAdapterFailureCode.TIMEOUT)
    )
    assert called is False


def test_invalid_structured_output_retains_only_safe_usage_metadata() -> None:
    adapter = OpenAICoordinatorAdapter(
        OpenAICoordinatorConfig(api_key="test-secret"),
        http_post=lambda *_args: (
            HTTPStatus.OK,
            _provider_response('{"private_raw_output":"must not escape"}'),
        ),
        monotonic=lambda: 1.0,
    )

    result = adapter.decide(_context(), deadline_monotonic=2.0)

    assert isinstance(result, CoordinatorAdapterFailure)
    assert result.code is CoordinatorAdapterFailureCode.OUTPUT_INVALID
    assert result.metadata is not None
    assert result.metadata.input_tokens == 120
    assert result.metadata.output_tokens == 40
    assert not hasattr(result, "raw_output")


def test_incomplete_response_retains_usage_and_fails_closed() -> None:
    body = _provider_response(_decision()).replace(
        b'"status": "completed"', b'"status": "incomplete"'
    )
    adapter = OpenAICoordinatorAdapter(
        OpenAICoordinatorConfig(api_key="test-secret"),
        http_post=lambda *_args: (HTTPStatus.OK, body),
        monotonic=lambda: 1.0,
    )

    result = adapter.decide(_context(), deadline_monotonic=2.0)

    assert isinstance(result, CoordinatorAdapterFailure)
    assert result.code is CoordinatorAdapterFailureCode.OUTPUT_INVALID
    assert result.metadata is not None
    assert result.metadata.estimated_cost_micro_usd == 720


def test_configuration_rejects_silent_model_substitution() -> None:
    with pytest.raises(ValueError, match="allowlisted"):
        OpenAICoordinatorConfig(api_key="test-secret", model="gpt-5.6-sol")


@pytest.mark.parametrize(
    "api_key", ["", "short", "test-secret\nInjected: true", "秘密-key"]
)
def test_configuration_rejects_unsafe_secret_header_values(api_key: str) -> None:
    with pytest.raises(ValueError, match="header"):
        OpenAICoordinatorConfig(api_key=api_key)
