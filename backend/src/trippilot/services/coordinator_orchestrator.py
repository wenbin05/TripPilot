"""Application-owned, bounded coordinator execution with deterministic failure."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

from trippilot.domain import TripRequest, validate_itinerary

from .coordinator_adapter import (
    CoordinatorAdapter,
    CoordinatorAdapterFailure,
    CoordinatorAdapterFailureCode,
    CoordinatorAdapterMetadata,
)
from .coordinator_context import BoundCoordinatorContext
from .coordinator_schemas import (
    CoordinatorDecision,
    CoordinatorRetryCode,
    CoordinatorRetryFeedback,
    DecisionContextFailure,
    DecisionContextFailureCode,
    validate_decision_for_context,
)
from .models import CanonicalCandidate


class CoordinatorRunFailureCode(StrEnum):
    MODEL_NOT_CONFIGURED = "MODEL_NOT_CONFIGURED"
    MODEL_TIMEOUT = "MODEL_TIMEOUT"
    MODEL_RATE_LIMITED = "MODEL_RATE_LIMITED"
    MODEL_PROVIDER_ERROR = "MODEL_PROVIDER_ERROR"
    MODEL_REFUSAL = "MODEL_REFUSAL"
    MODEL_OUTPUT_INVALID = "MODEL_OUTPUT_INVALID"
    MODEL_ABSTAINED = "MODEL_ABSTAINED"
    UNKNOWN_CANDIDATE = "UNKNOWN_CANDIDATE"
    CANDIDATE_REVALIDATION_FAILED = "CANDIDATE_REVALIDATION_FAILED"
    DEADLINE_RESERVE_REACHED = "DEADLINE_RESERVE_REACHED"


@dataclass(frozen=True, slots=True)
class CoordinatorRunSuccess:
    decision: CoordinatorDecision
    candidate: CanonicalCandidate
    adapter_metadata: tuple[CoordinatorAdapterMetadata, ...] = ()


@dataclass(frozen=True, slots=True)
class CoordinatorRunFailure:
    code: CoordinatorRunFailureCode
    adapter_metadata: tuple[CoordinatorAdapterMetadata, ...] = ()


CoordinatorRunResult = CoordinatorRunSuccess | CoordinatorRunFailure


def run_coordinator(
    request: TripRequest,
    bound: BoundCoordinatorContext,
    adapter: CoordinatorAdapter,
    *,
    deadline_monotonic: float,
    monotonic: Callable[[], float] = time.monotonic,
) -> CoordinatorRunResult:
    """Allow at most two serial calls under one absolute deadline."""

    retry_feedback: CoordinatorRetryFeedback | None = None
    metadata: list[CoordinatorAdapterMetadata] = []
    for attempt in range(2):
        if monotonic() >= deadline_monotonic:
            return CoordinatorRunFailure(
                CoordinatorRunFailureCode.DEADLINE_RESERVE_REACHED,
                tuple(metadata),
            )
        adapter_result = adapter.decide(
            bound.context,
            deadline_monotonic=deadline_monotonic,
            retry_feedback=retry_feedback,
        )
        if adapter_result.metadata is not None:
            metadata.append(adapter_result.metadata)
        if isinstance(adapter_result, CoordinatorAdapterFailure):
            if adapter_result.allows_retry and attempt == 0:
                retry_feedback = _retry_feedback(
                    bound, CoordinatorRetryCode.OUTPUT_SCHEMA_INVALID
                )
                continue
            return CoordinatorRunFailure(
                _map_adapter_failure(adapter_result.code), tuple(metadata)
            )

        checked = validate_decision_for_context(adapter_result.decision, bound.context)
        if isinstance(checked, DecisionContextFailure):
            if attempt == 0:
                retry_code = (
                    CoordinatorRetryCode.UNKNOWN_CANDIDATE
                    if checked.code is DecisionContextFailureCode.UNKNOWN_CANDIDATE
                    else CoordinatorRetryCode.OUTPUT_SCHEMA_INVALID
                )
                retry_feedback = _retry_feedback(bound, retry_code)
                continue
            code = (
                CoordinatorRunFailureCode.UNKNOWN_CANDIDATE
                if checked.code is DecisionContextFailureCode.UNKNOWN_CANDIDATE
                else CoordinatorRunFailureCode.MODEL_OUTPUT_INVALID
            )
            return CoordinatorRunFailure(code, tuple(metadata))
        if checked.status == "abstention":
            return CoordinatorRunFailure(
                CoordinatorRunFailureCode.MODEL_ABSTAINED, tuple(metadata)
            )

        selected_id = checked.selected_candidate_id
        if selected_id is None:
            return CoordinatorRunFailure(
                CoordinatorRunFailureCode.MODEL_OUTPUT_INVALID,
                tuple(metadata),
            )
        candidate = bound.resolve(selected_id)
        if candidate is None:
            return CoordinatorRunFailure(
                CoordinatorRunFailureCode.UNKNOWN_CANDIDATE, tuple(metadata)
            )
        report = validate_itinerary(
            request, candidate.itinerary, candidate.provider_snapshot
        )
        if not report.is_valid:
            return CoordinatorRunFailure(
                CoordinatorRunFailureCode.CANDIDATE_REVALIDATION_FAILED,
                tuple(metadata),
            )
        return CoordinatorRunSuccess(checked, candidate, tuple(metadata))

    return CoordinatorRunFailure(
        CoordinatorRunFailureCode.MODEL_OUTPUT_INVALID, tuple(metadata)
    )


def _retry_feedback(
    bound: BoundCoordinatorContext, code: CoordinatorRetryCode
) -> CoordinatorRetryFeedback:
    return CoordinatorRetryFeedback(
        contract_version="coordinator-retry-v1",
        code=code,
        candidate_ids=tuple(
            candidate.candidate_id for candidate in bound.context.candidates
        ),
    )


def _map_adapter_failure(
    code: CoordinatorAdapterFailureCode,
) -> CoordinatorRunFailureCode:
    return {
        CoordinatorAdapterFailureCode.NOT_CONFIGURED: (
            CoordinatorRunFailureCode.MODEL_NOT_CONFIGURED
        ),
        CoordinatorAdapterFailureCode.TIMEOUT: (
            CoordinatorRunFailureCode.MODEL_TIMEOUT
        ),
        CoordinatorAdapterFailureCode.RATE_LIMITED: (
            CoordinatorRunFailureCode.MODEL_RATE_LIMITED
        ),
        CoordinatorAdapterFailureCode.PROVIDER_ERROR: (
            CoordinatorRunFailureCode.MODEL_PROVIDER_ERROR
        ),
        CoordinatorAdapterFailureCode.REFUSAL: (
            CoordinatorRunFailureCode.MODEL_REFUSAL
        ),
        CoordinatorAdapterFailureCode.OUTPUT_INVALID: (
            CoordinatorRunFailureCode.MODEL_OUTPUT_INVALID
        ),
    }[code]
