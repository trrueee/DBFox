"""Independent regression for the actual Sidecar RunLoop composition boundary."""
from __future__ import annotations

import json
from uuid import uuid4

from dbfox_dlc_api import RequestedResourceRef, ToolKey
from engine.agent.repositories.session import SessionRepository
from engine.models import AgentRun, AgentSession, AgentToolInvocation, Project
from engine.runtime_composition import authorize_project_resources, build_product_run_loop
from verification.bench.capabilities.dbfox_shader.runtime import ShaderRuntime
from verification.testkit.scripted_provider import answer_events, tool_call_events


def test_sidecar_factory_executes_signed_owner_scope_and_returns_native_observation(tmp_path):
    """The real factory must supply everything; the test replaces only its model."""
    with ShaderRuntime(tmp_path) as runtime:
        project_id, session_id = str(uuid4()), str(uuid4())
        with runtime.factory() as db:
            db.add(Project(id=project_id, name="Independent production factory"))
            db.flush()
            db.add(AgentSession(id=session_id, project_id=project_id, title="Create after inspecting the signed owner"))
            db.commit()
            refs = authorize_project_resources(db, project_id,
                (RequestedResourceRef(kind="dbfox.shader.studio", id=project_id),), snapshot=runtime.snapshot)
            sessions = SessionRepository(db)
            admitted = sessions.admit(session_id=session_id, resource_refs=refs,
                content="Inspect this empty Shader Studio, then create one document called Factory proof.",
                idempotency_key=str(uuid4()), llm_credential_id="independent-model-boundary", api_base=None,
                model_name="scripted", request_payload={"verification": "production_factory"})
            lease = sessions.claim(session_id=session_id, owner="independent-verifier", ttl_seconds=60)
            assert lease is not None
            sessions.promote_next_input(lease=lease)
            db.commit()

        observations = {}
        sent = []
        names = {local: runtime.registry.provider_name_for_key(ToolKey(owner_id="dbfox.shader", local_name=local))
                 for local in ("shader_inspect", "shader_create")}

        class Model:
            def stream(self, *, messages, **_kwargs):
                for item in messages:
                    if item.get("type") == "function_call_output":
                        observations[item["call_id"]] = json.loads(item["output"])
                if not sent:
                    sent.append("inspect")
                    yield from tool_call_events(call_id="inspect", tool_name=names["shader_inspect"], arguments={"section": "documents"})
                elif len(sent) == 1:
                    assert observations["inspect"]["status"] == "succeeded"
                    sent.append("create")
                    yield from tool_call_events(call_id="create", tool_name=names["shader_create"],
                        arguments={"title": "Factory proof", "expected_generation": observations["inspect"]["facts"]["studio_generation"]})
                else:
                    assert observations["create"]["status"] == "succeeded"
                    yield from answer_events("Created the requested document; no GPU execution was requested.")

        loop = build_product_run_loop(session_factory=runtime.factory, snapshot=runtime.snapshot)
        loop.model_factory = lambda _settings: Model()
        try:
            loop.execute(lease=lease, run_id=admitted.run_id)
        finally:
            loop.close()
        with runtime.factory() as db:
            run = db.get(AgentRun, admitted.run_id)
            assert run.status == "completed"
            invocations = db.query(AgentToolInvocation).filter_by(run_id=admitted.run_id).all()
            assert len(invocations) == 2
            assert all(item.status == "succeeded" and item.attempt_count == 1 for item in invocations)
            assert all(item.owner_id == "dbfox.shader" and item.package_digest == runtime.package.package_digest for item in invocations)
        created = observations["create"]["facts"]["document"]
        durable = runtime.operation(project_id, "documents.head", {"document_id": created["id"]})
        assert durable == {key: created[key] for key in ("id", "version", "content_hash", "deleted")}
