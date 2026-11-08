"""Run signed capability scenarios through the actual Sidecar composition factory."""
from pathlib import Path

import pytest

from engine.runtime_composition import build_product_run_loop
from verification.bench.capabilities.dbfox_scene import runtime as scene
from verification.bench.capabilities.dbfox_voxel import runtime as voxel


@pytest.mark.parametrize("suite,runtime_type", [(scene, scene.SceneRuntime), (voxel, voxel.VoxelRuntime)], ids=["scene", "voxel"])
def test_product_factory_executes_signed_capability_and_publishes_proven_artifacts(tmp_path: Path, monkeypatch, suite, runtime_type):
    with runtime_type(tmp_path) as runtime:
        case = suite.load_cases(suite.HERE / "cases.json").cases[0]
        factory_calls = []

        def production_factory(**fixture_arguments):
            # Reuse the suite's admission and independent domain scorer, but
            # replace its manually composed constructor with the real entrypoint.
            # Only the model is controlled; do not inject registry or resolvers.
            loop = build_product_run_loop(session_factory=runtime.factory, snapshot=runtime.snapshot)
            loop.model_factory = fixture_arguments["model_factory"]
            factory_calls.append(loop)
            return loop

        monkeypatch.setattr(suite, "RunLoop", production_factory)
        outcome = suite.run_case(runtime, case)
        assert len(factory_calls) == 1
        assert outcome.verdict == "pass", outcome.failed_checks
        assert outcome.evidence["invocations"]
        assert outcome.evidence["artifacts"]
        assert all(item["status"] == "succeeded" and item["attempts"] == 1 for item in outcome.evidence["invocations"])
