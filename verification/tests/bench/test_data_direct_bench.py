from __future__ import annotations

from verification.bench.capabilities.dbfox_data.direct.runtime import (
    run_data_direct_bench,
)


def test_data_direct_bench_executes_public_system_dlc_operations(tmp_path) -> None:
    output = tmp_path / "data-direct-report"

    summary = run_data_direct_bench(output_dir=output)

    assert summary["passed_trials"] == 3
    assert summary["scored_trials"] == 3
    assert summary["failed_checks"] == []
    assert (output / "report.md").is_file()
