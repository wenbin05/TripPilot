from __future__ import annotations

import json
import socket
from pathlib import Path

import pytest
from pydantic import ValidationError

from trippilot.evaluation import (
    CoordinatorEvaluationManifest,
    EvaluationCaseBehavior,
    EvaluationRunOutcome,
    load_coordinator_evaluation_manifest,
    run_evaluation_case,
    validate_evaluation_manifest,
)
from trippilot.providers import JsonMockTravelDataProvider
from trippilot.services import (
    CoordinatorAdapterFailure,
    CoordinatorAdapterFailureCode,
    CoordinatorAdapterMetadata,
    CoordinatorAdapterResult,
    CoordinatorAdapterSuccess,
    CoordinatorContext,
    CoordinatorDecision,
    CoordinatorRetryFeedback,
)

REPOSITORY_ROOT = Path(__file__).parents[3]
MANIFEST_PATH = REPOSITORY_ROOT / "data/evaluation/coordinator-eval-v1.json"
FIXTURE_PATH = REPOSITORY_ROOT / "data/mock/kingston-toronto-v1.json"


@pytest.fixture(scope="module")
def manifest() -> CoordinatorEvaluationManifest:
    return load_coordinator_evaluation_manifest(MANIFEST_PATH)


@pytest.fixture(scope="module")
def provider() -> JsonMockTravelDataProvider:
    return JsonMockTravelDataProvider(FIXTURE_PATH)


class SelectingAdapter:
    def decide(
        self,
        context: CoordinatorContext,
        *,
        deadline_monotonic: float,
        retry_feedback: CoordinatorRetryFeedback | None = None,
    ) -> CoordinatorAdapterResult:
        del deadline_monotonic, retry_feedback
        return CoordinatorAdapterSuccess(
            CoordinatorDecision(
                contract_version="coordinator-decision-v1",
                status="selection",
                selected_candidate_id=context.candidates[-1].candidate_id,
                interpreted_preference_tags=(),
                prioritized_interests=(),
                abstention_reason=None,
            ),
            CoordinatorAdapterMetadata(
                prompt_id="trippilot-coordinator-prompt-v1",
                requested_model="gpt-5.6-terra",
                returned_model="gpt-5.6-terra-2026-08-01",
                input_tokens=120,
                output_tokens=40,
                latency_ms=250,
                estimated_cost_micro_usd=900,
            ),
        )


class RepairingAdapter:
    def __init__(self) -> None:
        self.calls: list[CoordinatorRetryFeedback | None] = []

    def decide(
        self,
        context: CoordinatorContext,
        *,
        deadline_monotonic: float,
        retry_feedback: CoordinatorRetryFeedback | None = None,
    ) -> CoordinatorAdapterResult:
        del deadline_monotonic
        self.calls.append(retry_feedback)
        if len(self.calls) == 1:
            return CoordinatorAdapterFailure(
                CoordinatorAdapterFailureCode.OUTPUT_INVALID,
                CoordinatorAdapterMetadata(
                    prompt_id="trippilot-coordinator-prompt-v1",
                    requested_model="gpt-5.6-terra",
                    returned_model="gpt-5.6-terra-2026-08-01",
                    input_tokens=100,
                    output_tokens=20,
                    latency_ms=100,
                    estimated_cost_micro_usd=550,
                ),
            )
        return CoordinatorAdapterSuccess(
            CoordinatorDecision(
                contract_version="coordinator-decision-v1",
                status="selection",
                selected_candidate_id=context.candidates[0].candidate_id,
                interpreted_preference_tags=(),
                prioritized_interests=(),
                abstention_reason=None,
            ),
            CoordinatorAdapterMetadata(
                prompt_id="trippilot-coordinator-prompt-v1",
                requested_model="gpt-5.6-terra",
                returned_model="gpt-5.6-terra-2026-08-01",
                input_tokens=120,
                output_tokens=40,
                latency_ms=250,
                estimated_cost_micro_usd=900,
            ),
        )


def test_manifest_freezes_all_protocol_cohorts_and_repetitions(
    manifest: CoordinatorEvaluationManifest,
) -> None:
    assert len(manifest.cases) == 26
    model_cases = tuple(
        case
        for case in manifest.cases
        if case.expected_behavior is EvaluationCaseBehavior.MODEL_EXERCISED
    )
    assert len(model_cases) == 20
    assert sum(case.repeated_runs for case in model_cases) == 100
    assert (
        sum(
            case.expected_behavior is EvaluationCaseBehavior.SCHEMA_STUB_ACCEPTED
            for case in manifest.cases
        )
        == 3
    )
    assert (
        sum(
            case.expected_behavior is EvaluationCaseBehavior.SCHEMA_REJECTED
            for case in manifest.cases
        )
        == 1
    )


def test_manifest_validates_offline_against_frozen_candidates(
    manifest: CoordinatorEvaluationManifest,
    provider: JsonMockTravelDataProvider,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def reject_network(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("evaluation manifest validation must remain offline")

    monkeypatch.setattr(socket, "socket", reject_network)

    result = validate_evaluation_manifest(manifest, provider)

    assert len(result.cases) == 26
    assert result.fixture_snapshot_version == "2026-08-01.v1"
    assert all(
        item.candidate_count >= 2
        for item in result.cases
        if item.behavior
        in {
            EvaluationCaseBehavior.MODEL_EXERCISED,
            EvaluationCaseBehavior.SCHEMA_STUB_ACCEPTED,
        }
    )
    assert {
        item.planning_failure_code
        for item in result.cases
        if item.planning_failure_code
    } == {"INSUFFICIENT_BUDGET", "UNSUPPORTED_ROUTE"}


def test_manifest_rejects_unknown_fields() -> None:
    payload = json.loads(MANIFEST_PATH.read_text("utf-8"))
    payload["secret_notes"] = "must not be accepted"

    with pytest.raises(ValidationError, match="Extra inputs"):
        CoordinatorEvaluationManifest.model_validate(payload)


def test_manifest_detects_candidate_metric_drift(
    manifest: CoordinatorEvaluationManifest,
    provider: JsonMockTravelDataProvider,
) -> None:
    changed_case = manifest.cases[0].model_copy(
        update={"candidate_set_digest": "0" * 64}
    )
    changed = manifest.model_copy(update={"cases": (changed_case, *manifest.cases[1:])})

    with pytest.raises(ValueError, match="candidate digest changed"):
        validate_evaluation_manifest(changed, provider)


def test_offline_runner_records_three_arms_without_sensitive_payloads(
    manifest: CoordinatorEvaluationManifest,
    provider: JsonMockTravelDataProvider,
) -> None:
    record = run_evaluation_case(
        manifest,
        "preference-budget-buffer",
        provider,
        SelectingAdapter(),
        code_revision="ae32ef9",
        run_number=1,
        monotonic=lambda: 100.0,
    )

    assert record.outcome is EvaluationRunOutcome.COORDINATOR_SELECTION
    assert record.baseline_candidate_id == "candidate_01"
    assert record.fixed_ranker_candidate_id == "candidate_01"
    assert record.selected_candidate_id == "candidate_02"
    assert record.attempt_count == 1
    assert record.returned_models == ("gpt-5.6-terra-2026-08-01",)
    assert record.input_tokens == 120
    assert record.output_tokens == 40
    assert record.latency_ms == 250
    assert record.estimated_cost_micro_usd == 900
    serialized = record.model_dump_json()
    assert "Keep as much" not in serialized
    assert "preference_notes" not in serialized
    assert "proposed_itinerary" not in serialized
    assert "provider_snapshot" not in serialized


def test_offline_runner_records_one_bounded_repair(
    manifest: CoordinatorEvaluationManifest,
    provider: JsonMockTravelDataProvider,
) -> None:
    adapter = RepairingAdapter()

    record = run_evaluation_case(
        manifest,
        "schema-notes-missing",
        provider,
        adapter,
        code_revision="ae32ef9",
        run_number=1,
        monotonic=lambda: 100.0,
    )

    assert record.attempt_count == 2
    assert record.selected_candidate_id == "candidate_01"
    assert adapter.calls[0] is None
    assert adapter.calls[1] is not None
    assert adapter.calls[1].code == "OUTPUT_SCHEMA_INVALID"
    assert record.returned_models == (
        "gpt-5.6-terra-2026-08-01",
        "gpt-5.6-terra-2026-08-01",
    )
    assert record.input_tokens == 220
    assert record.output_tokens == 60
    assert record.latency_ms == 350
    assert record.estimated_cost_micro_usd == 1_450


@pytest.mark.parametrize(
    "scenario_id", ["failure-impossible-budget", "schema-notes-over-limit"]
)
def test_runner_stops_cases_that_must_not_call_a_model(
    manifest: CoordinatorEvaluationManifest,
    provider: JsonMockTravelDataProvider,
    scenario_id: str,
) -> None:
    with pytest.raises(ValueError, match="only accepted candidate cases"):
        run_evaluation_case(
            manifest,
            scenario_id,
            provider,
            SelectingAdapter(),
            code_revision="ae32ef9",
            run_number=1,
        )
