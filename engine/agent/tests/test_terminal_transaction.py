from uuid import uuid4
from datetime import UTC, datetime
import json

import pytest

from engine.agent.artifact import ArtifactSelectionSuggestion, ArtifactType
from engine.agent.evidence import Evidence, EvidenceLocator
from engine.agent.repositories.artifact import ArtifactRepository
from engine.agent.repositories.run import RunRepository
from engine.agent.repositories.session import SessionRepository
from engine.agent.response import AnswerCandidate, CompletionDisposition, ResponseComposer
from engine.models import AgentEvidenceRecord, AgentMessage, AgentRun, AgentSession, AgentSessionMemory


def test_answer_evidence_memory_and_terminal_state_commit_together(db_session, test_datasource):
    db_session.add(AgentSession(id="session_terminal", datasource_id=str(test_datasource.id), title="Terminal"))
    db_session.commit()
    sessions = SessionRepository(db_session)
    admission = sessions.admit(
        session_id="session_terminal", datasource_id=str(test_datasource.id), datasource_generation=1,
        content="统计订单", idempotency_key="terminal", llm_credential_id="credential",
        api_base=None, model_name="model", request_payload={},
    )
    lease = sessions.claim(session_id="session_terminal", owner="worker")
    sessions.promote_next_input(lease=lease)
    turn = sessions.start_turn(
        lease=lease, run_id=admission.run_id, agent_definition_version="1", prompt_version="1",
        prompt_hash="prompt", context_snapshot={}, context_hash="context",
        tool_materialization={}, tool_materialization_hash="tools", provider="test", model_name="test",
    )
    artifact = ArtifactRepository(db_session).create(
        lease=lease, run_id=admission.run_id, turn_id=str(turn.id),
        artifact_type=ArtifactType.RESULT_VIEW, title="订单数", payload={"rowCount": 1},
    )
    evidence = Evidence(
        id=f"evidence_{uuid4().hex}", session_id="session_terminal", run_id=admission.run_id,
        claim_id="claim_total", artifact_id=artifact.id, label="订单数 42",
        query_fingerprint="fingerprint_total", observed_at=datetime.now(UTC),
        locator=EvidenceLocator(kind="metric", value={"column": "count"}), value=42,
    )
    answer = AnswerCandidate(text="共有 42 条订单。", evidence=[evidence])
    response = ResponseComposer().compose(
        session_id="session_terminal", run_id=admission.run_id,
        completion_disposition=CompletionDisposition.COMPLETE, limitation_codes=[], answer=answer,
        artifacts=[artifact], selection_suggestion=ArtifactSelectionSuggestion(
            artifact_id=artifact.id, reason="首个主要查询结果"
        ),
    )
    RunRepository(db_session).complete(lease=lease, response=response)
    db_session.commit()

    assert db_session.get(AgentRun, admission.run_id).status == "completed"
    assert db_session.get(AgentMessage, admission.assistant_message_id).content == "共有 42 条订单。"
    assert db_session.get(AgentEvidenceRecord, evidence.id).artifact_id == artifact.id
    memory_row = db_session.query(AgentSessionMemory).filter_by(session_id="session_terminal").one()
    memory = json.loads(memory_row.memory_json)
    assert memory["recent_runs"][0]["run_id"] == admission.run_id
    assert memory["working_set"]["referenced_artifact_ids"] == [artifact.id]
    assert "rows" not in memory_row.memory_json
    assert db_session.get(AgentSession, "session_terminal").selected_artifact_id == artifact.id


def test_terminal_transaction_rolls_back_as_a_unit(db_session, test_datasource):
    # A foreign-key failure in Evidence must not leave a completed Run or answer.
    db_session.add(AgentSession(id="session_rollback", datasource_id=str(test_datasource.id), title="Rollback"))
    db_session.commit()
    sessions = SessionRepository(db_session)
    admission = sessions.admit(
        session_id="session_rollback", datasource_id=str(test_datasource.id), datasource_generation=1,
        content="test", idempotency_key="rollback", llm_credential_id="credential",
        api_base=None, model_name="model", request_payload={},
    )
    lease = sessions.claim(session_id="session_rollback", owner="worker")
    sessions.promote_next_input(lease=lease)
    db_session.commit()
    invalid = Evidence(
        id="evidence_invalid", session_id="session_rollback", run_id=admission.run_id,
        claim_id="claim", artifact_id="artifact_missing", label="invalid",
        query_fingerprint="fingerprint_invalid", observed_at=datetime.now(UTC),
    )
    # Bypass Composer deliberately to prove the database transaction boundary.
    from engine.agent.response import ComposedResponse
    response = ComposedResponse(
        session_id="session_rollback", run_id=admission.run_id,
        completion_disposition=CompletionDisposition.COMPLETE, limitation_codes=[],
        answer=AnswerCandidate(text="must rollback", evidence=[invalid]), artifacts=[],
        referenced_artifact_ids=[],
    )
    with pytest.raises(Exception):
        RunRepository(db_session).complete(lease=lease, response=response)
        db_session.commit()
    db_session.rollback()
    assert db_session.get(AgentRun, admission.run_id).status == "running"
    assert db_session.get(AgentMessage, admission.assistant_message_id).content == ""


def test_interrupted_model_turn_is_closed_before_run_recovery(db_session, test_datasource):
    db_session.add(AgentSession(id="session_turn_recovery", datasource_id=str(test_datasource.id), title="Recovery"))
    db_session.commit()
    sessions = SessionRepository(db_session)
    admission = sessions.admit(
        session_id="session_turn_recovery", datasource_id=str(test_datasource.id), datasource_generation=1,
        content="分析趋势", idempotency_key="turn-recovery", llm_credential_id="credential",
        api_base=None, model_name="model", request_payload={},
    )
    lease = sessions.claim(session_id="session_turn_recovery", owner="worker")
    sessions.promote_next_input(lease=lease)
    turn = sessions.start_turn(
        lease=lease, run_id=admission.run_id, agent_definition_version="1", prompt_version="1",
        prompt_hash="prompt", context_snapshot={}, context_hash="context",
        tool_materialization={}, tool_materialization_hash="tools", provider="test", model_name="test",
    )
    runs = RunRepository(db_session)
    runs.merge_answer_draft(lease=lease, run_id=admission.run_id, content="未完成的半截回答")
    db_session.commit()

    assert runs.recover_interrupted_turns(lease=lease, run_id=admission.run_id) == 1
    db_session.commit()
    db_session.refresh(turn)
    message = db_session.get(AgentMessage, admission.assistant_message_id)
    assert turn.status == "failed"
    assert turn.error_code == "MODEL_STREAM_INTERRUPTED"
    assert message.content == ""
    assert message.status == "created"
