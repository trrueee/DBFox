"""Independent deterministic Pixel capability suite on the production RunLoop."""
from pathlib import Path
from io import BytesIO

import pytest
from PIL import Image

from dbfox_dlc_api import ArtifactRepresentationContext, ArtifactRepresentationRequest
from engine.agent.repositories.artifact import ArtifactRepository
from engine.representation import execute_artifact_representation

from verification.bench.capabilities.dbfox_pixel.runtime import PixelRuntime, run_case, run_segment
from verification.bench.capabilities.dbfox_pixel.schema import load_cases
from verification.bench.capabilities.dbfox_pixel.schema import Step
from verification.bench.framework.schema import load_suite_manifest

HERE = Path(__file__).resolve().parents[2] / "bench" / "capabilities" / "dbfox_pixel"
CASES = load_cases(HERE / "cases.json").cases


@pytest.fixture(scope="module")
def runtime(tmp_path_factory):
    with PixelRuntime(tmp_path_factory.mktemp("pixel-independent-bench")) as value:
        yield value


def test_pixel_manifest_has_independently_scored_required_cases():
    manifest = load_suite_manifest(HERE / "suite.json")
    assert manifest.suite_id == "capability.dbfox-pixel.scripted"
    assert len(CASES) == 15 and len({case.case_id for case in CASES}) == 15
    assert all(case.assertions for case in CASES)


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.case_id)
def test_pixel_production_runloop_capability(runtime, case):
    outcome = run_case(runtime, case)
    assert outcome.verdict == "pass", {"failed": outcome.failed_checks,
        "invocations": outcome.evidence["invocations"], "observations": outcome.evidence["observations"]}


def test_two_hundred_wide_frames_export_rows_without_padding_or_reordering(runtime):
    scale = next(case for case in CASES if case.case_id == "hundreds-of-frames")
    steps = list(scale.steps)
    steps[0] = steps[0].model_copy(update={"arguments": {**steps[0].arguments, "width": 128, "height": 1}})
    steps.insert(-1, Step(id="edge-pixels", tool="pixel_apply", arguments={"document_id": "$document_id", "expected_version": "$revision", "operations": [
        {"kind": "rect", "frame_id": "$frames.items.0.id", "layer_id": "$layers.items.0.id", "rect": {"x": 0, "y": 0, "width": 1, "height": 1}, "palette_index": 1},
        {"kind": "rect", "frame_id": "$scale-page-12.items.7.id", "layer_id": "$layers.items.0.id", "rect": {"x": 127, "y": 0, "width": 1, "height": 1}, "palette_index": 2},
    ]}))
    case = scale.model_copy(update={"case_id": "wide-sheet", "steps": tuple(steps)})
    evidence, _ = run_segment(runtime, case)
    assert evidence["run_status"] == "completed" and all(item["status"] == "succeeded" for item in evidence["invocations"])
    invocation = next(item for item in evidence["invocations"] if item["call_id"] == "scale-export")
    identity = next(item["id"] for item in evidence["artifacts"] if item["provenance"]["tool_invocation_id"] == invocation["id"])
    with runtime.factory() as db:
        row = ArtifactRepository(db).get(identity)
        artifact = ArtifactRepository(db).available_artifact(session_id=row.session_id, current_run_id=row.run_id, artifact_id=identity)
    assert artifact is not None
    provider = runtime.snapshot.get_artifact_representation("dbfox.pixel.revision", "dbfox.pixel.sprite.v1").provider
    outputs = {}
    for operation, kind in (("sheet", "stream"), ("sheet_layout", "json")):
        _, outputs[operation] = execute_artifact_representation(artifact=artifact, representation_type="dbfox.pixel.sprite.v1",
            request=ArtifactRepresentationRequest(operation=operation, parameters={}), provider=provider,
            context=ArtifactRepresentationContext(artifact_loader=lambda key: None), expected_kind=kind)
    decoded = Image.open(BytesIO(b"".join(outputs["sheet"].chunks))).convert("RGBA")
    assert decoded.size == (6400, 4) and decoded.width * decoded.height == 200 * 128
    expected = bytearray(6400 * 4 * 4)
    expected[:4] = bytes((24, 24, 37, 255))
    expected[-4:] = bytes((255, 255, 255, 255))
    assert decoded.tobytes() == expected
    frames = outputs["sheet_layout"].payload["frames"]
    assert [item["frame_id"] for item in frames] == ["frame_1", *[f"scale_{index}" for index in range(1, 200)]]
    assert [(item["x"], item["y"]) for item in frames] == [((index % 50) * 128, index // 50) for index in range(200)]
