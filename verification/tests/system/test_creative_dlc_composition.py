"""Director integration gate: three signed owners share the production Agent Run.

No owner-private imports or state reads; only model events are scripted. This is
ordinary orchestration and does not justify another Composition DLC.
"""
from __future__ import annotations

import hashlib
import json

import httpx
from openai import AsyncOpenAI
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric import ed25519
import pytest
from sqlalchemy.orm import sessionmaker

from dbfox_dlc_api import ArtifactRepresentationContext, ArtifactRepresentationRequest, RequestedResourceRef, ToolKey
from engine.agent.context_budget import estimate_input_items_tokens, estimate_tool_schema_tokens
from engine.agent.run import RunLimits
from engine.agent.providers.openai import OpenAIModelAdapter
from engine.agent.repositories.artifact import ArtifactRepository
from engine.agent.repositories.session import SessionRepository
from engine.dlc import DlcPackageService
from engine.dlc.package_builder import build_dlc_package_from_source
from engine.models import AgentObservationRecord, AgentRun, AgentSession, AgentToolInvocation, AgentTurn, Project
from engine.runtime_composition import (
    active_runtime_snapshot, authorize_project_resources, build_product_run_loop,
    build_product_tool_registry, initialize_runtime_snapshot, set_active_runtime_snapshot,
)
from verification.support.metadata import create_migrated_metadata_engine

ROOT = Path(__file__).resolve().parents[3]
OWNERS = ("dbfox.scene", "dbfox.voxel", "dbfox.pixel")


@pytest.fixture(params=[False, True], ids=["three-studios", "four-studios"])
def studios(tmp_path, request):
    service = DlcPackageService(tmp_path / "dlcs")
    key = ed25519.Ed25519PrivateKey.from_private_bytes(hashlib.sha256(b"Creative composition verification publisher").digest())
    digests = {}
    owners = OWNERS + (("dbfox.shader",) if request.param else ())
    for owner in owners:
        built = build_dlc_package_from_source(ROOT / "dlcs" / owner, private_key=key)
        archive = tmp_path / f"{owner}.dbfox-dlc"
        archive.write_bytes(built.archive_bytes)
        service.trust_publisher_from_file(archive, expected_package_digest=built.package_digest,
            expected_publisher_key_id=built.publisher_fingerprint)
        service.install_from_file(archive)
        service.set_desired_enabled(owner, True)
        digests[owner] = built.package_digest
    previous = active_runtime_snapshot()
    engine = create_migrated_metadata_engine(tmp_path / "metadata.sqlite")
    try:
        snapshot = initialize_runtime_snapshot(storage_root=service.storage_root)
        assert not snapshot.activation_failures
        yield service, snapshot, sessionmaker(bind=engine, expire_on_commit=False), digests
    finally:
        set_active_runtime_snapshot(previous)
        engine.dispose()


class CreativeModel:
    """IDs and versions come solely from provider-visible function outputs."""

    def __init__(self, registry, *, shader=False):
        self.registry = registry
        self.shader = shader
        self.state = {}
        self.requests = []
        self.outputs = {}
        self.plan = self.steps()
        self.provider_requests = []
        self.searches = 0
        self.transport_errors = []

    def steps(self):
        if self.shader:
            yield "dbfox.shader", "shader_create", {"title": "Fox world shader", "expected_generation": 0}, True
        yield "dbfox.scene", "scene_create", {"title": "Fox world scene"}, True
        yield "dbfox.voxel", "voxel_create", {"title": "Fox world blocks", "size": [16, 16, 16]}, True
        yield "dbfox.pixel", "pixel_create", {"library_id": "creative-project", "title": "Fox world sprite", "width": 16, "height": 16, "expected_version": 0}, True
        scene, voxel, pixel = (self.state[owner] for owner in OWNERS)
        yield "dbfox.scene", "object_create", {"scene_id": scene["id"], "expected_version": scene["version"],
            "operation": {"kind": "object_create", "objects": [{"id": "fox", "name": "Fox", "kind": "mesh"},
                {"id": "keep", "name": "Keep", "kind": "mesh", "position": [9, 0, 0]}]}}, True
        yield "dbfox.voxel", "voxel_fill", {"world_id": voxel["world_id"], "expected_version": voxel["version"],
            "operation": {"kind": "fill", "layer_id": "base", "bounds": {"min": [0, 0, 0], "max": [2, 2, 2]}, "palette_index": 1}}, True
        yield "dbfox.pixel", "pixel_rect", {"document_id": pixel["document_id"], "expected_version": pixel["revision"],
            "operation": {"kind": "rect", "frame_id": "frame_1", "layer_id": "layer_1", "palette_index": 1,
                "rect": {"x": 1, "y": 1, "width": 3, "height": 3}}}, True
        # Valid-looking private selectors from another owner must not acquire authority.
        yield "dbfox.scene", "scene_inspect", {"scene_id": voxel["world_id"]}, False
        yield "dbfox.voxel", "voxel_inspect", {"world_id": pixel["document_id"]}, False
        yield "dbfox.pixel", "pixel_inspect", {"document_id": scene["id"]}, False
        scene, voxel, pixel = (self.state[owner] for owner in OWNERS)
        yield "dbfox.scene", "object_transform", {"scene_id": scene["id"], "expected_version": scene["version"],
            "operation": {"kind": "object_transform", "transforms": [{"object_id": "fox", "position": [2, 3, 4]}]}}, True
        yield "dbfox.voxel", "voxel_fill", {"world_id": voxel["world_id"], "expected_version": voxel["version"],
            "operation": {"kind": "fill", "layer_id": "base", "bounds": {"min": [1, 1, 1], "max": [2, 2, 2]}, "palette_index": 2}}, True
        yield "dbfox.pixel", "pixel_line", {"document_id": pixel["document_id"], "expected_version": pixel["revision"],
            "operation": {"kind": "line", "frame_id": "frame_1", "layer_id": "layer_1", "palette_index": 2, "x0": 2, "y0": 2, "x1": 2, "y1": 2}}, True
        scene, voxel, pixel = (self.state[owner] for owner in OWNERS)
        yield "dbfox.scene", "scene_export", {"scene_id": scene["id"], "expected_version": scene["version"]}, True
        yield "dbfox.voxel", "voxel_export", {"world_id": voxel["world_id"], "version": voxel["version"]}, True
        yield "dbfox.pixel", "pixel_export", {"document_id": pixel["document_id"], "expected_version": pixel["revision"]}, True

        if self.shader:
            shader = self.state["dbfox.shader"]
            yield "dbfox.shader", "shader_modify", {"document_id": shader["id"], "expected_version": shader["version"],
                "operations": [{"kind": "rename_document", "title": "Fox world glow"}]}, True
            shader = self.state["dbfox.shader"]
            yield "dbfox.shader", "shader_export", {"document_id": shader["id"], "expected_version": shader["version"]}, True

    def respond(self, request: httpx.Request) -> httpx.Response:
        try:
            return self._respond(request)
        except Exception as exc:
            self.transport_errors.append(repr(exc))
            raise

    def _respond(self, request: httpx.Request) -> httpx.Response:
        """Script only the external HTTP boundary; use the production SDK/adapter."""
        assert request.url.host == "creative-provider.invalid"
        payload = json.loads(request.content)
        assert payload["model"] in {"gpt-5.4", "gpt-4o-mini"}
        assert payload["store"] is False and payload["parallel_tool_calls"] is False
        self.provider_requests.append(payload)
        messages, tools = payload["input"], payload["tools"]
        for item in messages:
            if item.get("type") != "function_call_output" or item["call_id"] in self.outputs:
                continue
            result = json.loads(item["output"])
            previous = self.requests[int(item["call_id"].split("-")[-1])]
            assert (result["status"] == "succeeded") == previous["success"], (previous, result)
            self.outputs[item["call_id"]] = result
            if previous["success"]:
                facts = result["facts"]
                owner = previous["owner"]
                self.state[owner] = (facts["scene"] if owner == "dbfox.scene" else
                    facts["document"] if owner == "dbfox.shader" else facts.get("summary", facts))
        step = next(self.plan, None)
        items = []
        if step is None:
            items.append({"id": "msg_creative", "type": "message", "role": "assistant",
                "status": "completed", "phase": "final_answer", "content": [{"type": "output_text",
                "text": "The scene, voxel world and sprite were incrementally edited and exported. Cross-owner private references were rejected.",
                "annotations": [], "logprobs": []}]})
        else:
            owner, name, arguments, success = step
            wire_name = self.registry.provider_name_for_key(ToolKey(owner_id=owner, local_name=name))
            by_name = {tool["name"]: tool for tool in tools if tool["type"] == "function"}
            assert wire_name in by_name
            definition = by_name[wire_name]
            loaded = {tool["name"] for item in messages if item.get("type") == "tool_search_output"
                for tool in item["tools"] if tool["type"] == "function"}
            if definition.get("defer_loading") and wire_name not in loaded:
                assert any(tool["type"] == "tool_search" for tool in tools)
                self.searches += 1
                items.extend([
                    {"id": f"ts_{self.searches}", "type": "tool_search_call", "execution": "server",
                        "call_id": None, "status": "completed", "arguments": {"paths": [wire_name]}},
                    {"id": f"tso_{self.searches}", "type": "tool_search_output", "execution": "server",
                        "call_id": None, "status": "completed", "tools": [definition]},
                ])
            call_id = f"creative-{len(self.requests)}"
            self.requests.append({"owner": owner, "name": name, "arguments": arguments, "success": success})
            items.append({"id": f"fc_{len(self.requests)}", "type": "function_call", "status": "completed",
                "call_id": call_id, "name": wire_name, "arguments": json.dumps(arguments)})
        events = []
        for index, item in enumerate(items):
            events.extend([
                {"type": "response.output_item.added", "output_index": index, "item": {**item, "status": "in_progress"}},
                {"type": "response.output_item.done", "output_index": index, "item": item},
            ])
        events.append({"type": "response.completed", "response": {"id": f"resp_{len(self.provider_requests)}",
            "object": "response", "created_at": 0, "model": payload["model"], "status": "completed",
            "output": items, "parallel_tool_calls": False, "tool_choice": "auto", "tools": tools}})
        body = "".join(f"event: {event['type']}\ndata: {json.dumps({**event, 'sequence_number': index})}\n\n"
            for index, event in enumerate(events))
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=body)


@pytest.mark.parametrize("model_name,max_prompt_tokens", [("gpt-5.4", None), ("gpt-4o-mini", None), ("gpt-4o-mini", 32_768)])
def test_signed_studios_share_one_run_and_keep_private_authority(studios, model_name, max_prompt_tokens, record_property):
    service, snapshot, factory, digests = studios
    registry = build_product_tool_registry(snapshot)
    has_shader = "dbfox.shader" in digests
    owners = tuple(digests)
    wire_names = [registry.provider_name_for_key(ToolKey(owner_id=entry.owner_id, local_name=entry.tool.name))
        for entry in snapshot.tools]
    assert len(wire_names) == len(set(wire_names))
    assert sum(entry.owner_id in owners for entry in snapshot.tools) == 52 + (13 if has_shader else 0)
    with factory() as db:
        db.add(Project(id="creative-project", name="Fox world")); db.flush()
        db.add(AgentSession(id="creative-session", project_id="creative-project", title="Three creative media")); db.commit()
        refs = authorize_project_resources(db, "creative-project", tuple(RequestedResourceRef(kind=f"{owner}.studio" if owner == "dbfox.shader" else f"{owner}.library", id="creative-project") for owner in owners), snapshot=snapshot)
        sessions = SessionRepository(db)
        admission = sessions.admit(session_id="creative-session", resource_refs=refs, content="Create a fox scene, voxel world and sprite; locally revise each and export all three.",
            idempotency_key="creative-three", llm_credential_id="scripted", api_base=None, model_name=model_name, request_payload={})
        lease = sessions.claim(session_id="creative-session", owner="creative-integration", ttl_seconds=600)
        assert lease is not None
        sessions.promote_next_input(lease=lease); db.commit()
    model = CreativeModel(registry, shader=has_shader)
    loop = build_product_run_loop(session_factory=factory, snapshot=snapshot)
    if max_prompt_tokens is not None:
        loop.definition = loop.definition.model_copy(update={"limits": RunLimits(max_prompt_tokens=max_prompt_tokens)})
    def model_factory(settings):
        client = AsyncOpenAI(api_key="test-only-mock-transport", base_url="https://creative-provider.invalid/v1",
            http_client=httpx.AsyncClient(transport=httpx.MockTransport(model.respond)), max_retries=0)
        return OpenAIModelAdapter(client=client, model_name=settings.model_name, owns_client=True)
    loop.model_factory = model_factory
    try:
        if max_prompt_tokens == 32_768:
            loop.execute(lease=lease, run_id=admission.run_id)
            with factory() as db:
                run = db.get(AgentRun, admission.run_id)
                assert run.status == "failed" and run.error_code == "AGENT_CONTEXT_BUDGET_EXCEEDED"
            assert model.searches == 0
            # A smaller explicit budget can admit the first calls, then stop
            # before dropping the latest complete native tool turn.
            assert 0 < len(model.requests) < 15 + (3 if has_shader else 0)
            assert all(not any(tool["type"] == "tool_search" for tool in request["tools"])
                for request in model.provider_requests)
            return
        loop.execute(lease=lease, run_id=admission.run_id)
    finally:
        loop.close()
        assert not model.transport_errors, model.transport_errors
    prompt_peak = max(estimate_input_items_tokens(request["input"]) + estimate_tool_schema_tokens(request["tools"])
        for request in model.provider_requests)
    record_property("prompt_estimate_peak", prompt_peak)
    record_property("hosted_searches", model.searches)
    record_property("provider_requests", len(model.provider_requests))
    record_property("signed_owners", len(owners))
    assert prompt_peak <= loop.definition.limits.max_prompt_tokens == 65536
    if model_name == "gpt-5.4":
        assert model.searches > 0
        assert any(item.get("type") == "tool_search_output" for request in model.provider_requests for item in request["input"])
    else:
        assert model.searches == 0
        assert all(tool["type"] == "function" for request in model.provider_requests for tool in request["tools"])
    with factory() as db:
        assert db.get(AgentRun, admission.run_id).status == "completed"
        invocations = db.query(AgentToolInvocation).filter_by(run_id=admission.run_id).all()
        assert len(invocations) == len(model.outputs) == 15 + (3 if has_shader else 0)
        assert sum(item.status == "succeeded" for item in invocations) == 12 + (3 if has_shader else 0)
        assert all(item.package_digest == digests[item.owner_id] for item in invocations)
        for item in invocations:
            if item.status == "succeeded":
                scopes = json.loads(item.resource_refs_json)
                assert len(scopes) == 1 and scopes[0]["kind"].startswith(item.owner_id + ".")
        observations = db.query(AgentObservationRecord).filter_by(run_id=admission.run_id).all()
        assert all(len(item.model_output_json.encode()) <= 25600 for item in observations)
        turns = db.query(AgentTurn).filter_by(run_id=admission.run_id).all()
        assert any("tool_search_output" in str(turn.response_items_json) for turn in turns) == (model_name == "gpt-5.4")
        for turn in turns:
            fragments = json.loads(turn.context_snapshot_json).get("context_fragments", [])
            assert sum(len(json.dumps(item, ensure_ascii=False)) for item in fragments if any(str(item.get("source_id", "")).startswith(owner) for owner in OWNERS)) < 12000
        repository = ArtifactRepository(db)
        artifacts = repository.list_for_run(admission.run_id)
        assert len(artifacts) == 12 + (3 if has_shader else 0)
        if has_shader:
            shader_artifacts = [item for item in artifacts if item.type.startswith("dbfox.shader.")]
            assert {item.type for item in shader_artifacts} == {"dbfox.shader.document-revision"}
            assert shader_artifacts[-1].payload["title"] == "Fox world glow"
            assert shader_artifacts[-1].payload["version"] == 2
            assert shader_artifacts[0].payload["version"] == 1
            assert shader_artifacts[0].payload["title"] == "Fox world shader"
        assert all(repository.available_artifact(current_run_id=admission.run_id, artifact_id=item.id, session_id="creative-session") for item in artifacts)
        final = {owner: next(item for item in reversed(artifacts) if item.type.startswith(owner + ".")) for owner in OWNERS}

    # Registered immutable representations supply independent content assertions.
    def read(owner, representation, operation, parameters=None):
        artifact = final[owner]
        provider = snapshot.get_artifact_representation(artifact.type, representation).provider
        result = provider.execute(artifact, ArtifactRepresentationRequest(operation=operation, parameters=parameters or {}),
            ArtifactRepresentationContext(artifact_loader=lambda identity: None))
        assert result.consistency == "durable_snapshot" and result.source_version == "3"
        assert result.source_fingerprint == artifact.payload["content_hash"]
        return result.payload

    scene = read("dbfox.scene", "dbfox.scene.document.v1", "objects_page")
    assert {item["id"]: item["position"] for item in scene["objects"]} == {"fox": [2, 3, 4], "keep": [9, 0, 0]}
    voxel = read("dbfox.voxel", "dbfox.voxel.world.v1", "chunks")
    values = voxel["chunks"][0]["values"]
    assert values[1 + 16 + 256] == 2 and sum(value != 0 for value in values) == 8 and values[0] == 1
    pixels = read("dbfox.pixel", "dbfox.pixel.sprite.v1", "frame", {"frame_id": "frame_1", "rect": {"x": 0, "y": 0, "width": 4, "height": 4}})["rgba"]
    assert sum(pixels[offset + 3] != 0 for offset in range(0, len(pixels), 4)) == 9
    assert pixels[(2 * 4 + 2) * 4:(2 * 4 + 2) * 4 + 4] != pixels[(1 * 4 + 1) * 4:(1 * 4 + 1) * 4 + 4]

    # Removing one owner must remove only its contributions, and preserve the others.
    service.set_desired_enabled("dbfox.voxel", False)
    disabled = initialize_runtime_snapshot(storage_root=service.storage_root)
    assert not disabled.activation_failures
    assert {entry.owner_id for entry in disabled.tools if entry.owner_id in owners} == set(owners) - {"dbfox.voxel"}
    assert disabled.get_artifact_representation(final["dbfox.voxel"].type, "dbfox.voxel.world.v1") is None
    for owner, representation, operation in (("dbfox.scene", "dbfox.scene.document.v1", "summary"), ("dbfox.pixel", "dbfox.pixel.sprite.v1", "metadata")):
        item = final[owner]
        result = disabled.get_artifact_representation(item.type, representation).provider.execute(item,
            ArtifactRepresentationRequest(operation=operation), ArtifactRepresentationContext(artifact_loader=lambda identity: None))
        assert result.source_version == "3"
    service.set_desired_enabled("dbfox.voxel", True)
    restored = initialize_runtime_snapshot(storage_root=service.storage_root)
    assert not restored.activation_failures and {entry.owner_id for entry in restored.tools if entry.owner_id in owners} == set(owners)
    artifact = final["dbfox.voxel"]
    result = restored.get_artifact_representation(artifact.type, "dbfox.voxel.world.v1").provider.execute(artifact,
        ArtifactRepresentationRequest(operation="manifest"), ArtifactRepresentationContext(artifact_loader=lambda identity: None))
    assert result.source_version == "3" and result.payload["nonzero_count"] == 8
