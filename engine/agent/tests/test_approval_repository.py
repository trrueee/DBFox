from datetime import timedelta

import pytest

from engine.agent.approval import ApprovalConflict, ApprovalStatus
from engine.agent.repositories.approval import ApprovalRepository
from engine.agent.repositories.session import SessionRepository
from engine.agent.repositories.tool import ToolInvocationRepository
from engine.agent.tool import ToolInvocationStatus
from engine.models import AgentApproval, AgentRun, AgentSession, AgentSessionInput, AgentToolInvocation
from engine.models import AgentObservationRecord
from engine.tools.dbfox_tools import register_dbfox_tools
from engine.tools.materialization import materialize_tools


def test_approval_resolves_once_and_resumes_exact_invocation(db_session, test_datasource):
    db_session.add(AgentSession(id="session_approval", datasource_id=str(test_datasource.id), title="Approval"))
    db_session.commit()
    sessions = SessionRepository(db_session)
    admission = sessions.admit(
        session_id="session_approval", datasource_id=str(test_datasource.id), datasource_generation=1,
        content="执行查询", idempotency_key="approval", llm_credential_id="credential",
        api_base=None, model_name="model", request_payload={},
    )
    lease = sessions.claim(session_id="session_approval", owner="worker")
    sessions.promote_next_input(lease=lease)
    tools = materialize_tools(
        register_dbfox_tools(), allowed_groups={"sql"}, execution_mode="agent_autonomous_read"
    )
    turn = sessions.start_turn(
        lease=lease, run_id=admission.run_id, agent_definition_version="1", prompt_version="1",
        prompt_hash="prompt", context_snapshot={}, context_hash="context",
        tool_materialization=tools.model_dump(mode="json"), tool_materialization_hash=tools.hash,
        provider="test", model_name="test",
    )
    invocation = ToolInvocationRepository(db_session).request(
        lease=lease, run_id=admission.run_id, turn_id=str(turn.id), provider_call_id="call",
        tool_name="sql.execute_readonly", raw_input={}, materialization=tools,
        policy_decision={"status": "approval_required", "reason": "生产只读查询", "risk_level": "warning"},
    )
    approval = ApprovalRepository(db_session).request(
        lease=lease, invocation_id=invocation.id,
        policy_decision={"status": "approval_required", "reason": "生产只读查询", "risk_level": "warning"},
    )
    sessions.release(lease=lease)
    db_session.commit()

    resolved = ApprovalRepository(db_session).resolve(
        approval_id=approval.id, expected_version=0, approved=True, actor="user",
    )
    db_session.commit()
    assert resolved.status is ApprovalStatus.APPROVED
    assert db_session.get(AgentToolInvocation, invocation.id).status == ToolInvocationStatus.REQUESTED.value
    assert db_session.get(AgentRun, admission.run_id).status == "running"

    with pytest.raises(ApprovalConflict):
        ApprovalRepository(db_session).resolve(
            approval_id=approval.id, expected_version=0, approved=True, actor="user",
        )


def test_rejected_approval_becomes_a_model_visible_observation(db_session, test_datasource):
    db_session.add(AgentSession(id="session_rejection", datasource_id=str(test_datasource.id), title="Reject"))
    db_session.commit()
    sessions = SessionRepository(db_session)
    admission = sessions.admit(
        session_id="session_rejection", datasource_id=str(test_datasource.id), datasource_generation=1,
        content="执行查询", idempotency_key="rejection", llm_credential_id="credential",
        api_base=None, model_name="model", request_payload={},
    )
    lease = sessions.claim(session_id="session_rejection", owner="worker")
    sessions.promote_next_input(lease=lease)
    tools = materialize_tools(register_dbfox_tools(), allowed_groups={"sql"}, execution_mode="agent_autonomous_read")
    turn = sessions.start_turn(
        lease=lease, run_id=admission.run_id, agent_definition_version="1", prompt_version="1",
        prompt_hash="prompt", context_snapshot={}, context_hash="context",
        tool_materialization=tools.model_dump(mode="json"), tool_materialization_hash=tools.hash,
        provider="test", model_name="test",
    )
    invocation = ToolInvocationRepository(db_session).request(
        lease=lease, run_id=admission.run_id, turn_id=str(turn.id), provider_call_id="call",
        tool_name="sql.execute_readonly", raw_input={}, materialization=tools,
        policy_decision={"status": "approval_required", "reason": "需要确认", "risk_level": "warning"},
    )
    approval = ApprovalRepository(db_session).request(
        lease=lease, invocation_id=invocation.id,
        policy_decision={"status": "approval_required", "reason": "需要确认", "risk_level": "warning"},
    )
    sessions.release(lease=lease)
    db_session.commit()

    ApprovalRepository(db_session).resolve(
        approval_id=approval.id, expected_version=0, approved=False, actor="user",
    )
    db_session.commit()
    observation = db_session.query(AgentObservationRecord).filter_by(
        tool_invocation_id=invocation.id
    ).one()
    assert observation.status == "rejected"
    assert observation.error_code == "APPROVAL_REJECTED"


def test_exact_rejected_action_requires_new_formal_input_before_reapproval(db_session, test_datasource):
    db_session.add(AgentSession(id="session_repeat_rejection", datasource_id=str(test_datasource.id), title="Reject"))
    db_session.commit()
    sessions = SessionRepository(db_session)
    admission = sessions.admit(
        session_id="session_repeat_rejection", datasource_id=str(test_datasource.id), datasource_generation=1,
        content="执行查询", idempotency_key="repeat-rejection", llm_credential_id="credential",
        api_base=None, model_name="model", request_payload={},
    )
    lease = sessions.claim(session_id="session_repeat_rejection", owner="worker")
    sessions.promote_next_input(lease=lease)
    tools = materialize_tools(register_dbfox_tools(), allowed_groups={"sql"}, execution_mode="agent_autonomous_read")
    turn = sessions.start_turn(
        lease=lease, run_id=admission.run_id, agent_definition_version="1", prompt_version="1",
        prompt_hash="prompt", context_snapshot={}, context_hash="context",
        tool_materialization=tools.model_dump(mode="json"), tool_materialization_hash=tools.hash,
        provider="test", model_name="test",
    )
    invocation = ToolInvocationRepository(db_session).request(
        lease=lease, run_id=admission.run_id, turn_id=str(turn.id), provider_call_id="call",
        tool_name="sql.execute_readonly", raw_input={}, materialization=tools,
        policy_decision={"status": "approval_required", "safe_args": {}, "reason": "需要确认"},
    )
    approval = ApprovalRepository(db_session).request(
        lease=lease, invocation_id=invocation.id,
        policy_decision={"status": "approval_required", "safe_args": {}, "reason": "需要确认"},
    )
    sessions.release(lease=lease)
    db_session.commit()
    ApprovalRepository(db_session).resolve(
        approval_id=approval.id, expected_version=0, approved=False, actor="user",
    )
    db_session.commit()

    repository = ApprovalRepository(db_session)
    assert repository.was_rejected_without_new_input(
        run_id=admission.run_id,
        tool_name=invocation.tool_name,
        input_hash=invocation.authorized_input_hash,
    ) is True

    rejected_at = db_session.get(AgentApproval, approval.id).decided_at
    db_session.add(AgentSessionInput(
        id="input_redirect", session_id="session_repeat_rejection", run_id=admission.run_id,
        sequence=2, idempotency_key="redirect", content="改用安全方案", delivery_mode="steer",
        status="admitted", admitted_at=rejected_at + timedelta(microseconds=1),
    ))
    db_session.commit()
    assert repository.was_rejected_without_new_input(
        run_id=admission.run_id,
        tool_name=invocation.tool_name,
        input_hash=invocation.authorized_input_hash,
    ) is False
