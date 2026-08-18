"""One production-shaped vertical path for Runtime convergence."""

from __future__ import annotations

import hashlib
import json

from sqlalchemy.orm import sessionmaker

from engine.agent.context import ContextAssembler
from engine.agent.control import LeaseAwareRunControl
from engine.agent.definition import AgentDefinition
from engine.agent.repositories.approval import ApprovalRepository
from engine.agent.repositories.session import SessionRepository
from engine.agent.repositories.tool import ToolInvocationRepository
from engine.agent.run import RunLimits
from engine.agent.tool_dispatcher import ToolDispatchOutcome, ToolDispatcher
from engine.agent.turn import ModelToolCall
from engine.tools.runtime.attempt import ResourceScopeRef
from engine.models import (
    AgentArtifactRecord,
    AgentApproval,
    AgentObservationRecord,
    AgentRun,
    AgentMessage,
    AgentSession,
    AgentToolInvocation,
    Project,
)
from engine.runtime_composition import default_context_contributors
from engine.tools.builtin.registry import (
    register_workspace_extension,
    register_workspace_write_extension,
    register_remote_job_extension,
)
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
            project_id="project-vertical",
            datasource_id=str(test_datasource.id),
            title="Vertical",
        )
    )
    db_session.commit()

    # Compute workspace version for the resource ref
    ws_digest = hashlib.sha256(str(root).encode("utf-8")).hexdigest()[:16]

    sessions = SessionRepository(db_session)
    admission = sessions.admit(
        session_id="session-vertical",
        resource_refs=(
            ResourceScopeRef(kind="database", id=str(test_datasource.id), version=1),
            ResourceScopeRef(kind="workspace", id="project-vertical", version=ws_digest),
        ),
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

    snapshot = ContextAssembler(
        db_session,
        contributors=default_context_contributors(),
    ).build(admission.run_id)
    assert len(snapshot.context_fragments) == 1
    assert snapshot.context_fragments[0].lane == "resource"


def test_vertical_chain_handoff_after_failed_run(
    db_session,
    test_datasource,
) -> None:
    db_session.add(
        AgentSession(
            id="session-vertical-failed",
            datasource_id=str(test_datasource.id),
            title="Vertical failed run handoff",
        )
    )
    db_session.commit()
    sessions = SessionRepository(db_session)
    first = sessions.admit(
        session_id="session-vertical-failed",
        resource_refs=(ResourceScopeRef(kind="database", id=str(test_datasource.id), version=1),),
        content="首次分析失败",
        idempotency_key="vertical-failed-first",
        llm_credential_id="credential",
        api_base=None,
        model_name="test",
        request_payload={},
    )
    first_run = db_session.get(AgentRun, first.run_id)
    assert first_run is not None
    first_run.status = "failed"
    first_run.error_code = "AGENT_RUNTIME_ERROR"
    first_run.error_message = "private failure secret should not leak"
    first_run.result_json = json.dumps(
        {"completion_disposition": "failed", "limitation_codes": []}
    )
    first_assistant = db_session.get(AgentMessage, first.assistant_message_id)
    assert first_assistant is not None
    first_assistant.status = "failed"
    db_session.commit()

    second = sessions.admit(
        session_id="session-vertical-failed",
        resource_refs=(ResourceScopeRef(kind="database", id=str(test_datasource.id), version=1),),
        content="上次失败，继续重试。",
        idempotency_key="vertical-failed-second",
        llm_credential_id="credential",
        api_base=None,
        model_name="test",
        request_payload={},
    )
    db_session.commit()

    snapshot = ContextAssembler(db_session).build(second.run_id)
    assert snapshot.previous_run_outcome is not None
    assert snapshot.previous_run_outcome.status == "failed"
    assert snapshot.previous_run_outcome.error_code == "AGENT_RUNTIME_ERROR"
    assert "private failure secret" not in json.dumps(
        snapshot.previous_run_outcome.model_dump(mode="json"),
        ensure_ascii=False,
    )
    assert snapshot.previous_run_outcome.public_message


def test_vertical_chain_handoff_after_failed_tool_run(
    db_session,
    test_datasource,
    tmp_path,
) -> None:
    root = tmp_path / "project"
    (root / "src").mkdir(parents=True)
    (root / "src" / "main.py").write_text("print('ok')\n", encoding="utf-8")

    db_session.add(
        Project(
            id="project-vertical-tool-failed",
            name="Vertical Tool Failed",
            workspace_root=str(root),
        )
    )
    db_session.flush()
    test_datasource.project_id = "project-vertical-tool-failed"
    db_session.add(
        AgentSession(
            id="session-vertical-tool-failed",
            datasource_id=str(test_datasource.id),
            title="Vertical tool failed run handoff",
        )
    )
    db_session.commit()

    sessions = SessionRepository(db_session)
    first = sessions.admit(
        session_id="session-vertical-tool-failed",
        resource_refs=(ResourceScopeRef(kind="database", id=str(test_datasource.id), version=1),),
        content="先读文件再失败",
        idempotency_key="vertical-tool-failed-first",
        llm_credential_id="credential",
        api_base=None,
        model_name="test",
        request_payload={},
    )
    lease = sessions.claim(session_id="session-vertical-tool-failed", owner="vertical-tool")
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
        run_id=first.run_id,
        agent_definition_version=definition.version,
        prompt_version="tool-fail",
        prompt_hash="tool-fail",
        context_snapshot={},
        context_hash="tool-fail",
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
    run = db_session.get(AgentRun, first.run_id)
    assert run is not None
    control = LeaseAwareRunControl(
        run=run,
        limits=RunLimits(),
        cancellation_probe=lambda: False,
        lease_lost_probe=lambda: False,
    )
    call = ModelToolCall(
        id="call-tool-failed",
        name="file_read",
        arguments={"path": "src/main.py"},
    )
    try:
        first_call = dispatcher.request_and_execute(
            lease=lease,
            run_id=first.run_id,
            turn_id=str(turn.id),
            call=call,
            materialization=tools,
            control=control,
        )
    finally:
        executor.close(wait=False)

    assert first_call.outcome is ToolDispatchOutcome.SETTLED
    assert first_call.provider_output is not None
    payload = json.loads(first_call.provider_output.output)
    assert payload["status"] == "succeeded"

    first_run = db_session.get(AgentRun, first.run_id)
    assert first_run is not None
    first_run.status = "failed"
    first_run.error_code = "AGENT_RUNTIME_ERROR"
    first_run.error_message = "private tool failure secret"
    first_run.result_json = json.dumps({"completion_disposition": "failed", "limitation_codes": []})
    first_assistant = db_session.get(AgentMessage, first.assistant_message_id)
    assert first_assistant is not None
    first_assistant.status = "failed"
    db_session.commit()

    second = sessions.admit(
        session_id="session-vertical-tool-failed",
        resource_refs=(ResourceScopeRef(kind="database", id=str(test_datasource.id), version=1),),
        content="从失败工具链路继续。",
        idempotency_key="vertical-tool-failed-second",
        llm_credential_id="credential",
        api_base=None,
        model_name="test",
        request_payload={},
    )
    db_session.commit()

    snapshot = ContextAssembler(db_session).build(second.run_id)
    assert snapshot.previous_run_outcome is not None
    assert snapshot.previous_run_outcome.status == "failed"
    assert snapshot.previous_run_outcome.error_code == "AGENT_RUNTIME_ERROR"
    assert snapshot.previous_run_outcome.public_message
    assert "private tool failure secret" not in json.dumps(
        snapshot.previous_run_outcome.model_dump(mode="json"),
        ensure_ascii=False,
    )


def test_vertical_chain_handoff_after_cancelled_run(
    db_session,
    test_datasource,
) -> None:
    db_session.add(
        AgentSession(
            id="session-vertical-cancel",
            datasource_id=str(test_datasource.id),
            title="Vertical cancelled run handoff",
        )
    )
    db_session.commit()
    sessions = SessionRepository(db_session)
    first = sessions.admit(
        session_id="session-vertical-cancel",
        resource_refs=(ResourceScopeRef(kind="database", id=str(test_datasource.id), version=1),),
        content="首次分析取消",
        idempotency_key="vertical-cancel-first",
        llm_credential_id="credential",
        api_base=None,
        model_name="test",
        request_payload={},
    )
    first_run = db_session.get(AgentRun, first.run_id)
    assert first_run is not None
    first_run.status = "cancelled"
    first_run.error_code = "AGENT_CANCELLED"
    first_run.error_message = "user cancelled"
    first_assistant = db_session.get(AgentMessage, first.assistant_message_id)
    assert first_assistant is not None
    first_assistant.status = "cancelled"
    db_session.commit()

    second = sessions.admit(
        session_id="session-vertical-cancel",
        resource_refs=(ResourceScopeRef(kind="database", id=str(test_datasource.id), version=1),),
        content="取消后再发起重试。",
        idempotency_key="vertical-cancel-second",
        llm_credential_id="credential",
        api_base=None,
        model_name="test",
        request_payload={},
    )
    db_session.commit()

    snapshot = ContextAssembler(db_session).build(second.run_id)
    assert snapshot.previous_run_outcome is not None
    assert snapshot.previous_run_outcome.status == "cancelled"
    assert snapshot.previous_run_outcome.error_code == "AGENT_CANCELLED"
    assert snapshot.previous_run_outcome.public_message


def test_vertical_chain_file_write_patch_approval_recovery(
    db_session,
    test_datasource,
    tmp_path,
    monkeypatch,
) -> None:
    root = tmp_path / "project"
    (root / "src").mkdir(parents=True)
    target = root / "src" / "notes.txt"
    target.write_text("old-content\n", encoding="utf-8")
    old_sha = hashlib.sha256(target.read_bytes()).hexdigest()

    db_session.add(
        Project(
            id="project-vertical-write",
            name="Vertical Write Workspace",
            workspace_root=str(root),
        )
    )
    db_session.flush()
    test_datasource.project_id = "project-vertical-write"
    db_session.add(
        AgentSession(
            id="session-vertical-write",
            datasource_id=str(test_datasource.id),
            title="Vertical file-write",
        )
    )
    db_session.commit()

    sessions = SessionRepository(db_session)
    admission = sessions.admit(
        session_id="session-vertical-write",
        resource_refs=(ResourceScopeRef(kind="database", id=str(test_datasource.id), version=1),),
        content="更新文件",
        idempotency_key="vertical-file-write-approval",
        llm_credential_id="credential",
        api_base=None,
        model_name="test",
        request_payload={},
    )
    lease = sessions.claim(session_id="session-vertical-write", owner="vertical-write")
    assert lease is not None
    sessions.promote_next_input(lease=lease)

    registry = ToolRegistry(
        available_backends=frozenset({"in_process", "isolated_process"})
    )
    register_workspace_write_extension(registry)
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
        prompt_hash="context",
        context_snapshot={},
        context_hash="context",
        tool_materialization=tools.model_dump(mode="json"),
        tool_materialization_hash=tools.hash,
        provider="test",
        model_name="test",
    )
    db_session.commit()
    # The isolated worker rehydrates the workspace from the canonical Project
    # binding in metadata, so point its fresh process at this test's database.
    monkeypatch.setenv("DBFOX_DATABASE_URL", str(db_session.get_bind().url))

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

    waiting = dispatcher.request(
        lease=lease,
        run_id=admission.run_id,
        turn_id=str(turn.id),
        call=ModelToolCall(
            id="call-file-write-patch",
            name="file_write_patch",
            arguments={
                "path": "src/notes.txt",
                "content": "new-content\n",
                "expected_sha256": old_sha,
            },
        ),
        materialization=tools,
        control=LeaseAwareRunControl(
            run=run,
            limits=RunLimits(),
            cancellation_probe=lambda: False,
            lease_lost_probe=None,
        ),
    )
    db_session.commit()
    assert waiting.outcome is ToolDispatchOutcome.WAITING_APPROVAL
    db_session.expire_all()
    first_invocation = db_session.query(AgentToolInvocation).filter_by(
        run_id=admission.run_id,
        turn_id=str(turn.id),
        tool_name="file_write_patch",
    ).one()
    assert first_invocation.status == "waiting_approval"
    assert first_invocation.approval_id is not None

    ApprovalRepository(db_session).resolve(
        approval_id=str(first_invocation.approval_id),
        expected_version=0,
        approved=True,
        actor="approval-user",
    )
    db_session.commit()

    lease = sessions.claim(session_id="session-vertical-write", owner="vertical-write")
    assert lease is not None
    sessions.bind_run(lease=lease, run_id=admission.run_id)
    invocations = ToolInvocationRepository(db_session)
    invocations.mark_running(
        lease=lease,
        invocation_id=str(first_invocation.id),
    )
    db_session.commit()
    recovered = invocations.recover_interrupted(lease=lease, run_id=admission.run_id)
    db_session.commit()
    assert len(recovered) == 1
    assert recovered[0].status.value == "requested"
    assert recovered[0].attempt_count == 1

    run = db_session.get(AgentRun, admission.run_id)
    assert run is not None
    control = LeaseAwareRunControl(
        run=run,
        limits=RunLimits(),
        cancellation_probe=lambda: False,
        lease_lost_probe=None,
    )
    try:
        settled = dispatcher.execute_requested(
            lease=lease,
            invocation=recovered[0],
            control=control,
        )
    finally:
        executor.close(wait=False)

    assert settled is not None
    payload = json.loads(settled.output)
    assert payload["status"] == "succeeded"

    db_session.expire_all()
    invocation = (
        db_session.query(AgentToolInvocation)
        .filter_by(id=str(recovered[0].id))
        .one()
    )
    observation = (
        db_session.query(AgentObservationRecord)
        .filter_by(tool_invocation_id=str(recovered[0].id))
        .one()
    )
    artifact = db_session.query(AgentArtifactRecord).one()
    approval = db_session.get(AgentApproval, first_invocation.approval_id)
    assert approval is not None and approval.status == "approved"
    assert invocation.status == "succeeded"
    assert invocation.attempt_count == 2
    assert observation.status == "succeeded"
    assert artifact.type == "dbfox.workspace.code_patch"
    assert (
        db_session.query(AgentArtifactRecord)
        .filter_by(type="dbfox.workspace.code_patch")
        .count()
        == 1
    )
    assert target.read_text(encoding="utf-8") == "new-content\n"
    context_lanes = {
        context.lane
        for context in ContextAssembler(
            db_session,
            contributors=default_context_contributors(),
        ).build(admission.run_id).context_fragments
    }
    assert context_lanes == set()


def test_vertical_chain_remote_job_submit_status_cancel_across_runs(
    db_session,
    test_datasource,
) -> None:
    session_id = "session-vertical-remote-job"
    db_session.add(
        AgentSession(
            id=session_id,
            datasource_id=str(test_datasource.id),
            title="Vertical remote job",
        )
    )
    db_session.commit()
    sessions = SessionRepository(db_session)

    first = sessions.admit(
        session_id=session_id,
        resource_refs=(ResourceScopeRef(kind="database", id=str(test_datasource.id), version=1),),
        content="提交远端任务",
        idempotency_key="vertical-remote-job-first",
        llm_credential_id="credential",
        api_base=None,
        model_name="test",
        request_payload={},
    )
    first_lease = sessions.claim(session_id=session_id, owner="vertical-remote-job")
    assert first_lease is not None
    sessions.promote_next_input(lease=first_lease)

    registry = ToolRegistry(available_backends=frozenset({"in_process"}))
    register_remote_job_extension(registry)
    registry.freeze()
    definition = AgentDefinition(
        allowed_tool_groups=("remote_job",),
        execution_mode="user_requested_read",
    )
    tools = materialize_tools(
        registry,
        allowed_groups={"remote_job"},
        execution_mode=definition.execution_mode,
    )
    first_turn = sessions.start_turn(
        lease=first_lease,
        run_id=first.run_id,
        agent_definition_version=definition.version,
        prompt_version="remote-job",
        prompt_hash="remote-job",
        context_snapshot={},
        context_hash="remote-job",
        tool_materialization=tools.model_dump(mode="json"),
        tool_materialization_hash=tools.hash,
        provider="test",
        model_name="test",
    )
    db_session.commit()

    first_run = db_session.get(AgentRun, first.run_id)
    assert first_run is not None
    first_control = LeaseAwareRunControl(
        run=first_run,
        limits=RunLimits(),
        cancellation_probe=lambda: False,
        lease_lost_probe=None,
    )

    factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)
    executor = ToolExecutor(max_workers=1)
    dispatcher = ToolDispatcher(
        session_factory=factory,
        registry=registry,
        definition=definition,
        executor=executor,
    )
    try:
        submit_result = dispatcher.request_and_execute(
            lease=first_lease,
            run_id=first.run_id,
            turn_id=str(first_turn.id),
            call=ModelToolCall(
                id="call-remote-job-submit",
                name="remote_job_submit",
                arguments={
                    "command": "echo hello",
                    "command_type": "run",
                },
            ),
            materialization=tools,
            control=first_control,
        )
    finally:
        executor.close(wait=False)

    assert submit_result.outcome is ToolDispatchOutcome.SETTLED
    assert submit_result.provider_output is not None
    submit_payload = json.loads(submit_result.provider_output.output)
    job_id = str(submit_payload["facts"]["job_id"])
    assert submit_payload["facts"]["status"] == "queued"

    db_session.expire_all()
    submit_artifacts = (
        db_session.query(AgentArtifactRecord)
        .filter_by(type="dbfox.remote_job")
        .filter(AgentArtifactRecord.semantic_id == f"remote_job:{job_id}")
        .all()
    )
    assert len(submit_artifacts) == 1

    second = sessions.admit(
        session_id=session_id,
        resource_refs=(ResourceScopeRef(kind="database", id=str(test_datasource.id), version=1),),
        content="查询远端任务并取消",
        idempotency_key="vertical-remote-job-second",
        llm_credential_id="credential",
        api_base=None,
        model_name="test",
        request_payload={},
    )
    second_lease = sessions.claim(session_id=session_id, owner="vertical-remote-job")
    assert second_lease is not None
    sessions.promote_next_input(lease=second_lease)

    second_turn = sessions.start_turn(
        lease=second_lease,
        run_id=second.run_id,
        agent_definition_version=definition.version,
        prompt_version="remote-job",
        prompt_hash="remote-job",
        context_snapshot={},
        context_hash="remote-job",
        tool_materialization=tools.model_dump(mode="json"),
        tool_materialization_hash=tools.hash,
        provider="test",
        model_name="test",
    )
    db_session.commit()

    second_run = db_session.get(AgentRun, second.run_id)
    assert second_run is not None
    second_control = LeaseAwareRunControl(
        run=second_run,
        limits=RunLimits(),
        cancellation_probe=lambda: False,
        lease_lost_probe=None,
    )

    executor = ToolExecutor(max_workers=1)
    dispatcher = ToolDispatcher(
        session_factory=factory,
        registry=registry,
        definition=definition,
        executor=executor,
    )
    try:
        status_result = dispatcher.request_and_execute(
            lease=second_lease,
            run_id=second.run_id,
            turn_id=str(second_turn.id),
            call=ModelToolCall(
                id="call-remote-job-status",
                name="remote_job_status",
                arguments={"job_id": job_id},
            ),
            materialization=tools,
            control=second_control,
        )
        cancel_result = dispatcher.request_and_execute(
            lease=second_lease,
            run_id=second.run_id,
            turn_id=str(second_turn.id),
            call=ModelToolCall(
                id="call-remote-job-cancel",
                name="remote_job_cancel",
                arguments={"job_id": job_id},
            ),
            materialization=tools,
            control=second_control,
        )
    finally:
        executor.close(wait=False)

    assert status_result.outcome is ToolDispatchOutcome.SETTLED
    assert status_result.provider_output is not None
    status_payload = json.loads(status_result.provider_output.output)
    assert status_payload["facts"]["status"] == "queued"
    assert status_payload["facts"]["job_id"] == job_id

    assert cancel_result.outcome is ToolDispatchOutcome.SETTLED
    assert cancel_result.provider_output is not None
    cancel_payload = json.loads(cancel_result.provider_output.output)
    assert cancel_payload["facts"]["status"] == "cancelled"
    assert cancel_payload["facts"]["job_id"] == job_id
    assert "artifact_id" not in cancel_payload

    remote_job_artifacts = (
        db_session.query(AgentArtifactRecord)
        .filter_by(type="dbfox.remote_job", session_id=session_id)
        .order_by(AgentArtifactRecord.version, AgentArtifactRecord.created_at)
        .all()
    )
    assert len(remote_job_artifacts) >= 2
    assert json.loads(remote_job_artifacts[-1].payload_json).get("status") == "cancelled"
    assert all(
        "artifact_id" not in json.loads(artifact.payload_json)
        for artifact in remote_job_artifacts
    )
