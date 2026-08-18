from __future__ import annotations

import json

from engine.agent.context import ContextAssembler
from engine.agent.repositories.session import SessionRepository
from engine.agent.session import DeliveryMode
from engine.tools.runtime.attempt import ResourceScopeRef
from engine.models import (
    AgentArtifactRecord,
    AgentMessage,
    AgentRun,
    AgentSession,
    AgentTaskPlanRecord,
    AgentTurn,
)


def test_next_run_reads_durable_history_and_selected_artifact(
    db_session, test_datasource
) -> None:
    db_session.add(
        AgentSession(id="session_context", project_id=None, datasource_id=str(test_datasource.id), title="Context"
        )
    )
    db_session.commit()
    repository = SessionRepository(db_session)
    first = repository.admit(
        session_id="session_context",
        resource_refs=(ResourceScopeRef(kind="database", id=str(test_datasource.id), version=1),),
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
        payload_json=json.dumps(
            {
                "sourceSqlArtifactId": "artifact_sql_42",
                "queryFingerprint": "query-42",
                "rowCount": 1,
                "previewRows": [{"secret": "sensitive-cell-value"}],
            }
        ),
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
        resource_refs=(ResourceScopeRef(kind="database", id=str(test_datasource.id), version=1),),
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
    ]
    assert snapshot.current_request == "按地区拆分刚才结果"
    assert snapshot.conversation_archive == {
        "message_count": 3,
        "oldest_sequence": 1,
        "newest_sequence": 3,
        "loaded_message_count": 3,
        "omitted_message_count": 0,
        "search_available": True,
        "scope": "current_session_only",
    }
    assert snapshot.selected_artifacts[0].id == artifact.id
    assert snapshot.selected_artifacts[0].descriptor == {
        "sourceSqlArtifactId": "artifact_sql_42",
        "queryFingerprint": "query-42",
        "rowCount": 1,
    }
    assert snapshot.previous_run_outcome is None
    assert "sensitive-cell-value" not in json.dumps(snapshot.model_dump(mode="json"))
    assert snapshot.hash == ContextAssembler(db_session).build(second.run_id).hash


def test_context_never_resolves_artifact_from_another_session(
    db_session, test_datasource
) -> None:
    db_session.add_all(
        [
            AgentSession(id="session_a", project_id=None, datasource_id=str(test_datasource.id), title="A"
            ),
            AgentSession(id="session_b", project_id=None, datasource_id=str(test_datasource.id), title="B"
            ),
        ]
    )
    db_session.commit()
    repository = SessionRepository(db_session)
    foreign = repository.admit(
        session_id="session_b",
        resource_refs=(ResourceScopeRef(kind="database", id=str(test_datasource.id), version=1),),
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
        resource_refs=(ResourceScopeRef(kind="database", id=str(test_datasource.id), version=1),),
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
    db_session.add(
        AgentSession(id="session_steer_context", project_id=None, datasource_id=str(test_datasource.id),
            title="Steer context",
        )
    )
    db_session.commit()
    repository = SessionRepository(db_session)
    active = repository.admit(
        session_id="session_steer_context",
        resource_refs=(ResourceScopeRef(kind="database", id=str(test_datasource.id), version=1),),
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
        resource_refs=(ResourceScopeRef(kind="database", id=str(test_datasource.id), version=1),),
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
        resource_refs=(ResourceScopeRef(kind="database", id=str(test_datasource.id), version=1),),
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

    assert snapshot.messages == []
    assert snapshot.current_request == "分析所有地区的退款率"
    assert snapshot.consumed_steers == ["补充：只看华东区"]
    assert "下一项任务：分析客单价" not in snapshot.current_request


def test_next_run_receives_failed_outcome_without_failed_assistant_draft(
    db_session,
    test_datasource,
) -> None:
    db_session.add(
        AgentSession(id="session_failed_context", project_id=None, datasource_id=str(test_datasource.id),
            title="Failed context",
        )
    )
    db_session.commit()
    repository = SessionRepository(db_session)
    first = repository.admit(
        session_id="session_failed_context",
        resource_refs=(ResourceScopeRef(kind="database", id=str(test_datasource.id), version=1),),
        content="分析数据库",
        idempotency_key="failed-first",
        llm_credential_id="credential",
        api_base=None,
        model_name="model",
        request_payload={},
    )
    failed_run = db_session.get(AgentRun, first.run_id)
    failed_run.status = "failed"
    failed_run.error_code = "AGENT_NO_PROGRESS"
    failed_run.error_message = "private provider payload must not be reused"
    failed_draft = db_session.get(AgentMessage, first.assistant_message_id)
    failed_draft.content = "我正在猜测一个尚未验证的结论。"
    failed_draft.status = "failed"
    db_session.commit()

    second = repository.admit(
        session_id="session_failed_context",
        resource_refs=(ResourceScopeRef(kind="database", id=str(test_datasource.id), version=1),),
        content="为什么会失败？",
        idempotency_key="failed-second",
        llm_credential_id="credential",
        api_base=None,
        model_name="model",
        request_payload={},
    )
    db_session.commit()

    snapshot = ContextAssembler(db_session).build(second.run_id)

    assert snapshot.previous_run_outcome is not None
    assert snapshot.previous_run_outcome.status == "failed"
    assert snapshot.previous_run_outcome.error_code == "AGENT_NO_PROGRESS"
    assert "连续多轮" in snapshot.previous_run_outcome.public_message
    rendered = json.dumps(snapshot.model_dump(mode="json"), ensure_ascii=False)
    assert "private provider payload" not in rendered
    assert "我正在猜测一个尚未验证的结论" not in rendered


def test_next_run_receives_bounded_partial_plan_and_artifact_index(
    db_session,
    test_datasource,
) -> None:
    db_session.add(
        AgentSession(id="session_partial_context", project_id=None, datasource_id=str(test_datasource.id),
            title="Partial context",
        )
    )
    db_session.commit()
    repository = SessionRepository(db_session)
    first = repository.admit(
        session_id="session_partial_context",
        resource_refs=(ResourceScopeRef(kind="database", id=str(test_datasource.id), version=1),),
        content="完整分析订单收入与留存",
        idempotency_key="partial-first",
        llm_credential_id="credential",
        api_base=None,
        model_name="model",
        request_payload={},
    )
    first_run = db_session.get(AgentRun, first.run_id)
    first_run.status = "completed"
    first_run.result_json = json.dumps(
        {
            "completion_disposition": "bounded_partial",
            "limitation_codes": ["TURN_BUDGET_REACHED"],
        }
    )
    first_assistant = db_session.get(AgentMessage, first.assistant_message_id)
    first_assistant.content = "分析以部分结果结束。"
    first_assistant.status = "completed"
    turn = AgentTurn(
        id="turn_partial_context",
        session_id="session_partial_context",
        run_id=first.run_id,
        sequence=1,
        status="completed",
        agent_definition_version="1",
        prompt_version="1",
        prompt_hash="prompt",
        context_snapshot_json="{}",
        context_hash="context",
        tool_materialization_json="{}",
        tool_materialization_hash="tools",
        provider="test",
        model_name="test",
    )
    db_session.add(turn)
    db_session.flush()
    db_session.add_all(
        [
            AgentTaskPlanRecord(
                id="plan_partial_context",
                session_id="session_partial_context",
                run_id=first.run_id,
                turn_id=turn.id,
                objective="分析订单收入、退款和订阅留存",
                status="partial",
                summary="收入与退款已完成，留存未完成。",
                steps_json=json.dumps(
                    [
                        {
                            "id": "revenue",
                            "title": "计算收入趋势",
                            "status": "completed",
                            "evidence_required": True,
                            "artifact_ids": ["artifact_partial_result"],
                            "note": "已得到月度趋势",
                        },
                        {
                            "id": "retention",
                            "title": "计算订阅留存",
                            "status": "skipped",
                            "evidence_required": True,
                            "artifact_ids": [],
                            "note": "运行以部分结果结束，此步骤未继续执行。",
                        },
                    ],
                    ensure_ascii=False,
                ),
            ),
            AgentArtifactRecord(
                id="artifact_partial_result",
                run_id=first.run_id,
                session_id="session_partial_context",
                turn_id=turn.id,
                type="result_view",
                title="月度收入趋势",
                summary="返回 2 行月度汇总。",
                payload_json=json.dumps(
                    {
                        "sourceSqlArtifactId": "artifact_partial_sql",
                        "queryFingerprint": "partial-fingerprint",
                        "rowCount": 2,
                    }
                ),
                presentation_json="{}",
                refs_json="{}",
                provenance_json="{}",
                relations_json="[]",
                status="completed",
                sequence=1,
            ),
        ]
    )
    db_session.commit()

    second = repository.admit(
        session_id="session_partial_context",
        resource_refs=(ResourceScopeRef(kind="database", id=str(test_datasource.id), version=1),),
        content="继续完成剩余分析",
        idempotency_key="partial-second",
        llm_credential_id="credential",
        api_base=None,
        model_name="model",
        request_payload={},
    )
    db_session.commit()

    snapshot = ContextAssembler(db_session).build(second.run_id)

    assert snapshot.previous_run_outcome is not None
    assert snapshot.previous_run_outcome.completion_disposition == "bounded_partial"
    assert snapshot.previous_run_outcome.limitation_codes == ["TURN_BUDGET_REACHED"]
    assert snapshot.previous_run_outcome.plan is not None
    assert snapshot.previous_run_outcome.plan.objective == (
        "分析订单收入、退款和订阅留存"
    )
    assert snapshot.previous_run_outcome.plan.steps[0].artifact_ids == [
        "artifact_partial_result"
    ]
    assert [
        artifact.model_dump(mode="json")
        for artifact in snapshot.previous_run_outcome.artifacts
    ] == [
        {
            "id": "artifact_partial_result",
            "type": "result_view",
            "title": "月度收入趋势",
            "summary": "返回 2 行月度汇总。",
        }
    ]
    rendered = json.dumps(
        snapshot.previous_run_outcome.model_dump(mode="json"),
        ensure_ascii=False,
    )
    assert "sourceSqlArtifactId" not in rendered
    assert "继续完成剩余分析" not in rendered


def test_next_run_indexes_result_artifacts_from_a_completed_previous_run(
    db_session,
    test_datasource,
) -> None:
    db_session.add(
        AgentSession(id="session_completed_result_context", project_id=None, datasource_id=str(test_datasource.id),
            title="Completed result context",
        )
    )
    db_session.commit()
    repository = SessionRepository(db_session)
    first = repository.admit(
        session_id="session_completed_result_context",
        resource_refs=(ResourceScopeRef(kind="database", id=str(test_datasource.id), version=1),),
        content="查询订单状态分布",
        idempotency_key="completed-result-first",
        llm_credential_id="credential",
        api_base=None,
        model_name="model",
        request_payload={},
    )
    first_run = db_session.get(AgentRun, first.run_id)
    first_run.status = "completed"
    first_run.result_json = json.dumps({"completion_disposition": "complete"})
    first_answer = db_session.get(AgentMessage, first.assistant_message_id)
    first_answer.content = "状态分布已查询。"
    first_answer.status = "completed"
    db_session.add(
        AgentArtifactRecord(
            id="artifact_completed_result",
            run_id=first.run_id,
            session_id="session_completed_result_context",
            type="result_view",
            title="订单状态分布",
            summary="返回 4 行状态汇总。",
            payload_json=json.dumps(
                {
                    "sourceSqlArtifactId": "artifact_completed_sql",
                    "queryFingerprint": "completed-result-fingerprint",
                    "rowCount": 4,
                }
            ),
            presentation_json="{}",
            refs_json="{}",
            provenance_json="{}",
            relations_json="[]",
            status="completed",
            sequence=1,
        )
    )
    db_session.commit()

    second = repository.admit(
        session_id="session_completed_result_context",
        resource_refs=(ResourceScopeRef(kind="database", id=str(test_datasource.id), version=1),),
        content="继续，告诉我最大的类别",
        idempotency_key="completed-result-second",
        llm_credential_id="credential",
        api_base=None,
        model_name="model",
        request_payload={},
    )
    db_session.commit()

    snapshot = ContextAssembler(db_session).build(second.run_id)

    assert snapshot.previous_run_outcome is not None
    assert snapshot.previous_run_outcome.status == "completed"
    assert snapshot.previous_run_outcome.completion_disposition == "complete"
    assert [item.id for item in snapshot.previous_run_outcome.artifacts] == [
        "artifact_completed_result"
    ]
    assert "可复用" in snapshot.previous_run_outcome.public_message
