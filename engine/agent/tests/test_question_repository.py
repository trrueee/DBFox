from __future__ import annotations

import json

import pytest

from engine.agent.question import QuestionAnswer, QuestionConflict, QuestionStatus
from engine.agent.context import ContextAssembler
from engine.agent.repositories.question import QuestionRepository
from engine.agent.repositories.session import SessionRepository
from engine.agent.run import SessionLeaseConflict
from engine.models import (
    AgentMessage,
    AgentQuestionRequest,
    AgentRun,
    AgentSession,
    AgentSessionInput,
    AgentToolInvocation,
)


def _waiting_question_invocation(
    db_session,
    *,
    session_id: str,
    run_id: str,
    turn_id: str,
    suffix: str,
) -> AgentToolInvocation:
    invocation = AgentToolInvocation(
        id=f"invocation_{suffix}",
        session_id=session_id,
        run_id=run_id,
        turn_id=turn_id,
        provider_call_id=f"call_{suffix}",
        tool_name="request_clarification",
        tool_version="1.0.0",
        input_json="{}",
        input_hash=f"input_{suffix}",
        idempotency_key=f"idempotency_{suffix}",
        status="waiting_input",
        policy_json='{"status":"allowed"}',
        presentation_json=json.dumps(
            {
                "title": "请求补充信息",
                "category": "manage",
                "visibility": "details",
                "progress": "none",
            }
        ),
        recovery_policy="retry_safe",
        attempt_count=0,
    )
    db_session.add(invocation)
    db_session.flush()
    return invocation


def test_question_persists_user_response_and_resumes_original_run_once(
    db_session, test_datasource
) -> None:
    db_session.add(AgentSession(
        id="session_question", datasource_id=str(test_datasource.id), title="Question"
    ))
    db_session.commit()
    sessions = SessionRepository(db_session)
    admission = sessions.admit(
        session_id="session_question",
        datasource_id=str(test_datasource.id),
        datasource_generation=1,
        content="统计收入",
        idempotency_key="question-start",
        llm_credential_id="credential",
        api_base=None,
        model_name="model",
        request_payload={},
    )
    lease = sessions.claim(session_id="session_question", owner="worker")
    assert lease is not None
    sessions.promote_next_input(lease=lease)
    turn = sessions.start_turn(
        lease=lease,
        run_id=admission.run_id,
        agent_definition_version="1",
        prompt_version="1",
        prompt_hash="prompt",
        context_snapshot={},
        context_hash="context",
        tool_materialization={"tools": []},
        tool_materialization_hash="tools",
        provider="test",
        model_name="test",
    )
    invocation = _waiting_question_invocation(
        db_session,
        session_id=lease.session_id,
        run_id=admission.run_id,
        turn_id=str(turn.id),
        suffix="question",
    )
    turn.status = "completed"
    turn.response_items_json = json.dumps(
        [
            {
                "type": "function_call",
                "call_id": str(invocation.provider_call_id),
                "name": "request_clarification",
                "arguments": "{}",
            }
        ]
    )
    question = QuestionRepository(db_session).request(
        lease=lease,
        run_id=admission.run_id,
        turn_id=str(turn.id),
        tool_invocation_id=str(invocation.id),
        question="收入按自然月还是财务月统计？",
        reason="两种口径会产生不同结果",
        options=[
            {"value": "calendar", "label": "自然月"},
            {"value": "fiscal", "label": "财务月"},
        ],
        allow_free_text=False,
    )
    sessions.release(lease=lease)
    db_session.commit()

    assert db_session.get(AgentRun, admission.run_id).status == "waiting_input"
    resolved = QuestionRepository(db_session).resolve(
        question_id=question.id,
        expected_version=0,
        answer=QuestionAnswer(selected_value="calendar"),
        actor="user",
    )
    db_session.commit()

    assert resolved.status is QuestionStatus.ANSWERED
    assert db_session.get(AgentRun, admission.run_id).status == "running"
    row = db_session.get(AgentQuestionRequest, question.id)
    response = db_session.get(AgentMessage, row.response_message_id)
    assert response.content == "自然月"
    stored_input = db_session.query(AgentSessionInput).filter_by(
        reply_to_request_id=question.id
    ).one()
    assert stored_input.run_id == admission.run_id
    assert stored_input.status == "consumed"
    context = ContextAssembler(db_session).build(admission.run_id)
    assert context.messages == []
    assert context.current_request == "统计收入"
    response_items = context.response_batches[0].items
    assert [item["type"] for item in response_items] == [
        "function_call",
        "function_call_output",
    ]
    assert {
        item["call_id"] for item in response_items
    } == {"call_question"}

    with pytest.raises(QuestionConflict):
        QuestionRepository(db_session).resolve(
            question_id=question.id,
            expected_version=0,
            answer=QuestionAnswer(selected_value="fiscal"),
            actor="user",
        )


def test_expired_question_terminalizes_the_waiting_run(db_session, test_datasource) -> None:
    db_session.add(AgentSession(
        id="session_expired_question",
        datasource_id=str(test_datasource.id),
        title="Expired question",
    ))
    db_session.commit()
    sessions = SessionRepository(db_session)
    admission = sessions.admit(
        session_id="session_expired_question",
        datasource_id=str(test_datasource.id),
        datasource_generation=1,
        content="统计收入",
        idempotency_key="expired-question",
        llm_credential_id="credential",
        api_base=None,
        model_name="model",
        request_payload={},
    )
    lease = sessions.claim(session_id="session_expired_question", owner="worker")
    sessions.promote_next_input(lease=lease)
    turn = sessions.start_turn(
        lease=lease,
        run_id=admission.run_id,
        agent_definition_version="1",
        prompt_version="1",
        prompt_hash="prompt",
        context_snapshot={},
        context_hash="context",
        tool_materialization={"tools": []},
        tool_materialization_hash="tools",
        provider="test",
        model_name="test",
    )
    invocation = _waiting_question_invocation(
        db_session,
        session_id=lease.session_id,
        run_id=admission.run_id,
        turn_id=str(turn.id),
        suffix="expired_question",
    )
    question = QuestionRepository(db_session).request(
        lease=lease,
        run_id=admission.run_id,
        turn_id=str(turn.id),
        tool_invocation_id=str(invocation.id),
        question="收入按自然月还是财务月统计？",
        reason="两种口径会产生不同结果",
        options=[{"value": "calendar", "label": "自然月"}],
        allow_free_text=False,
        expires_in_seconds=-1,
    )
    sessions.release(lease=lease)
    db_session.commit()

    stale_lease = sessions.claim(session_id="session_expired_question", owner="recovery")
    sessions.release(lease=stale_lease)
    recovery_lease = sessions.claim(session_id="session_expired_question", owner="replacement")
    db_session.commit()
    with pytest.raises(SessionLeaseConflict):
        QuestionRepository(db_session).expire_pending(lease=stale_lease)
    db_session.rollback()
    expired = QuestionRepository(db_session).expire_pending(lease=recovery_lease)
    db_session.commit()

    assert [item.id for item in expired] == [question.id]
    assert db_session.get(AgentQuestionRequest, question.id).status == QuestionStatus.EXPIRED.value
    run = db_session.get(AgentRun, admission.run_id)
    assert run.status == "failed"
    assert run.error_code == "AGENT_QUESTION_EXPIRED"
    assert db_session.get(AgentToolInvocation, invocation.id).status == "failed"
