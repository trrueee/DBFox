from __future__ import annotations

from engine.agent.observation import ObservationStatus
from engine.agent.repositories.session import SessionRepository
from engine.agent.repositories.tool import ToolInvocationRepository
from engine.agent.tool import ToolInvocationStatus
from engine.models import AgentSession, AgentToolInvocation
from engine.tools.dbfox_tools import register_dbfox_tools
from engine.tools.materialization import materialize_tools


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
    tools = materialize_tools(registry, allowed_groups={"schema"}, execution_mode="user_requested_read")
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
        tool_name="schema.list_tables",
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
    db_session.commit()

    assert observation.tool_invocation_id == invocation.id
    assert observation.facts == {"table_count": 3}
    assert db_session.get(AgentToolInvocation, invocation.id).status == ToolInvocationStatus.SUCCEEDED.value


def test_interrupted_retry_safe_tool_is_requeued_with_the_same_invocation_id(
    db_session, test_datasource
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
        register_dbfox_tools(), allowed_groups={"schema"}, execution_mode="user_requested_read"
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
        tool_name="schema.list_tables", raw_input={}, materialization=tools,
        policy_decision={"status": "allowed"},
    )
    repository.mark_running(lease=lease, invocation_id=invocation.id)
    db_session.commit()

    recovered = repository.recover_interrupted(lease=lease, run_id=admission.run_id)
    db_session.commit()
    assert [item.id for item in recovered] == [invocation.id]
    assert db_session.get(AgentToolInvocation, invocation.id).status == "requested"
