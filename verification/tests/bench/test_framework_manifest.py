from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from verification.bench.framework.schema import (
    BenchSubjectKind,
    SuiteManifest,
    load_suite_manifest,
)


ROOT = Path(__file__).resolve().parents[3]


def test_every_registered_suite_declares_its_subject_and_metrics() -> None:
    paths = (
        ROOT / "verification" / "bench" / "core" / "loop" / "suite.json",
        ROOT
        / "verification"
        / "bench"
        / "capabilities"
        / "dbfox_data"
        / "agent"
        / "suite.json",
    )
    manifests = tuple(load_suite_manifest(path) for path in paths)
    assert [item.subject.kind for item in manifests] == [
        BenchSubjectKind.CORE,
        BenchSubjectKind.CAPABILITY,
    ]
    assert all(item.metrics for item in manifests)


def test_core_subject_cannot_smuggle_a_capability_into_the_subject() -> None:
    with pytest.raises(ValidationError, match="CoreBench"):
        SuiteManifest.model_validate(
            {
                "schema_version": "1.0",
                "suite_id": "core.invalid",
                "suite_version": "1.0.0",
                "description": "invalid core ownership",
                "subject": {
                    "kind": "core",
                    "components": ["dbfox.data"],
                },
                "dataset": "cases.json",
                "metrics": [
                    {
                        "name": "task.success",
                        "direction": "higher_is_better",
                        "unit": "ratio",
                        "description": "invalid fixture",
                    }
                ],
            }
        )
