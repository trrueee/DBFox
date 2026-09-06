"""Fresh Shader studio-generation and Artifact attacks through the real factory.

Only the external native function-calling Provider is deterministic. No private
document facts, alternate RunLoop/resolver, or enlarged prompt budget is injected.
"""
from __future__ import annotations

import json
from uuid import uuid4

import pytest

from dbfox_dlc_api import ArtifactRepresentationContext, ArtifactRepresentationError, ArtifactRepresentationRequest, RequestedResourceRef, ToolKey
from engine.agent.context import ContextAssembler
from engine.agent.references import ConversationInputReference
from engine.agent.repositories.artifact import ArtifactRepository
from engine.agent.repositories.session import SessionRepository
from engine.api.conversation_commands import _reference_resource_identities
from engine.models import AgentArtifactRecord, AgentRun, AgentSession, AgentToolInvocation, Project
from engine.runtime_composition import authorize_project_resources, build_product_run_loop
from verification.bench.capabilities.dbfox_shader.runtime import ShaderRuntime
from verification.testkit.scripted_provider import answer_events, tool_call_events


def admit(runtime, project, session, references=None):
    with runtime.factory() as db:
        refs = authorize_project_resources(db, project,
            (RequestedResourceRef(kind="dbfox.shader.studio", id=project),) if references is None
            else _reference_resource_identities(references), snapshot=runtime.snapshot)
        sessions = SessionRepository(db)
        value = sessions.admit(session_id=session, resource_refs=refs, references=references or (),
            content="Use the explicitly attached Shader work only.", idempotency_key=str(uuid4()),
            llm_credential_id="shader-adversarial-model", api_base=None, model_name="scripted", request_payload={})
        lease = sessions.claim(session_id=session, owner="shader-adversarial", ttl_seconds=600)
        assert lease is not None
        sessions.promote_next_input(lease=lease)
        db.commit()
        return value, lease


class Producer:
    def __init__(self, runtime):
        self.runtime = runtime
        self.sent = 0
        self.observed = {}

    def stream(self, *, messages, tools, **kwargs):
        for item in messages:
            if item.get("type") == "function_call_output":
                self.observed[item["call_id"]] = json.loads(item["output"])
        if self.sent == 0:
            name, payload = "shader_create", {"title": "Studio producer source", "expected_generation": 0}
        elif self.sent == 1:
            facts = self.observed["producer-0"]["facts"]
            name, payload = "shader_modify", {"document_id": facts["document"]["id"],
                "expected_version": facts["document"]["version"],
                "operations": [{"kind": "rename_document", "title": "Saved producer revision"}]}
        elif self.sent == 2:
            facts = self.observed["producer-1"]["facts"]
            name, payload = "shader_export", {"document_id": facts["document"]["id"], "expected_version": facts["document"]["version"]}
        else:
            yield from answer_events("Saved and exported the exact revision. No GPU execution was requested.")
            return
        wire = self.runtime.registry.provider_name_for_key(ToolKey(owner_id="dbfox.shader", local_name=name))
        assert wire in {item["name"] for item in tools}
        call = f"producer-{self.sent}"
        self.sent += 1
        yield from tool_call_events(call_id=call, tool_name=wire, arguments=payload)


@pytest.fixture
def produced(tmp_path):
    with ShaderRuntime(tmp_path) as runtime:
        project, session = str(uuid4()), str(uuid4())
        with runtime.factory() as db:
            db.add(Project(id=project, name="Shader separate adversarial"))
            db.flush()
            db.add(AgentSession(id=session, project_id=project, title="Producer"))
            db.commit()
        admission, lease = admit(runtime, project, session)
        model = Producer(runtime)
        loop = build_product_run_loop(session_factory=runtime.factory, snapshot=runtime.snapshot)
        loop.model_factory = lambda _: model
        try:
            loop.execute(lease=lease, run_id=admission.run_id)
        finally:
            loop.close()
        with runtime.factory() as db:
            assert db.get(AgentRun, admission.run_id).status == "completed"
            calls = db.query(AgentToolInvocation).filter_by(run_id=admission.run_id).all()
            assert len(calls) == 3 and all(row.status == "succeeded" and row.attempt_count == 1 for row in calls)
            assert all(row.owner_id == "dbfox.shader" and row.package_digest == runtime.package.package_digest for row in calls)
            artifacts = ArtifactRepository(db).list_for_run(admission.run_id)
            assert len(artifacts) == 3
        yield runtime, project, session, admission.run_id, artifacts, model.observed["producer-2"]["facts"]["document"]


def reference(project, summary):
    # Exact shape emitted by studio.js onAsk. Object identity is separate from authority.
    return ConversationInputReference(label=summary["title"], authority={"kind": "dbfox.shader.studio", "id": project},
        object={"kind": "dbfox.shader.document", "id": summary["id"], "version": summary["version"]},
        locator=f"document/{summary['id']}")


def test_unrelated_document_generation_revokes_cross_run_artifact_but_not_historical_bytes(produced):
    runtime, project, session, run_id, artifacts, summary = produced
    assert [item.resource_refs[0].version for item in artifacts] == [0, 1, 2]
    assert [item.payload["version"] for item in artifacts] == [1, 2, 2]
    with runtime.factory() as db:
        repo = ArtifactRepository(db)
        assert all(repo.available_artifact(session_id=session, current_run_id=run_id, artifact_id=item.id) for item in artifacts)
    runtime.operation(project, "documents.create", {"title": "Unrelated studio member", "expected_generation": 2, "request_id": str(uuid4())})
    current = runtime.operation(project, "documents.head", {"document_id": summary["id"]})
    assert current["version"] == 2 and current["content_hash"] == summary["content_hash"]
    admission, _ = admit(runtime, project, session, (reference(project, summary), ConversationInputReference(label="Export", artifact_id=artifacts[-1].id)))
    with runtime.factory() as db:
        assert ArtifactRepository(db).available_artifact(session_id=session, current_run_id=admission.run_id, artifact_id=artifacts[-1].id) is None
        assert artifacts[-1].id not in [item.id for item in ContextAssembler(db).build(admission.run_id).selected_artifacts]
    provider = runtime.snapshot.get_artifact_representation("dbfox.shader.document-revision", "dbfox.shader.document.v1").provider
    page = provider.execute(artifacts[-1], ArtifactRepresentationRequest(operation="page", parameters={"section": "summary"}),
        ArtifactRepresentationContext(artifact_loader=lambda _: None))
    assert page.source_fingerprint == summary["content_hash"] and page.payload["document"]["version"] == 2


@pytest.mark.parametrize("shape", ["artifact-only", "private-object", "document-and-artifact"])
def test_onask_shape_cannot_upgrade_private_selectors_to_studio_authority(produced, shape):
    runtime, project, session, _, artifacts, summary = produced
    selected = ConversationInputReference(label="Saved export", artifact_id=artifacts[-1].id)
    if shape == "private-object":
        references = (ConversationInputReference(label="Private document", object={"kind": "dbfox.shader.document", "id": summary["id"]}), selected)
    elif shape == "artifact-only":
        references = (selected,)
    else:
        references = (reference(project, summary), selected)
    admission, _ = admit(runtime, project, session, references)
    with runtime.factory() as db:
        found = ArtifactRepository(db).available_artifact(session_id=session, current_run_id=admission.run_id, artifact_id=artifacts[-1].id)
        assert (found is not None) == (shape == "document-and-artifact")
        context = ContextAssembler(db).build(admission.run_id)
        assert (artifacts[-1].id in [value.id for value in context.selected_artifacts]) == (shape == "document-and-artifact")


@pytest.mark.parametrize("fault", ["wrong-producer", "wrong-project", "internal", "nonterminal"])
def test_structured_artifact_reads_enforce_exact_producer_and_scope(produced, fault):
    runtime, project, session, run_id, artifacts, summary = produced
    selected = artifacts[-1]
    admission, _ = admit(runtime, project, session, (reference(project, summary), ConversationInputReference(label="Saved export", artifact_id=selected.id)))
    seen = []
    class Capture:
        def build(self, input):
            seen.extend(item.artifact_id for item in input.recent_artifacts)
            return ()
    with runtime.factory() as db:
        row = db.get(AgentArtifactRecord, selected.id)
        producer_run = db.get(AgentRun, run_id)
        producer_run.result_json = json.dumps({"completion_disposition": "bounded_partial"})
        if fault == "wrong-producer":
            row.provenance_json = json.dumps({**selected.provenance, "tool_invocation_id": artifacts[0].provenance["tool_invocation_id"]})
        elif fault == "wrong-project":
            row.resource_refs_json = json.dumps([{**selected.resource_refs[0].model_dump(mode="json"), "id": str(uuid4())}])
        elif fault == "internal":
            row.presentation_json = json.dumps({"visibility": "internal"})
        else:
            producer_run.status = "running"
        db.commit()
        assert ArtifactRepository(db).available_artifact(session_id=session, current_run_id=admission.run_id, artifact_id=selected.id) is None
        context = ContextAssembler(db, contributors=(lambda _: Capture(),)).build(admission.run_id)
        assert selected.id not in seen and selected.id not in [item.id for item in context.selected_artifacts]
        if context.previous_run_outcome:
            assert selected.id not in [item.id for item in context.previous_run_outcome.artifacts]
            assert all(selected.id not in item.artifact_ids for item in context.previous_run_outcome.tool_outcomes)


def test_historical_representation_rejects_identity_or_external_resource_overrides(produced):
    runtime, _, _, _, artifacts, _ = produced
    provider = runtime.snapshot.get_artifact_representation("dbfox.shader.document-revision", "dbfox.shader.document.v1").provider
    for forbidden in ({"project_id": str(uuid4())}, {"document_id": str(uuid4())}, {"version": 1},
            {"url": "https://example.invalid/private.png"}, {"path": "../../private"}):
        with pytest.raises(ArtifactRepresentationError):
            provider.execute(artifacts[-1], ArtifactRepresentationRequest(operation="page", parameters=forbidden),
                ArtifactRepresentationContext(artifact_loader=lambda _: None))
