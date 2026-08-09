"""Validate offline or run the explicitly acknowledged live evaluation."""

from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from pathlib import Path

from trippilot.providers import JsonMockTravelDataProvider
from trippilot.services import OpenAICoordinatorAdapter, OpenAICoordinatorConfig

from .batch import run_live_evaluation_batch
from .coordinator import (
    EvaluationRunRecord,
    load_coordinator_evaluation_manifest,
    validate_evaluation_manifest,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
MANIFEST_PATH = REPOSITORY_ROOT / "data/evaluation/coordinator-eval-v1.json"
FIXTURE_PATH = REPOSITORY_ROOT / "data/mock/kingston-toronto-v1.json"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live-output", type=Path)
    parser.add_argument("--code-revision")
    parser.add_argument("--acknowledge-paid-api", action="store_true")
    return parser


def main() -> None:
    arguments = _parser().parse_args()
    manifest = load_coordinator_evaluation_manifest(MANIFEST_PATH)
    provider = JsonMockTravelDataProvider(FIXTURE_PATH)
    validation = validate_evaluation_manifest(manifest, provider)
    if arguments.live_output is not None:
        if not arguments.acknowledge_paid_api or arguments.code_revision is None:
            raise SystemExit(
                "live runs require --acknowledge-paid-api and --code-revision"
            )
        api_key = os.getenv("TRIPPILOT_OPENAI_API_KEY", "")
        try:
            adapter = OpenAICoordinatorAdapter(OpenAICoordinatorConfig(api_key=api_key))
        except ValueError as error:
            raise SystemExit("TRIPPILOT_OPENAI_API_KEY is not configured") from error

        def report_progress(
            record: EvaluationRunRecord, completed: int, expected: int
        ) -> None:
            del record
            print(
                json.dumps(
                    {"completed": completed, "expected": expected},
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                flush=True,
            )

        summary = run_live_evaluation_batch(
            manifest,
            provider,
            adapter,
            code_revision=arguments.code_revision,
            output_path=arguments.live_output,
            on_record=report_progress,
        )
        print(summary.model_dump_json())
        return
    if arguments.code_revision is not None or arguments.acknowledge_paid_api:
        raise SystemExit("live options require --live-output")
    cohorts = Counter(case.cohort.value for case in manifest.cases)
    output = {
        "contract_version": validation.contract_version,
        "fixture_snapshot_version": validation.fixture_snapshot_version,
        "manifest_case_count": len(validation.cases),
        "model_exercising_run_count": sum(
            case.repeated_runs
            for case in manifest.cases
            if case.expected_behavior.value == "model_exercised"
        ),
        "cohorts": dict(sorted(cohorts.items())),
        "status": "valid",
    }
    print(json.dumps(output, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
