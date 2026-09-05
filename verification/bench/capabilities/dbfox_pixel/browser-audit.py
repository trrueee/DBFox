"""Independent reads and scripted Agent follow-up against this browser's installed package."""
from pathlib import Path
from io import BytesIO
import hashlib
import json
import sys

from PIL import Image
from dbfox_dlc_api import RequestedResourceRef
from engine.agent.references import ConversationInputReference
from engine.agent.repositories.artifact import ArtifactRepository
from engine.models import AgentRun, AgentToolInvocation
from .runtime import HERE, ROOT, PixelRuntime, run_segment
from .schema import PixelCase, Step
from .scoring import independent_rgba


def verify(directory, evidence_name):
    evidence = json.loads((HERE / "evidence" / evidence_name).read_text(encoding="utf-8"))
    project = evidence["state"]["project"]
    workbench = evidence["state"]["workbench"]
    artifact_id = next(tab["target"]["id"] for tab in workbench["tabs"] if tab["viewKey"] == workbench["activeViewKey"])
    with PixelRuntime(directory, existing=True) as runtime:
        with runtime.factory() as db:
            target = ArtifactRepository(db).get(artifact_id)
        owner_ref = next(ref for ref in workbench["references"] if ref.get("authority", {}).get("id") == target.payload["document_id"])
        document = runtime.document(project, owner_ref["authority"]["id"], int(owner_ref["object"]["version"]))
        frames = document["document"]["frames"]
        width, height = document["document"]["canvas"]["width"], document["document"]["canvas"]["height"]
        for item in evidence["downloads"]:
            path = ROOT / "output/playwright" / ("interactive-pixel.png" if item["format"] == "png" else "interactive-pixel-sheet.png")
            data = path.read_bytes()
            assert hashlib.sha256(data).hexdigest() == item["blob"]["sha256"]
            decoded = Image.open(BytesIO(data)).convert("RGBA")
            expected_frames = frames[:1] if item["format"] == "png" else frames
            assert decoded.size == (width * len(expected_frames), height)
            for index, frame in enumerate(expected_frames):
                actual = decoded.crop((index * width, 0, (index + 1) * width, height)).tobytes()
                assert actual == independent_rgba(document, frame["id"])
            item["independent_rgba_equal"] = True
            item["dimensions"] = list(decoded.size)
        with runtime.factory() as db:
            artifact = ArtifactRepository(db).get(artifact_id)
            run = db.get(AgentRun, artifact.run_id)
            invocations = db.query(AgentToolInvocation).filter_by(run_id=artifact.run_id).all()
            assert run.status == "completed" and len(invocations) == 1 and invocations[0].status == "succeeded"
            evidence["producer"] = {"run_id": run.id, "session_id": artifact.session_id, "status": run.status,
                "artifact_id": artifact.id, "payload": artifact.payload, "provenance": artifact.provenance,
                "invocation_id": invocations[0].id, "resource_refs": json.loads(invocations[0].resource_refs_json)}
        evidence["package_digest"] = runtime.package.package_digest
    (HERE / "evidence" / evidence_name).write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"verified": len(evidence["downloads"]), "package_digest": evidence["package_digest"]}))


def agent(directory, evidence_name):
    evidence = json.loads((HERE / "evidence" / evidence_name).read_text(encoding="utf-8"))
    raw = next(ref for ref in evidence["state"]["workbench"]["references"] if ref.get("authority"))
    reference = ConversationInputReference.model_validate(raw)
    selected_id = reference.authority.id  # Actual user-selected onAsk identity; revisions come only from observations.
    case = PixelCase(case_id="browser-human-agent", category="human-agent", prompt="Inspect my selected work, then draw an Ink pixel at (0,15) in its first frame and layer.", steps=(
        Step(id="frames", tool="pixel_inspect", arguments={"document_id": selected_id, "kind": "frames"}),
        Step(id="layers", tool="pixel_inspect", arguments={"document_id": "$document_id", "kind": "layers"}),
        Step(id="human-agent-mark", tool="pixel_rect", arguments={"document_id": "$document_id", "expected_version": "$revision", "operation": {
            "kind": "rect", "frame_id": "$frames.items.0.id", "layer_id": "$layers.items.0.id", "rect": {"x": 0, "y": 15, "width": 1, "height": 1}, "palette_index": 1}}),
    ))
    with PixelRuntime(directory, existing=True) as runtime:
        result, script = run_segment(runtime, case, project_id=evidence["state"]["project"],
            initial_resources=(RequestedResourceRef.model_validate(raw["authority"]),), input_references=(reference,))
        assert result["run_status"] == "completed" and all(item["status"] == "succeeded" for item in result["invocations"])
        result["observed_summary"] = script.summary
        result["actual_on_ask"] = raw
        generic = next((ref for ref in evidence["state"]["workbench"]["references"] if ref.get("artifactId")), None)
        if generic:
            with runtime.factory() as db:
                available = ArtifactRepository(db).available_artifact(session_id=result["session_id"], current_run_id=result["run_id"], artifact_id=generic["artifactId"])
            assert available is None
            result["artifact_from_other_action_session_available"] = False
            result["tested_artifact_only_reference"] = generic
        final = runtime.document(result["project_id"], selected_id, script.summary["revision"])
        assert final["frame_reads"][0]["frame"]["cels"][0]["pixels"][15 * 16] == 1
    (HERE / "evidence/browser-human-agent.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"run_id": result["run_id"], "status": result["run_status"], "revision": script.summary["revision"]}))


if __name__ == "__main__":
    (agent if sys.argv[1] == "agent" else verify)(Path(sys.argv[2]).resolve(), sys.argv[3])
