"""Independent composition: real signed owners, public artifacts, real Agent loop.

Only the external model HTTP response is scripted. This does not claim live-model
quality or Phaser rendering; it verifies the actual durable asset transfer.
"""
from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric import ed25519
import httpx
from openai import AsyncOpenAI
from sqlalchemy.orm import sessionmaker

from dbfox_dlc_api import ArtifactRelationType, ArtifactRepresentationContext, ArtifactRepresentationRequest, RequestedResourceRef, ToolKey
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
PROJECT = "pixel-game-independent"


class ModelBoundary:
    def __init__(self, registry):
        self.registry = registry
        self.requests = []
        self.outputs = []
        self.errors = []
        self.searches = 0
        self.plan = self.steps()

    def steps(self):
        yield "dbfox.pixel", "pixel_create", {"library_id": PROJECT, "title": "Fox texture", "width": 48, "height": 40, "expected_version": 0}
        pixel = self.outputs[-1]["facts"]
        self.pixel_id = pixel["document_id"]
        yield "dbfox.pixel", "pixel_rect", {"document_id": self.pixel_id, "expected_version": pixel["revision"],
            "operation": {"kind": "rect", "frame_id": "frame_1", "layer_id": "layer_1", "palette_index": 1,
                "rect": {"x": 0, "y": 0, "width": 48, "height": 40}}}
        self.source_artifact_id = self.outputs[-1]["artifact_ids"][0]
        yield "dbfox.game", "game_create", {"title": "Pixel fox game", "expected_library_version": 1}
        game = self.outputs[-1]["facts"]["game"]
        self.game_id = game["id"]
        self.import_call_id = str(len(self.outputs))
        yield "dbfox.game", "asset_import", {"game_id": self.game_id, "expected_version": game["version"],
            "name": "Pixel fox", "source_artifact_id": self.source_artifact_id, "frame_id": "frame_1",
            "rect": {"x": 0, "y": 0, "width": 48, "height": 40}}
        self.import_artifact_id = self.outputs[-1]["artifact_ids"][0]
        self.asset_id = self.outputs[-1]["facts"]["created_refs"]["asset"]
        yield "dbfox.game", "game_inspect", {"game_id": self.game_id, "section": "summary"}
        facts = self.outputs[-1]["facts"]
        yield "dbfox.game", "entity_create", {"game_id": self.game_id, "expected_version": facts["game"]["version"],
            "operation": {"kind": "entity_create", "entities": [{"scene_id": {"id": facts["metadata"]["initial_scene_id"]},
                "name": "Fox from Pixel", "components": [{"kind": "transform", "x": 80, "y": 100, "width": 48, "height": 40},
                    {"kind": "visual", "shape": "asset", "asset_id": {"id": self.asset_id}}]}]}}
        self.game_version = self.outputs[-1]["facts"]["game"]["version"]
        # Editing the source must not silently replace a previously imported asset.
        yield "dbfox.pixel", "pixel_rect", {"document_id": self.pixel_id, "expected_version": 2,
            "operation": {"kind": "rect", "frame_id": "frame_1", "layer_id": "layer_1", "palette_index": 2,
                "rect": {"x": 31, "y": 31, "width": 2, "height": 2}}}
        self.new_pixel_artifact_id = self.outputs[-1]["artifact_ids"][0]
        yield "dbfox.game", "game_export", {"game_id": self.game_id, "expected_version": self.game_version}
        self.export_artifact_id = self.outputs[-1]["artifact_ids"][0]

    def respond(self, request):
        try:
            return self.response(request)
        except Exception as error:
            self.errors.append(repr(error))
            raise

    def response(self, request):
        assert request.url.host == "pixel-game-model.invalid"
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
            assert output["status"] == "succeeded", (self.last_step, output)
            self.outputs.append(output)
        step = next(self.plan, None)
        if step is None:
            items = [{"id": "msg_done", "type": "message", "role": "assistant", "status": "completed",
                "phase": "final_answer", "content": [{"type": "output_text", "text": "Imported a fixed Pixel texture into a Game entity and exported the game. Later Pixel edits preserved the imported snapshot.", "annotations": [], "logprobs": []}]}]
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


def test_real_pixel_frames_become_immutable_game_assets(tmp_path, record_property):
    previous = active_runtime_snapshot()
    service = DlcPackageService(tmp_path / "dlcs")
    digests = {}
    publisher = ed25519.Ed25519PrivateKey.generate()
    for owner in ("dbfox.pixel", "dbfox.game"):
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
            db.add(Project(id=PROJECT, name="Pixel Game")); db.flush()
            db.add(AgentSession(id="composition-session", project_id=PROJECT, title="Sprite composition")); db.commit()
            refs = authorize_project_resources(db, PROJECT, tuple(RequestedResourceRef(kind=f"{owner}.library", id=PROJECT) for owner in digests), snapshot=snapshot)
            sessions = SessionRepository(db)
            admission = sessions.admit(session_id="composition-session", resource_refs=refs,
                content="Draw a Pixel sprite, import its fixed frame into a Game entity and export. Then modify Pixel without replacing the imported texture.",
                idempotency_key="pixel-game", llm_credential_id="scripted", api_base=None, model_name="gpt-5.4", request_payload={})
            lease = sessions.claim(session_id="composition-session", owner="independent-review", ttl_seconds=300)
            assert lease is not None
            sessions.promote_next_input(lease=lease); db.commit()
        loop = build_product_run_loop(session_factory=factory, snapshot=snapshot)

        def adapter(settings):
            client = AsyncOpenAI(api_key="mock-transport-only", base_url="https://pixel-game-model.invalid/v1",
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
            assert len(invocations) == len(model.outputs) == 8
            assert all(i.status == "succeeded" and i.package_digest == digests[i.owner_id] for i in invocations)
            artifacts = {a.id: a for a in ArtifactRepository(db).list_for_run(admission.run_id)}

        source = artifacts[model.source_artifact_id]
        imported = artifacts[model.import_artifact_id]
        exported = artifacts[model.export_artifact_id]
        assert any(r.artifact_id == source.id and r.relation == ArtifactRelationType.DERIVED_FROM for r in imported.relations)
        assert {r.kind for r in imported.resource_refs} == {"dbfox.pixel.document", "dbfox.game.project"}
        assert all(r in imported.resource_refs for r in source.resource_refs)
        imported_invocation = next(i for i in invocations if i.provider_call_id == model.import_call_id)
        assert imported_invocation.owner_id == "dbfox.game"
        invocation_scopes = json.loads(imported_invocation.resource_refs_json)
        assert len(invocation_scopes) == 1
        assert invocation_scopes[0]["kind"] == "dbfox.game.project"
        assert invocation_scopes[0]["id"] == model.game_id

        def representation(artifact, kind, operation, parameters=None, active=snapshot):
            provider = active.get_artifact_representation(artifact.type, kind).provider
            return provider.execute(artifact, ArtifactRepresentationRequest(operation=operation, parameters=parameters or {}),
                ArtifactRepresentationContext(artifact_loader=artifacts.get))

        # Read four genuine bounded Pixel tiles and independently stitch expected RGBA.
        raw = bytearray(48 * 40 * 4)
        for y in (0, 32):
            for x in (0, 32):
                w, h = min(32, 48 - x), min(32, 40 - y)
                tile = representation(source, "dbfox.pixel.sprite.v1", "frame", {"frame_id": "frame_1", "rect": {"x": x, "y": y, "width": w, "height": h}})
                assert tile.source_version == "2"
                for row in range(h):
                    start = ((y + row) * 48 + x) * 4
                    raw[start:start + w * 4] = bytes(tile.payload["rgba"][row * w * 4:(row + 1) * w * 4])
        stream = representation(exported, "dbfox.game.document.v1", "export")
        bundle_bytes = b"".join(stream.chunks)
        bundle = json.loads(bundle_bytes)
        asset = bundle["document"]["assets"][0]
        assert asset["id"] == model.asset_id
        assert asset["content_hash"] == hashlib.sha256(raw).hexdigest()
        assert base64.b64decode(bundle["rgba_assets"][asset["content_hash"]]) == raw
        assert asset["source"]["artifact_id"] == source.id
        assert asset["source"]["source_version"] == "2"
        assert asset["source"]["source_fingerprint"] == source.payload["content_hash"]
        entity = bundle["document"]["entities"][0]
        assert next(c for c in entity["components"] if c["spec"]["kind"] == "visual")["spec"]["asset_id"] == asset["id"]
        current = representation(artifacts[model.new_pixel_artifact_id], "dbfox.pixel.sprite.v1", "frame",
            {"frame_id": "frame_1", "rect": {"x": 31, "y": 31, "width": 1, "height": 1}})
        assert current.source_version == "3"
        assert bytes(current.payload["rgba"]) != raw[(31 * 48 + 31) * 4:(31 * 48 + 31) * 4 + 4]
        service.set_desired_enabled("dbfox.pixel", False)
        disabled = initialize_runtime_snapshot(storage_root=service.storage_root)
        assert not disabled.activation_failures
        assert b"".join(representation(exported, "dbfox.game.document.v1", "export", active=disabled).chunks) == bundle_bytes
    finally:
        if loop is not None:
            loop.close()
        set_active_runtime_snapshot(previous)
        engine.dispose()
