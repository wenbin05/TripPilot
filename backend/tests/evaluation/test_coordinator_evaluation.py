from __future__ import annotations

import json
import socket
from dataclasses import replace
from pathlib import Path

import pytest
from pydantic import ValidationError

from trippilot.evaluation import (
    CoordinatorEvaluationManifest,
    EvaluationCaseBehavior,
    EvaluationRunOutcome,
    load_coordinator_evaluation_manifest,
    load_evaluation_run_records,
    run_evaluation_case,
    run_live_evaluation_batch,
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
V2_MANIFEST_PATH = REPOSITORY_ROOT / "data/evaluation/coordinator-eval-v2.json"
V3_MANIFEST_PATH = REPOSITORY_ROOT / "data/evaluation/coordinator-eval-v3.json"
FIXTURE_PATH = REPOSITORY_ROOT / "data/mock/kingston-toronto-v1.json"


@pytest.fixture(scope="module")
def manifest() -> CoordinatorEvaluationManifest:
    return load_coordinator_evaluation_manifest(MANIFEST_PATH)


@pytest.fixture(scope="module")
def manifest_v2() -> CoordinatorEvaluationManifest:
    return load_coordinator_evaluation_manifest(V2_MANIFEST_PATH)


@pytest.fixture(scope="module")
def manifest_v3() -> CoordinatorEvaluationManifest:
    return load_coordinator_evaluation_manifest(V3_MANIFEST_PATH)


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


class CountingSelectingAdapter(SelectingAdapter):
    def __init__(self) -> None:
        self.call_count = 0

    def decide(
        self,
        context: CoordinatorContext,
        *,
        deadline_monotonic: float,
        retry_feedback: CoordinatorRetryFeedback | None = None,
    ) -> CoordinatorAdapterResult:
        self.call_count += 1
        return super().decide(
            context,
            deadline_monotonic=deadline_monotonic,
            retry_feedback=retry_feedback,
        )


class V2SelectingAdapter(SelectingAdapter):
    def decide(
        self,
        context: CoordinatorContext,
        *,
        deadline_monotonic: float,
        retry_feedback: CoordinatorRetryFeedback | None = None,
    ) -> CoordinatorAdapterResult:
        result = super().decide(
            context,
            deadline_monotonic=deadline_monotonic,
            retry_feedback=retry_feedback,
        )
        assert isinstance(result, CoordinatorAdapterSuccess)
        assert result.metadata is not None
        return CoordinatorAdapterSuccess(
            result.decision,
            replace(
                result.metadata,
                prompt_id="trippilot-coordinator-prompt-v2",
            ),
        )


class CountingV2SelectingAdapter(V2SelectingAdapter):
    def __init__(self) -> None:
        self.call_count = 0

    def decide(
        self,
        context: CoordinatorContext,
        *,
        deadline_monotonic: float,
        retry_feedback: CoordinatorRetryFeedback | None = None,
    ) -> CoordinatorAdapterResult:
        self.call_count += 1
        return super().decide(
            context,
            deadline_monotonic=deadline_monotonic,
            retry_feedback=retry_feedback,
        )


class FailIfCalledAdapter:
    def decide(
        self,
        context: CoordinatorContext,
        *,
        deadline_monotonic: float,
        retry_feedback: CoordinatorRetryFeedback | None = None,
    ) -> CoordinatorAdapterResult:
        del context, deadline_monotonic, retry_feedback
        raise AssertionError("a complete checkpoint must not call the adapter")


class TimeoutWithoutMetadataAdapter:
    def decide(
        self,
        context: CoordinatorContext,
        *,
        deadline_monotonic: float,
        retry_feedback: CoordinatorRetryFeedback | None = None,
    ) -> CoordinatorAdapterResult:
        del context, deadline_monotonic, retry_feedback
        return CoordinatorAdapterFailure(CoordinatorAdapterFailureCode.TIMEOUT)


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


def test_v2_manifest_changes_only_the_versioned_model_configuration(
    manifest: CoordinatorEvaluationManifest,
    manifest_v2: CoordinatorEvaluationManifest,
    provider: JsonMockTravelDataProvider,
) -> None:
    assert manifest_v2.contract_version == "coordinator-eval-v2"
    assert manifest_v2.prompt_id == "trippilot-coordinator-prompt-v2"
    assert manifest_v2.reasoning_effort == "none"
    assert manifest_v2.request_profiles == manifest.request_profiles
    assert manifest_v2.cases == manifest.cases
    assert (
        validate_evaluation_manifest(manifest_v2, provider).contract_version
        == "coordinator-eval-validation-v2"
    )


def test_v2_manifest_rejects_a_mismatched_reasoning_configuration() -> None:
    payload = json.loads(V2_MANIFEST_PATH.read_text("utf-8"))
    payload["reasoning_effort"] = "low"

    with pytest.raises(ValidationError, match="configuration is inconsistent"):
        CoordinatorEvaluationManifest.model_validate_json(json.dumps(payload))


def test_v3_manifest_restores_low_reasoning_without_changing_cases(
    manifest_v2: CoordinatorEvaluationManifest,
    manifest_v3: CoordinatorEvaluationManifest,
    provider: JsonMockTravelDataProvider,
) -> None:
    assert manifest_v3.contract_version == "coordinator-eval-v3"
    assert manifest_v3.prompt_id == "trippilot-coordinator-prompt-v2"
    assert manifest_v3.reasoning_effort == "low"
    assert manifest_v3.request_profiles == manifest_v2.request_profiles
    assert manifest_v3.cases == manifest_v2.cases
    assert (
        validate_evaluation_manifest(manifest_v3, provider).contract_version
        == "coordinator-eval-validation-v2"
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


def test_v2_run_records_end_to_end_elapsed_time_and_complete_cost(
    manifest_v2: CoordinatorEvaluationManifest,
    provider: JsonMockTravelDataProvider,
) -> None:
    clock = iter((100.0, 101.0, 101.0, 103.5))

    record = run_evaluation_case(
        manifest_v2,
        "preference-budget-buffer",
        provider,
        V2SelectingAdapter(),
        code_revision="abcdef2",
        run_number=1,
        monotonic=lambda: next(clock),
    )

    assert record.contract_version == "coordinator-eval-run-v2"
    assert record.prompt_id == "trippilot-coordinator-prompt-v2"
    assert record.coordinator_elapsed_ms == 3_500
    assert record.cost_complete is True
    payload = json.loads(record.model_dump_json())
    payload["cost_complete"] = False
    with pytest.raises(ValidationError, match="must match attempt metadata"):
        type(record).model_validate_json(json.dumps(payload))


def test_v2_timeout_preserves_elapsed_time_and_marks_cost_incomplete(
    manifest_v2: CoordinatorEvaluationManifest,
    provider: JsonMockTravelDataProvider,
) -> None:
    clock = iter((100.0, 101.0, 101.0, 104.0))

    record = run_evaluation_case(
        manifest_v2,
        "baseline-one-day",
        provider,
        TimeoutWithoutMetadataAdapter(),
        code_revision="abcdef2",
        run_number=1,
        monotonic=lambda: next(clock),
    )

    assert record.outcome is EvaluationRunOutcome.DETERMINISTIC_FALLBACK
    assert record.fallback_code == "MODEL_TIMEOUT"
    assert record.coordinator_elapsed_ms == 4_000
    assert record.cost_complete is False
    assert record.estimated_cost_micro_usd is None


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


def test_live_batch_checkpoints_all_runs_and_resumes_without_model_calls(
    manifest_v2: CoordinatorEvaluationManifest,
    provider: JsonMockTravelDataProvider,
    tmp_path: Path,
) -> None:
    output = tmp_path / "sanitized-runs.json"
    adapter = CountingV2SelectingAdapter()

    summary = run_live_evaluation_batch(
        manifest_v2,
        provider,
        adapter,
        code_revision="abcdef1",
        output_path=output,
    )

    assert summary.expected_run_count == 100
    assert summary.contract_version == "coordinator-eval-batch-v2"
    assert summary.completed_run_count == 100
    assert summary.coordinator_selection_count == 100
    assert summary.first_attempt_selection_count == 100
    assert summary.cost_complete_run_count == 100
    assert adapter.call_count == 100
    records = load_evaluation_run_records(output)
    assert len(records) == 100
    assert len({(record.scenario_id, record.run_number) for record in records}) == 100
    serialized = output.read_text("utf-8")
    assert "preference_notes" not in serialized
    assert "provider_snapshot" not in serialized
    assert "proposed_itinerary" not in serialized

    resumed = run_live_evaluation_batch(
        manifest_v2,
        provider,
        FailIfCalledAdapter(),
        code_revision="abcdef1",
        output_path=output,
    )

    assert resumed == summary


def test_live_batch_rejects_a_checkpoint_from_another_revision(
    manifest: CoordinatorEvaluationManifest,
    provider: JsonMockTravelDataProvider,
    tmp_path: Path,
) -> None:
    output = tmp_path / "sanitized-runs.json"
    record = run_evaluation_case(
        manifest,
        "baseline-one-day",
        provider,
        SelectingAdapter(),
        code_revision="abcdef1",
        run_number=1,
        monotonic=lambda: 100.0,
    )
    output.write_text(f"[{record.model_dump_json()}]", "utf-8")

    with pytest.raises(ValueError, match="does not match the frozen run"):
        run_live_evaluation_batch(
            manifest,
            provider,
            FailIfCalledAdapter(),
            code_revision="abcdef2",
            output_path=output,
        )


def test_v3_filtered_live_batch_runs_exact_scenarios_and_resumes(
    manifest_v3: CoordinatorEvaluationManifest,
    provider: JsonMockTravelDataProvider,
    tmp_path: Path,
) -> None:
    output = tmp_path / "sanitized-v3-diagnostic.json"
    adapter = CountingV2SelectingAdapter()
    scenarios = ("preference-conflicting", "preference-shorter-transfers")

    summary = run_live_evaluation_batch(
        manifest_v3,
        provider,
        adapter,
        code_revision="abcdef3",
        output_path=output,
        scenario_ids=scenarios,
    )

    assert summary.contract_version == "coordinator-eval-batch-v2"
    assert summary.expected_run_count == 10
    assert summary.completed_run_count == 10
    assert summary.cost_complete_run_count == 10
    assert adapter.call_count == 10
    records = load_evaluation_run_records(output)
    assert tuple(dict.fromkeys(record.scenario_id for record in records)) == (
        "preference-shorter-transfers",
        "preference-conflicting",
    )
    assert all(
        record.contract_version == "coordinator-eval-run-v2" for record in records
    )
    assert {(record.scenario_id, record.run_number) for record in records} == {
        (scenario_id, run_number)
        for scenario_id in scenarios
        for run_number in range(1, 6)
    }

    resumed = run_live_evaluation_batch(
        manifest_v3,
        provider,
        FailIfCalledAdapter(),
        code_revision="abcdef3",
        output_path=output,
        scenario_ids=scenarios,
    )

    assert resumed == summary


@pytest.mark.parametrize(
    "scenario_ids",
    [
        (),
        ("preference-conflicting", "preference-conflicting"),
        ("not-a-frozen-scenario",),
        ("schema-notes-over-limit",),
    ],
)
def test_filtered_live_batch_rejects_invalid_scenario_filters(
    manifest_v3: CoordinatorEvaluationManifest,
    provider: JsonMockTravelDataProvider,
    tmp_path: Path,
    scenario_ids: tuple[str, ...],
) -> None:
    with pytest.raises(ValueError, match="scenario filter"):
        run_live_evaluation_batch(
            manifest_v3,
            provider,
            FailIfCalledAdapter(),
            code_revision="abcdef3",
            output_path=tmp_path / "must-not-run.json",
            scenario_ids=scenario_ids,
        )
