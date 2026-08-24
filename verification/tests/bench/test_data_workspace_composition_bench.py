from __future__ import annotations

from verification.bench.composition.data_workspace.runtime import (
    run_data_workspace_bench,
)


def test_data_workspace_bench_executes_one_production_cross_capability_run(
    tmp_path,
) -> None:
    output = tmp_path / "data-workspace-report"

    summary = run_data_workspace_bench(output_dir=output)

    assert summary["passed_trials"] == 1
    assert summary["scored_trials"] == 1
    assert summary["failed_checks"] == []
    assert summary["metrics"]["composition.authorized_resource_count"]["median"] == 2.0
