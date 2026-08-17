from __future__ import annotations

import json

import pytest

from engine.agent.context import ContextAssembler
from engine.agent.observation import ObservationStatus
from engine.agent.repositories.session import SessionRepository
from engine.agent.repositories.tool import ToolInvocationRepository
from engine.agent.tool import ToolInvocationStatus
from engine.models import AgentObservationRecord, AgentSession, AgentToolInvocation
from engine.tools.builtin import register_dbfox_tools
from engine.tools.materialization import materialize_tools
from engine.tools.runtime.base import ToolRecoveryPolicy


def test_tool_intent_is_durable_before_running_and_settles_once(db_session, test_datasource) -> None:
    db_session.add(AgentSession(id="session_tool", datasource_id=str(test_datasource.id), title="Tool"))
    db_session.commit()
    sessions = SessionRepository(db_session)
    admission = sessions.admit(
        session_id="session_tool",
        datasource_id=str(test_datasource.id),
        datasource_generation=1,
        content="查看表",
        idempotency_key="request_tool",
        llm_credential_id="credential_1",
        api_base="https://api.example.test/v1",
        model_name="model-test",
        request_payload={"question": "查看表"},
    )
    lease = sessions.claim(session_id="session_tool", owner="worker")
    assert lease is not None
    sessions.promote_next_input(lease=lease)
    registry = register_dbfox_tools()
    tools = materialize_tools(registry, allowed_groups={"catalog"}, execution_mode="user_requested_read")
    turn = sessions.start_turn(
        lease=lease,
        run_id=admission.run_id,
        agent_definition_version="analyst@1",
        prompt_version="prompt@1",
        prompt_hash="prompt-hash",
        context_snapshot={},
        context_hash="context-hash",
        tool_materialization=tools.model_dump(mode="json"),
        tool_materialization_hash=tools.hash,
        provider="openai-compatible",
        model_name="model-test",
    )
    db_session.commit()

    repository = ToolInvocationRepository(db_session)
    invocation = repository.request(
        lease=lease,
        run_id=admission.run_id,
        turn_id=str(turn.id),
        provider_call_id="call_1",
        tool_name="schema_list",
        raw_input={},
        materialization=tools,
        policy_decision={"status": "allowed", "reason": "safe"},
    )
    db_session.commit()

    durable = db_session.get(AgentToolInvocation, invocation.id)
    assert durable.status == ToolInvocationStatus.REQUESTED.value
    assert durable.input_hash == invocation.authorized_input_hash

    running = repository.mark_running(lease=lease, invocation_id=invocation.id)
    assert running.status is ToolInvocationStatus.RUNNING
    observation = repository.settle(
        lease=lease,
        invocation_id=invocation.id,
        status=ObservationStatus.SUCCEEDED,
        model_visible_summary="找到 3 张表。",
        facts={"table_count": 3},
    )
    turn.status = "completed"
    turn.response_items_json = json.dumps(
        [
            {
                "type": "function_call",
                "call_id": "call_1",
                "name": "schema_list",
                "arguments": "{}",
            }
        ]
    )
    db_session.commit()

    assert observation.tool_invocation_id == invocation.id
    assert observation.facts == {"table_count": 3}
    assert observation.model_output == (
        '{"artifact_ids":[],"facts":{"table_count":3},"retryable":false,'
        '"status":"succeeded","summary":"找到 3 张表。"}'
    )
    assert db_session.get(AgentObservationRecord, observation.id).model_output_json == (
        observation.model_output
    )
    assert db_session.get(AgentToolInvocation, invocation.id).status == ToolInvocationStatus.SUCCEEDED.value
    recovered_context = ContextAssembler(db_session).build(admission.run_id)
    output_item = next(
        item
        for batch in recovered_context.response_batches
        for item in batch.items
        if item["type"] == "function_call_output"
    )
    assert json.loads(output_item["output"]) == {
        "artifact_ids": [],
        "facts": {"table_count": 3},
        "retryable": False,
        "status": "succeeded",
        "summary": "找到 3 张表。",
    }


@pytest.mark.parametrize(
    "recovery_policy",
    [ToolRecoveryPolicy.RETRY_SAFE, ToolRecoveryPolicy.RECONCILE],
)
def test_interrupted_recoverable_tool_is_requeued_with_the_same_invocation_id(
    db_session,
    test_datasource,
    recovery_policy,
) -> None:
    db_session.add(AgentSession(id="session_recovery", datasource_id=str(test_datasource.id), title="Recovery"))
    db_session.commit()
    sessions = SessionRepository(db_session)
    admission = sessions.admit(
        session_id="session_recovery", datasource_id=str(test_datasource.id), datasource_generation=1,
        content="查看表", idempotency_key="request_recovery", llm_credential_id="credential_1",
        api_base=None, model_name="model-test", request_payload={},
    )
    lease = sessions.claim(session_id="session_recovery", owner="worker")
    sessions.promote_next_input(lease=lease)
    tools = materialize_tools(
        register_dbfox_tools(), allowed_groups={"catalog"}, execution_mode="user_requested_read"
    )
    turn = sessions.start_turn(
        lease=lease, run_id=admission.run_id, agent_definition_version="1", prompt_version="1",
        prompt_hash="prompt", context_snapshot={}, context_hash="context",
        tool_materialization=tools.model_dump(mode="json"), tool_materialization_hash=tools.hash,
        provider="test", model_name="test",
    )
    repository = ToolInvocationRepository(db_session)
    invocation = repository.request(
        lease=lease, run_id=admission.run_id, turn_id=str(turn.id), provider_call_id="call",
        tool_name="schema_list", raw_input={}, materialization=tools,
        policy_decision={"status": "allowed"},
    )
    repository.mark_running(lease=lease, invocation_id=invocation.id)
    db_session.get(AgentToolInvocation, invocation.id).recovery_policy = (
        recovery_policy.value
    )
    db_session.commit()

    recovered = repository.recover_interrupted(lease=lease, run_id=admission.run_id)
    db_session.commit()
    assert [item.id for item in recovered] == [invocation.id]
    assert db_session.get(AgentToolInvocation, invocation.id).status == "requested"


def test_run_cancellation_terminalizes_a_running_tool_invocation(
    db_session,
    test_datasource,
    monkeypatch,
) -> None:
    canceled: list[str] = []

    def fake_cancel(execution_id: str) -> dict[str, object]:
        canceled.append(execution_id)
        return {
            "success": True,
            "cancelled": True,
            "executionId": execution_id,
            "message": "mocked",
        }

    monkeypatch.setattr(
        "engine.agent.repositories.tool.QUERY_REGISTRY.cancel",
        fake_cancel,
    )

    db_session.add(
        AgentSession(
            id="session_cancel_tool",
            datasource_id=str(test_datasource.id),
            title="Cancel Tool",
        )
    )
    db_session.commit()
    sessions = SessionRepository(db_session)
    admission = sessions.admit(
        session_id="session_cancel_tool",
        datasource_id=str(test_datasource.id),
        datasource_generation=1,
        content="查看表",
        idempotency_key="request_cancel_tool",
        llm_credential_id="credential_1",
        api_base=None,
        model_name="model-test",
        request_payload={},
    )
    lease = sessions.claim(session_id="session_cancel_tool", owner="worker")
    assert lease is not None
    sessions.promote_next_input(lease=lease)
    tools = materialize_tools(
        register_dbfox_tools(),
        allowed_groups={"catalog"},
        execution_mode="user_requested_read",
    )
    turn = sessions.start_turn(
        lease=lease,
        run_id=admission.run_id,
        agent_definition_version="1",
        prompt_version="1",
        prompt_hash="prompt",
        context_snapshot={},
        context_hash="context",
        tool_materialization=tools.model_dump(mode="json"),
        tool_materialization_hash=tools.hash,
        provider="test",
        model_name="test",
    )
    repository = ToolInvocationRepository(db_session)
    invocation = repository.request(
        lease=lease,
        run_id=admission.run_id,
        turn_id=str(turn.id),
        provider_call_id="cancel-call",
        tool_name="schema_list",
        raw_input={},
        materialization=tools,
        policy_decision={"status": "allowed"},
    )
    repository.mark_running(lease=lease, invocation_id=invocation.id)

    observations = repository.cancel_active_for_run(
        lease=lease,
        run_id=admission.run_id,
    )
    db_session.commit()

    assert [item.status for item in observations] == [ObservationStatus.CANCELLED]
    assert db_session.get(AgentToolInvocation, invocation.id).status == "cancelled"
    observation = db_session.query(AgentObservationRecord).filter_by(
        tool_invocation_id=invocation.id
    ).one()
    assert observation.status == "cancelled"
    assert observation.error_code == "TOOL_CANCELLED"
    assert canceled == [invocation.id]
