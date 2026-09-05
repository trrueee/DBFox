"""Persist UI evidence and independently follow its real onAsk via production composition."""
from __future__ import annotations

import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import shutil
import sys
from uuid import uuid4


def audit(directory):
    root = Path(__file__).resolve().parents[4]
    here = Path(__file__).resolve().parent
    for name in ("gestures", "artifact-close", "generation-stream"):
        text = (root / f"output/playwright/pixel-redteam-{name}.txt").read_text(encoding="utf-8-sig")
        value = json.loads(text.split("### Result\n", 1)[1].split("\n### Ran", 1)[0])
        (here / f"evidence/redteam-{name}.json").write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    for name in ("gestures", "artifact"):
        shutil.copyfile(root / f"output/playwright/pixel-redteam-{name}.png", root / f"docs/images/pixel-redteam-{name}.png")
    os.environ.update(DBFOX_RUNTIME_DIR=str(directory), DBFOX_DATABASE_URL="sqlite:///" + str(directory / "metadata.sqlite").replace("\\", "/"),
        DBFOX_TESTING="1", DBFOX_SYSTEM_DLC_DIR="", DBFOX_SYSTEM_DLC_MANIFEST="")
    from PIL import Image
    from dbfox_dlc_api import ArtifactRepresentationContext, ArtifactRepresentationRequest, ToolKey
    from engine.agent.context import ContextAssembler
    from engine.agent.references import ConversationInputReference
    from engine.agent.repositories.artifact import ArtifactRepository
    from engine.agent.repositories.session import SessionRepository
    from engine.api.conversation_commands import _reference_resource_identities
    from engine.models import AgentRun, AgentSession, AgentToolInvocation
    from engine.runtime_composition import authorize_project_resources, build_product_run_loop
    from .runtime import PixelRuntime, PixelScript
    from .schema import PixelCase, Step
    capture = json.loads((here / "evidence/redteam-artifact-close.json").read_text(encoding="utf-8"))
    references = []
    for item in capture["after"]["workbench"]["references"]:
        wire = dict(item)
        if "artifactId" in wire:
            wire["artifact_id"] = wire.pop("artifactId")
        references.append(ConversationInputReference.model_validate(wire))
    refs = tuple(references)
    document_id = next(item.authority.id for item in refs if item.authority)
    project = capture["after"]["project"]
    with PixelRuntime(directory, existing=True) as runtime:
        result = {"package_digest": runtime.package.package_digest, "actual_references": [item.model_dump(mode="json", exclude_none=True) for item in refs], "exports": []}
        before = runtime.operation(project, "documents.get", {"document_id": document_id})["summary"]
        before_pixels = runtime.operation(project, "frames.read", {"document_id": document_id, "revision": before["revision"], "frame_id": "frame_1"})["frame"]["cels"][0]["pixels"]
        with runtime.factory() as db:
            repo = ArtifactRepository(db)
            for key in ("cancelled", "current"):
                envelope = capture[key]
                artifact = repo.available_artifact(session_id=envelope["session_id"], current_run_id=envelope["run_id"], artifact_id=envelope["artifact_ids"][0])
                assert artifact is not None
                run = db.get(AgentRun, artifact.run_id)
                calls = db.query(AgentToolInvocation).filter_by(run_id=artifact.run_id).all()
                assert run.status == "completed" and len(calls) == 1 and calls[0].status == "succeeded" and calls[0].attempt_count == 1
                result["exports"].append({"key": key, "run_id": run.id, "session_id": run.session_id, "artifact_id": artifact.id,
                    "payload": artifact.payload, "provenance": artifact.provenance, "invocation_id": calls[0].id,
                    "invocation_resources": json.loads(calls[0].resource_refs_json), "package_digest": calls[0].package_digest})
            selected = artifact
            session_id = "pixel-red-onask-" + uuid4().hex
            db.add(AgentSession(id=session_id, project_id=project, title="Independent actual Pixel onAsk")); db.commit()
            resources = authorize_project_resources(db, project, _reference_resource_identities(refs), snapshot=runtime.snapshot)
            sessions = SessionRepository(db)
            admission = sessions.admit(session_id=session_id, resource_refs=resources, references=refs,
                content="Inspect my selected Pixel frame and layer, then draw one Ink pixel at (0,15).", idempotency_key=uuid4().hex,
                llm_credential_id="pixel-red-scripted", api_base=None, model_name="scripted", request_payload={"purpose": "actual onAsk red team"})
            lease = sessions.claim(session_id=session_id, owner="pixel-red", ttl_seconds=600)
            assert lease is not None
            sessions.promote_next_input(lease=lease); db.commit()
            available = repo.available_artifact(session_id=session_id, current_run_id=admission.run_id, artifact_id=selected.id)
            assert available is None
            context = ContextAssembler(db).build(admission.run_id)
            assert selected.id not in [item.id for item in context.selected_artifacts]
        case = PixelCase(case_id="actual-red-onask", category="adversarial", prompt="Inspect and draw the requested one pixel.", steps=(
            Step(id="frames", tool="pixel_inspect", arguments={"document_id": document_id, "kind": "frames"}),
            Step(id="layers", tool="pixel_inspect", arguments={"document_id": "$document_id", "kind": "layers"}),
            Step(id="edit", tool="pixel_rect", arguments={"document_id": "$document_id", "expected_version": "$revision", "operation": {
                "kind": "rect", "frame_id": "$frames.items.0.id", "layer_id": "$layers.items.0.id", "palette_index": 1,
                "rect": {"x": 0, "y": 15, "width": 1, "height": 1}}}),
        ))
        script = PixelScript(case, project, lambda _: None, {item.tool.name: runtime.registry.provider_name_for_key(ToolKey(owner_id="dbfox.pixel", local_name=item.tool.name))
            for item in runtime.snapshot.tools if item.owner_id == "dbfox.pixel"})
        loop = build_product_run_loop(session_factory=runtime.factory, snapshot=runtime.snapshot)
        loop.model_factory = lambda _: script
        try:
            loop.execute(lease=lease, run_id=admission.run_id)
        finally:
            loop.close()
        final = runtime.operation(project, "documents.get", {"document_id": document_id})["summary"]
        pixels = runtime.operation(project, "frames.read", {"document_id": document_id, "revision": final["revision"], "frame_id": "frame_1"})["frame"]["cels"][0]["pixels"]
        assert final["revision"] == before["revision"] + 1 and pixels[240] == 1
        assert [index for index, (left, right) in enumerate(zip(before_pixels, pixels, strict=True)) if left != right] == [240]
        with runtime.factory() as db:
            run = db.get(AgentRun, admission.run_id)
            calls = db.query(AgentToolInvocation).filter_by(run_id=admission.run_id).all()
            assert run.status == "completed" and len(calls) == 3 and all(item.status == "succeeded" for item in calls)
            result["onask"] = {"run_id": run.id, "status": run.status, "before": before, "after": final, "artifact_other_session_available": False,
                "changed_pixel_indices": [240], "observations": script.observations, "max_observation_bytes": script.max_observation_bytes,
                "invocations": [{"id": item.id, "name": item.tool_name, "attempts": item.attempt_count, "package_digest": item.package_digest,
                    "resources": json.loads(item.resource_refs_json), "input": json.loads(item.input_json)} for item in calls]}
        provider = runtime.snapshot.get_artifact_representation("dbfox.pixel.revision", "dbfox.pixel.sprite.v1").provider
        stream = provider.execute(selected, ArtifactRepresentationRequest(operation="png", parameters={"frame_id": "frame_1"}), ArtifactRepresentationContext(artifact_loader=lambda _: None))
        data = b"".join(stream.chunks)
        assert hashlib.sha256(data).hexdigest() == capture["preview"]["sha256"]
        image = Image.open(BytesIO(data)).convert("RGBA")
        assert image.getpixel((0, 15))[3] == 0
        result["historical_preview"] = {"unchanged_after_agent_edit": True, "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data), "size": list(image.size)}
        (here / "evidence/redteam-durable.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"run": result["onask"]["run_id"], "status": "completed", "before": before["revision"], "after": final["revision"], "package_digest": result["package_digest"]}))


if __name__ == "__main__":
    audit(Path(sys.argv[1]).resolve())
