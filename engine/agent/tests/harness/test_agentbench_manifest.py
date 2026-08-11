from __future__ import annotations

from collections import Counter
from pathlib import Path

from scripts.agentbench.schema import DatasetRole, load_manifest


ROOT = Path(__file__).resolve().parents[4]
MANIFEST = ROOT / "scripts" / "agentbench" / "datasets" / "regression-v1.json"


def test_regression_manifest_has_the_versioned_sixty_case_matrix() -> None:
    manifest = load_manifest(MANIFEST)
    assert manifest.role is DatasetRole.REGRESSION
    assert len(manifest.cases) == 60
    assert Counter(case.category for case in manifest.cases) == {
        "basic_sql": 12,
        "multi_stage": 8,
        "tool_recovery": 8,
        "context_memory": 8,
        "security": 8,
        "large_result": 6,
        "fault_interrupt": 5,
        "uncertainty": 5,
    }


def test_nightly_and_fault_profiles_are_explicit_and_non_overlapping() -> None:
    manifest = load_manifest(MANIFEST)
    nightly = manifest.select(tags=frozenset({"nightly", "real_provider"}))
    fault = manifest.select(tags=frozenset({"deterministic_fault"}))
    assert len(nightly) == 40
    assert len(fault) == 5
    assert not ({case.case_id for case in nightly} & {case.case_id for case in fault})


def test_hidden_holdout_can_be_loaded_from_an_external_manifest() -> None:
    manifest = load_manifest(MANIFEST)
    selected = manifest.select(case_ids=frozenset({"sql-count-orders"}))
    assert [case.case_id for case in selected] == ["sql-count-orders"]
