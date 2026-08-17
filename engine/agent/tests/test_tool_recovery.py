from __future__ import annotations

import json
import pytest
from sqlalchemy.orm import sessionmaker

from engine.agent.control import LeaseAwareRunControl
from engine.agent.definition import AgentDefinition
from engine.agent.repositories.session import SessionRepository
from engine.agent.repositories.tool import ToolInvocationRepository
from engine.agent.run import RunLimits
from engine.agent.tool_dispatcher import ToolDispatchOutcome, ToolDispatcher
from engine.agent.turn import ModelToolCall
from engine.models import (
    AgentObservationRecord,
    AgentRun,
    AgentSession,
    AgentToolInvocation,
)
from engine.tools.materialization import materialize_tools
from engine.tools.runtime import (
    BaseTool,
    ToolExecutionSpec,
    ToolExecutor,
    ToolInputModel,
    ToolOutputModel,
    ToolPolicy,
    ToolPresentation,
    ToolReconciliation,
    ToolRecoveryPolicy,
    ToolRegistry,
    ToolRunContext,
)


def test_unknown_provider_tool_is_durably_rejected_without_failing_the_run(
    db_session, test_datasource
) -> None:
    db_session.add(
        AgentSession(
            id="session_unknown_tool",
            datasource_id=str(test_datasource.id),
            title="Unknown tool",
        )
    )
    db_session.commit()
    sessions = SessionRepository(db_session)
    admission = sessions.admit(
        session_id="session_unknown_tool",
        datasource_id=str(test_datasource.id),
        datasource_generation=1,
        content="call a tool",
        idempotency_key="request_unknown_tool",
        llm_credential_id="credential",
        api_base=None,
        model_name="test",
        request_payload={},
    )
    lease = sessions.claim(session_id="session_unknown_tool", owner="worker")
    assert lease is not None
    sessions.promote_next_input(lease=lease)
    registry = ToolRegistry()
    definition = AgentDefinition(
        allowed_tool_groups=(),
        execution_mode="user_requested_read",
    )
    tools = materialize_tools(
        registry,
        allowed_groups=set(),
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
        id="call_unknown",
        name="not_a_real_tool",
        arguments={"untrusted": "not persisted"},
    )
    try:
        first = dispatcher.request_and_execute(
            lease=lease,
            run_id=admission.run_id,
            turn_id=str(turn.id),
            call=call,
            materialization=tools,
            control=control,
        )
        repeated = dispatcher.request_and_execute(
            lease=lease,
            run_id=admission.run_id,
            turn_id=str(turn.id),
            call=call,
            materialization=tools,
            control=control,
        )
    finally:
        executor.close(wait=False)

    assert first.outcome is ToolDispatchOutcome.SETTLED
    assert repeated.outcome is ToolDispatchOutcome.SETTLED
    assert first.provider_output is not None
    payload = json.loads(first.provider_output.output)
    assert payload["status"] == "rejected"
    assert payload["error_code"] == "UNKNOWN_TOOL"
    db_session.expire_all()
    assert db_session.query(AgentToolInvocation).count() == 1
    assert db_session.query(AgentObservationRecord).count() == 1
    invocation = db_session.query(AgentToolInvocation).one()
    assert invocation.input_json == "{}"
    assert db_session.get(AgentRun, admission.run_id).status == "running"


class _RecoveryInput(ToolInputModel):
    value: str


class _RecoveryOutput(ToolOutputModel):
    value: str


@pytest.mark.parametrize(
    ("reconciliation_status", "expected_execution_count"),
    [("succeeded", 0), ("not_applied", 1)],
)
def test_recovery_reconciles_by_invocation_key_before_repeating_an_action(
    db_session,
    test_datasource,
    reconciliation_status,
    expected_execution_count,
) -> None:
    reconciliation_keys: list[str] = []
    execution_keys: list[str] = []

    class _ExternalWriteTool(BaseTool[_RecoveryInput, _RecoveryOutput]):
        name = "external_write"
        group = "schema"
        description = "Exercise the external-write recovery contract."
        input_model = _RecoveryInput
        output_model = _RecoveryOutput
        presentation = ToolPresentation(title="External write", category="manage")
        execution = ToolExecutionSpec(recovery=ToolRecoveryPolicy.RECONCILE)

        def run(
            self,
            tool_input: _RecoveryInput,
            context: ToolRunContext,
        ) -> dict[str, str]:
            execution_keys.append(context.idempotency_key)
            return {"value": tool_input.value}

        def reconcile(
            self,
            tool_input: _RecoveryInput,
            context: ToolRunContext,
        ) -> ToolReconciliation:
            reconciliation_keys.append(context.idempotency_key)
            return ToolReconciliation(
                status=reconciliation_status,
                output=(
                    {"value": tool_input.value}
                    if reconciliation_status == "succeeded"
                    else None
                ),
            )

    db_session.add(
        AgentSession(
            id="session_external_recovery",
            datasource_id=str(test_datasource.id),
            title="Recovery",
        )
    )
    db_session.commit()
    sessions = SessionRepository(db_session)
    admission = sessions.admit(
        session_id="session_external_recovery",
        datasource_id=str(test_datasource.id),
        datasource_generation=1,
        content="write once",
        idempotency_key="request_external_recovery",
        llm_credential_id="credential",
        api_base=None,
        model_name="test",
        request_payload={},
    )
    lease = sessions.claim(
        session_id="session_external_recovery",
        owner="worker",
        ttl_seconds=120,
    )
    assert lease is not None
    sessions.promote_next_input(lease=lease)
    registry = ToolRegistry().register(_ExternalWriteTool())
    definition = AgentDefinition(
        allowed_tool_groups=("schema",),
        execution_mode="user_requested_read",
    )
    tools = materialize_tools(
        registry,
        allowed_groups={"schema"},
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
    invocations = ToolInvocationRepository(db_session)
    invocation = invocations.request(
        lease=lease,
        run_id=admission.run_id,
        turn_id=str(turn.id),
        provider_call_id="call_external_write",
        tool_name="external_write",
        raw_input={"value": "once"},
        materialization=tools,
        policy_decision={
            "status": "allowed",
            "reason": "test",
            "safe_args": {"value": "once"},
        },
    )
    invocations.mark_running(lease=lease, invocation_id=invocation.id)
    db_session.commit()

    recovered = invocations.recover_interrupted(
        lease=lease,
        run_id=admission.run_id,
    )
    db_session.commit()
    assert [item.id for item in recovered] == [invocation.id]
    if reconciliation_status == "succeeded":
        # Reconciliation is a read-only recovery step, so a later execution-policy
        # change must not hide an external action that already completed.
        registry.require("external_write").policy = ToolPolicy(
            allowed_execution_modes=("never",),
        )

    factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)
    run = db_session.get(AgentRun, admission.run_id)
    executor = ToolExecutor(max_workers=1)
    try:
        ToolDispatcher(
            session_factory=factory,
            registry=registry,
            definition=definition,
            executor=executor,
        ).execute_requested(
            lease,
            recovered[0],
            control=LeaseAwareRunControl(
                run=run,
                limits=RunLimits(),
                cancellation_probe=lambda: False,
                lease_lost_probe=None,
            ),
        )
    finally:
        executor.close()

    db_session.expire_all()
    durable = db_session.get(AgentToolInvocation, invocation.id)
    observation = (
        db_session.query(AgentObservationRecord)
        .filter_by(tool_invocation_id=invocation.id)
        .one()
    )
    assert durable.status == "succeeded"
    assert observation.status == "succeeded"
    assert reconciliation_keys == [invocation.idempotency_key]
    assert execution_keys == [invocation.idempotency_key] * expected_execution_count


def test_tool_execution_registry_is_indexed_by_invocation_id(
    db_session,
    test_datasource,
    monkeypatch,
) -> None:
    reserved_execution_ids: list[str] = []
    released_execution_ids: list[str] = []

    def fake_reserve(execution_id: str, _datasource_id: str) -> None:
        reserved_execution_ids.append(execution_id)

    def fake_unregister(execution_id: str) -> None:
        released_execution_ids.append(execution_id)

    monkeypatch.setattr(
        "engine.agent.tool_dispatcher.QUERY_REGISTRY.reserve",
        fake_reserve,
    )
    monkeypatch.setattr(
        "engine.agent.tool_dispatcher.QUERY_REGISTRY.unregister",
        fake_unregister,
    )

    class _NoopExecutionInput(ToolInputModel):
        marker: str

    class _NoopExecutionOutput(ToolOutputModel):
        marker: str

    class _NoopExecutionTool(BaseTool[_NoopExecutionInput, _NoopExecutionOutput]):
        name = "noop_execution_tool"
        group = "schema"
        description = "No-op tool to verify execution keying."
        input_model = _NoopExecutionInput
        output_model = _NoopExecutionOutput
        presentation = ToolPresentation(title="Noop execution", category="query")
        execution = ToolExecutionSpec(timeout_seconds=2)

        def run(self, tool_input: _NoopExecutionInput, context: ToolRunContext):
            del context
            return {"marker": tool_input.marker}

    db_session.add(
        AgentSession(
            id="session_invocation_execution_key",
            datasource_id=str(test_datasource.id),
            title="Execution key",
        )
    )
    db_session.commit()
    sessions = SessionRepository(db_session)
    admission = sessions.admit(
        session_id="session_invocation_execution_key",
        datasource_id=str(test_datasource.id),
        datasource_generation=1,
        content="执行两个工具并验证执行标识",
        idempotency_key="request_execution_key",
        llm_credential_id="credential",
        api_base=None,
        model_name="test",
        request_payload={},
    )
    lease = sessions.claim(session_id="session_invocation_execution_key", owner="worker")
    assert lease is not None
    sessions.promote_next_input(lease=lease)

    registry = ToolRegistry().register(_NoopExecutionTool())
    definition = AgentDefinition(
        allowed_tool_groups=("schema",),
        execution_mode="user_requested_read",
    )
    tools = materialize_tools(
        registry,
        allowed_groups={"schema"},
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

    run = db_session.get(AgentRun, admission.run_id)
    assert run is not None
    factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)
    dispatcher = ToolDispatcher(
        session_factory=factory,
        registry=registry,
        definition=definition,
        executor=ToolExecutor(max_workers=2),
    )
    control = LeaseAwareRunControl(
        run=run,
        limits=RunLimits(),
        cancellation_probe=lambda: False,
        lease_lost_probe=None,
    )
    first = ToolInvocationRepository(db_session).request(
        lease=lease,
        run_id=admission.run_id,
        turn_id=str(turn.id),
        provider_call_id="call-noop-1",
        tool_name="noop_execution_tool",
        raw_input={"marker": "A"},
        materialization=tools,
        policy_decision={
            "status": "allowed",
            "safe_args": {"marker": "A"},
        },
    )
    second = ToolInvocationRepository(db_session).request(
        lease=lease,
        run_id=admission.run_id,
        turn_id=str(turn.id),
        provider_call_id="call-noop-2",
        tool_name="noop_execution_tool",
        raw_input={"marker": "B"},
        materialization=tools,
        policy_decision={
            "status": "allowed",
            "safe_args": {"marker": "B"},
        },
    )
    db_session.commit()

    try:
        dispatcher.execute_requested(
            lease=lease,
            invocation=first,
            control=control,
        )
        dispatcher.execute_requested(
            lease=lease,
            invocation=second,
            control=control,
        )
    finally:
        dispatcher.executor.close(wait=False)

    db_session.expire_all()
    assert set(reserved_execution_ids) == {first.id, second.id}
    assert set(released_execution_ids) == {first.id, second.id}
