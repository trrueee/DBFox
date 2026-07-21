from __future__ import annotations

import json

from engine.agent.context import ContextAssembler
from engine.agent.repositories.session import SessionRepository
from engine.agent.session import DeliveryMode
from engine.models import AgentArtifactRecord, AgentMessage, AgentRun, AgentSession


def test_next_run_reads_durable_history_and_selected_artifact(db_session, test_datasource) -> None:
    db_session.add(AgentSession(id="session_context", datasource_id=str(test_datasource.id), title="Context"))
    db_session.commit()
    repository = SessionRepository(db_session)
    first = repository.admit(
        session_id="session_context",
        datasource_id=str(test_datasource.id),
        datasource_generation=1,
        content="统计订单数量",
        idempotency_key="first",
        llm_credential_id="credential",
        api_base="https://api.example.test/v1",
        model_name="model",
        request_payload={},
    )
    assistant = db_session.get(AgentMessage, first.assistant_message_id)
    assistant.content = "共有 42 条订单。"
    assistant.status = "completed"
    artifact = AgentArtifactRecord(
        id="artifact_result_42",
        run_id=first.run_id,
        session_id="session_context",
        message_id=first.assistant_message_id,
        semantic_id="orders-count",
        type="result_view",
        title="订单数量",
        payload_json=json.dumps({
            "sourceSqlArtifactId": "artifact_sql_42",
            "queryFingerprint": "query-42",
            "rowCount": 1,
            "previewRows": [{"secret": "sensitive-cell-value"}],
        }),
        presentation_json="{}",
        refs_json="{}",
        provenance_json="{}",
        relations_json="[]",
        status="completed",
        sequence=1,
    )
    db_session.add(artifact)
    aggregate = db_session.get(AgentSession, "session_context")
    aggregate.selected_artifact_id = artifact.id
    db_session.commit()

    second = repository.admit(
        session_id="session_context",
        datasource_id=str(test_datasource.id),
        datasource_generation=1,
        content="按地区拆分刚才结果",
        idempotency_key="second",
        llm_credential_id="credential",
        api_base="https://api.example.test/v1",
        model_name="model",
        request_payload={},
        selected_artifact_ids=[artifact.id],
    )
    db_session.commit()

    snapshot = ContextAssembler(db_session).build(second.run_id)

    assert [message["content"] for message in snapshot.messages] == [
        "统计订单数量",
        "共有 42 条订单。",
        "按地区拆分刚才结果",
    ]
    assert snapshot.selected_artifacts[0].id == artifact.id
    assert snapshot.selected_artifacts[0].descriptor == {
        "sourceSqlArtifactId": "artifact_sql_42",
        "queryFingerprint": "query-42",
        "rowCount": 1,
    }
    assert "sensitive-cell-value" not in json.dumps(snapshot.model_dump(mode="json"))
    assert snapshot.hash == ContextAssembler(db_session).build(second.run_id).hash


def test_context_never_resolves_artifact_from_another_session(db_session, test_datasource) -> None:
    db_session.add_all(
        [
            AgentSession(id="session_a", datasource_id=str(test_datasource.id), title="A"),
            AgentSession(id="session_b", datasource_id=str(test_datasource.id), title="B"),
        ]
    )
    db_session.commit()
    repository = SessionRepository(db_session)
    foreign = repository.admit(
        session_id="session_b",
        datasource_id=str(test_datasource.id),
        datasource_generation=1,
        content="foreign",
        idempotency_key="foreign",
        llm_credential_id="credential",
        api_base=None,
        model_name=None,
        request_payload={},
    )
    db_session.add(
        AgentArtifactRecord(
            id="artifact_foreign",
            run_id=foreign.run_id,
            session_id="session_b",
            type="result_view",
            title="Foreign",
            payload_json="{}",
            presentation_json="{}",
            refs_json="{}",
            provenance_json="{}",
            relations_json="[]",
            status="completed",
            sequence=1,
        )
    )
    local = repository.admit(
        session_id="session_a",
        datasource_id=str(test_datasource.id),
        datasource_generation=1,
        content="local",
        idempotency_key="local",
        llm_credential_id="credential",
        api_base=None,
        model_name=None,
        request_payload={},
        selected_artifact_ids=["artifact_foreign"],
    )
    db_session.commit()

    assert ContextAssembler(db_session).build(local.run_id).selected_artifacts == []


def test_context_includes_consumed_steer_without_leaking_queued_input(
    db_session, test_datasource
) -> None:
    db_session.add(AgentSession(
        id="session_steer_context",
        datasource_id=str(test_datasource.id),
        title="Steer context",
    ))
    db_session.commit()
    repository = SessionRepository(db_session)
    active = repository.admit(
        session_id="session_steer_context",
        datasource_id=str(test_datasource.id),
        datasource_generation=1,
        content="分析所有地区的退款率",
        idempotency_key="active",
        llm_credential_id="credential",
        api_base=None,
        model_name="model",
        request_payload={},
    )
    lease = repository.claim(session_id="session_steer_context", owner="worker")
    assert lease is not None
    repository.promote_next_input(lease=lease)
    repository.admit(
        session_id="session_steer_context",
        datasource_id=str(test_datasource.id),
        datasource_generation=1,
        content="下一项任务：分析客单价",
        idempotency_key="queued",
        llm_credential_id="credential",
        api_base=None,
        model_name="model",
        request_payload={},
        delivery_mode=DeliveryMode.QUEUE,
    )
    repository.admit(
        session_id="session_steer_context",
        datasource_id=str(test_datasource.id),
        datasource_generation=1,
        content="补充：只看华东区",
        idempotency_key="steer",
        llm_credential_id="credential",
        api_base=None,
        model_name="model",
        request_payload={},
        delivery_mode=DeliveryMode.STEER,
    )
    repository.consume_steering_inputs(lease=lease, run_id=active.run_id)
    db_session.commit()

    snapshot = ContextAssembler(db_session).build(active.run_id)

    assert [message["content"] for message in snapshot.messages] == [
        "分析所有地区的退款率",
        "补充：只看华东区",
    ]
