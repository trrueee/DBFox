"""Story observations -> Comic creation in one real authorized production Run.

Only the external OpenAI HTTP boundary is scripted. Story has no Representation
provider: do not invent a source Artifact or a DERIVED_FROM relationship.
"""
import hashlib
import json

import httpx
import pytest
from openai import AsyncOpenAI

from dbfox_dlc_api import ArtifactRepresentationContext, ArtifactRepresentationRequest, RequestedResourceRef, ToolKey
from engine.agent.context_budget import estimate_input_items_tokens, estimate_tool_schema_tokens
from engine.agent.providers.openai import OpenAIModelAdapter
from engine.agent.repositories.artifact import ArtifactRepository
from engine.agent.repositories.session import SessionRepository
from engine.models import AgentRun, AgentSession, AgentToolInvocation
from engine.errors import ToolInputError
from engine.runtime_composition import authorize_project_resources, build_product_run_loop, discover_project_resources
from engine.tools.runtime.resource_authority import bind_tool_invocation_resources
from verification.testkit.comic_independent import InstalledComic

STORY_TEXT = "暮色落在灯塔上。旅行者把最后一盏灯举向海面。\n我们回家了。"


class ModelBoundary:
    def __init__(self, registry):
        self.registry = registry
        self.requests, self.outputs, self.errors = [], [], []
        self.plan = self.steps()

    def steps(self):
        yield "dbfox.story", "story_chapters_list", {}
        chapter_id = self.outputs[-1]["facts"]["chapters"][0]["id"]
        yield "dbfox.story", "story_chapter_read", {"chapter_id": chapter_id}
        self.chapter = self.outputs[-1]["facts"]["chapter"]
        yield "dbfox.comic", "comic_create", {"title": self.chapter["title"] + " · 分镜"}
        self.comic_id = self.outputs[-1]["facts"]["comic"]["id"]
        operations = [
            {"kind": "page_create", "page": {"id": "page-home", "title": self.chapter["title"]}},
            {"kind": "panel_create", "page_id": "page-home", "panels": [{"id": "arrival", "title": "灯塔"}, {"id": "home", "title": "归途"}]},
            {"kind": "panel_layout", "page_id": "page-home", "placements": [
                {"panel_id": "arrival", "rect": {"x": .05, "y": .05, "width": .9, "height": .4}},
                {"panel_id": "home", "rect": {"x": .05, "y": .5, "width": .9, "height": .4}}]},
            {"kind": "shot_set", "panel_id": "arrival", "shot": {"framing": "wide", "description": self.chapter["content"].split("\n")[0]}},
            {"kind": "character_place", "panel_id": "home", "character": {"id": "traveler", "label": "旅行者", "pose": "reaching"}},
            {"kind": "bubble_create", "panel_id": "home", "bubble": {"id": "home-speech", "text": self.chapter["content"].split("\n")[1], "speaker_id": "traveler"}},
            {"kind": "caption_create", "panel_id": "arrival", "caption": {"id": "dusk", "text": self.chapter["content"].split("。")[0]}},
            {"kind": "panel_reorder", "page_id": "page-home", "panel_ids": ["home", "arrival"]},
        ]
        for operation in operations:
            yield "dbfox.comic", operation["kind"], {"comic_id": self.comic_id,
                "expected_version": self.outputs[-1]["facts"]["comic"]["version"], "operation": operation}
        yield "dbfox.comic", "comic_export", {"comic_id": self.comic_id, "expected_version": self.outputs[-1]["facts"]["comic"]["version"]}
        self.export_id = self.outputs[-1]["artifact_ids"][0]

    def respond(self, request):
        try:
            return self.response(request)
        except Exception as error:
            self.errors.append(repr(error))
            raise

    def response(self, request):
        assert request.url.host == "story-comic-model.invalid"
        payload = json.loads(request.content)
        assert payload["model"] == "gpt-5.4" and payload["store"] is False
        self.requests.append(payload)
        seen = {str(n) for n in range(len(self.outputs))}
        for item in payload["input"]:
            if item.get("type") == "function_call_output" and item["call_id"] not in seen:
                assert item["call_id"] == str(len(self.outputs))
                output = json.loads(item["output"])
                assert output["status"] == "succeeded", output
                self.outputs.append(output)
        step = next(self.plan, None)
        n = len(self.outputs)
        if step is None:
            items = [{"id": "done", "type": "message", "role": "assistant", "status": "completed",
                "phase": "final_answer", "content": [{"type": "output_text", "text": "已依据读取的章节创作固定版本分镜并导出；未修改Story事实。", "annotations": [], "logprobs": []}]}]
        else:
            owner, name, arguments = step
            wire = self.registry.provider_name_for_key(ToolKey(owner, name))
            schema = next(t for t in payload["tools"] if t.get("name") == wire)
            assert schema["defer_loading"] and any(t["type"] == "tool_search" for t in payload["tools"])
            items = [
                {"id": f"search{n}", "type": "tool_search_call", "execution": "server", "call_id": None,
                    "status": "completed", "arguments": {"paths": [wire]}},
                {"id": f"loaded{n}", "type": "tool_search_output", "execution": "server", "call_id": None,
                    "status": "completed", "tools": [schema]},
                {"id": f"call{n}", "type": "function_call", "status": "completed", "call_id": str(n),
                    "name": wire, "arguments": json.dumps(arguments)},
            ]
        events = []
        for index, item in enumerate(items):
            events.extend([{"type": "response.output_item.added", "output_index": index, "item": {**item, "status": "in_progress"}},
                {"type": "response.output_item.done", "output_index": index, "item": item}])
        events.append({"type": "response.completed", "response": {"id": f"response{n}", "object": "response", "created_at": 0,
            "model": payload["model"], "status": "completed", "output": items, "parallel_tool_calls": False,
            "tool_choice": "auto", "tools": payload["tools"]}})
        sse = "".join(f"event: {e['type']}\ndata: {json.dumps({**e, 'sequence_number': i})}\n\n" for i, e in enumerate(events))
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=sse)


def test_story_public_observation_becomes_immutable_comic(tmp_path, record_property):
    runtime = InstalledComic(tmp_path, owners=("dbfox.story", "dbfox.comic"))
    loop = None
    try:
        world = runtime.op("worlds.ensure", {"title": "灯塔世界"}, owner="dbfox.story")
        source = runtime.op("chapters.create", {"title": "灯塔归途", "content": STORY_TEXT}, owner="dbfox.story")
        model = ModelBoundary(runtime.registry)
        with runtime.factory() as db:
            db.add(AgentSession(id="story-comic-run", project_id=runtime.project, title="Story to Comic")); db.commit()
            refs = authorize_project_resources(db, runtime.project, (
                RequestedResourceRef(kind="dbfox.story.world", id=world.id),
                RequestedResourceRef(kind="dbfox.comic.library", id=runtime.project)), snapshot=runtime.snapshot)
            sessions = SessionRepository(db)
            admission = sessions.admit(session_id="story-comic-run", resource_refs=refs,
                content="阅读灯塔归途章节，用它制作一页两面板的视觉分镜。保留原对白、建立角色及对白关联、调整镜头和阅读顺序，导出固定版本；不修改Story。",
                idempotency_key="story-comic", llm_credential_id="fixture", api_base=None, model_name="gpt-5.4", request_payload={})
            lease = sessions.claim(session_id="story-comic-run", owner="independent-comic", ttl_seconds=300)
            assert lease is not None
            sessions.promote_next_input(lease=lease); db.commit()
        loop = build_product_run_loop(session_factory=runtime.factory, snapshot=runtime.snapshot)
        def adapter(settings):
            client = AsyncOpenAI(api_key="mock-http-only", base_url="https://story-comic-model.invalid/v1",
                http_client=httpx.AsyncClient(transport=httpx.MockTransport(model.respond)), max_retries=0)
            return OpenAIModelAdapter(client=client, model_name=settings.model_name, owns_client=True)
        loop.model_factory = adapter
        loop.execute(lease=lease, run_id=admission.run_id)
        assert not model.errors, model.errors
        assert len(model.outputs) == 12 and len(model.requests) == 13
        assert model.chapter["content"] == STORY_TEXT
        assert model.chapter["id"] == source.id
        assert model.chapter["content_sha256"] == source.content_sha256 == hashlib.sha256(STORY_TEXT.encode()).hexdigest()
        peak = max(estimate_input_items_tokens(r["input"]) + estimate_tool_schema_tokens(r["tools"]) for r in model.requests)
        record_property("prompt_estimate_peak", peak)
        record_property("package_digests", json.dumps(runtime.digests))
        assert peak <= loop.definition.limits.max_prompt_tokens == 32768
        with runtime.factory() as db:
            assert db.get(AgentRun, admission.run_id).status == "completed"
            invocations = db.query(AgentToolInvocation).filter_by(run_id=admission.run_id).all()
            assert len(invocations) == 12
            assert all(i.status == "succeeded" and i.package_digest == runtime.digests[i.owner_id] for i in invocations)
            story_calls = [i for i in invocations if i.owner_id == "dbfox.story"]
            assert len(story_calls) == 2
            for invocation in story_calls:
                scopes = json.loads(invocation.resource_refs_json)
                assert len(scopes) == 1 and scopes[0]["kind"] == "dbfox.story.world" and scopes[0]["id"] == world.id
            artifacts = {a.id: a for a in ArtifactRepository(db).list_for_run(admission.run_id)}
        exported = artifacts[model.export_id]
        assert len(artifacts) == 10
        for artifact in artifacts.values():
            producer = next(i for i in invocations if i.id == artifact.provenance["tool_invocation_id"])
            scopes = json.loads(producer.resource_refs_json)
            assert len(scopes) == 1 and scopes[0]["kind"].startswith("dbfox.comic.")
            assert [r.model_dump(mode="json") for r in artifact.resource_refs] == scopes
            assert not artifact.relations  # No fabricated Story Artifact lineage.
        def export(operation="export_json"):
            provider = runtime.snapshot.get_artifact_representation(exported.type, "dbfox.comic.document.v1").provider
            stream = provider.execute(exported, ArtifactRepresentationRequest(operation=operation), ArtifactRepresentationContext(artifact_loader=artifacts.get))
            return b"".join(stream.chunks)
        frozen = export()
        document = json.loads(frozen)
        home, arrival = document["pages"][0]["panels"]
        assert home["id"] == "home" and arrival["id"] == "arrival"
        assert home["elements"][0]["label"] == "旅行者"
        assert home["elements"][1]["speaker_id"] == "traveler" and home["elements"][1]["text"] == "我们回家了。"
        assert arrival["shot"]["description"] == STORY_TEXT.split("\n")[0]
        assert arrival["elements"][0]["text"] == "暮色落在灯塔上"
        html = export("export_html")
        assert "我们回家了。".encode() in html
        # A later, authorized Story edit is a separate source fact, not Comic authority.
        newer = runtime.op("chapters.update", {"chapter_id": source.id, "title": source.title,
            "content": "清晨，旅行者去了另一座岛。", "expected_sha256": source.content_sha256}, owner="dbfox.story")
        assert newer.content_sha256 != source.content_sha256
        assert export() == frozen
        runtime.service.set_desired_enabled("dbfox.story", False)
        runtime.reload()
        assert not any(t.owner_id == "dbfox.story" for t in runtime.snapshot.tools)
        assert export() == frozen and export("export_html") == html
    finally:
        if loop is not None:
            loop.close()
        runtime.close()


def test_story_binding_rejects_foreign_world_and_proposal_uses_canonical_scope(tmp_path):
    runtime = InstalledComic(tmp_path, owners=("dbfox.story", "dbfox.comic"))
    try:
        world = runtime.op("worlds.ensure", {"title": "Authorized"}, owner="dbfox.story")
        other = runtime.op("worlds.ensure", {"title": "Foreign"}, owner="dbfox.story", project="foreign-project")
        with runtime.factory() as db:
            discovered = discover_project_resources(db, runtime.project, snapshot=runtime.snapshot)
        listing = runtime.registry.require(runtime.registry.provider_name_for_key(ToolKey("dbfox.story", "story_chapters_list")))
        with pytest.raises(ToolInputError, match="unavailable"):
            bind_tool_invocation_resources(listing, {"world_id": other.id}, discovered=discovered)
        with pytest.raises(ToolInputError, match="no available"):
            bind_tool_invocation_resources(listing, {}, discovered=())
        assert runtime.invoke("story_chapters_list", {}, (), owner="dbfox.story").status == "failed"
        refs = bind_tool_invocation_resources(listing, {}, discovered=discovered)
        assert len(refs) == 1 and refs[0].kind == "dbfox.story.world" and refs[0].id == world.id
        assert runtime.invoke("story_chapters_list", {"world_id": other.id}, refs, owner="dbfox.story").status == "failed"
        for name in ("Traveler", "Keeper"):
            runtime.op("entities.create", {"kind": "character", "name": name}, owner="dbfox.story")
        proposal = runtime.registry.require(runtime.registry.provider_name_for_key(ToolKey("dbfox.story", "story_propose_relations")))
        payload = {"relations": [{"from_name": "Traveler", "to_name": "Keeper", "kind": "friend", "reason": "Chapter evidence"}]}
        validated = proposal.input_model.model_validate(payload).model_dump(mode="json")
        assert "world_id" not in validated
        proposal_refs = bind_tool_invocation_resources(proposal, validated, discovered=discovered)
        assert proposal_refs == refs
        outcome = runtime.invoke("story_propose_relations", validated, proposal_refs, owner="dbfox.story")
        assert outcome.status == "success", outcome.error
        assert outcome.output["created_count"] == 1
    finally:
        runtime.close()
