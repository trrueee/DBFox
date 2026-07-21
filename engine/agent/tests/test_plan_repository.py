from __future__ import annotations

import pytest

from engine.agent.events import RuntimeEventType
from engine.agent.plan import PlanStep, PlanStepStatus
from engine.agent.repositories.plan import PlanRepository
from engine.agent.repositories.session import SessionRepository
from engine.models import AgentArtifactRecord, AgentSession


def test_task_plan_is_versioned_and_replayed_as_a_public_event(db_session, test_datasource) -> None:
    db_session.add(AgentSession(id="session-plan", datasource_id=str(test_datasource.id), title="Plan"))
    db_session.commit()
    sessions = SessionRepository(db_session)
    admission = sessions.admit(
        session_id="session-plan",
        datasource_id=str(test_datasource.id),
        datasource_generation=1,
        content="分析订单增长并解释异常",
        idempotency_key="plan-request",
        llm_credential_id="credential-1",
        api_base=None,
        model_name="model-test",
        request_payload={},
    )
    lease = sessions.claim(session_id="session-plan", owner="worker-plan")
    assert lease is not None
    assert sessions.promote_next_input(lease=lease) == admission.run_id
    turn = sessions.start_turn(
        lease=lease,
        run_id=admission.run_id,
        agent_definition_version="analyst@2",
        prompt_version="prompt@2.1",
        prompt_hash="prompt-hash",
        context_snapshot={},
        context_hash="context-hash",
        tool_materialization={"tools": []},
        tool_materialization_hash="tools-hash",
        provider="openai-compatible",
        model_name="model-test",
    )
    db_session.commit()

    repository = PlanRepository(db_session)
    first = repository.update(
        lease=lease,
        run_id=admission.run_id,
        turn_id=str(turn.id),
        objective="分析订单增长并解释异常",
        steps=[
            PlanStep(id="trend", title="确认增长趋势", status=PlanStepStatus.IN_PROGRESS),
            PlanStep(id="cause", title="定位异常原因", status=PlanStepStatus.PENDING),
        ],
        summary="先建立趋势基线。",
    )
    second = repository.update(
        lease=lease,
        run_id=admission.run_id,
        turn_id=str(turn.id),
        objective="分析订单增长并解释异常",
        steps=[
            PlanStep(id="trend", title="确认增长趋势", status=PlanStepStatus.COMPLETED),
            PlanStep(id="cause", title="定位异常原因", status=PlanStepStatus.COMPLETED),
        ],
        summary="趋势和异常原因均已核验。",
    )
    db_session.commit()

    assert first.version == 1
    assert second.version == 2
    assert second.status.value == "completed"
    events = sessions.list_events("session-plan")
    assert [event.event_type for event in events[-2:]] == [
        RuntimeEventType.PLAN_UPDATED,
        RuntimeEventType.PLAN_UPDATED,
    ]
    assert events[-1].payload["plan"]["steps"][0]["id"] == "trend"


def test_task_plan_rejects_artifacts_from_another_run_in_the_same_session(
    db_session,
    test_datasource,
) -> None:
    db_session.add(AgentSession(id="session-plan-scope", datasource_id=str(test_datasource.id), title="Plan"))
    db_session.commit()
    sessions = SessionRepository(db_session)
    active = sessions.admit(
        session_id="session-plan-scope", datasource_id=str(test_datasource.id), datasource_generation=1,
        content="当前分析", idempotency_key="active", llm_credential_id="credential",
        api_base=None, model_name="model", request_payload={},
    )
    lease = sessions.claim(session_id="session-plan-scope", owner="worker-plan-scope")
    assert lease is not None
    sessions.promote_next_input(lease=lease)
    turn = sessions.start_turn(
        lease=lease, run_id=active.run_id, agent_definition_version="analyst@2",
        prompt_version="prompt@2", prompt_hash="prompt", context_snapshot={},
        context_hash="context", tool_materialization={"tools": []},
        tool_materialization_hash="tools", provider="provider", model_name="model",
    )
    other = sessions.admit(
        session_id="session-plan-scope", datasource_id=str(test_datasource.id), datasource_generation=1,
        content="下一轮分析", idempotency_key="queued", llm_credential_id="credential",
        api_base=None, model_name="model", request_payload={},
    )
    db_session.add(AgentArtifactRecord(
        id="artifact-other-run", run_id=other.run_id, session_id="session-plan-scope",
        type="result_view", title="其他 Run 结果", payload_json="{}",
        presentation_json="{}", provenance_json="{}", relations_json="[]",
    ))
    db_session.commit()

    with pytest.raises(ValueError, match="unavailable Artifacts"):
        PlanRepository(db_session).update(
            lease=lease, run_id=active.run_id, turn_id=str(turn.id), objective="当前分析",
            steps=[PlanStep(
                id="evidence", title="使用证据", status=PlanStepStatus.COMPLETED,
                evidence_required=True, artifact_ids=["artifact-other-run"],
            )],
            summary="不应接受其他 Run 的证据。",
        )
