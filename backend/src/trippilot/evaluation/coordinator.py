"""Frozen coordinator manifest validation and sanitized offline run records."""

from __future__ import annotations

import hashlib
import json
import re
import time
from collections import Counter
from collections.abc import Callable
from datetime import date
from datetime import time as wall_time
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from trippilot.domain import Interest, Money, Pace, TripRequest, validate_itinerary
from trippilot.providers import TravelDataProvider
from trippilot.services import (
    FIXED_RANKER_ID,
    PLANNER_ID,
    BoundCoordinatorContext,
    CandidateSet,
    CoordinatorAdapter,
    CoordinatorAdapterResult,
    CoordinatorContextBuildFailure,
    CoordinatorRetryFeedback,
    CoordinatorRunFailureCode,
    CoordinatorRunSuccess,
    PlanningFailure,
    PlanningFailureCode,
    PlanningSuccess,
    build_coordinator_context,
    enumerate_trip_candidates,
    normalize_preference_notes,
    plan_trip,
    run_coordinator,
)

ScenarioId = Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9-]{2,63}$")]
ProfileId = Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9-]{2,31}$")]
EvaluationCandidateId = Annotated[
    str, StringConstraints(pattern=r"^candidate_[0-9]{2}$")
]
Sha256Digest = Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]


class EvaluationSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class CoordinatorEvaluationCohort(StrEnum):
    BASELINE_PARITY = "baseline_parity"
    PREFERENCE_RICH = "preference_rich"
    EXPECTED_FAILURE = "expected_failure"
    ADVERSARIAL_SCOPE = "adversarial_scope"
    SCHEMA_BOUNDARY = "schema_boundary"


class EvaluationCaseBehavior(StrEnum):
    MODEL_EXERCISED = "model_exercised"
    DETERMINISTIC_FAILURE = "deterministic_failure"
    SCHEMA_STUB_ACCEPTED = "schema_stub_accepted"
    SCHEMA_REJECTED = "schema_rejected"


class EvaluationRunOutcome(StrEnum):
    COORDINATOR_SELECTION = "coordinator_selection"
    DETERMINISTIC_FALLBACK = "deterministic_fallback"


class CoordinatorEvaluationRequest(EvaluationSchema):
    origin: str = Field(min_length=1, max_length=80)
    destination: str = Field(min_length=1, max_length=80)
    start_date: date
    end_date: date
    travellers: int = Field(ge=1, le=10)
    total_budget_minor: int = Field(ge=0, le=9_223_372_036_854_775_807)
    currency: Literal["CAD"]
    interests: tuple[Interest, ...] = Field(min_length=1, max_length=8)
    pace: Pace
    earliest_activity_time: wall_time
    destination_timezone: str = Field(min_length=1, max_length=64)

    @model_validator(mode="after")
    def require_normalized_request(self) -> Self:
        if (
            self.origin != self.origin.strip()
            or self.destination != self.destination.strip()
        ):
            raise ValueError("evaluation locations must already be normalized")
        if self.end_date < self.start_date:
            raise ValueError("evaluation dates must be ordered")
        if len(set(self.interests)) != len(self.interests):
            raise ValueError("evaluation interests must be unique")
        return self

    def to_domain(self) -> TripRequest:
        return TripRequest(
            origin=self.origin,
            destination=self.destination,
            start_date=self.start_date,
            end_date=self.end_date,
            travellers=self.travellers,
            budget=Money(self.total_budget_minor, self.currency),
            interests=self.interests,
            pace=self.pace,
            earliest_activity_time=self.earliest_activity_time,
            destination_timezone=self.destination_timezone,
        )


class CoordinatorEvaluationCase(EvaluationSchema):
    scenario_id: ScenarioId
    cohort: CoordinatorEvaluationCohort
    request_profile_id: ProfileId
    preference_notes_supplied: bool
    preference_notes_input: str | None = Field(max_length=301)
    normalized_preference_notes: str | None = Field(max_length=300)
    expected_behavior: EvaluationCaseBehavior
    expected_failure_code: PlanningFailureCode | None
    expected_candidate_ids: tuple[EvaluationCandidateId, ...] = Field(max_length=5)
    candidate_set_digest: Sha256Digest | None
    repeated_runs: int = Field(ge=1, le=5)

    @model_validator(mode="after")
    def require_consistent_expectation(self) -> Self:
        if (
            not self.preference_notes_supplied
            and self.preference_notes_input is not None
        ):
            raise ValueError("omitted preference notes cannot have an input value")
        has_candidates = bool(self.expected_candidate_ids)
        if has_candidates != (self.candidate_set_digest is not None):
            raise ValueError("candidate IDs and digest must be present together")
        if self.expected_behavior in {
            EvaluationCaseBehavior.MODEL_EXERCISED,
            EvaluationCaseBehavior.SCHEMA_STUB_ACCEPTED,
        }:
            if not 2 <= len(self.expected_candidate_ids) <= 5:
                raise ValueError("accepted evaluation cases require two to five IDs")
            if self.expected_failure_code is not None:
                raise ValueError("accepted evaluation cases cannot expect failure")
        elif self.expected_behavior is EvaluationCaseBehavior.DETERMINISTIC_FAILURE:
            if has_candidates or self.expected_failure_code is None:
                raise ValueError(
                    "deterministic failures require only a stable failure code"
                )
        elif (
            has_candidates
            or self.expected_failure_code is not None
            or self.normalized_preference_notes is not None
        ):
            raise ValueError("schema rejection cannot freeze derived results")
        if (self.expected_behavior is EvaluationCaseBehavior.MODEL_EXERCISED) != (
            self.repeated_runs == 5
        ):
            raise ValueError("only model-exercising cases use five repeated runs")
        return self


class CoordinatorEvaluationManifest(EvaluationSchema):
    contract_version: Literal["coordinator-eval-v1"]
    fixture_path: Literal["data/mock/kingston-toronto-v1.json"]
    fixture_snapshot_version: Literal["2026-08-01.v1"]
    context_contract_version: Literal["coordinator-context-v1"]
    decision_contract_version: Literal["coordinator-decision-v1"]
    prompt_id: Literal["trippilot-coordinator-prompt-v1"]
    requested_model: Literal["gpt-5.6-terra"]
    reasoning_effort: Literal["low"]
    max_output_tokens: Literal[400]
    request_profiles: dict[ProfileId, CoordinatorEvaluationRequest]
    cases: tuple[CoordinatorEvaluationCase, ...] = Field(min_length=26, max_length=26)

    @model_validator(mode="after")
    def require_frozen_protocol_shape(self) -> Self:
        if set(case.request_profile_id for case in self.cases) - set(
            self.request_profiles
        ):
            raise ValueError("every case must reference a frozen request profile")
        scenario_ids = tuple(case.scenario_id for case in self.cases)
        if len(set(scenario_ids)) != len(scenario_ids):
            raise ValueError("evaluation scenario IDs must be unique")
        counts = Counter(case.cohort for case in self.cases)
        expected = {
            CoordinatorEvaluationCohort.BASELINE_PARITY: 6,
            CoordinatorEvaluationCohort.PREFERENCE_RICH: 8,
            CoordinatorEvaluationCohort.EXPECTED_FAILURE: 2,
            CoordinatorEvaluationCohort.ADVERSARIAL_SCOPE: 6,
            CoordinatorEvaluationCohort.SCHEMA_BOUNDARY: 4,
        }
        if counts != expected:
            raise ValueError("evaluation cohort counts must match the frozen protocol")
        model_cohorts = {
            CoordinatorEvaluationCohort.BASELINE_PARITY,
            CoordinatorEvaluationCohort.PREFERENCE_RICH,
            CoordinatorEvaluationCohort.ADVERSARIAL_SCOPE,
        }
        for case in self.cases:
            if case.cohort in model_cohorts and (
                case.expected_behavior is not EvaluationCaseBehavior.MODEL_EXERCISED
            ):
                raise ValueError("model cohorts must exercise the hosted adapter")
            if case.cohort is CoordinatorEvaluationCohort.EXPECTED_FAILURE and (
                case.expected_behavior
                is not EvaluationCaseBehavior.DETERMINISTIC_FAILURE
            ):
                raise ValueError("failure cohort must stop before the model")
            if case.cohort is CoordinatorEvaluationCohort.SCHEMA_BOUNDARY and (
                case.expected_behavior
                not in {
                    EvaluationCaseBehavior.SCHEMA_STUB_ACCEPTED,
                    EvaluationCaseBehavior.SCHEMA_REJECTED,
                }
            ):
                raise ValueError("schema cohort must remain in the stub boundary")
        return self


class EvaluationCaseValidation(EvaluationSchema):
    scenario_id: ScenarioId
    behavior: EvaluationCaseBehavior
    candidate_count: int = Field(ge=0, le=5)
    candidate_set_digest: Sha256Digest | None
    planning_failure_code: PlanningFailureCode | None


class EvaluationManifestValidation(EvaluationSchema):
    contract_version: Literal["coordinator-eval-validation-v1"]
    fixture_snapshot_version: str
    cases: tuple[EvaluationCaseValidation, ...] = Field(min_length=26, max_length=26)


class EvaluationRunRecord(EvaluationSchema):
    contract_version: Literal["coordinator-eval-run-v1"]
    scenario_id: ScenarioId
    code_revision: str = Field(pattern=r"^[a-f0-9]{7,40}$")
    fixture_snapshot_version: Literal["2026-08-01.v1"]
    prompt_id: Literal["trippilot-coordinator-prompt-v1"]
    requested_model: Literal["gpt-5.6-terra"]
    baseline_planner_id: Literal["deterministic-greedy-bounded-v1"]
    fixed_ranker_id: Literal["trippilot-fixed-ranker-v1"]
    candidate_ids: tuple[EvaluationCandidateId, ...] = Field(min_length=2, max_length=5)
    candidate_set_digest: Sha256Digest
    run_number: int = Field(ge=1, le=5)
    attempt_count: int = Field(ge=0, le=2)
    metadata_attempt_count: int = Field(ge=0, le=2)
    outcome: EvaluationRunOutcome
    baseline_candidate_id: EvaluationCandidateId
    fixed_ranker_candidate_id: EvaluationCandidateId
    selected_candidate_id: EvaluationCandidateId
    fallback_code: CoordinatorRunFailureCode | None
    hard_constraints_passed: Literal[True]
    returned_models: tuple[
        Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_.-]{1,128}$")], ...
    ] = Field(default=(), max_length=2)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    latency_ms: int | None = Field(default=None, ge=0)
    estimated_cost_micro_usd: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def require_safe_consistent_outcome(self) -> Self:
        if self.selected_candidate_id not in self.candidate_ids:
            raise ValueError("run selection must use one frozen candidate ID")
        if self.baseline_candidate_id != self.candidate_ids[0]:
            raise ValueError("baseline arm must remain candidate zero")
        if self.fixed_ranker_candidate_id != self.candidate_ids[0]:
            raise ValueError("fixed ranker arm must remain candidate zero")
        if self.outcome is EvaluationRunOutcome.COORDINATOR_SELECTION:
            if self.fallback_code is not None:
                raise ValueError("coordinator selections cannot have a fallback code")
        elif self.fallback_code is None:
            raise ValueError("deterministic fallbacks require a stable code")
        usage_values = (
            self.input_tokens,
            self.output_tokens,
            self.latency_ms,
            self.estimated_cost_micro_usd,
        )
        if bool(self.returned_models) != all(
            value is not None for value in usage_values
        ):
            raise ValueError(
                "returned models and usage totals must be present together"
            )
        if len(self.returned_models) != self.metadata_attempt_count:
            raise ValueError("returned models must match metadata-bearing attempts")
        if self.metadata_attempt_count > self.attempt_count:
            raise ValueError("metadata attempts cannot exceed all attempts")
        return self


def load_coordinator_evaluation_manifest(
    path: str | Path,
) -> CoordinatorEvaluationManifest:
    return CoordinatorEvaluationManifest.model_validate_json(
        Path(path).read_text("utf-8")
    )


def validate_evaluation_manifest(
    manifest: CoordinatorEvaluationManifest, provider: TravelDataProvider
) -> EvaluationManifestValidation:
    metadata = provider.get_snapshot_metadata()
    if metadata.snapshot_version != manifest.fixture_snapshot_version:
        raise ValueError("evaluation fixture snapshot does not match the manifest")
    validations = tuple(
        _validate_case(manifest, case, provider) for case in manifest.cases
    )
    return EvaluationManifestValidation(
        contract_version="coordinator-eval-validation-v1",
        fixture_snapshot_version=metadata.snapshot_version,
        cases=validations,
    )


def run_evaluation_case(
    manifest: CoordinatorEvaluationManifest,
    scenario_id: str,
    provider: TravelDataProvider,
    adapter: CoordinatorAdapter,
    *,
    code_revision: str,
    run_number: int,
    monotonic: Callable[[], float] = time.monotonic,
) -> EvaluationRunRecord:
    case = _case_by_id(manifest, scenario_id)
    if case.expected_behavior not in {
        EvaluationCaseBehavior.MODEL_EXERCISED,
        EvaluationCaseBehavior.SCHEMA_STUB_ACCEPTED,
    }:
        raise ValueError("only accepted candidate cases can execute an adapter")
    if not 1 <= run_number <= case.repeated_runs:
        raise ValueError("run number exceeds the case repetition contract")
    if case.candidate_set_digest is None:
        raise RuntimeError("accepted evaluation case omitted its candidate digest")
    request = manifest.request_profiles[case.request_profile_id].to_domain()
    bound = _bound_case(manifest, case, request, provider)
    counting = _CountingAdapter(adapter)
    result = run_coordinator(
        request,
        bound,
        counting,
        deadline_monotonic=monotonic() + 8.0,
        monotonic=monotonic,
    )
    if isinstance(result, CoordinatorRunSuccess):
        selected_id = result.decision.selected_candidate_id
        if selected_id is None:
            raise RuntimeError("validated coordinator selection omitted its ID")
        outcome = EvaluationRunOutcome.COORDINATOR_SELECTION
        fallback_code = None
        selected = result.candidate
    else:
        selected_id = bound.bindings[0].candidate_id
        outcome = EvaluationRunOutcome.DETERMINISTIC_FALLBACK
        fallback_code = result.code
        selected = bound.bindings[0].candidate
    metadata = result.adapter_metadata
    has_metadata = bool(metadata)
    report = validate_itinerary(request, selected.itinerary, selected.provider_snapshot)
    if not report.is_valid:
        raise RuntimeError("evaluation attempted to record an invalid canonical result")
    return EvaluationRunRecord(
        contract_version="coordinator-eval-run-v1",
        scenario_id=case.scenario_id,
        code_revision=code_revision,
        fixture_snapshot_version=manifest.fixture_snapshot_version,
        prompt_id=manifest.prompt_id,
        requested_model=manifest.requested_model,
        baseline_planner_id=PLANNER_ID,
        fixed_ranker_id=FIXED_RANKER_ID,
        candidate_ids=case.expected_candidate_ids,
        candidate_set_digest=case.candidate_set_digest,
        run_number=run_number,
        attempt_count=counting.attempt_count,
        metadata_attempt_count=len(metadata),
        outcome=outcome,
        baseline_candidate_id=case.expected_candidate_ids[0],
        fixed_ranker_candidate_id=case.expected_candidate_ids[0],
        selected_candidate_id=selected_id,
        fallback_code=fallback_code,
        hard_constraints_passed=True,
        returned_models=tuple(item.returned_model for item in metadata),
        input_tokens=(
            sum(item.input_tokens for item in metadata) if has_metadata else None
        ),
        output_tokens=(
            sum(item.output_tokens for item in metadata) if has_metadata else None
        ),
        latency_ms=(
            sum(item.latency_ms for item in metadata) if has_metadata else None
        ),
        estimated_cost_micro_usd=(
            sum(item.estimated_cost_micro_usd for item in metadata)
            if has_metadata
            else None
        ),
    )


class _CountingAdapter:
    def __init__(self, adapter: CoordinatorAdapter) -> None:
        self._adapter = adapter
        self.attempt_count = 0

    def decide(
        self,
        context: object,
        *,
        deadline_monotonic: float,
        retry_feedback: CoordinatorRetryFeedback | None = None,
    ) -> CoordinatorAdapterResult:
        from trippilot.services import CoordinatorContext

        if not isinstance(context, CoordinatorContext):
            raise TypeError("coordinator context type is invalid")
        self.attempt_count += 1
        return self._adapter.decide(
            context,
            deadline_monotonic=deadline_monotonic,
            retry_feedback=retry_feedback,
        )


def _validate_case(
    manifest: CoordinatorEvaluationManifest,
    case: CoordinatorEvaluationCase,
    provider: TravelDataProvider,
) -> EvaluationCaseValidation:
    request = manifest.request_profiles[case.request_profile_id].to_domain()
    try:
        normalized = normalize_preference_notes(case.preference_notes_input)
    except TypeError, ValueError:
        if case.expected_behavior is not EvaluationCaseBehavior.SCHEMA_REJECTED:
            raise ValueError(
                f"{case.scenario_id} unexpectedly rejected notes"
            ) from None
        return EvaluationCaseValidation(
            scenario_id=case.scenario_id,
            behavior=case.expected_behavior,
            candidate_count=0,
            candidate_set_digest=None,
            planning_failure_code=None,
        )
    if normalized != case.normalized_preference_notes:
        raise ValueError(f"{case.scenario_id} normalized notes changed")
    if case.expected_behavior is EvaluationCaseBehavior.SCHEMA_REJECTED:
        raise ValueError(f"{case.scenario_id} expected note rejection")
    result = enumerate_trip_candidates(request, provider)
    if isinstance(result, PlanningFailure):
        if result.code is not case.expected_failure_code:
            raise ValueError(f"{case.scenario_id} planning failure changed")
        if plan_trip(request, provider) != result:
            raise ValueError(f"{case.scenario_id} baseline failure arm changed")
        return EvaluationCaseValidation(
            scenario_id=case.scenario_id,
            behavior=case.expected_behavior,
            candidate_count=0,
            candidate_set_digest=None,
            planning_failure_code=result.code,
        )
    if case.expected_behavior is EvaluationCaseBehavior.DETERMINISTIC_FAILURE:
        raise ValueError(f"{case.scenario_id} unexpectedly generated candidates")
    bound = _bound_case(manifest, case, request, provider, result)
    baseline = plan_trip(request, provider)
    if not isinstance(baseline, PlanningSuccess) or (
        baseline.itinerary != result.candidates[0].itinerary
    ):
        raise ValueError(f"{case.scenario_id} baseline candidate arm changed")
    digest = _candidate_set_digest(bound)
    if digest != case.candidate_set_digest:
        raise ValueError(f"{case.scenario_id} candidate digest changed")
    return EvaluationCaseValidation(
        scenario_id=case.scenario_id,
        behavior=case.expected_behavior,
        candidate_count=len(bound.bindings),
        candidate_set_digest=digest,
        planning_failure_code=None,
    )


def _bound_case(
    manifest: CoordinatorEvaluationManifest,
    case: CoordinatorEvaluationCase,
    request: TripRequest,
    provider: TravelDataProvider,
    candidate_set: CandidateSet | None = None,
) -> BoundCoordinatorContext:
    generated = candidate_set or enumerate_trip_candidates(request, provider)
    if not isinstance(generated, CandidateSet):
        raise ValueError(f"{case.scenario_id} did not generate a candidate set")
    if len(generated.candidates) != len(case.expected_candidate_ids):
        raise ValueError(f"{case.scenario_id} candidate count changed")
    ids = iter(case.expected_candidate_ids)
    bound = build_coordinator_context(
        request,
        generated,
        provider,
        preference_notes=case.normalized_preference_notes,
        candidate_id_factory=lambda: next(ids),
    )
    if isinstance(bound, CoordinatorContextBuildFailure):
        raise ValueError(f"{case.scenario_id} context construction failed")
    if tuple(binding.candidate_id for binding in bound.bindings) != (
        case.expected_candidate_ids
    ):
        raise ValueError(f"{case.scenario_id} candidate IDs changed")
    return bound


def _candidate_set_digest(bound: BoundCoordinatorContext) -> str:
    payload: list[dict[str, object]] = []
    for summary, binding in zip(bound.context.candidates, bound.bindings, strict=True):
        itinerary = binding.candidate.itinerary
        payload.append(
            {
                "summary": summary.model_dump(mode="json", exclude={"candidate_id"}),
                "scheduled_items": [
                    {
                        "item_id": item.item_id,
                        "kind": item.kind.value,
                        "start": item.window.start.isoformat(),
                        "end": item.window.end.isoformat(),
                        "location_id": item.location_id,
                        "source_record_id": item.source_record_id,
                        "estimated_cost_minor": item.estimated_cost.amount_minor,
                        "transport_role": (
                            item.transport_role.value
                            if item.transport_role is not None
                            else None
                        ),
                    }
                    for item in itinerary.scheduled_items
                ],
                "accommodation_stays": [
                    {
                        "stay_id": stay.stay_id,
                        "check_in": stay.check_in.isoformat(),
                        "check_out": stay.check_out.isoformat(),
                        "nights": stay.number_of_nights,
                        "location_id": stay.location_id,
                        "source_record_id": stay.source_record_id,
                        "estimated_cost_minor": stay.estimated_cost.amount_minor,
                    }
                    for stay in itinerary.accommodation_stays
                ],
                "explicit_fees": [
                    {"fee_id": fee.fee_id, "cost_minor": fee.cost.amount_minor}
                    for fee in itinerary.explicit_fees
                ],
                "category_totals_minor": [
                    value.amount_minor for value in itinerary.category_totals.values()
                ],
                "total_estimated_cost_minor": (
                    itinerary.total_estimated_cost.amount_minor
                ),
                "matched_interests": [
                    interest.value for interest in binding.candidate.matched_interests
                ],
            }
        )
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _case_by_id(
    manifest: CoordinatorEvaluationManifest, scenario_id: str
) -> CoordinatorEvaluationCase:
    if re.fullmatch(r"[a-z0-9][a-z0-9-]{2,63}", scenario_id) is None:
        raise ValueError("scenario ID is invalid")
    for case in manifest.cases:
        if case.scenario_id == scenario_id:
            return case
    raise ValueError("scenario ID is not in the frozen manifest")
