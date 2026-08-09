"""Validate the frozen coordinator evaluation manifest without model egress."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from trippilot.providers import JsonMockTravelDataProvider

from .coordinator import (
    load_coordinator_evaluation_manifest,
    validate_evaluation_manifest,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
MANIFEST_PATH = REPOSITORY_ROOT / "data/evaluation/coordinator-eval-v1.json"
FIXTURE_PATH = REPOSITORY_ROOT / "data/mock/kingston-toronto-v1.json"


def main() -> None:
    manifest = load_coordinator_evaluation_manifest(MANIFEST_PATH)
    validation = validate_evaluation_manifest(
        manifest, JsonMockTravelDataProvider(FIXTURE_PATH)
    )
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
