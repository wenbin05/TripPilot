"""Resumable, sanitized live coordinator evaluation batches."""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Literal

from pydantic import Field, TypeAdapter

from trippilot.providers import TravelDataProvider
from trippilot.services import CoordinatorAdapter

from .coordinator import (
    CoordinatorEvaluationManifest,
    EvaluationCaseBehavior,
    EvaluationRunOutcome,
    EvaluationRunRecord,
    EvaluationSchema,
    run_evaluation_case,
    validate_evaluation_manifest,
)

RunProgress = Callable[[EvaluationRunRecord, int, int], None]
_RUN_RECORDS = TypeAdapter(tuple[EvaluationRunRecord, ...])


class EvaluationBatchSummary(EvaluationSchema):
    contract_version: Literal["coordinator-eval-batch-v1"]
    code_revision: str = Field(pattern=r"^[a-f0-9]{7,40}$")
    expected_run_count: int = Field(ge=1, le=100)
    completed_run_count: int = Field(ge=0, le=100)
    coordinator_selection_count: int = Field(ge=0, le=100)
    deterministic_fallback_count: int = Field(ge=0, le=100)
    first_attempt_selection_count: int = Field(ge=0, le=100)
    total_estimated_cost_micro_usd: int = Field(ge=0)


def run_live_evaluation_batch(
    manifest: CoordinatorEvaluationManifest,
    provider: TravelDataProvider,
    adapter: CoordinatorAdapter,
    *,
    code_revision: str,
    output_path: str | Path,
    on_record: RunProgress | None = None,
) -> EvaluationBatchSummary:
    """Run or resume all frozen model cases with an atomic checkpoint per run."""

    if not _valid_revision(code_revision):
        raise ValueError("code revision must be a lowercase hexadecimal Git revision")
    validate_evaluation_manifest(manifest, provider)
    expected = _expected_runs(manifest)
    if len(expected) != 100:
        raise ValueError("live evaluation contract must contain exactly 100 runs")

    destination = Path(output_path)
    completed = list(_load_checkpoint(destination))
    _validate_checkpoint(manifest, completed, expected, code_revision)
    completed_keys = {(record.scenario_id, record.run_number) for record in completed}

    for scenario_id, run_number in expected:
        if (scenario_id, run_number) in completed_keys:
            continue
        record = run_evaluation_case(
            manifest,
            scenario_id,
            provider,
            adapter,
            code_revision=code_revision,
            run_number=run_number,
        )
        completed.append(record)
        completed_keys.add((scenario_id, run_number))
        _write_checkpoint(destination, completed)
        if on_record is not None:
            on_record(record, len(completed), len(expected))

    return _batch_summary(code_revision, completed, len(expected))


def load_evaluation_run_records(path: str | Path) -> tuple[EvaluationRunRecord, ...]:
    """Load strict sanitized records from an existing batch checkpoint."""

    return _load_checkpoint(Path(path))


def _expected_runs(
    manifest: CoordinatorEvaluationManifest,
) -> tuple[tuple[str, int], ...]:
    return tuple(
        (case.scenario_id, run_number)
        for case in manifest.cases
        if case.expected_behavior is EvaluationCaseBehavior.MODEL_EXERCISED
        for run_number in range(1, case.repeated_runs + 1)
    )


def _load_checkpoint(path: Path) -> tuple[EvaluationRunRecord, ...]:
    if not path.exists():
        return ()
    try:
        return _RUN_RECORDS.validate_json(path.read_text("utf-8"))
    except (OSError, ValueError) as error:
        raise ValueError(
            "evaluation checkpoint is not a strict run-record array"
        ) from error


def _validate_checkpoint(
    manifest: CoordinatorEvaluationManifest,
    records: list[EvaluationRunRecord],
    expected: tuple[tuple[str, int], ...],
    code_revision: str,
) -> None:
    expected_keys = set(expected)
    seen: set[tuple[str, int]] = set()
    cases = {case.scenario_id: case for case in manifest.cases}
    for record in records:
        key = (record.scenario_id, record.run_number)
        if key not in expected_keys or key in seen:
            raise ValueError("evaluation checkpoint has an unknown or duplicate run")
        seen.add(key)
        case = cases[record.scenario_id]
        if (
            record.code_revision != code_revision
            or record.fixture_snapshot_version != manifest.fixture_snapshot_version
            or record.prompt_id != manifest.prompt_id
            or record.requested_model != manifest.requested_model
            or record.candidate_ids != case.expected_candidate_ids
            or record.candidate_set_digest != case.candidate_set_digest
        ):
            raise ValueError("evaluation checkpoint does not match the frozen run")


def _write_checkpoint(path: Path, records: list[EvaluationRunRecord]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    payload = json.dumps(
        [record.model_dump(mode="json") for record in records],
        sort_keys=True,
        separators=(",", ":"),
    )
    with temporary.open("w", encoding="utf-8") as file:
        file.write(payload)
        file.write("\n")
        file.flush()
        os.fsync(file.fileno())
    temporary.replace(path)


def _batch_summary(
    code_revision: str, records: list[EvaluationRunRecord], expected_count: int
) -> EvaluationBatchSummary:
    selections = sum(
        record.outcome is EvaluationRunOutcome.COORDINATOR_SELECTION
        for record in records
    )
    return EvaluationBatchSummary(
        contract_version="coordinator-eval-batch-v1",
        code_revision=code_revision,
        expected_run_count=expected_count,
        completed_run_count=len(records),
        coordinator_selection_count=selections,
        deterministic_fallback_count=len(records) - selections,
        first_attempt_selection_count=sum(
            record.outcome is EvaluationRunOutcome.COORDINATOR_SELECTION
            and record.attempt_count == 1
            for record in records
        ),
        total_estimated_cost_micro_usd=sum(
            record.estimated_cost_micro_usd or 0 for record in records
        ),
    )


def _valid_revision(value: str) -> bool:
    return 7 <= len(value) <= 40 and all(
        character in "0123456789abcdef" for character in value
    )
