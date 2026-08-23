from __future__ import annotations

import json
import pytest
from sqlalchemy.orm import sessionmaker

from engine.agent.approval import ApprovalConflict, ApprovalStatus
from engine.agent.question import QuestionAnswer, QuestionConflict, QuestionStatus
from engine.agent.repositories.approval import ApprovalRepository
from engine.agent.repositories.question import QuestionRepository
from engine.agent.repositories.plan import PlanRepository
from engine.agent.repositories.run import RunRepository
from engine.agent.repositories.session import SessionRepository
from engine.agent.repositories.tool import ToolInvocationRepository
from engine.agent.terminalizer import Terminalizer
from engine.agent.plan import PlanStep, PlanStepStatus
from engine.agent.projection import conversation_snapshot
from engine.agent.run_item import RunItemStatus
from engine.agent.turn import TurnTermination
from engine.agent.tool import ToolInvocationStatus
from engine.tools.runtime.attempt import ResourceScopeRef
from engine.models import (
    AgentApproval,
    AgentQuestionRequest,
    AgentRun,
    AgentRunItemRecord,
    AgentSession,
    AgentTaskPlanRecord,
    AgentToolInvocation,
    AgentTurn,
)
from engine.runtime_composition import build_product_tool_registry
from engine.tools.materialization import ToolMaterialization, materialize_tools


def _start_run(
    db_session,
    test_datasource,
    *,
    session_id: str,
    materialization: ToolMaterialization | None = None,
):
    db_session.add(
        AgentSession(
            id=session_id,
            title="Cancellation",
        )
    )
    db_session.commit()
    sessions = SessionRepository(db_session)
    admission = sessions.admit(
        session_id=session_id,
        resource_refs=(ResourceScopeRef(kind="dbfox.data.database", id=str(test_datasource.id), version="1:1"),),
        content="继续分析",
        idempotency_key=f"{session_id}:start",
        llm_credential_id="credential",
        api_base=None,
        model_name="model",
        request_payload={},
    )
    lease = sessions.claim(session_id=session_id, owner="worker")
    assert lease is not None
    sessions.promote_next_input(lease=lease)
    frozen_tools = materialization.model_dump(mode="json") if materialization is not None else {"tools": []}
    frozen_hash = materialization.hash if materialization is not None else "tools"
    turn = sessions.start_turn(
        lease=lease,
        run_id=admission.run_id,
        agent_definition_version="1",
        prompt_version="1",
        prompt_hash="prompt",
        context_snapshot={},
        context_hash="context",
        tool_materialization=frozen_tools,
        tool_materialization_hash=frozen_hash,
        provider="test",
        model_name="test",
    )
    return sessions, admission, lease, turn


def _cancel_with_terminalizer(db_session, *, sessions, admission, lease) -> None:
    RunRepository(db_session).request_cancel(run_id=admission.run_id)
    db_session.commit()
    factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)
    assert Terminalizer(session_factory=factory).cancelled(lease, admission.run_id) is True
    db_session.expire_all()


def test_cancellation_terminalizes_pending_approval_and_blocks_late_resolution(
    db_session,
    test_datasource,
) -> None:
    tools = materialize_tools(
        build_product_tool_registry(),
        allowed_groups={"query"},
        execution_mode="agent_autonomous_read",
    )
    sessions, admission, lease, turn = _start_run(
        db_session,
        test_datasource,
        session_id="session_cancel_approval",
        materialization=tools,
    )
    invocation = ToolInvocationRepository(db_session).request(
        lease=lease,
        run_id=admission.run_id,
        turn_id=str(turn.id),
        provider_call_id="cancel-approval-call",
        tool_name="sql_execute_readonly",
        raw_input={},
        materialization=tools,
        policy_decision={
            "status": "approval_required",
            "reason": "需要确认",
            "risk_level": "warning",
        },
    )
    approval = ApprovalRepository(db_session).request(
        lease=lease,
        invocation_id=invocation.id,
        policy_decision={
            "status": "approval_required",
            "reason": "需要确认",
            "risk_level": "warning",
        },
    )

    _cancel_with_terminalizer(
        db_session,
        sessions=sessions,
        admission=admission,
        lease=lease,
    )

    assert db_session.get(AgentRun, admission.run_id).status == "cancelled"
    assert db_session.get(AgentApproval, approval.id).status == ApprovalStatus.CANCELLED.value
    assert (
        db_session.get(AgentToolInvocation, invocation.id).status
        == ToolInvocationStatus.CANCELLED.value
    )
    with pytest.raises(ApprovalConflict):
        ApprovalRepository(db_session).resolve(
            approval_id=approval.id,
            expected_version=0,
            approved=True,
            actor="user",
        )


def test_cancellation_terminalizes_pending_question_and_blocks_late_response(
    db_session,
    test_datasource,
) -> None:
    tools = materialize_tools(
        build_product_tool_registry(),
        allowed_groups={"control"},
        execution_mode="user_requested_read",
    )
    sessions, admission, lease, turn = _start_run(
        db_session,
        test_datasource,
        session_id="session_cancel_question",
        materialization=tools,
    )
    arguments = {
        "question": "使用哪个统计口径？",
        "reason": "缺少必要口径",
        "options": [{"value": "calendar", "label": "自然月"}],
        "allow_free_text": False,
    }
    invocation = ToolInvocationRepository(db_session).request(
        lease=lease,
        run_id=admission.run_id,
        turn_id=str(turn.id),
        provider_call_id="cancel-question-call",
        tool_name="request_clarification",
        raw_input=arguments,
        materialization=tools,
        policy_decision={
            "status": "allowed",
            "reason": "safe interaction",
            "risk_level": "safe",
            "safe_args": arguments,
        },
    )
    invocation = ToolInvocationRepository(db_session).mark_waiting_input(
        lease=lease,
        invocation_id=invocation.id,
    )
    question = QuestionRepository(db_session).request(
        lease=lease,
        run_id=admission.run_id,
        turn_id=str(turn.id),
        tool_invocation_id=invocation.id,
        **arguments,
    )

    _cancel_with_terminalizer(
        db_session,
        sessions=sessions,
        admission=admission,
        lease=lease,
    )

    assert db_session.get(AgentRun, admission.run_id).status == "cancelled"
    assert (
        db_session.get(AgentQuestionRequest, question.id).status
        == QuestionStatus.CANCELLED.value
    )
    assert (
        db_session.get(AgentToolInvocation, invocation.id).status
        == ToolInvocationStatus.CANCELLED.value
    )
    with pytest.raises(QuestionConflict):
        QuestionRepository(db_session).resolve(
            question_id=question.id,
            expected_version=0,
            answer=QuestionAnswer(selected_value="calendar"),
            actor="user",
        )


def test_cancellation_terminalizes_the_visible_plan(
    db_session,
    test_datasource,
) -> None:
    sessions, admission, lease, turn = _start_run(
        db_session,
        test_datasource,
        session_id="session_cancel_plan",
    )
    PlanRepository(db_session).update(
        lease=lease,
        run_id=admission.run_id,
        turn_id=str(turn.id),
        objective="分析订单趋势",
        steps=[
            PlanStep(
                id="trend",
                title="查询订单趋势",
                status=PlanStepStatus.IN_PROGRESS,
            ),
            PlanStep(
                id="explain",
                title="解释趋势变化",
                status=PlanStepStatus.PENDING,
            ),
        ],
        summary=None,
    )
    db_session.commit()

    _cancel_with_terminalizer(
        db_session,
        sessions=sessions,
        admission=admission,
        lease=lease,
    )

    row = db_session.query(AgentTaskPlanRecord).filter_by(
        run_id=admission.run_id,
    ).one()
    assert row.status == "cancelled"
    steps = json.loads(row.steps_json)
    assert [step["status"] for step in steps] == ["skipped", "skipped"]
    snapshot = conversation_snapshot(db_session, "session_cancel_plan")
    assert snapshot is not None
    plan_item = next(
        item
        for item in snapshot["items"]
        if item["type"] == "plan"
    )
    assert plan_item["status"] == "cancelled"
    assert plan_item["completed_at"] is not None


def test_cancellation_terminalizes_the_active_turn_and_partial_message(
    db_session,
    test_datasource,
) -> None:
    sessions, admission, lease, turn = _start_run(
        db_session,
        test_datasource,
        session_id="session_cancel_turn",
    )
    item_id = RunRepository(db_session).persist_turn_message(
        lease=lease,
        run_id=admission.run_id,
        turn_id=str(turn.id),
        output_index=0,
        revision=1,
        phase=None,
        content="尚未完成的部分回答",
        status=RunItemStatus.IN_PROGRESS,
    )
    db_session.commit()

    _cancel_with_terminalizer(
        db_session,
        sessions=sessions,
        admission=admission,
        lease=lease,
    )

    run = db_session.get(AgentRun, admission.run_id)
    cancelled_turn = db_session.get(AgentTurn, turn.id)
    message_item = db_session.get(AgentRunItemRecord, item_id)
    assert run is not None and run.status == "cancelled"
    assert run.current_turn_id is None
    assert cancelled_turn is not None and cancelled_turn.status == "cancelled"
    assert cancelled_turn.termination == TurnTermination.CANCELLED.value
    assert cancelled_turn.error_code is None
    assert cancelled_turn.completed_at is not None
    assert message_item is not None
    assert message_item.status == RunItemStatus.CANCELLED.value
    assert message_item.completed_at is not None

    factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)
    assert Terminalizer(session_factory=factory).cancelled(lease, admission.run_id) is True
    db_session.expire_all()
    assert db_session.get(AgentTurn, turn.id).status == "cancelled"


def test_failure_terminalizes_pending_children_in_one_transaction(
    db_session,
    test_datasource,
) -> None:
    tools = materialize_tools(
        build_product_tool_registry(),
        allowed_groups={"query"},
        execution_mode="agent_autonomous_read",
    )
    sessions, admission, lease, turn = _start_run(
        db_session,
        test_datasource,
        session_id="session_fail_children",
        materialization=tools,
    )
    PlanRepository(db_session).update(
        lease=lease,
        run_id=admission.run_id,
        turn_id=str(turn.id),
        objective="执行查询",
        steps=[PlanStep(id="query", title="执行查询", status=PlanStepStatus.IN_PROGRESS)],
        summary=None,
    )
    invocation = ToolInvocationRepository(db_session).request(
        lease=lease,
        run_id=admission.run_id,
        turn_id=str(turn.id),
        provider_call_id="fail-approval-call",
        tool_name="sql_execute_readonly",
        raw_input={},
        materialization=tools,
        policy_decision={
            "status": "approval_required",
            "reason": "需要确认",
            "risk_level": "warning",
        },
    )
    approval = ApprovalRepository(db_session).request(
        lease=lease,
        invocation_id=invocation.id,
        policy_decision={
            "status": "approval_required",
            "reason": "需要确认",
            "risk_level": "warning",
        },
    )
    db_session.commit()

    factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)
    Terminalizer(session_factory=factory).fail(
        lease,
        admission.run_id,
        "AGENT_RUNTIME_ERROR",
        "分析未能完成，请重试。",
    )
    db_session.expire_all()

    assert db_session.get(AgentRun, admission.run_id).status == "failed"
    failed_turn = db_session.get(AgentTurn, turn.id)
    assert failed_turn is not None and failed_turn.status == "failed"
    assert failed_turn.termination == TurnTermination.FAILED.value
    assert failed_turn.error_code == "AGENT_RUNTIME_ERROR"
    assert failed_turn.completed_at is not None
    assert db_session.get(AgentApproval, approval.id).status == ApprovalStatus.CANCELLED.value
    assert db_session.get(AgentToolInvocation, invocation.id).status == ToolInvocationStatus.CANCELLED.value
    assert db_session.query(AgentTaskPlanRecord).filter_by(run_id=admission.run_id).one().status == "failed"


def test_failure_terminalization_preserves_a_concurrent_cancel_request(
    db_session, test_datasource
) -> None:
    _, admission, lease, turn = _start_run(
        db_session,
        test_datasource,
        session_id="session_cancel_wins_failure",
    )
    RunRepository(db_session).request_cancel(run_id=admission.run_id)
    db_session.commit()
    factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)

    Terminalizer(session_factory=factory).fail(
        lease,
        admission.run_id,
        "AGENT_RUNTIME_ERROR",
        "分析未能完成，请重试。",
    )
    db_session.expire_all()

    run = db_session.get(AgentRun, admission.run_id)
    stored_turn = db_session.get(AgentTurn, turn.id)
    assert run is not None and run.status == "cancelled"
    assert run.error_code is None
    assert stored_turn is not None and stored_turn.status == "cancelled"
    assert stored_turn.termination == TurnTermination.CANCELLED.value
