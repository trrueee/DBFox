"""Independent composition: real signed owners, public artifacts, real Agent loop.

Only the external model HTTP response is scripted. This does not claim live-model
quality or browser playback; it verifies durable Scene bindings and tracks.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric import ed25519
import httpx
from openai import AsyncOpenAI
from sqlalchemy.orm import sessionmaker

from dbfox_dlc_api import ArtifactRepresentationContext, ArtifactRepresentationRequest, RequestedResourceRef, ToolKey
from engine.agent.context_budget import estimate_input_items_tokens, estimate_tool_schema_tokens
from engine.agent.providers.openai import OpenAIModelAdapter
from engine.agent.repositories.artifact import ArtifactRepository
from engine.agent.repositories.session import SessionRepository
from engine.dlc import DlcPackageService
from engine.dlc.package_builder import build_dlc_package_from_source
from engine.models import AgentRun, AgentSession, AgentToolInvocation, Project
from engine.runtime_composition import (
    active_runtime_snapshot, authorize_project_resources, build_product_run_loop,
    build_product_tool_registry, initialize_runtime_snapshot, set_active_runtime_snapshot,
)
from verification.support.metadata import create_migrated_metadata_engine

ROOT = Path(__file__).resolve().parents[3]
PROJECT = "scene-animation-independent"


class ModelBoundary:
    def __init__(self, registry):
        self.registry = registry
        self.requests, self.outputs, self.errors = [], [], []
        self.searches = 0
        self.plan = self.steps()

    def steps(self):
        yield "dbfox.scene", "scene_create", {"title": "Fixed fox source"}
        self.scene_id = self.outputs[-1]["facts"]["scene"]["id"]
        yield "dbfox.scene", "object_create", {"scene_id": self.scene_id, "expected_version": 1,
            "operation": {"kind": "object_create", "objects": [{"kind": "group", "id": "fox", "name": "Fox", "position": [3,2,1]}]}}
        self.source_artifact_id = self.outputs[-1]["artifact_ids"][0]
        yield "dbfox.animation", "animation_create", {"title": "Fox motion"}
        self.animation_id = self.outputs[-1]["facts"]["animation"]["id"]
        self.bind_call_id = str(len(self.outputs))
        yield "dbfox.animation", "scene_bind", {"animation_id": self.animation_id, "expected_version": 1,
            "artifact_id": self.source_artifact_id, "object_ids": ["fox"]}
        self.bound_artifact_id = self.outputs[-1]["artifact_ids"][0]
        yield "dbfox.animation", "animation_inspect", {"animation_id": self.animation_id, "section": "targets"}
        self.target = self.outputs[-1]["facts"]["items"][0]
        yield "dbfox.animation", "track_create", {"animation_id": self.animation_id, "expected_version": 2,
            "operation": {"kind": "track_create", "track": {"id": "motion", "name": "Move X", "target_id": self.target["id"], "property": "position.x"}}}
        yield "dbfox.animation", "keyframe_add", {"animation_id": self.animation_id, "expected_version": 3,
            "operation": {"kind": "keyframe_add", "keyframes": [{"id": "start", "track_id": "motion", "tick": 0, "value": 3}, {"id": "end", "track_id": "motion", "tick": 4000, "value": 9}]}}
        self.fixed_artifact_id = self.outputs[-1]["artifact_ids"][0]
        yield "dbfox.scene", "object_delete", {"scene_id": self.scene_id, "expected_version": 2,
            "operation": {"kind": "object_delete", "object_ids": ["fox"]}}
        self.deleted_source_artifact_id = self.outputs[-1]["artifact_ids"][0]
        yield "dbfox.animation", "keyframe_move", {"animation_id": self.animation_id, "expected_version": 4,
            "operation": {"kind": "keyframe_move", "keyframes": [{"id": "end", "tick": 4001, "value": 10}]}}
        self.changed_artifact_id = self.outputs[-1]["artifact_ids"][0]
        yield "dbfox.animation", "animation_export", {"animation_id": self.animation_id, "expected_version": 5}
        self.export_artifact_id = self.outputs[-1]["artifact_ids"][0]
    def respond(self, request):
        try:
            return self.response(request)
        except Exception as error:
            self.errors.append(repr(error))
            raise

    def response(self, request):
        assert request.url.host == "scene-animation-model.invalid"
        payload = json.loads(request.content)
        assert payload["model"] == "gpt-5.4"
        assert payload["store"] is False and payload["parallel_tool_calls"] is False
        self.requests.append(payload)
        seen = {str(n) for n in range(len(self.outputs))}
        for item in payload["input"]:
            if item.get("type") != "function_call_output" or item["call_id"] in seen:
                continue
            assert item["call_id"] == str(len(self.outputs))
            output = json.loads(item["output"])
            assert output["status"] == getattr(self, "expected_status", "succeeded"), (self.last_step, output)
            self.outputs.append(output)
        step = next(self.plan, None)
        if step is None:
            items = [{"id": "msg_done", "type": "message", "role": "assistant", "status": "completed",
                "phase": "final_answer", "content": [{"type": "output_text", "text": "Processed the Animation workflow. The tool results identify completed changes and any rejected operations.", "annotations": [], "logprobs": []}]}]
        else:
            owner, local_name, arguments = step
            self.last_step = step
            name = self.registry.provider_name_for_key(ToolKey(owner_id=owner, local_name=local_name))
            tool = next(t for t in payload["tools"] if t.get("name") == name)
            assert tool["defer_loading"] is True
            assert any(t["type"] == "tool_search" for t in payload["tools"])
            self.searches += 1
            # Hosted definitions, like every other external model event, are scripted.
            items = [
                {"id": f"ts_{self.searches}", "type": "tool_search_call", "execution": "server", "call_id": None,
                    "status": "completed", "arguments": {"paths": [name]}},
                {"id": f"tso_{self.searches}", "type": "tool_search_output", "execution": "server", "call_id": None,
                    "status": "completed", "tools": [tool]},
                {"id": f"fc_{len(self.outputs)}", "type": "function_call", "status": "completed", "call_id": str(len(self.outputs)),
                    "name": name, "arguments": json.dumps(arguments)},
            ]
        events = []
        for n, item in enumerate(items):
            events.extend([
                {"type": "response.output_item.added", "output_index": n, "item": {**item, "status": "in_progress"}},
                {"type": "response.output_item.done", "output_index": n, "item": item},
            ])
        events.append({"type": "response.completed", "response": {"id": f"resp_{len(self.requests)}", "object": "response",
            "created_at": 0, "model": payload["model"], "status": "completed", "output": items,
            "parallel_tool_calls": False, "tool_choice": "auto", "tools": payload["tools"]}})
        sse = "".join(f"event: {event['type']}\ndata: {json.dumps({**event, 'sequence_number': n})}\n\n" for n, event in enumerate(events))
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=sse)


def test_signed_scene_animation_uses_fixed_public_objects(tmp_path, record_property):
    previous = active_runtime_snapshot()
    service = DlcPackageService(tmp_path / "dlcs")
    digests = {}
    publisher = ed25519.Ed25519PrivateKey.generate()
    for owner in ("dbfox.scene", "dbfox.animation"):
        package = build_dlc_package_from_source(ROOT / "dlcs" / owner, private_key=publisher)
        archive = tmp_path / f"{owner}.dbfox-dlc"
        archive.write_bytes(package.archive_bytes)
        service.trust_publisher_from_file(archive, expected_package_digest=package.package_digest,
            expected_publisher_key_id=package.publisher_fingerprint)
        service.install_from_file(archive)
        service.set_desired_enabled(owner, True)
        digests[owner] = package.package_digest
    engine = create_migrated_metadata_engine(tmp_path / "metadata.sqlite")
    loop = None
    try:
        snapshot = initialize_runtime_snapshot(storage_root=service.storage_root)
        assert not snapshot.activation_failures
        factory = sessionmaker(bind=engine, expire_on_commit=False)
        model = ModelBoundary(build_product_tool_registry(snapshot))
        with factory() as db:
            db.add(Project(id=PROJECT, name="Scene Animation")); db.flush()
            db.add(AgentSession(id="composition-session", project_id=PROJECT, title="Animation composition")); db.commit()
            refs = authorize_project_resources(db, PROJECT, tuple(RequestedResourceRef(kind=f"{owner}.library", id=PROJECT) for owner in digests), snapshot=snapshot)
            sessions = SessionRepository(db)
            admission = sessions.admit(session_id="composition-session", resource_refs=refs,
                content="Create a Scene fox, bind its fixed public object into an Animation X track, animate it, delete the live Scene object, then edit the animation without replacing the old revision.",
                idempotency_key="scene-animation", llm_credential_id="scripted", api_base=None, model_name="gpt-5.4", request_payload={})
            lease = sessions.claim(session_id="composition-session", owner="independent-review", ttl_seconds=300)
            assert lease is not None
            sessions.promote_next_input(lease=lease); db.commit()
        loop = build_product_run_loop(session_factory=factory, snapshot=snapshot)

        def adapter(settings):
            client = AsyncOpenAI(api_key="mock-transport-only", base_url="https://scene-animation-model.invalid/v1",
                http_client=httpx.AsyncClient(transport=httpx.MockTransport(model.respond)), max_retries=0)
            return OpenAIModelAdapter(client=client, model_name=settings.model_name, owns_client=True)

        loop.model_factory = adapter
        loop.execute(lease=lease, run_id=admission.run_id)
        assert not model.errors, model.errors
        peak = max(estimate_input_items_tokens(r["input"]) + estimate_tool_schema_tokens(r["tools"]) for r in model.requests)
        record_property("prompt_estimate_peak", peak)
        record_property("provider_requests", len(model.requests))
        record_property("signed_owners", len(digests))
        assert peak <= loop.definition.limits.max_prompt_tokens == 65536
        with factory() as db:
            assert db.get(AgentRun, admission.run_id).status == "completed"
            invocations = db.query(AgentToolInvocation).filter_by(run_id=admission.run_id).all()
            assert len(invocations) == len(model.outputs) == 10
            assert all(i.status == "succeeded" and i.package_digest == digests[i.owner_id] for i in invocations)
            artifacts = {a.id: a for a in ArtifactRepository(db).list_for_run(admission.run_id)}

        source = artifacts[model.source_artifact_id]
        def representation(artifact, kind, operation, active=snapshot):
            return active.get_artifact_representation(artifact.type, kind).provider.execute(artifact,
                ArtifactRepresentationRequest(operation=operation, parameters={}),
                ArtifactRepresentationContext(artifact_loader=artifacts.get))
        def export(identity, active=snapshot):
            return b"".join(representation(artifacts[identity], "dbfox.animation.document.v1", "export_json", active).chunks)
        fixed = export(model.fixed_artifact_id)
        changed = export(model.export_artifact_id)
        doc = json.loads(fixed)
        assert hashlib.sha256(fixed).hexdigest() == artifacts[model.fixed_artifact_id].payload["content_hash"]
        assert doc["targets"][0] == model.target
        assert doc["targets"][0]["position"] == [3,2,1]
        assert doc["targets"][0]["source"] == {"artifact_id": source.id, "scene_id": model.scene_id,
            "version": 2, "content_hash": source.payload["content_hash"], "object_id": "fox"}
        assert doc["tracks"][0]["target_id"] == model.target["id"]
        assert next(k for k in doc["keyframes"] if k["id"] == "end")["tick"] == 4000
        assert next(k for k in json.loads(changed)["keyframes"] if k["id"] == "end")["tick"] == 4001
        assert representation(artifacts[model.deleted_source_artifact_id], "dbfox.scene.document.v1", "objects_page").payload["objects"] == []
        binding = next(i for i in invocations if i.provider_call_id == model.bind_call_id)
        scopes = json.loads(binding.resource_refs_json)
        assert len(scopes) == 1 and scopes[0]["kind"] == "dbfox.animation.document" and scopes[0]["id"] == model.animation_id
        service.set_desired_enabled("dbfox.scene", False)
        disabled = initialize_runtime_snapshot(storage_root=service.storage_root)
        assert not disabled.activation_failures
        assert export(model.fixed_artifact_id, disabled) == fixed
        assert export(model.export_artifact_id, disabled) == changed
    finally:
        if loop is not None:
            loop.close()
        set_active_runtime_snapshot(previous)
        engine.dispose()
