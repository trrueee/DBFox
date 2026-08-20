"""Tests for GitHubContextContributor: fragment generation, freshness fencing, and bounds."""

from __future__ import annotations

import base64
import hashlib
import httpx

from engine.agent.context import ContextAssembler
from engine.agent.context_fragment import ContextContributionInput, ContextFragment
from engine.agent.repositories.session import SessionRepository
from engine.github.context import GitHubContextContributor
from engine.github.contracts import GITHUB_FILE_SNAPSHOT_ARTIFACT_TYPE
from engine.github.models import GithubRepositoryBinding
from engine.json_codec import dumps
from engine.models import (
    AgentArtifactRecord,
    AgentObservationRecord,
    AgentSession,
    AgentTurn,
    AgentToolInvocation,
    Project,
)
from engine.tools.runtime.attempt import ResourceScopeRef


def _turn_and_invocation(db_session, *, run_id, session_id):
    turn = AgentTurn(
        id=f"turn_{run_id}",
        session_id=session_id,
        run_id=run_id,
        sequence=1,
        status="completed",
        agent_definition_version="1",
        prompt_version="1",
        prompt_hash="prompt",
        context_snapshot_json="{}",
        context_hash="context",
        tool_materialization_json="{}",
        tool_materialization_hash="tools",
        provider="test",
        model_name="test",
    )
    db_session.add(turn)
    db_session.flush()
    invocation = AgentToolInvocation(
        id=f"invocation_{run_id}",
        session_id=session_id,
        run_id=run_id,
        turn_id=turn.id,
        provider_call_id=f"call_{run_id}",
        tool_name="github_read_file",
        declared_version="1",
        contract_hash="sha256:1",
        input_json=dumps({"path": "README.md"}),
        input_hash="input",
        idempotency_key=f"idem_{run_id}",
        status="succeeded",
        policy_json="{}",
        presentation_json="{}",
        recovery_policy="retry_safe",
    )
    db_session.add(invocation)
    db_session.flush()
    return turn, invocation


def _mock_github_transport() -> httpx.BaseTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/repos/facebook/react/contents/README.md":
            content_str = "# React\nA JavaScript library for building user interfaces"
            b64 = base64.b64encode(content_str.encode("utf-8")).decode("ascii")
            return httpx.Response(
                200,
                json={
                    "type": "file",
                    "path": "README.md",
                    "sha": "blob_readme_sha",
                    "size": len(content_str),
                    "encoding": "base64",
                    "content": b64,
                },
            )
        return httpx.Response(404)

    return httpx.MockTransport(handler)


def test_github_context_contributor_rehydrates_snapshot(db_session, monkeypatch) -> None:
    project_id = "proj-gh-ctx"
    db_session.add(Project(id=project_id, name="GH Context Project"))
    db_session.flush()

    binding_id = "bind-gh-1"
    rev = "4a736a61b8f042617f1a3ec958742b6a5b9e0721"
    content_str = "# React\nA JavaScript library for building user interfaces"
    content_sha256 = hashlib.sha256(content_str.encode("utf-8")).hexdigest()

    db_session.add(
        GithubRepositoryBinding(
            id=binding_id,
            project_id=project_id,
            owner="facebook",
            repository="react",
            ref_name="main",
            resolved_revision=rev,
        )
    )
    session_id = "session-gh-ctx"
    db_session.add(
        AgentSession(
            id=session_id,
            project_id=project_id,
            title="GitHub Session",
        )
    )
    db_session.commit()

    sessions = SessionRepository(db_session)
    admission = sessions.admit(
        session_id=session_id,
        resource_refs=(
            ResourceScopeRef(kind="github.repository", id=binding_id, version=rev),
        ),
        content="Read README.md",
        idempotency_key="gh-ctx-key",
        llm_credential_id="cred-1",
        api_base=None,
        model_name="model",
        request_payload={},
    )
    turn, invocation = _turn_and_invocation(
        db_session,
        run_id=admission.run_id,
        session_id=session_id,
    )

    artifact_id = "artifact-gh-snap-1"
    db_session.add(
        AgentArtifactRecord(
            id=artifact_id,
            run_id=admission.run_id,
            session_id=session_id,
            turn_id=turn.id,
            type=GITHUB_FILE_SNAPSHOT_ARTIFACT_TYPE,
            schema_version=1,
            title="README.md",
            payload_json=dumps(
                {
                    "repositoryBindingId": binding_id,
                    "owner": "facebook",
                    "repository": "react",
                    "revision": rev,
                    "relativePath": "README.md",
                    "blobSha": "blob_readme_sha",
                    "contentSha256": content_sha256,
                    "sizeBytes": len(content_str),
                    "truncated": False,
                }
            ),
            presentation_json="{}",
            provenance_json="{}",
            relations_json="[]",
            status="completed",
        )
    )
    db_session.add(
        AgentObservationRecord(
            id="observation-gh-snap-1",
            session_id=session_id,
            run_id=admission.run_id,
            turn_id=turn.id,
            tool_invocation_id=invocation.id,
            sequence=1,
            status="succeeded",
            model_visible_summary="Read README.md",
            model_output_json="{}",
            artifact_ids_json=dumps([artifact_id]),
            facts_json="{}",
            semantic_capabilities_json=dumps([GITHUB_FILE_SNAPSHOT_ARTIFACT_TYPE]),
            contributes_progress=True,
        )
    )
    db_session.commit()

    captured_inputs: list[ContextContributionInput] = []

    class CapturingContributor:
        id = "test.capture"

        def build(
            self,
            input: ContextContributionInput,
        ) -> tuple[ContextFragment, ...]:
            captured_inputs.append(input)
            return ()

    ContextAssembler(
        db_session,
        contributors=(lambda _session: CapturingContributor(),),
    ).build(admission.run_id)
    assert len(captured_inputs) == 1
    recent = captured_inputs[0].recent_artifacts
    assert len(recent) == 1
    assert recent[0].observation_id == "observation-gh-snap-1"
    assert recent[0].artifact_id == artifact_id
    assert recent[0].artifact_type == GITHUB_FILE_SNAPSHOT_ARTIFACT_TYPE
    assert recent[0].semantic_capabilities == (
        GITHUB_FILE_SNAPSHOT_ARTIFACT_TYPE,
    )
    assert recent[0].payload["repositoryBindingId"] == binding_id

    # Monkeypatch transport on GithubReadService
    transport = _mock_github_transport()
    from engine.github import context as gh_context_module
    original_resolve = gh_context_module.resolve_github_repository

    def patched_resolve(session, scope):
        srv = original_resolve(session, scope)
        srv._custom_transport = transport
        return srv

    monkeypatch.setattr(gh_context_module, "resolve_github_repository", patched_resolve)

    contributor = GitHubContextContributor(db_session)
    fragments = contributor.build(
        ContextContributionInput(
            session_id=session_id,
            run_id=admission.run_id,
            current_request="Tell me about react",
            resource_refs=(
                ResourceScopeRef(kind="github.repository", id=binding_id, version=rev),
            ),
        )
    )

    assert len(fragments) == 1
    assert fragments[0].source_id == "dbfox.github"
    assert fragments[0].lane == "resource"
    assert "facebook/react" in fragments[0].content
    assert "README.md" in fragments[0].content
    assert content_str in fragments[0].content
    assert fragments[0].provenance["artifact_id"] == artifact_id


def test_github_context_contributor_stale_fence(db_session, monkeypatch) -> None:
    # If the current input resource ref has a different revision, the contributor skips rehydrating
    project_id = "proj-gh-stale"
    db_session.add(Project(id=project_id, name="GH Stale Project"))
    db_session.flush()

    binding_id = "bind-gh-stale"
    old_rev = "1111111111111111111111111111111111111111"
    new_rev = "2222222222222222222222222222222222222222"

    db_session.add(
        GithubRepositoryBinding(
            id=binding_id,
            project_id=project_id,
            owner="facebook",
            repository="react",
            ref_name="main",
            resolved_revision=new_rev,
        )
    )
    session_id = "session-gh-stale"
    db_session.add(AgentSession(id=session_id, project_id=project_id, title="Stale"))
    db_session.commit()

    contributor = GitHubContextContributor(db_session)
    # Asking with old_rev (which no longer matches current binding or frozen scope) returns empty
    fragments = contributor.build(
        ContextContributionInput(
            session_id=session_id,
            run_id="any-run",
            current_request="check",
            resource_refs=(
                ResourceScopeRef(kind="github.repository", id=binding_id, version=old_rev),
            ),
        )
    )
    assert fragments == ()
