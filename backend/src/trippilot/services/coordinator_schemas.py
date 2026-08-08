"""Strict internal contracts for the bounded coordinator experiment."""

from __future__ import annotations

import json
import unicodedata
from dataclasses import dataclass
from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
    field_validator,
    model_validator,
)

from trippilot.domain import Interest, Pace

MAX_SIGNED_64 = 9_223_372_036_854_775_807
MAX_COORDINATOR_DECISION_BYTES = 4_096

CandidateId = Annotated[
    str,
    StringConstraints(pattern=r"^[A-Za-z0-9_-]{1,64}$"),
]
BoundedCount = Annotated[int, Field(ge=0, le=16)]


class CoordinatorSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class AccommodationStyleTag(StrEnum):
    QUIET = "quiet"
    SOCIAL = "social"


class CoordinatorTransportModeTag(StrEnum):
    COACH = "coach"
    TRAIN = "train"


class InterpretedPreferenceTag(StrEnum):
    LOWER_COST = "lower_cost"
    LARGER_BUDGET_BUFFER = "larger_budget_buffer"
    FEWER_ACTIVITIES = "fewer_activities"
    MORE_ACTIVITIES = "more_activities"
    SHORTER_TRANSFERS = "shorter_transfers"
    ACTIVITY_VARIETY = "activity_variety"
    DAYTIME_FOCUS = "daytime_focus"
    EVENING_FOCUS = "evening_focus"


class AbstentionReason(StrEnum):
    NO_PREFERENCE_SIGNAL = "no_preference_signal"
    CONFLICTING_PREFERENCES = "conflicting_preferences"
    INSUFFICIENT_CANDIDATE_DIFFERENCE = "insufficient_candidate_difference"


class DecisionContextFailureCode(StrEnum):
    UNKNOWN_CANDIDATE = "UNKNOWN_CANDIDATE"
    PRIORITIZED_INTEREST_NOT_REQUESTED = "PRIORITIZED_INTEREST_NOT_REQUESTED"


class CoordinatorOutputFailureCode(StrEnum):
    OUTPUT_TOO_LARGE = "OUTPUT_TOO_LARGE"
    INVALID_JSON = "INVALID_JSON"
    OUTPUT_SCHEMA_INVALID = "OUTPUT_SCHEMA_INVALID"


class CoordinatorRetryCode(StrEnum):
    OUTPUT_SCHEMA_INVALID = "OUTPUT_SCHEMA_INVALID"
    UNKNOWN_CANDIDATE = "UNKNOWN_CANDIDATE"


class ActivityInterestCounts(CoordinatorSchema):
    food: BoundedCount
    arts_culture: BoundedCount
    nature: BoundedCount
    history: BoundedCount
    nightlife: BoundedCount
    shopping: BoundedCount
    sports: BoundedCount
    student_budget: BoundedCount

    def count_for(self, interest: Interest) -> int:
        return {
            Interest.FOOD: self.food,
            Interest.ARTS_CULTURE: self.arts_culture,
            Interest.NATURE: self.nature,
            Interest.HISTORY: self.history,
            Interest.NIGHTLIFE: self.nightlife,
            Interest.SHOPPING: self.shopping,
            Interest.SPORTS: self.sports,
            Interest.STUDENT_BUDGET: self.student_budget,
        }[interest]

    def values(self) -> tuple[int, ...]:
        return tuple(self.count_for(interest) for interest in Interest)


class DaypartActivityCounts(CoordinatorSchema):
    morning: BoundedCount
    afternoon: BoundedCount
    evening: BoundedCount

    def values(self) -> tuple[int, int, int]:
        return (self.morning, self.afternoon, self.evening)


class CandidateSummary(CoordinatorSchema):
    contract_version: Literal["candidate-summary-v1"]
    candidate_id: CandidateId
    total_estimated_cost_minor: int = Field(ge=0, le=MAX_SIGNED_64)
    remaining_budget_minor: int = Field(ge=0, le=MAX_SIGNED_64)
    primary_activity_count: int = Field(ge=0, le=16)
    distinct_primary_activity_count: int = Field(ge=0, le=16)
    total_transfer_minutes: int = Field(ge=0, le=5_760)
    activity_interest_counts: ActivityInterestCounts
    requested_interest_coverage_count: int = Field(ge=0, le=8)
    daypart_activity_counts: DaypartActivityCounts
    accommodation_style_tags: tuple[AccommodationStyleTag, ...] = Field(max_length=2)
    transport_mode_tags: tuple[CoordinatorTransportModeTag, ...] = Field(
        min_length=1, max_length=2
    )

    @model_validator(mode="after")
    def require_coherent_metrics(self) -> Self:
        if self.distinct_primary_activity_count > self.primary_activity_count:
            raise ValueError("distinct activities cannot exceed all activities")
        if (
            self.primary_activity_count > 0
            and self.distinct_primary_activity_count == 0
        ):
            raise ValueError("activities require at least one distinct source record")
        if any(
            count > self.primary_activity_count
            for count in self.activity_interest_counts.values()
        ):
            raise ValueError("interest counts cannot exceed all activities")
        if sum(self.activity_interest_counts.values()) < self.primary_activity_count:
            raise ValueError("each activity must contribute at least one interest")
        if sum(self.daypart_activity_counts.values()) != self.primary_activity_count:
            raise ValueError("daypart counts must sum to all activities")
        _require_canonical_unique_tags(
            self.accommodation_style_tags,
            tuple(AccommodationStyleTag),
            "accommodation style tags",
        )
        _require_canonical_unique_tags(
            self.transport_mode_tags,
            tuple(CoordinatorTransportModeTag),
            "transport mode tags",
        )
        return self


class CoordinatorContext(CoordinatorSchema):
    contract_version: Literal["coordinator-context-v1"]
    interests: tuple[Interest, ...] = Field(min_length=1, max_length=8)
    pace: Pace
    preference_notes: str | None
    candidates: tuple[CandidateSummary, ...] = Field(min_length=2, max_length=5)

    @field_validator("preference_notes")
    @classmethod
    def require_normalized_notes(cls, value: str | None) -> str | None:
        if normalize_preference_notes(value) != value:
            raise ValueError("preference notes must already be normalized")
        return value

    @model_validator(mode="after")
    def require_closed_consistent_context(self) -> Self:
        if len(set(self.interests)) != len(self.interests):
            raise ValueError("interests must be unique")
        candidate_ids = tuple(candidate.candidate_id for candidate in self.candidates)
        if len(set(candidate_ids)) != len(candidate_ids):
            raise ValueError("candidate IDs must be unique")
        metric_payloads = tuple(
            candidate.model_dump_json(exclude={"candidate_id"})
            for candidate in self.candidates
        )
        if len(set(metric_payloads)) != len(metric_payloads):
            raise ValueError("candidate metric payloads must be unique")
        budgets = {
            candidate.total_estimated_cost_minor + candidate.remaining_budget_minor
            for candidate in self.candidates
        }
        if len(budgets) != 1:
            raise ValueError("all candidate summaries must use one request budget")
        requested = set(self.interests)
        for candidate in self.candidates:
            coverage = sum(
                candidate.activity_interest_counts.count_for(interest) > 0
                for interest in requested
            )
            if coverage != candidate.requested_interest_coverage_count:
                raise ValueError("requested interest coverage is inconsistent")
        return self


class CoordinatorDecision(CoordinatorSchema):
    contract_version: Literal["coordinator-decision-v1"]
    status: Literal["selection", "abstention"]
    selected_candidate_id: CandidateId | None
    interpreted_preference_tags: tuple[InterpretedPreferenceTag, ...] = Field(
        max_length=5
    )
    prioritized_interests: tuple[Interest, ...] = Field(max_length=3)
    abstention_reason: AbstentionReason | None

    @model_validator(mode="after")
    def require_consistent_decision(self) -> Self:
        if len(set(self.interpreted_preference_tags)) != len(
            self.interpreted_preference_tags
        ):
            raise ValueError("interpreted preference tags must be unique")
        if len(set(self.prioritized_interests)) != len(self.prioritized_interests):
            raise ValueError("prioritized interests must be unique")
        if self.status == "selection":
            if self.selected_candidate_id is None or self.abstention_reason is not None:
                raise ValueError("selection requires one candidate and no reason")
        elif self.selected_candidate_id is not None or self.abstention_reason is None:
            raise ValueError("abstention requires no candidate and one reason")
        return self


class CoordinatorRetryFeedback(CoordinatorSchema):
    contract_version: Literal["coordinator-retry-v1"]
    code: CoordinatorRetryCode
    candidate_ids: tuple[CandidateId, ...] = Field(min_length=2, max_length=5)

    @model_validator(mode="after")
    def require_unique_ids(self) -> Self:
        if len(set(self.candidate_ids)) != len(self.candidate_ids):
            raise ValueError("retry candidate IDs must be unique")
        return self


@dataclass(frozen=True, slots=True)
class DecisionContextFailure:
    code: DecisionContextFailureCode


DecisionContextResult = CoordinatorDecision | DecisionContextFailure


@dataclass(frozen=True, slots=True)
class CoordinatorOutputFailure:
    code: CoordinatorOutputFailureCode


CoordinatorOutputParseResult = CoordinatorDecision | CoordinatorOutputFailure


def normalize_preference_notes(value: object) -> str | None:
    """Normalize opted-in notes without laundering prohibited controls."""

    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError("preference notes must be a string or null")
    normalized = unicodedata.normalize("NFC", value).translate(
        {ord("\r"): " ", ord("\n"): " ", ord("\t"): " "}
    )
    if any(_is_forbidden_note_codepoint(ord(character)) for character in normalized):
        raise ValueError("preference notes contain a prohibited control character")

    collapsed: list[str] = []
    pending_space = False
    for character in normalized:
        if character.isspace():
            pending_space = bool(collapsed)
            continue
        if pending_space:
            collapsed.append(" ")
            pending_space = False
        collapsed.append(character)
    result = "".join(collapsed)
    if not result:
        return None
    if len(result) > 300:
        raise ValueError("preference notes cannot exceed 300 Unicode code points")
    return result


def validate_decision_for_context(
    decision: CoordinatorDecision, context: CoordinatorContext
) -> DecisionContextResult:
    if (
        decision.selected_candidate_id is not None
        and decision.selected_candidate_id
        not in {candidate.candidate_id for candidate in context.candidates}
    ):
        return DecisionContextFailure(DecisionContextFailureCode.UNKNOWN_CANDIDATE)
    if not set(decision.prioritized_interests).issubset(context.interests):
        return DecisionContextFailure(
            DecisionContextFailureCode.PRIORITIZED_INTEREST_NOT_REQUESTED
        )
    return decision


def parse_coordinator_decision(value: object) -> CoordinatorOutputParseResult:
    """Parse exactly one small JSON object without returning raw validation text."""

    if not isinstance(value, str):
        return CoordinatorOutputFailure(CoordinatorOutputFailureCode.INVALID_JSON)
    if len(value) > MAX_COORDINATOR_DECISION_BYTES:
        return CoordinatorOutputFailure(CoordinatorOutputFailureCode.OUTPUT_TOO_LARGE)
    try:
        encoded = value.encode("utf-8")
    except UnicodeEncodeError:
        return CoordinatorOutputFailure(CoordinatorOutputFailureCode.INVALID_JSON)
    if len(encoded) > MAX_COORDINATOR_DECISION_BYTES:
        return CoordinatorOutputFailure(CoordinatorOutputFailureCode.OUTPUT_TOO_LARGE)
    try:
        json.loads(
            value,
            object_pairs_hook=_reject_duplicate_json_keys,
            parse_constant=_reject_nonstandard_json_constant,
        )
    except JSONDuplicateKeyError, ValueError, TypeError, json.JSONDecodeError:
        return CoordinatorOutputFailure(CoordinatorOutputFailureCode.INVALID_JSON)
    try:
        return CoordinatorDecision.model_validate_json(value)
    except ValidationError, ValueError, TypeError:
        return CoordinatorOutputFailure(
            CoordinatorOutputFailureCode.OUTPUT_SCHEMA_INVALID
        )


class JSONDuplicateKeyError(ValueError):
    pass


def _reject_duplicate_json_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise JSONDuplicateKeyError
        result[key] = value
    return result


def _reject_nonstandard_json_constant(value: str) -> None:
    raise ValueError("non-standard JSON constants are forbidden")


def _is_forbidden_note_codepoint(value: int) -> bool:
    return (
        0x00 <= value <= 0x1F
        or 0x7F <= value <= 0x9F
        or 0xD800 <= value <= 0xDFFF
        or value == 0x061C
        or 0x200E <= value <= 0x200F
        or 0x202A <= value <= 0x202E
        or 0x2066 <= value <= 0x2069
    )


def _require_canonical_unique_tags[T: StrEnum](
    values: tuple[T, ...], canonical_order: tuple[T, ...], label: str
) -> None:
    if len(set(values)) != len(values):
        raise ValueError(f"{label} must be unique")
    expected = tuple(value for value in canonical_order if value in values)
    if values != expected:
        raise ValueError(f"{label} must use canonical order")
