"""Production vertical integration test for dbfox.github DLC."""

from __future__ import annotations

import base64
from datetime import datetime
from uuid import uuid4
import httpx
from sqlalchemy.orm import sessionmaker

from engine.agent.context import ContextAssembler
from engine.agent.control import LeaseAwareRunControl
from engine.agent.definition import AgentDefinition
from engine.agent.repositories.session import SessionRepository
from engine.agent.resource_refs import RequestedResourceRef
from engine.agent.run import RunLimits
from engine.agent.tool_dispatcher import ToolDispatchOutcome, ToolDispatcher
from engine.agent.turn import ModelToolCall
from engine.github.contracts import GITHUB_FILE_SNAPSHOT_ARTIFACT_TYPE
from engine.github.migration import GithubBindingRecord, transitional_store
from engine.json_codec import loads
from engine.models import AgentArtifactRecord, AgentRun, AgentSession, Project
from engine.runtime_composition import (
    authorize_project_resources,
    build_product_tool_registry,
    default_context_contributors,
)
from engine.tools.materialization import materialize_tools
from engine.tools.runtime import ToolExecutor


def _mock_github_transport() -> httpx.BaseTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/repos/astral-sh/uv/contents/README.md":
            content_str = "# uv\nAn extremely fast Python package and project manager"
            b64 = base64.b64encode(content_str.encode("utf-8")).decode("ascii")
            return httpx.Response(
                200,
                json={
                    "type": "file",
                    "path": "README.md",
                    "sha": "uv_readme_blob_sha",
                    "size": len(content_str),
                    "encoding": "base64",
                    "content": b64,
                },
            )
        elif path == "/repos/astral-sh/uv":
            return httpx.Response(
                200,
                json={
                    "name": "uv",
                    "private": False,
                    "default_branch": "main",
                    "description": "Extremely fast Python package manager",
                },
            )
        return httpx.Response(404)

    return httpx.MockTransport(handler)


def test_github_production_vertical_slice(db_session, monkeypatch) -> None:
    project_id = "proj-uv-test"
    db_session.add(Project(id=project_id, name="uv project"))
    db_session.flush()

    binding_id = "binding-uv-1"
    rev = "8899aabbccddeeff00112233445566778899aabb"

    transitional_store(db_session).create_binding(
        GithubBindingRecord(
            id=binding_id,
            project_id=project_id,
            owner="astral-sh",
            repository="uv",
            ref_name="main",
            resolved_revision=rev,
            default_branch="main",
            description=None,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
    )
    session_id = "session-uv-1"
    db_session.add(AgentSession(id=session_id, project_id=project_id, title="uv session"))
    db_session.commit()

    # Monkeypatch transport in GithubReadService
    transport = _mock_github_transport()
    from engine.github import resource as gh_resource_module
    original_resolve = gh_resource_module.resolve_github_repository

    def patched_resolve(db, ref, custom_transport=None):
        srv = original_resolve(db, ref, custom_transport=transport)
        return srv

    monkeypatch.setattr(gh_resource_module, "resolve_github_repository", patched_resolve)
    monkeypatch.setattr("engine.github.context.resolve_github_repository", patched_resolve)

    # 1. Frontend sends RequestedResourceRef (wire-only, NO version)
    requested = (RequestedResourceRef(kind="github.repository", id=binding_id),)

    # 2. Server authorizes against project discovery -> canonical version attached
    authorized_scopes = authorize_project_resources(db_session, project_id, requested)
    assert len(authorized_scopes) == 1
    assert authorized_scopes[0].kind == "github.repository"
    assert authorized_scopes[0].id == binding_id
    assert authorized_scopes[0].version == rev

    # 3. Admission with frozen resource scopes
    sessions = SessionRepository(db_session)
    admission = sessions.admit(
        session_id=session_id,
        resource_refs=authorized_scopes,
        content="Read the uv README.md",
        idempotency_key="uv-idem-1",
        llm_credential_id="cred-1",
        api_base="https://api.example.test/v1",
        model_name="model-test",
        request_payload={},
    )
    lease = sessions.claim(session_id=session_id, owner="github-worker")
    assert lease is not None
    sessions.promote_next_input(lease=lease)
    db_session.commit()

    # 4. Tool Materialization for authorized scope
    registry = build_product_tool_registry()
    definition = AgentDefinition(
        allowed_tool_groups=("github", "workspace", "data"),
        execution_mode="agent_autonomous_read",
    )
    materialized = materialize_tools(
        registry,
        execution_mode=definition.execution_mode,
        available_resource_kinds=frozenset({"github.repository"}),
    )
    tool_names = {t.name for t in materialized.tools}
    assert "github_repo_overview" in tool_names
    assert "github_list_files" in tool_names
    assert "github_read_file" in tool_names
    # Database and workspace tools are omitted since their resources are not present
    assert "sql_validate" not in tool_names
    assert "file_read" not in tool_names

    # 5. Start turn and dispatch tool
    turn = sessions.start_turn(
        lease=lease,
        run_id=admission.run_id,
        agent_definition_version=definition.version,
        prompt_version="test",
        prompt_hash="prompt",
        context_snapshot={},
        context_hash="context",
        tool_materialization=materialized.model_dump(mode="json"),
        tool_materialization_hash=materialized.hash,
        provider="test",
        model_name="test",
    )
    db_session.commit()

    factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)
    executor = ToolExecutor(max_workers=1)
    dispatcher = ToolDispatcher(
        session_factory=factory,
        registry=registry,
        definition=definition,
        executor=executor,
    )
    run = db_session.get(AgentRun, admission.run_id)
    assert run is not None
    control = LeaseAwareRunControl(
        run=run,
        limits=RunLimits(),
        cancellation_probe=lambda: False,
        lease_lost_probe=lambda: False,
    )

    call = ModelToolCall(
        id=f"call_{uuid4().hex[:8]}",
        name="github_read_file",
        arguments={"path": "README.md"},
    )
    outcome = dispatcher.request_and_execute(
        lease=lease,
        run_id=admission.run_id,
        turn_id=str(turn.id),
        call=call,
        materialization=materialized,
        control=control,
    )
    assert outcome.outcome is ToolDispatchOutcome.SETTLED

    # Check artifact created
    gh_artifact = (
        db_session.query(AgentArtifactRecord)
        .filter_by(session_id=session_id, type=GITHUB_FILE_SNAPSHOT_ARTIFACT_TYPE)
        .first()
    )
    assert gh_artifact is not None
    payload = loads(gh_artifact.payload_json)
    assert payload["repositoryBindingId"] == binding_id
    assert payload["relativePath"] == "README.md"
    assert payload["revision"] == rev

    # 6. Complete Run 1 and release lease
    run.status = "completed"
    sessions.release(lease=lease)
    db_session.commit()

    # 7. True Second Admission (Run 2 in the same session)
    admission_2 = sessions.admit(
        session_id=session_id,
        resource_refs=authorized_scopes,
        content="Summarize the uv README you read in the previous turn.",
        idempotency_key="uv-idem-2",
        llm_credential_id="cred-1",
        api_base="https://api.example.test/v1",
        model_name="model-test",
        request_payload={},
    )
    lease_2 = sessions.claim(session_id=session_id, owner="github-worker-2")
    assert lease_2 is not None
    sessions.promote_next_input(lease=lease_2)
    db_session.commit()

    # 8. Context Assembler with GitHub contributor on True Second Run (Run 2)
    assembler = ContextAssembler(
        session=db_session,
        contributors=default_context_contributors(),
    )
    snapshot = assembler.build(admission_2.run_id)
    github_fragments = [f for f in snapshot.context_fragments if f.source_id == "dbfox.github"]
    assert len(github_fragments) == 1
    assert "astral-sh/uv" in github_fragments[0].content
    assert "README.md" in github_fragments[0].content
    assert "An extremely fast Python package" in github_fragments[0].content
