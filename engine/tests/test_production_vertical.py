"""One production-shaped vertical path for Runtime convergence."""

from __future__ import annotations

import json

from sqlalchemy.orm import sessionmaker

from engine.agent.context import ContextAssembler
from engine.agent.control import LeaseAwareRunControl
from engine.agent.definition import AgentDefinition
from engine.agent.repositories.session import SessionRepository
from engine.agent.run import RunLimits
from engine.agent.tool_dispatcher import ToolDispatchOutcome, ToolDispatcher
from engine.agent.turn import ModelToolCall
from engine.models import (
    AgentArtifactRecord,
    AgentObservationRecord,
    AgentRun,
    AgentSession,
    AgentToolInvocation,
    Project,
)
from engine.tools.builtin.registry import register_workspace_extension
from engine.tools.materialization import materialize_tools
from engine.tools.runtime import ToolExecutor, ToolRegistry


def test_workspace_file_read_vertical_chain_lands_artifact_and_context(
    db_session,
    test_datasource,
    tmp_path,
) -> None:
    root = tmp_path / "project"
    (root / "src").mkdir(parents=True)
    (root / "src" / "main.py").write_text("print('ok')\n", encoding="utf-8")

    db_session.add(
        Project(
            id="project-vertical",
            name="Vertical Workspace",
            workspace_root=str(root),
        )
    )
    db_session.flush()
    test_datasource.project_id = "project-vertical"
    db_session.add(
        AgentSession(
            id="session-vertical",
            datasource_id=str(test_datasource.id),
            title="Vertical",
        )
    )
    db_session.commit()

    sessions = SessionRepository(db_session)
    admission = sessions.admit(
        session_id="session-vertical",
        datasource_id=str(test_datasource.id),
        datasource_generation=1,
        content="read src/main.py",
        idempotency_key="vertical-file-read",
        llm_credential_id="credential",
        api_base=None,
        model_name="test",
        request_payload={},
    )
    lease = sessions.claim(session_id="session-vertical", owner="vertical")
    assert lease is not None
    sessions.promote_next_input(lease=lease)

    registry = ToolRegistry(available_backends=frozenset({"in_process"}))
    register_workspace_extension(registry)
    registry.freeze()
    definition = AgentDefinition(
        allowed_tool_groups=("workspace",),
        execution_mode="agent_autonomous_read",
    )
    tools = materialize_tools(
        registry,
        allowed_groups={"workspace"},
        execution_mode=definition.execution_mode,
    )
    turn = sessions.start_turn(
        lease=lease,
        run_id=admission.run_id,
        agent_definition_version=definition.version,
        prompt_version="test",
        prompt_hash="prompt",
        context_snapshot={},
        context_hash="context",
        tool_materialization=tools.model_dump(mode="json"),
        tool_materialization_hash=tools.hash,
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
        id="call-file-read",
        name="file_read",
        arguments={"path": "src/main.py"},
    )
    try:
        result = dispatcher.request_and_execute(
            lease=lease,
            run_id=admission.run_id,
            turn_id=str(turn.id),
            call=call,
            materialization=tools,
            control=control,
        )
    finally:
        executor.close(wait=False)

    assert result.outcome is ToolDispatchOutcome.SETTLED
    assert result.provider_output is not None
    payload = json.loads(result.provider_output.output)
    assert payload["status"] == "succeeded"

    db_session.expire_all()
    invocation = db_session.query(AgentToolInvocation).one()
    observation = db_session.query(AgentObservationRecord).one()
    artifact = db_session.query(AgentArtifactRecord).one()

    assert invocation.declared_version == "1"
    assert invocation.contract_hash.startswith("sha256:")
    assert observation.status == "succeeded"
    assert artifact.type == "dbfox.workspace.file_snapshot"

    snapshot = ContextAssembler(db_session).build(admission.run_id)
    assert len(snapshot.context_fragments) == 1
    assert snapshot.context_fragments[0]["lane"] == "resource"
