"""Declared work survives prompt eviction and cannot be erased by completion."""
from __future__ import annotations

import pytest

from engine.agent.completion import CompletionKind, CompletionPolicy
from engine.agent.context import ContextAssembler, ResponseItemBatch
from engine.agent.definition import DEFAULT_AGENT_DEFINITION
from engine.agent.prompt import PromptAssembler
from engine.agent.context_budget import ContextBudgetExceeded
from engine.agent.plan import PlanStatus, PlanStep, PlanStepStatus
from engine.agent.repositories.plan import PlanRepository, PlanTransitionError
from engine.agent.repositories.session import SessionRepository
from engine.agent.response import AnswerCandidate, CompletionDisposition, ResponseComposer
from engine.agent.terminalizer import Terminalizer
from engine.agent.turn import ModelTurnResult, TurnAssistantMessage, TurnTermination
from engine.models import AgentRun, AgentSession, AgentTaskPlanRecord


@pytest.fixture
def declared_plan(db_session):
    db_session.add(AgentSession(id="plan-contract", title="Declared work"))
    db_session.commit()
    sessions = SessionRepository(db_session)
    admission = sessions.admit(
        session_id="plan-contract", resource_refs=(), content="Perform and verify the requested work.",
        idempotency_key="plan-contract", llm_credential_id="fixture", api_base=None,
        model_name="fixture", request_payload={},
    )
    lease = sessions.claim(session_id="plan-contract", owner="fixture")
    assert lease is not None
    sessions.promote_next_input(lease=lease)
    turn = sessions.start_turn(
        lease=lease, run_id=admission.run_id, agent_definition_version="fixture",
        prompt_version="fixture", prompt_hash="fixture", context_snapshot={}, context_hash="fixture",
        tool_materialization={"tools": []}, tool_materialization_hash="fixture",
        provider="fixture", model_name="fixture",
    )
    plan = PlanRepository(db_session).update(
        lease=lease, run_id=admission.run_id, turn_id=turn.id,
        objective="Perform and verify the requested work.", summary=None,
        steps=[PlanStep(id="perform", title="Perform the work", status=PlanStepStatus.COMPLETED),
               PlanStep(id="verify", title="Verify the result", status=PlanStepStatus.PENDING)],
    )
    db_session.commit()
    return lease, admission.run_id, turn.id, plan


@pytest.mark.parametrize("status", [PlanStepStatus.PENDING, PlanStepStatus.IN_PROGRESS, PlanStepStatus.BLOCKED])
@pytest.mark.parametrize("at_budget", [False, True])
def test_completion_rejects_an_unsettled_plan_without_classifying_answer_words(
    db_session, declared_plan, status, at_budget,
):
    lease, run_id, turn_id, plan = declared_plan
    steps = [plan.steps[0], plan.steps[1].model_copy(update={"status": status})]
    plan = PlanRepository(db_session).update(lease=lease, run_id=run_id, turn_id=turn_id,
                                            objective=plan.objective, steps=steps, summary=None)
    context = ContextAssembler(db_session).build(run_id).model_copy(update={"task_plan": plan})
    candidate = ModelTurnResult(termination=TurnTermination.COMPLETED, messages=[TurnAssistantMessage(
        item_id="answer", output_index=0, phase="final_answer", status="completed", text="Everything is complete.",
    )])
    decision = CompletionPolicy(constraints=(), supports=()).evaluate(
        context=context, model_result=candidate, turn_count=2 if at_budget else 1, max_turns=2,
    )
    assert decision.kind is (CompletionKind.FAIL if at_budget else CompletionKind.CONTINUE)
    assert "settled_plan" in decision.missing


def test_prompt_snapshot_uses_the_current_durable_plan_without_its_original_tool_turn(db_session, declared_plan):
    _lease, run_id, _turn, plan = declared_plan
    snapshot = ContextAssembler(db_session).build(run_id)
    assert snapshot.task_plan.id == plan.id
    assert snapshot.task_plan.version == plan.version
    assert snapshot.response_batches == []
    rendered = str(PromptAssembler().assemble(definition=DEFAULT_AGENT_DEFINITION, context=snapshot).messages)
    assert "Verify the result" in rendered
    assert "pending" in rendered


def test_current_plan_follows_old_native_outputs_and_retains_its_own_budget(db_session, declared_plan):
    _lease, run_id, _turn, _plan = declared_plan
    old = {"type": "message", "role": "assistant", "content": "An older plan was complete."}
    snapshot = ContextAssembler(db_session).build(run_id).model_copy(update={
        "response_batches": [ResponseItemBatch(turn_id="old", items=[old])],
    })
    bundle = PromptAssembler().assemble(definition=DEFAULT_AGENT_DEFINITION, context=snapshot)
    assert bundle.messages[-2] == old
    assert '<dbfox_current_task_plan scope="active_run">' in bundle.messages[-1]["content"]
    assert '"pending"' in bundle.messages[-1]["content"]
    assert bundle.budget["task_plan_tokens"] > 0
    assert '"pending"' not in bundle.system_prompt


def test_terminalizer_cannot_turn_unperformed_steps_into_skipped_success(db_session, declared_plan):
    lease, run_id, _turn, plan = declared_plan
    response = ResponseComposer().compose(
        session_id=lease.session_id, run_id=run_id, completion_disposition=CompletionDisposition.COMPLETE,
        limitation_codes=[], answer=AnswerCandidate(text="Everything is complete.", evidence=[]), artifacts=[],
    )
    completed = Terminalizer.complete_in_session(db_session, lease, response)
    db_session.commit()
    assert not completed
    assert db_session.get(AgentRun, run_id).status == "running"
    row = db_session.get(AgentTaskPlanRecord, plan.id)
    assert row.status == "active"
    assert '"pending"' in row.steps_json


def test_plan_owner_refuses_to_invent_completion(db_session, declared_plan):
    lease, run_id, _turn, _plan = declared_plan
    with pytest.raises(PlanTransitionError, match="unfinished"):
        PlanRepository(db_session).terminalize(lease=lease, run_id=run_id, status=PlanStatus.COMPLETED)


def test_a_declared_plan_cannot_be_silently_dropped_to_fit_the_prompt(db_session, declared_plan):
    lease, run_id, turn_id, plan = declared_plan
    PlanRepository(db_session).update(
        lease=lease, run_id=run_id, turn_id=turn_id, objective=plan.objective, summary=None,
        steps=[PlanStep(id=f"step-{index}", title="t" * 240, note="n" * 500,
                        status=PlanStepStatus.PENDING) for index in range(12)],
    )
    snapshot = ContextAssembler(db_session).build(run_id)
    definition = DEFAULT_AGENT_DEFINITION.model_copy(update={
        "limits": DEFAULT_AGENT_DEFINITION.limits.model_copy(update={"max_prompt_tokens": 1024}),
    })
    with pytest.raises(ContextBudgetExceeded):
        PromptAssembler().assemble(definition=definition, context=snapshot)
