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
class CoordinatorAdapterMetadata:
    prompt_id: str
    requested_model: str
    returned_model: str
    input_tokens: int
    output_tokens: int
    latency_ms: int
    estimated_cost_micro_usd: int

    def __post_init__(self) -> None:
        identifiers = (self.prompt_id, self.requested_model, self.returned_model)
        if any(
            not value
            or len(value) > 128
            or not value.isascii()
            or any(not 0x21 <= ord(character) <= 0x7E for character in value)
            for value in identifiers
        ):
            raise ValueError("adapter metadata identifiers must be bounded ASCII")
        metrics = (
            self.input_tokens,
            self.output_tokens,
            self.latency_ms,
            self.estimated_cost_micro_usd,
        )
        if any(isinstance(value, bool) or value < 0 for value in metrics):
            raise ValueError("adapter metadata metrics must be non-negative integers")


@dataclass(frozen=True, slots=True)
class CoordinatorAdapterSuccess:
    decision: CoordinatorDecision
    metadata: CoordinatorAdapterMetadata | None = None


@dataclass(frozen=True, slots=True)
class CoordinatorAdapterFailure:
    code: CoordinatorAdapterFailureCode
    metadata: CoordinatorAdapterMetadata | None = None

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


class NotConfiguredCoordinatorAdapter:
    """Explicit safe adapter used when the hosted experiment is disabled."""

    def decide(
        self,
        context: CoordinatorContext,
        *,
        deadline_monotonic: float,
        retry_feedback: CoordinatorRetryFeedback | None = None,
    ) -> CoordinatorAdapterResult:
        del context, deadline_monotonic, retry_feedback
        return CoordinatorAdapterFailure(CoordinatorAdapterFailureCode.NOT_CONFIGURED)
