"""Production-boundary Shader scenarios and scorer sensitivity checks."""
from copy import deepcopy
from pathlib import Path

import pytest

from verification.bench.capabilities.dbfox_shader.build_cases import build_cases
from verification.bench.capabilities.dbfox_shader.runtime import ShaderRuntime, run_case
from verification.bench.capabilities.dbfox_shader.schema import Dataset, load_cases
from verification.bench.capabilities.dbfox_shader.scoring import score_case
from verification.bench.framework.schema import load_suite_manifest

HERE = Path(__file__).resolve().parents[2] / "bench" / "capabilities" / "dbfox_shader"
CASES = load_cases(HERE / "cases.json").cases


@pytest.fixture(scope="module")
def runtime(tmp_path_factory):
    with ShaderRuntime(tmp_path_factory.mktemp("shader-bench")) as value:
        yield value


def test_manifest_and_authored_cases():
    assert load_suite_manifest(HERE / "suite.json").suite_id == "capability.dbfox-shader.scripted"
    assert len(CASES) == 15
    assert len({case.category for case in CASES}) == 15
    assert Dataset.model_validate(build_cases()) == load_cases(HERE / "cases.json")
    assert all(case.assertions for case in CASES)


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.case_id)
def test_production_shader_capability(runtime, case):
    result = run_case(runtime, case)
    assert result.verdict == "pass", {"failed": result.failed_checks,
        "invocations": result.evidence["invocations"], "observations": result.evidence["observations"]}


def test_scorer_rejects_wrong_source_missing_artifact_and_replayed_invocation(runtime):
    case = next(case for case in CASES if case.case_id == "incremental-source")
    result = run_case(runtime, case)
    assert result.verdict == "pass", result.failed_checks
    evidence = deepcopy(result.evidence)
    evidence["artifacts"] = []
    evidence["invocations"][0]["attempts"] = 2
    wrong = case.model_copy(update={"assertions": ({"path": "document.stages.1.source", "value": "wrong"},)})
    rescored = score_case(runtime, wrong, evidence, 1)
    assert rescored.verdict == "fail"
    assert {"final.0", "package_owner_and_no_replay", "artifact.required.create"} <= set(rescored.failed_checks)
