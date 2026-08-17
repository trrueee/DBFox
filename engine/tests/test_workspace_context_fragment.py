"""P7 Workspace ContextFragment contributor contract tests."""

from __future__ import annotations

import hashlib

from engine.agent.context_fragment import ContextContributionInput
from engine.agent.repositories.session import SessionRepository
from engine.agent.workspace_context import WorkspaceContextContributor
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
from engine.workspace.read_service import WorkspaceReadService


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
        tool_name="file_read",
        declared_version="1",
        contract_hash="sha256:1",
        input_json=dumps({"path": "src/main.py"}),
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


def test_workspace_contributor_returns_bounded_file_snapshot_fragments(
    db_session,
    test_datasource,
    tmp_path,
) -> None:
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    source_file = workspace_root / "src" / "main.py"
    source_file.parent.mkdir()
    source_content = "print('fresh workspace context')\n"
    source_file.write_text(source_content, encoding="utf-8")
    initial_snapshot = WorkspaceReadService(workspace_root).read_text_file(
        "src/main.py"
    )
    workspace_id = "project-workspace-context"
    db_session.add(
        Project(
            id=workspace_id,
            name="Workspace context test",
            workspace_root=str(workspace_root),
        )
    )
    test_datasource.project_id = workspace_id
    session_id = "session-workspace-context"
    db_session.add(
        AgentSession(
            id=session_id,
            datasource_id=str(test_datasource.id),
            title="Workspace",
        )
    )
    db_session.commit()
    sessions = SessionRepository(db_session)
    admission = sessions.admit(
        session_id=session_id,
        datasource_id=str(test_datasource.id),
        datasource_generation=1,
        content="read src/main.py",
        idempotency_key="workspace-context",
        llm_credential_id="credential",
        api_base=None,
        model_name="model",
        request_payload={},
    )
    turn, invocation = _turn_and_invocation(
        db_session,
        run_id=admission.run_id,
        session_id=session_id,
    )
    artifact_id = "artifact-file-snapshot"
    db_session.add(
        AgentArtifactRecord(
            id=artifact_id,
            run_id=admission.run_id,
            session_id=session_id,
            turn_id=turn.id,
            type="dbfox.workspace.file_snapshot",
            schema_version=1,
            title="src/main.py",
            payload_json=dumps(
                {
                    "relativePath": "src/main.py",
                    "sizeBytes": initial_snapshot.size_bytes,
                    "sha256": initial_snapshot.sha256,
                    "truncated": False,
                    "workspaceId": workspace_id,
                    "workspaceVersion": hashlib.sha256(
                        str(workspace_root.resolve()).encode("utf-8")
                    ).hexdigest()[:16],
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
            id="observation-file-snapshot",
            session_id=session_id,
            run_id=admission.run_id,
            turn_id=turn.id,
            tool_invocation_id=invocation.id,
            sequence=1,
            status="succeeded",
            model_visible_summary="Read src/main.py",
            model_output_json="{}",
            artifact_ids_json=dumps([artifact_id]),
            facts_json="{}",
            semantic_capabilities_json=dumps(["dbfox.workspace.file_snapshot"]),
            contributes_progress=True,
        )
    )
    db_session.commit()

    fragments = WorkspaceContextContributor(db_session).build(
        ContextContributionInput(
            session_id=session_id,
            run_id=admission.run_id,
            current_request="read src/main.py",
            resource_refs=(
                ResourceScopeRef(
                    kind="workspace",
                    id=workspace_id,
                    version=hashlib.sha256(
                        str(workspace_root.resolve()).encode("utf-8")
                    ).hexdigest()[:16],
                    location=str(workspace_root),
                ),
            ),
        )
    )

    assert len(fragments) == 1
    assert fragments[0].lane == "resource"
    assert "src/main.py" in fragments[0].content
    assert initial_snapshot.content in fragments[0].content
    assert fragments[0].provenance["artifact_id"] == artifact_id

    source_file.write_text("print('stale')\n", encoding="utf-8")
    assert WorkspaceContextContributor(db_session).build(
        ContextContributionInput(
            session_id=session_id,
            run_id=admission.run_id,
            current_request="read src/main.py",
            resource_refs=(
                ResourceScopeRef(
                    kind="workspace",
                    id=workspace_id,
                    version=hashlib.sha256(
                        str(workspace_root.resolve()).encode("utf-8")
                    ).hexdigest()[:16],
                    location=str(workspace_root),
                ),
            ),
        )
    ) == ()


def test_workspace_contributor_omits_snapshots_without_an_active_workspace(
    db_session,
    test_datasource,
) -> None:
    del test_datasource
    assert WorkspaceContextContributor(db_session).build(
        ContextContributionInput(
            session_id="any-session",
            run_id="any-run",
            current_request="read src/main.py",
        )
    ) == ()
