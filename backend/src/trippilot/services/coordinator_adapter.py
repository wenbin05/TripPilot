"""SDK-neutral adapter protocol for one bounded coordinator decision."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, runtime_checkable

from .coordinator_schemas import (
    CoordinatorContext,
    CoordinatorDecision,
    CoordinatorRetryFeedback,
)


class CoordinatorAdapterFailureCode(StrEnum):
    NOT_CONFIGURED = "NOT_CONFIGURED"
    TIMEOUT = "TIMEOUT"
    RATE_LIMITED = "RATE_LIMITED"
    PROVIDER_ERROR = "PROVIDER_ERROR"
    REFUSAL = "REFUSAL"
    OUTPUT_INVALID = "OUTPUT_INVALID"


@dataclass(frozen=True, slots=True)
class CoordinatorAdapterSuccess:
    decision: CoordinatorDecision


@dataclass(frozen=True, slots=True)
class CoordinatorAdapterFailure:
    code: CoordinatorAdapterFailureCode

    @property
    def allows_retry(self) -> bool:
        return self.code is CoordinatorAdapterFailureCode.OUTPUT_INVALID


CoordinatorAdapterResult = CoordinatorAdapterSuccess | CoordinatorAdapterFailure


@runtime_checkable
class CoordinatorAdapter(Protocol):
    """One serial, deadline-bound decision call with no SDK-specific types."""

    def decide(
        self,
        context: CoordinatorContext,
        *,
        deadline_monotonic: float,
        retry_feedback: CoordinatorRetryFeedback | None = None,
    ) -> CoordinatorAdapterResult: ...
