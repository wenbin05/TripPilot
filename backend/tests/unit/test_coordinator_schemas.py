from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from trippilot.domain import Interest, Pace
from trippilot.services.coordinator_schemas import (
    MAX_COORDINATOR_DECISION_BYTES,
    AbstentionReason,
    AccommodationStyleTag,
    ActivityInterestCounts,
    CandidateSummary,
    CoordinatorContext,
    CoordinatorDecision,
    CoordinatorOutputFailure,
    CoordinatorOutputFailureCode,
    CoordinatorRetryCode,
    CoordinatorRetryFeedback,
    CoordinatorTransportModeTag,
    DaypartActivityCounts,
    DecisionContextFailure,
    DecisionContextFailureCode,
    InterpretedPreferenceTag,
    normalize_preference_notes,
    parse_coordinator_decision,
    validate_decision_for_context,
)


def interest_counts(**updates: int) -> ActivityInterestCounts:
    values = {
        "food": 0,
        "arts_culture": 1,
        "nature": 1,
        "history": 0,
        "nightlife": 0,
        "shopping": 0,
        "sports": 0,
        "student_budget": 0,
    }
    values.update(updates)
    return ActivityInterestCounts.model_validate(values)


def candidate(
    candidate_id: str = "candidate_A",
    **updates: object,
) -> CandidateSummary:
    values: dict[str, object] = {
        "contract_version": "candidate-summary-v1",
        "candidate_id": candidate_id,
        "total_estimated_cost_minor": 1_000,
        "remaining_budget_minor": 9_000,
        "primary_activity_count": 2,
        "distinct_primary_activity_count": 2,
        "total_transfer_minutes": 60,
        "activity_interest_counts": interest_counts(),
        "requested_interest_coverage_count": 2,
        "daypart_activity_counts": DaypartActivityCounts(
            morning=1, afternoon=1, evening=0
        ),
        "accommodation_style_tags": (AccommodationStyleTag.QUIET,),
        "transport_mode_tags": (CoordinatorTransportModeTag.COACH,),
    }
    values.update(updates)
    return CandidateSummary.model_validate(values)


def context(**updates: object) -> CoordinatorContext:
    values: dict[str, object] = {
        "contract_version": "coordinator-context-v1",
        "interests": (Interest.ARTS_CULTURE, Interest.NATURE),
        "pace": Pace.BALANCED,
        "preference_notes": "Prefer a calm afternoon",
        "candidates": (
            candidate(),
            candidate(
                "candidate_B",
                total_estimated_cost_minor=1_500,
                remaining_budget_minor=8_500,
                primary_activity_count=1,
                distinct_primary_activity_count=1,
                total_transfer_minutes=30,
                activity_interest_counts=interest_counts(arts_culture=1, nature=0),
                requested_interest_coverage_count=1,
                daypart_activity_counts=DaypartActivityCounts(
                    morning=0, afternoon=1, evening=0
                ),
                accommodation_style_tags=(AccommodationStyleTag.SOCIAL,),
                transport_mode_tags=(CoordinatorTransportModeTag.TRAIN,),
            ),
        ),
    }
    values.update(updates)
    return CoordinatorContext.model_validate(values)


def selection(**updates: object) -> CoordinatorDecision:
    values: dict[str, object] = {
        "contract_version": "coordinator-decision-v1",
        "status": "selection",
        "selected_candidate_id": "candidate_A",
        "interpreted_preference_tags": (InterpretedPreferenceTag.DAYTIME_FOCUS,),
        "prioritized_interests": (Interest.ARTS_CULTURE,),
        "abstention_reason": None,
    }
    values.update(updates)
    return CoordinatorDecision.model_validate(values)


@pytest.mark.parametrize(
    "candidate_id",
    [
        "",
        "a" * 65,
        "has space",
        "has.dot",
        "has/slash",
        "unicode–dash",
        "ｆｕｌｌｗｉｄｔｈ",
        "cаndidate",
        "zero\u200bwidth",
        "bidi\u202eid",
    ],
)
def test_candidate_id_is_bounded_ascii_only(candidate_id: str) -> None:
    with pytest.raises(ValidationError):
        candidate(candidate_id)


@pytest.mark.parametrize("candidate_id", ["a", "A" * 64, "a_B-9"])
def test_candidate_id_accepts_exact_lexical_boundary(candidate_id: str) -> None:
    assert candidate(candidate_id).candidate_id == candidate_id


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("total_estimated_cost_minor", -1),
        ("total_estimated_cost_minor", 9_223_372_036_854_775_808),
        ("total_transfer_minutes", 5_761),
        ("primary_activity_count", 17),
        ("primary_activity_count", True),
        ("primary_activity_count", 2.0),
        ("primary_activity_count", "2"),
    ],
)
def test_candidate_summary_rejects_bounds_and_coercion(
    field: str, value: object
) -> None:
    with pytest.raises(ValidationError):
        candidate(**{field: value})


def test_candidate_summary_enforces_cross_field_invariants() -> None:
    with pytest.raises(ValidationError, match="distinct activities"):
        candidate(distinct_primary_activity_count=3)
    with pytest.raises(ValidationError, match="daypart counts"):
        candidate(
            daypart_activity_counts=DaypartActivityCounts(
                morning=0, afternoon=1, evening=0
            )
        )
    with pytest.raises(ValidationError, match="interest counts"):
        candidate(activity_interest_counts=interest_counts(arts_culture=3))
    with pytest.raises(ValidationError, match="distinct source record"):
        candidate(distinct_primary_activity_count=0)
    with pytest.raises(ValidationError, match="at least one interest"):
        candidate(activity_interest_counts=interest_counts(arts_culture=0, nature=0))


def test_exact_count_maps_reject_missing_and_extra_keys() -> None:
    base = interest_counts().model_dump()
    base.pop("food")
    with pytest.raises(ValidationError):
        ActivityInterestCounts.model_validate(base)
    extra = interest_counts().model_dump()
    extra["culture"] = 1
    with pytest.raises(ValidationError):
        ActivityInterestCounts.model_validate(extra)
    with pytest.raises(ValidationError):
        DaypartActivityCounts.model_validate(
            {"morning": 1, "afternoon": 1, "evening": 0, "night": 0}
        )


def test_summary_tags_are_unique_bounded_and_canonically_ordered() -> None:
    with pytest.raises(ValidationError, match="unique"):
        candidate(
            accommodation_style_tags=(
                AccommodationStyleTag.QUIET,
                AccommodationStyleTag.QUIET,
            )
        )
    with pytest.raises(ValidationError, match="canonical order"):
        candidate(
            accommodation_style_tags=(
                AccommodationStyleTag.SOCIAL,
                AccommodationStyleTag.QUIET,
            )
        )
    with pytest.raises(ValidationError):
        candidate(transport_mode_tags=("plane",))
    with pytest.raises(ValidationError):
        candidate(transport_mode_tags=())


def test_context_is_closed_unique_and_budget_consistent() -> None:
    assert context().contract_version == "coordinator-context-v1"
    with pytest.raises(ValidationError):
        CoordinatorContext.model_validate(
            {**context().model_dump(), "origin": "Kingston"}
        )
    with pytest.raises(ValidationError, match="interests must be unique"):
        context(interests=(Interest.NATURE, Interest.NATURE))
    with pytest.raises(ValidationError, match="candidate IDs must be unique"):
        context(candidates=(candidate(), candidate()))
    with pytest.raises(ValidationError, match="metric payloads must be unique"):
        context(candidates=(candidate(), candidate("candidate_B")))
    with pytest.raises(ValidationError, match="one request budget"):
        context(
            candidates=(
                candidate(),
                candidate(
                    "candidate_B",
                    total_estimated_cost_minor=1_500,
                    remaining_budget_minor=9_000,
                ),
            )
        )


def test_context_checks_requested_interest_coverage() -> None:
    with pytest.raises(ValidationError, match="coverage is inconsistent"):
        context(
            candidates=(
                candidate(requested_interest_coverage_count=1),
                context().candidates[1],
            )
        )


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, None),
        ("", None),
        ("  \t\r\n  ", None),
        ("  calm\ttrip\nplease  ", "calm trip please"),
        ("Cafe\u0301", "Café"),
        ("calm\u2003\u2003afternoon", "calm afternoon"),
    ],
)
def test_preference_note_normalization(raw: object, expected: str | None) -> None:
    assert normalize_preference_notes(raw) == expected


def test_preference_note_codepoint_limit_counts_after_nfc() -> None:
    assert normalize_preference_notes("😀" * 300) == "😀" * 300
    assert normalize_preference_notes("e\u0301" * 300) == "é" * 300
    with pytest.raises(ValueError, match="300 Unicode code points"):
        normalize_preference_notes("😀" * 301)


@pytest.mark.parametrize(
    "value",
    [
        "\x00",
        "\x0b",
        "\x1f",
        "\x7f",
        "\x85",
        "\x9f",
        "\u061c",
        "\u200e",
        "\u200f",
        "\u202a",
        "\u202e",
        "\u2066",
        "\u2069",
        "\ud800",
        "\udfff",
    ],
)
def test_preference_notes_reject_controls_and_bidi(value: str) -> None:
    with pytest.raises(ValueError, match="prohibited control"):
        normalize_preference_notes(f"safe{value}text")


def test_context_requires_notes_to_be_normalized_before_construction() -> None:
    with pytest.raises(ValidationError, match="already be normalized"):
        context(preference_notes="  calm\ttrip  ")
    assert context(preference_notes=None).preference_notes is None


@pytest.mark.parametrize(
    "updates",
    [
        {"selected_candidate_id": None},
        {"abstention_reason": AbstentionReason.NO_PREFERENCE_SIGNAL},
        {
            "status": "abstention",
            "selected_candidate_id": "candidate_A",
            "abstention_reason": AbstentionReason.NO_PREFERENCE_SIGNAL,
        },
        {
            "status": "abstention",
            "selected_candidate_id": None,
            "abstention_reason": None,
        },
    ],
)
def test_decision_enforces_selection_and_abstention_matrix(
    updates: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        selection(**updates)


def test_valid_abstention_and_unique_decision_arrays() -> None:
    decision = selection(
        status="abstention",
        selected_candidate_id=None,
        interpreted_preference_tags=(),
        prioritized_interests=(),
        abstention_reason=AbstentionReason.CONFLICTING_PREFERENCES,
    )
    assert decision.status == "abstention"
    with pytest.raises(ValidationError, match="must be unique"):
        selection(
            interpreted_preference_tags=(
                InterpretedPreferenceTag.LOWER_COST,
                InterpretedPreferenceTag.LOWER_COST,
            )
        )
    with pytest.raises(ValidationError, match="must be unique"):
        selection(prioritized_interests=(Interest.NATURE, Interest.NATURE))


def test_contextual_decision_validation_rejects_stale_id_and_interest() -> None:
    current = context()
    assert validate_decision_for_context(selection(), current) == selection()
    unknown = validate_decision_for_context(
        selection(selected_candidate_id="stale_candidate"), current
    )
    assert unknown == DecisionContextFailure(
        DecisionContextFailureCode.UNKNOWN_CANDIDATE
    )
    unsupported = validate_decision_for_context(
        selection(prioritized_interests=(Interest.SPORTS,)), current
    )
    assert unsupported == DecisionContextFailure(
        DecisionContextFailureCode.PRIORITIZED_INTEREST_NOT_REQUESTED
    )


def test_retry_feedback_is_closed_and_uses_unique_bounded_ids() -> None:
    feedback = CoordinatorRetryFeedback(
        contract_version="coordinator-retry-v1",
        code=CoordinatorRetryCode.UNKNOWN_CANDIDATE,
        candidate_ids=("candidate_A", "candidate_B"),
    )
    assert feedback.candidate_ids == ("candidate_A", "candidate_B")
    with pytest.raises(ValidationError):
        CoordinatorRetryFeedback.model_validate(
            {**feedback.model_dump(), "raw_output": "secret"}
        )


def test_raw_output_parser_accepts_one_strict_json_object() -> None:
    raw = selection().model_dump_json()
    assert parse_coordinator_decision(f" \n{raw}\t ") == selection()


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "not json",
        "```json\n{}\n```",
        "[]",
        "{} {}",
        '{"status":"selection"} trailing',
        '{"value":NaN}',
        b"{}",
    ],
)
def test_raw_output_parser_rejects_non_contract_payloads(raw: object) -> None:
    assert isinstance(parse_coordinator_decision(raw), CoordinatorOutputFailure)


def test_raw_output_parser_rejects_duplicate_keys_before_schema_validation() -> None:
    raw = selection().model_dump_json()
    duplicate = raw[:-1] + ',"status":"selection"}'

    assert parse_coordinator_decision(duplicate) == CoordinatorOutputFailure(
        CoordinatorOutputFailureCode.INVALID_JSON
    )


def test_raw_output_parser_rejects_oversized_input_before_parsing() -> None:
    result = parse_coordinator_decision("x" * (MAX_COORDINATOR_DECISION_BYTES + 1))
    assert result == CoordinatorOutputFailure(
        CoordinatorOutputFailureCode.OUTPUT_TOO_LARGE
    )


def test_raw_output_parser_rejects_lone_surrogate_without_raising() -> None:
    assert parse_coordinator_decision("\ud800") == CoordinatorOutputFailure(
        CoordinatorOutputFailureCode.INVALID_JSON
    )


def test_raw_output_parser_enforces_exact_utf8_byte_boundary() -> None:
    assert parse_coordinator_decision("x" * 4_096) == CoordinatorOutputFailure(
        CoordinatorOutputFailureCode.INVALID_JSON
    )
    assert parse_coordinator_decision("x" * 4_097) == CoordinatorOutputFailure(
        CoordinatorOutputFailureCode.OUTPUT_TOO_LARGE
    )
    assert parse_coordinator_decision("é" * 2_048) == CoordinatorOutputFailure(
        CoordinatorOutputFailureCode.INVALID_JSON
    )
    assert parse_coordinator_decision("é" * 2_049) == CoordinatorOutputFailure(
        CoordinatorOutputFailureCode.OUTPUT_TOO_LARGE
    )


def test_raw_output_parser_rejects_escaped_surrogate_and_missing_nulls() -> None:
    escaped_surrogate = (
        selection().model_dump_json().replace('"candidate_A"', '"\\ud800"')
    )
    assert isinstance(
        parse_coordinator_decision(escaped_surrogate), CoordinatorOutputFailure
    )

    payload = selection().model_dump()
    del payload["abstention_reason"]
    assert parse_coordinator_decision(json.dumps(payload)) == CoordinatorOutputFailure(
        CoordinatorOutputFailureCode.OUTPUT_SCHEMA_INVALID
    )


def test_json_boundary_rejects_arrays_duplicates_and_extra_fields() -> None:
    payload = json.loads(selection().model_dump_json())
    payload["interpreted_preference_tags"] = ["lower_cost", "lower_cost"]
    parsed = parse_coordinator_decision(json.dumps(payload))
    assert parsed == CoordinatorOutputFailure(
        CoordinatorOutputFailureCode.OUTPUT_SCHEMA_INVALID
    )
    payload = json.loads(selection().model_dump_json())
    payload["explanation"] = "arbitrary prose"
    assert isinstance(
        parse_coordinator_decision(json.dumps(payload)), CoordinatorOutputFailure
    )
