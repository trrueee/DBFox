"""Director-authored Voxel CapabilityBench through the full production Agent path."""
from __future__ import annotations

import json
import pytest

from verification.bench.capabilities.dbfox_voxel.runtime import HERE, VoxelRuntime, run_case
from verification.bench.capabilities.dbfox_voxel.schema import load_cases


@pytest.fixture(scope="module")
def voxel_runtime(tmp_path_factory):
    with VoxelRuntime(tmp_path_factory.mktemp("voxel-capability-bench")) as runtime:
        yield runtime


@pytest.mark.parametrize("case", load_cases(HERE / "cases.json").cases, ids=lambda case: case.case_id)
def test_voxel_capability_case(voxel_runtime, case):
    outcome = run_case(voxel_runtime, case)
    assert outcome.verdict == "pass", json.dumps({"failed": outcome.failed_checks,
        "status": outcome.evidence["run_status"], "invocations": outcome.evidence["invocations"],
        "observations": outcome.evidence["observations"]}, ensure_ascii=False)
