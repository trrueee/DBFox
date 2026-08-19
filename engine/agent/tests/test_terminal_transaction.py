from uuid import uuid4
from datetime import UTC, datetime
import json

import pytest

from engine.agent.artifact import (
    ArtifactRelation,
    ArtifactRelationType,
    ArtifactSelectionSuggestion,
    ArtifactType,
)
from engine.agent.evidence import Evidence, EvidenceLocator
from engine.agent.repositories.artifact import ArtifactRepository
from engine.agent.repositories.run import RunRepository
from engine.agent.repositories.session import SessionRepository
from engine.agent.response import (
    AnswerCandidate,
    CompletionDisposition,
    ResponseComposer,
)
from engine.agent.run_item import RunItemStatus
from engine.agent.session import DeliveryMode
from engine.agent.terminalizer import Terminalizer
from engine.agent.turn import ModelTurnResult, TurnAssistantMessage, TurnTermination
from engine.tools.runtime.attempt import ResourceScopeRef
from engine.models import (
    AgentEvidenceRecord,
    AgentMessage,
    AgentRun,
    AgentRunItemRecord,
    AgentSession,
    AgentSessionMemory,
)


def test_successful_terminalization_yields_to_pending_steer(
    db_session, test_datasource
) -> None:
    db_session.add(
        AgentSession(
            id="session_pending_steer",
            datasource_id=str(test_datasource.id),
            title="Pending steer",
        )
    )
    db_session.commit()
    sessions = SessionRepository(db_session)
    admission = sessions.admit(
        session_id="session_pending_steer",
        resource_refs=(ResourceScopeRef(kind="database", id=str(test_datasource.id), version=1),),
        content="先分析订单",
        idempotency_key="pending-steer-start",
        llm_credential_id="credential",
        api_base=None,
        model_name="model",
        request_payload={},
    )
    lease = sessions.claim(session_id="session_pending_steer", owner="worker")
    assert lease is not None
    sessions.promote_next_input(lease=lease)
    sessions.admit(
        session_id="session_pending_steer",
        resource_refs=(ResourceScopeRef(kind="database", id=str(test_datasource.id), version=1),),
        content="只看华东",
        idempotency_key="pending-steer-input",
        llm_credential_id="credential",
        api_base=None,
        model_name="model",
        request_payload={},
        delivery_mode=DeliveryMode.STEER,
    )
    response = ResponseComposer().compose(
        session_id="session_pending_steer",
        run_id=admission.run_id,
        completion_disposition=CompletionDisposition.COMPLETE,
        limitation_codes=[],
        answer=AnswerCandidate(text="初步完成。"),
        artifacts=[],
        selection_suggestion=None,
    )

    assert Terminalizer.complete_in_session(db_session, lease, response) is False
    db_session.commit()
    db_session.expire_all()

    run = db_session.get(AgentRun, admission.run_id)
    assert run is not None and run.status == "running"


def test_answer_evidence_memory_and_terminal_state_commit_together(
    db_session, test_datasource
):
    db_session.add(
        AgentSession(
            id="session_terminal",
            datasource_id=str(test_datasource.id),
            title="Terminal",
        )
    )
    db_session.commit()
    sessions = SessionRepository(db_session)
    admission = sessions.admit(
        session_id="session_terminal",
        resource_refs=(ResourceScopeRef(kind="database", id=str(test_datasource.id), version=1),),
        content="统计订单",
        idempotency_key="terminal",
        llm_credential_id="credential",
        api_base=None,
        model_name="model",
        request_payload={},
    )
    lease = sessions.claim(session_id="session_terminal", owner="worker")
    sessions.promote_next_input(lease=lease)
    turn = sessions.start_turn(
        lease=lease,
        run_id=admission.run_id,
        agent_definition_version="1",
        prompt_version="1",
        prompt_hash="prompt",
        context_snapshot={},
        context_hash="context",
        tool_materialization={},
        tool_materialization_hash="tools",
        provider="test",
        model_name="test",
    )
    artifacts = ArtifactRepository(db_session)
    sql_artifact = artifacts.create(
        lease=lease,
        run_id=admission.run_id,
        turn_id=str(turn.id),
        artifact_type=ArtifactType.SQL,
        title="订单统计 SQL",
        payload={
            "sql": "SELECT COUNT(*) AS count FROM orders",
            "safeSql": "SELECT COUNT(*) AS count FROM orders",
            "dialect": "sqlite",
            "queryFingerprint": "fingerprint_total",
        },
    )
    artifact = artifacts.create(
        lease=lease,
        run_id=admission.run_id,
        turn_id=str(turn.id),
        artifact_type=ArtifactType.RESULT_VIEW,
        title="订单数",
        payload={
            "sourceSqlArtifactId": sql_artifact.id,
            "queryFingerprint": "fingerprint_total",
            "datasourceGeneration": 1,
            "columns": [{"name": "count", "type": "integer"}],
            "rowCount": 1,
            "returnedRows": 1,
            "latencyMs": 1,
            "executedAt": datetime.now(UTC).isoformat(),
            "truncated": False,
        },
        relations=[
            ArtifactRelation(
                relation=ArtifactRelationType.DERIVED_FROM,
                artifact_id=sql_artifact.id,
            )
        ],
    )
    evidence = Evidence(
        id=f"evidence_{uuid4().hex}",
        session_id="session_terminal",
        run_id=admission.run_id,
        claim_id="claim_total",
        artifact_id=artifact.id,
        label="订单数 42",
        query_fingerprint="fingerprint_total",
        observed_at=datetime.now(UTC),
        locator=EvidenceLocator(kind="metric", value={"column": "count"}),
        value=42,
    )
    answer = AnswerCandidate(text="共有 42 条订单。", evidence=[evidence])
    response = ResponseComposer().compose(
        session_id="session_terminal",
        run_id=admission.run_id,
        completion_disposition=CompletionDisposition.COMPLETE,
        limitation_codes=[],
        answer=answer,
        artifacts=[artifact],
        selection_suggestion=ArtifactSelectionSuggestion(
            artifact_id=artifact.id, reason="首个主要查询结果"
        ),
    )
    evidence_reference = {
        "evidence_id": evidence.id,
        "artifact_id": artifact.id,
        "query_fingerprint": evidence.query_fingerprint,
        "observed_at": evidence.observed_at.isoformat(),
        "run_id": admission.run_id,
    }
    db_session.add(
        AgentSessionMemory(
            id="memory_from_old_generation",
            session_id="session_terminal",
            datasource_id=str(test_datasource.id),
            memory_json=json.dumps(
                {
                    "version": 1,
                    "datasource_id": str(test_datasource.id),
                    "datasource_generation": 0,
                    "recent_runs": [
                        {
                            "run_id": "stale-run",
                            "datasource_id": str(test_datasource.id),
                            "datasource_generation": 0,
                        }
                    ],
                    "stable_context": {"database_name": "stale_database"},
                }
            ),
        )
    )
    db_session.flush()
    RunRepository(db_session).complete(
        lease=lease,
        response=response,
        memory_delta={"evidence_references": [evidence_reference]},
    )
    db_session.commit()

    assert db_session.get(AgentRun, admission.run_id).status == "completed"
    assert (
        db_session.get(AgentMessage, admission.assistant_message_id).content
        == "共有 42 条订单。"
    )
    assert db_session.get(AgentEvidenceRecord, evidence.id).artifact_id == artifact.id
    memory_row = (
        db_session.query(AgentSessionMemory)
        .filter_by(session_id="session_terminal")
        .one()
    )
    memory = json.loads(memory_row.memory_json)
    assert memory["version"] == 3
    assert "recent_runs" not in memory
    assert memory["working_set"]["referenced_artifact_ids"] == [artifact.id]
    stored_reference = memory["stable_context"]["evidence_references"][0]
    assert {
        key: stored_reference[key] for key in evidence_reference
    } == evidence_reference
    assert "claim" not in stored_reference
    assert stored_reference["datasource_id"] == str(test_datasource.id)
    assert stored_reference["datasource_generation"] == 1
    assert "verified_claims" not in memory["stable_context"]
    assert "database_name" not in memory["stable_context"]
    assert "rows" not in memory_row.memory_json
    assert memory_row.memory_v4_json
    memory_v4 = json.loads(memory_row.memory_v4_json)
    assert memory_v4["schema_version"] == 4
    catalog_projection = next(
        item
        for item in memory_v4["projections"]
        if item["projection_id"] == "dbfox.catalog.working_state"
    )
    assert catalog_projection["projected_through_session_sequence"] == 1
    assert catalog_projection["state_hash"]
    assert (
        db_session.get(AgentSession, "session_terminal").selected_artifact_id
        == artifact.id
    )


def test_terminal_transaction_rolls_back_as_a_unit(db_session, test_datasource):
    # A foreign-key failure in Evidence must not leave a completed Run or answer.
    db_session.add(
        AgentSession(
            id="session_rollback",
            datasource_id=str(test_datasource.id),
            title="Rollback",
        )
    )
    db_session.commit()
    sessions = SessionRepository(db_session)
    admission = sessions.admit(
        session_id="session_rollback",
        resource_refs=(ResourceScopeRef(kind="database", id=str(test_datasource.id), version=1),),
        content="test",
        idempotency_key="rollback",
        llm_credential_id="credential",
        api_base=None,
        model_name="model",
        request_payload={},
    )
    lease = sessions.claim(session_id="session_rollback", owner="worker")
    sessions.promote_next_input(lease=lease)
    db_session.commit()
    invalid = Evidence(
        id="evidence_invalid",
        session_id="session_rollback",
        run_id=admission.run_id,
        claim_id="claim",
        artifact_id="artifact_missing",
        label="invalid",
        query_fingerprint="fingerprint_invalid",
        observed_at=datetime.now(UTC),
    )
    # Bypass Composer deliberately to prove the database transaction boundary.
    from engine.agent.response import ComposedResponse

    response = ComposedResponse(
        session_id="session_rollback",
        run_id=admission.run_id,
        completion_disposition=CompletionDisposition.COMPLETE,
        limitation_codes=[],
        answer=AnswerCandidate(text="must rollback", evidence=[invalid]),
        artifacts=[],
        referenced_artifact_ids=[],
    )
    with pytest.raises(Exception):
        RunRepository(db_session).complete(lease=lease, response=response)
        db_session.commit()
    db_session.rollback()
    assert db_session.get(AgentRun, admission.run_id).status == "running"
    assert db_session.get(AgentMessage, admission.assistant_message_id).content == ""


def test_terminal_response_uses_the_answer_candidates_own_turn(
    db_session,
    test_datasource,
):
    db_session.add(
        AgentSession(
            id="session_cross_turn_terminal",
            datasource_id=str(test_datasource.id),
            title="Cross-turn terminal",
        )
    )
    db_session.commit()
    sessions = SessionRepository(db_session)
    admission = sessions.admit(
        session_id="session_cross_turn_terminal",
        resource_refs=(ResourceScopeRef(kind="database", id=str(test_datasource.id), version=1),),
        content="保留早期答案",
        idempotency_key="cross-turn-terminal",
        llm_credential_id="credential",
        api_base=None,
        model_name="model",
        request_payload={},
    )
    lease = sessions.claim(session_id="session_cross_turn_terminal", owner="worker")
    assert lease is not None
    sessions.promote_next_input(lease=lease)
    first_turn = sessions.start_turn(
        lease=lease,
        run_id=admission.run_id,
        agent_definition_version="1",
        prompt_version="1",
        prompt_hash="prompt-1",
        context_snapshot={},
        context_hash="context-1",
        tool_materialization={},
        tool_materialization_hash="tools-1",
        provider="test",
        model_name="test",
    )
    runs = RunRepository(db_session)
    runs.persist_turn_message(
        lease=lease,
        run_id=admission.run_id,
        turn_id=str(first_turn.id),
        output_index=0,
        revision=1,
        phase=None,
        content="早期轮最终答案",
        status=RunItemStatus.COMPLETED,
    )
    first_result = ModelTurnResult(
        turn_id=str(first_turn.id),
        messages=[
            TurnAssistantMessage(
                item_id="provider-message-1",
                output_index=0,
                phase=None,
                status="completed",
                text="早期轮最终答案",
            )
        ],
        termination=TurnTermination.COMPLETED,
    )
    runs.settle_turn(lease=lease, turn_id=str(first_turn.id), result=first_result)
    second_turn = sessions.start_turn(
        lease=lease,
        run_id=admission.run_id,
        agent_definition_version="1",
        prompt_version="1",
        prompt_hash="prompt-2",
        context_snapshot={},
        context_hash="context-2",
        tool_materialization={},
        tool_materialization_hash="tools-2",
        provider="test",
        model_name="test",
    )
    assert str(second_turn.id) != str(first_turn.id)

    response = ResponseComposer().compose(
        session_id="session_cross_turn_terminal",
        run_id=admission.run_id,
        completion_disposition=CompletionDisposition.BOUNDED_PARTIAL,
        limitation_codes=["TURN_BUDGET_REACHED"],
        answer=AnswerCandidate(text="早期轮最终答案", evidence=[]),
        artifacts=[],
        selection_suggestion=None,
    )
    runs.complete(
        lease=lease,
        response=response,
        terminal_turn_id=first_result.turn_id,
        terminal_output_index=0,
    )
    db_session.commit()

    record = db_session.get(
        AgentRunItemRecord,
        f"message:{admission.run_id}:{first_turn.id}:0",
    )
    assert record is not None
    item = json.loads(str(record.item_json))
    assert item["turn_id"] == str(first_turn.id)
    assert item["payload"]["content"] == "早期轮最终答案"
    assert db_session.get(AgentRun, admission.run_id).status == "completed"


def test_interrupted_model_turn_is_closed_before_run_recovery(
    db_session, test_datasource
):
    db_session.add(
        AgentSession(
            id="session_turn_recovery",
            datasource_id=str(test_datasource.id),
            title="Recovery",
        )
    )
    db_session.commit()
    sessions = SessionRepository(db_session)
    admission = sessions.admit(
        session_id="session_turn_recovery",
        resource_refs=(ResourceScopeRef(kind="database", id=str(test_datasource.id), version=1),),
        content="分析趋势",
        idempotency_key="turn-recovery",
        llm_credential_id="credential",
        api_base=None,
        model_name="model",
        request_payload={},
    )
    lease = sessions.claim(session_id="session_turn_recovery", owner="worker")
    sessions.promote_next_input(lease=lease)
    turn = sessions.start_turn(
        lease=lease,
        run_id=admission.run_id,
        agent_definition_version="1",
        prompt_version="1",
        prompt_hash="prompt",
        context_snapshot={},
        context_hash="context",
        tool_materialization={},
        tool_materialization_hash="tools",
        provider="test",
        model_name="test",
    )
    runs = RunRepository(db_session)
    item_id = runs.persist_turn_message(
        lease=lease,
        run_id=admission.run_id,
        turn_id=str(turn.id),
        output_index=0,
        revision=1,
        content="未完成的半截回答",
        phase="final_answer",
        status=RunItemStatus.IN_PROGRESS,
    )
    db_session.commit()

    assert runs.recover_interrupted_turns(lease=lease, run_id=admission.run_id) == 1
    db_session.commit()
    db_session.refresh(turn)
    message = db_session.get(AgentMessage, admission.assistant_message_id)
    assert turn.status == "failed"
    assert turn.error_code == "MODEL_STREAM_INTERRUPTED"
    recovered_item = db_session.get(AgentRunItemRecord, item_id)
    assert recovered_item.status == RunItemStatus.CANCELLED.value
    assert message.content == ""
    assert message.status == "created"
