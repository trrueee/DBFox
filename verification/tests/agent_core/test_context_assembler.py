from __future__ import annotations

import json
from uuid import uuid4

import pytest
from pydantic import BaseModel, ConfigDict

from engine.agent.context import ContextAssembler
from engine.agent.artifact import ArtifactDraft
from engine.agent.observation import ObservationStatus
from engine.agent.references import ConversationInputReference
from engine.agent.resource_refs import ProjectResourceDescriptor, resource_refs_for_run
from engine.agent.repositories.artifact import ArtifactRepository
from engine.agent.repositories.session import SessionRepository
from engine.agent.repositories.tool import ToolInvocationRepository
from engine.agent.session import DeliveryMode
from engine.tools.runtime.attempt import ResourceScopeRef
from engine.tools.materialization import materialize_tools
from verification.support.agent_tools import verification_registry
from engine.representation import (
    ArtifactRepresentationDescriptor,
    ArtifactRepresentationOperation,
)
from engine.models import (
    AgentArtifactRecord,
    AgentMessage,
    AgentRun,
    AgentSession,
    AgentTaskPlanRecord,
    AgentToolInvocation,
    Project,
)


class ContextFixturePayload(BaseModel):
    model_config = ConfigDict(extra="allow")


def _persist_context_artifact(db, admission, *, title, payload, summary=None):
    """Produce test metadata through durable Invocation and Artifact settlement."""
    sessions = SessionRepository(db)
    run = db.get(AgentRun, admission.run_id)
    lease = sessions.claim(session_id=run.session_id, owner="context-fixture")
    assert lease is not None
    sessions.promote_next_input(lease=lease)
    tools = materialize_tools(verification_registry(), allowed_groups={"verification"}, execution_mode="user_requested_read")
    turn = sessions.start_turn(lease=lease, run_id=run.id, agent_definition_version="1",
        prompt_version="1", prompt_hash="context-fixture", context_snapshot={}, context_hash="context-fixture",
        tool_materialization=tools.model_dump(mode="json"), tool_materialization_hash=tools.hash,
        provider="test", model_name="test")
    refs = resource_refs_for_run(db, run)
    invocations = ToolInvocationRepository(db)
    invocation = invocations.request(lease=lease, run_id=run.id, turn_id=turn.id,
        provider_call_id=f"context-{uuid4().hex}", tool_name="verification_read", raw_input={},
        materialization=tools, policy_decision={"status":"allowed", "safe_args":{}}, resource_refs=refs)
    artifacts = ArtifactRepository(db, payload_contract_resolver=lambda kind, version: ContextFixturePayload).persist_drafts(
        lease=lease, run_id=run.id, turn_id=turn.id, invocation_id=invocation.id, tool_name=invocation.tool_name,
        drafts=[ArtifactDraft(key="context_result", type="verification.result", title=title, summary=summary, payload=payload, resource_refs=refs)])
    invocations.settle(lease=lease, invocation_id=invocation.id, status=ObservationStatus.SUCCEEDED,
        model_visible_summary="Produced context result", artifact_ids=[artifacts[0].id])
    run.status = "completed"
    db.commit()
    return artifacts[0]


@pytest.mark.parametrize("selection", ["selected", "attached"])
@pytest.mark.parametrize("outcome", ["complete", "bounded_partial", "failed", "cancelled"])
@pytest.mark.parametrize("condition", ["valid", "internal", "producer_failed", "missing_producer", "future", "nonterminal", "stale_fence", "incomplete"])
def test_all_structured_artifact_context_obeys_availability(db_session, test_resource, selection, outcome, condition):
    session_id = f"context-fence-{selection}-{condition}"
    db_session.add(AgentSession(id=session_id, title="Artifact context fence"))
    db_session.commit()
    repository = SessionRepository(db_session)
    refs = (ResourceScopeRef(kind="verification.resource", id=str(test_resource.id), version="1:1"),)
    first = repository.admit(session_id=session_id, resource_refs=refs, content="Create a result",
        idempotency_key="first", llm_credential_id="credential", api_base=None, model_name="model", request_payload={})
    artifact = _persist_context_artifact(db_session, first, title="PROTECTED_ARTIFACT_TITLE",
        payload={"summary":"PROTECTED_ARTIFACT_PAYLOAD"})
    second = repository.admit(session_id=session_id,
        resource_refs=(ResourceScopeRef(kind=refs[0].kind, id=refs[0].id, version="2:1"),) if condition == "stale_fence" else refs,
        content="Continue", idempotency_key="second", llm_credential_id="credential", api_base=None,
        model_name="model", request_payload={},
        selected_artifact_ids=[artifact.id] if selection == "selected" else [],
        references=(ConversationInputReference(label="Chosen result", artifact_id=artifact.id),) if selection == "attached" else ())
    row = db_session.get(AgentArtifactRecord, artifact.id)
    owner = db_session.get(AgentRun, first.run_id)
    owner.status = outcome if outcome in {"failed", "cancelled"} else "completed"
    owner.result_json = json.dumps({"completion_disposition": outcome})
    db_session.add(AgentTaskPlanRecord(id=f"plan-{uuid4().hex}", session_id=session_id,
        run_id=first.run_id, turn_id=artifact.turn_id, objective="Continue the work", status="partial",
        steps_json=json.dumps([{"id":"result", "title":"Result", "status":"completed",
            "artifact_ids":[artifact.id]}])))
    if condition == "internal":
        row.presentation_json = '{"visibility":"internal"}'
    elif condition == "producer_failed":
        db_session.get(AgentToolInvocation, artifact.provenance["tool_invocation_id"]).status = "failed"
    elif condition == "missing_producer":
        row.provenance_json = json.dumps({"tool_name":"verification_read", "tool_invocation_id":"absent"})
    elif condition == "future":
        owner.session_sequence = db_session.get(AgentRun, second.run_id).session_sequence + 1
    elif condition == "nonterminal":
        owner.status = "running"
    elif condition == "incomplete":
        row.status = "failed"
    db_session.commit()
    available = ArtifactRepository(db_session).available_artifact(current_run_id=second.run_id,
        artifact_id=artifact.id, session_id=session_id)
    assert (available is not None) == (condition == "valid")
    captured = []

    class CaptureContributor:
        def build(self, input_data):
            captured.extend(input_data.recent_artifacts)
            return ()

    snapshot = ContextAssembler(db_session, contributors=(lambda _db: CaptureContributor(),)).build(second.run_id)
    if condition == "valid":
        assert [item.id for item in snapshot.selected_artifacts] == [artifact.id]
        assert [item.artifact_id for item in captured] == [artifact.id]
        assert snapshot.previous_run_outcome.artifacts[0].id == artifact.id
        assert snapshot.previous_run_outcome.plan.steps[0].artifact_ids == [artifact.id]
        assert snapshot.previous_run_outcome.tool_outcomes[0].artifact_ids == [artifact.id]
    else:
        assert snapshot.selected_artifacts == []
        assert captured == [], "Unavailable payload reached a capability context contributor"
        if snapshot.previous_run_outcome:
            assert snapshot.previous_run_outcome.artifacts == []
            assert all(not row.artifact_ids and not row.artifacts for row in snapshot.previous_run_outcome.tool_outcomes)
            assert all(not step.artifact_ids for step in snapshot.previous_run_outcome.plan.steps)
        assert "PROTECTED_ARTIFACT_TITLE" not in str(snapshot.model_message_plan(system_prompt="Context verification"))


def test_project_resource_directory_snapshot_is_bounded_and_reports_full_kind_counts(
    db_session,
) -> None:
    db_session.add(Project(id="context-resource-project", name="Resources"))
    db_session.commit()
    db_session.add(
        AgentSession(
            id="context-resource-session",
            project_id="context-resource-project",
            title="Resources",
        )
    )
    db_session.commit()
    admission = SessionRepository(db_session).admit(
        session_id="context-resource-session",
        resource_refs=(),
        content="Find a resource without attaching authority to this Input.",
        idempotency_key="context-resource-directory",
        llm_credential_id="credential",
        api_base=None,
        model_name="model",
        request_payload={},
    )

    def provider(_db, project_id):
        assert project_id == "context-resource-project"
        return tuple(
            ProjectResourceDescriptor(
                kind="verification.resource",
                id=f"resource-{index:03d}",
                version=index,
                name=f"Resource {index:03d}",
            )
            for index in range(75)
        )

    snapshot = ContextAssembler(
        db_session,
        resource_providers=(provider,),
    ).build(admission.run_id)

    assert len(snapshot.resource_directory) == 32
    assert snapshot.resource_directory_counts == {"verification.resource": 75}
    assert snapshot.resource_directory_truncated is True


def test_next_run_reads_durable_history_and_selected_artifact(
    db_session, test_resource
) -> None:
    db_session.add(
        AgentSession(id="session_context", project_id=None, title="Context"
        )
    )
    db_session.commit()
    repository = SessionRepository(db_session)
    first = repository.admit(
        session_id="session_context",
        resource_refs=(ResourceScopeRef(kind="verification.resource", id=str(test_resource.id), version="1:1"),),
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
    artifact = _persist_context_artifact(db_session, first, title="订单数量", payload={
        "summary": "verified work product", "privateValues": [{"secret":"sensitive-cell-value"}],
    })
    aggregate = db_session.get(AgentSession, "session_context")
    aggregate.selected_artifact_id = artifact.id
    db_session.commit()

    second = repository.admit(
        session_id="session_context",
        resource_refs=(ResourceScopeRef(kind="verification.resource", id=str(test_resource.id), version="1:1"),),
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
    assert snapshot.selected_artifacts[0].descriptor == {}
    assert snapshot.selected_artifacts[0].schema_version == 1
    assert snapshot.selected_artifacts[0].version == 1
    assert snapshot.previous_run_outcome is not None
    assert snapshot.previous_run_outcome.run_id == first.run_id
    assert snapshot.previous_run_outcome.status == "completed"
    assert "sensitive-cell-value" not in json.dumps(snapshot.model_dump(mode="json"))
    assert snapshot.hash == ContextAssembler(db_session).build(second.run_id).hash


def test_context_never_resolves_artifact_from_another_session(
    db_session, test_resource
) -> None:
    db_session.add_all(
        [
            AgentSession(id="session_a", project_id=None, title="A"
            ),
            AgentSession(id="session_b", project_id=None, title="B"
            ),
        ]
    )
    db_session.commit()
    repository = SessionRepository(db_session)
    foreign = repository.admit(
        session_id="session_b",
        resource_refs=(ResourceScopeRef(kind="verification.resource", id=str(test_resource.id), version="1:1"),),
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
            type="verification.result",
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
        resource_refs=(ResourceScopeRef(kind="verification.resource", id=str(test_resource.id), version="1:1"),),
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


def test_attached_artifact_reference_is_projected_as_selected_context(
    db_session, test_resource
) -> None:
    db_session.add(AgentSession(id="session_attached_artifact", title="Attached"))
    db_session.commit()
    repository = SessionRepository(db_session)
    first = repository.admit(
        session_id="session_attached_artifact",
        resource_refs=(ResourceScopeRef(kind="verification.resource", id=str(test_resource.id), version="1:1"),),
        content="Create a result",
        idempotency_key="attached-first",
        llm_credential_id="credential",
        api_base=None,
        model_name="model",
        request_payload={},
    )
    artifact = _persist_context_artifact(db_session, first, title="Attached result", payload={})

    second = repository.admit(
        session_id="session_attached_artifact",
        resource_refs=(ResourceScopeRef(kind="verification.resource", id=str(test_resource.id), version="1:1"),),
        content="Explain this artifact",
        idempotency_key="attached-second",
        llm_credential_id="credential",
        api_base=None,
        model_name="model",
        request_payload={},
        references=(
            ConversationInputReference(
                label="Attached result",
                artifact_id=artifact.id,
            ),
        ),
    )
    db_session.commit()

    snapshot = ContextAssembler(
        db_session,
        artifact_representation_describer=lambda value: (
            ArtifactRepresentationDescriptor(
                representation_type="verification.frame.v1",
                version=1,
                operations=(ArtifactRepresentationOperation(name="page"),),
            ),
        ) if value.id == artifact.id else (),
    ).build(second.run_id)

    assert [item.id for item in snapshot.selected_artifacts] == [artifact.id]
    assert snapshot.selected_artifacts[0].representations[0].representation_type == (
        "verification.frame.v1"
    )
    assert snapshot.input_references[0].artifact_id == artifact.id


def test_context_includes_consumed_steer_without_leaking_queued_input(
    db_session, test_resource
) -> None:
    db_session.add(
        AgentSession(id="session_steer_context", project_id=None,
            title="Steer context",
        )
    )
    db_session.commit()
    repository = SessionRepository(db_session)
    active = repository.admit(
        session_id="session_steer_context",
        resource_refs=(ResourceScopeRef(kind="verification.resource", id=str(test_resource.id), version="1:1"),),
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
        resource_refs=(ResourceScopeRef(kind="verification.resource", id=str(test_resource.id), version="1:1"),),
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
        resource_refs=(ResourceScopeRef(kind="verification.resource", id=str(test_resource.id), version="1:1"),),
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
    test_resource,
) -> None:
    db_session.add(
        AgentSession(id="session_failed_context", project_id=None,
            title="Failed context",
        )
    )
    db_session.commit()
    repository = SessionRepository(db_session)
    first = repository.admit(
        session_id="session_failed_context",
        resource_refs=(ResourceScopeRef(kind="verification.resource", id=str(test_resource.id), version="1:1"),),
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
        resource_refs=(ResourceScopeRef(kind="verification.resource", id=str(test_resource.id), version="1:1"),),
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
    test_resource,
) -> None:
    db_session.add(
        AgentSession(id="session_partial_context", project_id=None,
            title="Partial context",
        )
    )
    db_session.commit()
    repository = SessionRepository(db_session)
    first = repository.admit(
        session_id="session_partial_context",
        resource_refs=(ResourceScopeRef(kind="verification.resource", id=str(test_resource.id), version="1:1"),),
        content="完整分析订单收入与留存",
        idempotency_key="partial-first",
        llm_credential_id="credential",
        api_base=None,
        model_name="model",
        request_payload={},
    )
    artifact = _persist_context_artifact(db_session, first, title="月度收入趋势",
        summary="返回 2 行月度汇总。", payload={
                        "sourceSqlArtifactId": "artifact_partial_sql",
                        "queryFingerprint": "partial-fingerprint",
                        "rowCount": 2,
                    })
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
    db_session.add_all(
        [
            AgentTaskPlanRecord(
                id="plan_partial_context",
                session_id="session_partial_context",
                run_id=first.run_id,
                turn_id=artifact.turn_id,
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
                            "artifact_ids": [artifact.id],
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

        ]
    )
    db_session.commit()

    second = repository.admit(
        session_id="session_partial_context",
        resource_refs=(ResourceScopeRef(kind="verification.resource", id=str(test_resource.id), version="1:1"),),
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
        artifact.id
    ]
    assert [
        artifact.model_dump(mode="json")
        for artifact in snapshot.previous_run_outcome.artifacts
    ] == [
        {
            "id": artifact.id,
            "type": "verification.result",
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
    test_resource,
) -> None:
    db_session.add(
        AgentSession(id="session_completed_result_context", project_id=None,
            title="Completed result context",
        )
    )
    db_session.commit()
    repository = SessionRepository(db_session)
    first = repository.admit(
        session_id="session_completed_result_context",
        resource_refs=(ResourceScopeRef(kind="verification.resource", id=str(test_resource.id), version="1:1"),),
        content="查询订单状态分布",
        idempotency_key="completed-result-first",
        llm_credential_id="credential",
        api_base=None,
        model_name="model",
        request_payload={},
    )
    artifact = _persist_context_artifact(db_session, first, title="订单状态分布",
        summary="返回 4 行状态汇总。", payload={
                    "sourceSqlArtifactId": "artifact_completed_sql",
                    "queryFingerprint": "completed-result-fingerprint",
                    "rowCount": 4,
                })
    first_run = db_session.get(AgentRun, first.run_id)
    first_run.status = "completed"
    first_run.result_json = json.dumps({"completion_disposition": "complete"})
    first_answer = db_session.get(AgentMessage, first.assistant_message_id)
    first_answer.content = "状态分布已查询。"
    first_answer.status = "completed"
    db_session.commit()

    second = repository.admit(
        session_id="session_completed_result_context",
        resource_refs=(ResourceScopeRef(kind="verification.resource", id=str(test_resource.id), version="1:1"),),
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
        artifact.id
    ]
    assert "可复用" in snapshot.previous_run_outcome.public_message
