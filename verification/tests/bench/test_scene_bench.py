"""Independent Scene CapabilityBench through the full production Agent path."""
from __future__ import annotations

import json
import pytest

from verification.bench.capabilities.dbfox_scene.runtime import HERE, SceneRuntime, run_case
from verification.bench.capabilities.dbfox_scene.schema import load_cases


@pytest.fixture(scope="module")
def scene_runtime(tmp_path_factory):
    with SceneRuntime(tmp_path_factory.mktemp("scene-independent-bench")) as runtime:
        yield runtime


@pytest.mark.parametrize("case", load_cases(HERE / "cases.json").cases, ids=lambda case: case.case_id)
def test_scene_capability_case(scene_runtime, case):
    outcome = run_case(scene_runtime, case)
    assert outcome.verdict == "pass", json.dumps({"failed": outcome.failed_checks,
        "status": outcome.evidence["run_status"], "invocations": outcome.evidence["invocations"],
        "observations": outcome.evidence["observations"]}, ensure_ascii=False)
