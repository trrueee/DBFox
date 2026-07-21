from __future__ import annotations

import pytest

from engine.agent.question import QuestionAnswer, QuestionConflict, QuestionStatus
from engine.agent.context import ContextAssembler
from engine.agent.repositories.question import QuestionRepository
from engine.agent.repositories.session import SessionRepository
from engine.models import AgentMessage, AgentQuestionRequest, AgentRun, AgentSession, AgentSessionInput


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
    question = QuestionRepository(db_session).request(
        lease=lease,
        run_id=admission.run_id,
        turn_id=str(turn.id),
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
    assert [message["content"] for message in ContextAssembler(db_session).build(admission.run_id).messages] == [
        "统计收入",
        "自然月",
    ]

    with pytest.raises(QuestionConflict):
        QuestionRepository(db_session).resolve(
            question_id=question.id,
            expected_version=0,
            answer=QuestionAnswer(selected_value="fiscal"),
            actor="user",
        )
