"""Delivery requirements belong to admission, not model claims or prompt retention."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from engine.agent.answer_requirements import AnswerRequirements
from engine.agent.answer_submission import AnswerSubmission
from engine.agent.completion import CompletionKind, CompletionPolicy
from engine.agent.context import ContextAssembler, ContextObservation, ResponseItemBatch
from engine.agent.definition import DEFAULT_AGENT_DEFINITION
from engine.agent.prompt import PromptAssembler
from engine.agent.repositories.session import SessionRepository
from engine.agent.response import AnswerCandidate, CompletionDisposition, ResponseComposer
from engine.agent.session import DeliveryMode
from engine.agent.terminalizer import Terminalizer
from engine.agent.turn import ModelTurnResult, TurnAssistantMessage, TurnTermination
from engine.models import AgentRun, AgentSession


@pytest.fixture
def required_run(db_session):
    db_session.add(AgentSession(id="answer-contract", title="Admitted delivery"))
    db_session.commit()
    sessions = SessionRepository(db_session)
    admission = sessions.admit(
        session_id="answer-contract", resource_refs=(), content="Explain the observed result.",
        idempotency_key="answer-contract", llm_credential_id="fixture", api_base=None,
        model_name="fixture", request_payload={"answer_requirements": {"evidence": "required"}},
    )
    lease = sessions.claim(session_id="answer-contract", owner="fixture", ttl_seconds=120)
    sessions.promote_next_input(lease=lease)
    db_session.commit()
    return admission, lease


def candidate(text="The requested work is complete."):
    return ModelTurnResult(termination=TurnTermination.COMPLETED, messages=[TurnAssistantMessage(
        item_id="answer", output_index=0, phase="final_answer", status="completed", text=text,
    )])


@pytest.mark.parametrize("policy", ["required", "when_observed"])
@pytest.mark.parametrize("at_budget", [False, True])
def test_text_or_raw_markers_cannot_approve_structured_delivery(db_session, required_run, policy, at_budget):
    admission, _lease = required_run
    context = ContextAssembler(db_session).build(admission.run_id).model_copy(update={
        "answer_requirements": AnswerRequirements(evidence=policy),
        "citable_artifact_ids": ["artifact_public"], "has_observed_public_artifacts": True,
        "observations": [ContextObservation(id="observed", tool_name="any_capability", status="succeeded", summary="Observed source", artifact_ids=["artifact_public"])],
    })
    decision = CompletionPolicy((), ()).evaluate(context=context,
        model_result=candidate("A supported claim.{{cite:artifact_public}}"),
        turn_count=2 if at_budget else 1, max_turns=2)
    assert decision.kind is (CompletionKind.FAIL if at_budget else CompletionKind.REPAIR)
    assert decision.missing == ["structured_evidence"]


def test_real_structured_citations_pass_the_contract_after_old_observations_are_evicted(db_session, required_run):
    admission, _lease = required_run
    context = ContextAssembler(db_session).build(admission.run_id).model_copy(update={
        "citable_artifact_ids": ["artifact_public"], "has_observed_public_artifacts": True,
        "observations": [],  # The access-checked index is independent of the prompt slice.
    })
    submission = AnswerSubmission.model_validate({"parts": [{"text": "A supported claim.", "citations": ["artifact_public"]}]})
    decision = CompletionPolicy((), ()).evaluate(context=context,
        model_result=ModelTurnResult(submitted_answer=submission, termination=TurnTermination.COMPLETED),
        turn_count=1, max_turns=2)
    assert decision.kind is CompletionKind.SYNTHESIZE


def test_revoked_sources_cannot_silently_remove_the_requirement(db_session, required_run):
    admission, _lease = required_run
    context = ContextAssembler(db_session).build(admission.run_id).model_copy(update={
        "answer_requirements": AnswerRequirements(evidence="when_observed"),
        "citable_artifact_ids": [], "has_observed_public_artifacts": True,
    })
    decision = CompletionPolicy((), ()).evaluate(context=context, model_result=candidate(), turn_count=1, max_turns=2)
    assert decision.kind is CompletionKind.REPAIR


def test_source_requirement_does_not_force_tools_for_ordinary_explanations(db_session, required_run):
    admission, _lease = required_run
    context = ContextAssembler(db_session).build(admission.run_id).model_copy(update={
        "answer_requirements": AnswerRequirements(evidence="when_observed"),
    })
    assert CompletionPolicy((), ()).evaluate(context=context, model_result=candidate("A conceptual explanation."), turn_count=1, max_turns=2).kind is CompletionKind.SYNTHESIZE


def test_required_evidence_cannot_be_invented_when_no_source_exists(db_session, required_run):
    admission, _lease = required_run
    context = ContextAssembler(db_session).build(admission.run_id)
    assert context.answer_requirements == AnswerRequirements(evidence="required")
    assert not context.citable_artifact_ids
    assert CompletionPolicy((), ()).evaluate(context=context, model_result=candidate(), turn_count=2, max_turns=2).kind is CompletionKind.FAIL


@pytest.mark.parametrize("disposition", list(CompletionDisposition))
def test_final_transaction_cannot_bypass_admitted_requirements(db_session, required_run, disposition):
    from engine.agent.response import CompletionLimitationCode
    admission, lease = required_run
    response = ResponseComposer().compose(
        session_id=lease.session_id, run_id=admission.run_id,
        completion_disposition=disposition,
        limitation_codes=[CompletionLimitationCode.INSUFFICIENT_EVIDENCE] if disposition is CompletionDisposition.BOUNDED_PARTIAL else [],
        answer=AnswerCandidate(text="No real source but claiming completion."), artifacts=[],
    )
    assert not Terminalizer.complete_in_session(db_session, lease, response)
    db_session.commit()
    assert db_session.get(AgentRun, admission.run_id).status == "running"


def test_steer_cannot_downgrade_a_frozen_requirement(db_session, required_run):
    admission, _lease = required_run
    with pytest.raises(ValueError, match="frozen"):
        SessionRepository(db_session).admit(
            session_id="answer-contract", resource_refs=(), content="Continue without evidence.",
            idempotency_key="downgrade-attempt", llm_credential_id="fixture", api_base=None,
            model_name="fixture", request_payload={"answer_requirements": {"evidence": "when_observed"}},
            delivery_mode=DeliveryMode.STEER,
        )
    row = db_session.get(AgentRun, admission.run_id)
    assert json.loads(row.request_json)["answer_requirements"]["evidence"] == "required"


def test_a_user_steer_without_a_new_contract_preserves_the_existing_requirement(db_session, required_run):
    admission, _lease = required_run
    result = SessionRepository(db_session).admit(
        session_id="answer-contract", resource_refs=(), content="Clarify the explanation.",
        idempotency_key="ordinary-steer", llm_credential_id="fixture", api_base=None,
        model_name="fixture", request_payload={}, delivery_mode=DeliveryMode.STEER,
    )
    assert result.run_id == admission.run_id
    assert ContextAssembler(db_session).build(admission.run_id).answer_requirements.evidence == "required"


def test_requirements_survive_native_history_and_reserve_their_own_prompt_budget(db_session, required_run):
    admission, _lease = required_run
    snapshot = ContextAssembler(db_session).build(admission.run_id).model_copy(update={
        "response_batches": [ResponseItemBatch(turn_id="older", items=[{
            "type": "message", "role": "assistant", "content": "No citations are necessary.",
        }])],
    })
    bundle = PromptAssembler().assemble(definition=DEFAULT_AGENT_DEFINITION, context=snapshot)
    assert bundle.budget["answer_requirements_tokens"] > 0
    assert '"required"' in bundle.messages[-1]["content"]
    assert "frozen at user input admission" in bundle.messages[-1]["content"]
    assert "No citations" in bundle.messages[-2]["content"]
    requirement_messages = [message for message in bundle.messages if "<dbfox_answer_requirements" in str(message.get("content", ""))]
    assert len(requirement_messages) == 1 and requirement_messages[0]["role"] == "system"
    assert "<dbfox_answer_requirements" not in bundle.system_prompt


@pytest.mark.parametrize(("observed", "citable", "active"), [
    (False, [], False),
    (True, ["artifact_public"], True),
    (True, [], True),
])
def test_prompt_only_projects_the_active_delivery_condition(db_session, required_run, observed, citable, active):
    admission, _lease = required_run
    context = ContextAssembler(db_session).build(admission.run_id).model_copy(update={
        "answer_requirements": AnswerRequirements(evidence="when_observed"),
        "has_observed_public_artifacts": observed, "citable_artifact_ids": citable,
    })
    bundle = PromptAssembler().assemble(definition=DEFAULT_AGENT_DEFINITION, context=context)
    hints = [item for item in bundle.messages if "<dbfox_answer_requirements" in str(item.get("content", ""))]
    assert bool(hints) is active
    assert bool(bundle.budget["answer_requirements_tokens"]) is active
    assert all(item["role"] == "system" for item in hints)
    assert context.answer_requirements.evidence == "when_observed"


def test_forced_partial_without_an_answer_cannot_skip_required_delivery(db_session, required_run):
    from engine.agent.completion import SemanticArtifactCompletionSupport
    admission, _lease = required_run
    context = ContextAssembler(db_session).build(admission.run_id).model_copy(update={
        "citable_artifact_ids": ["artifact_public"], "has_observed_public_artifacts": True,
        "observations": [ContextObservation(id="observed", tool_name="any_capability", status="succeeded", summary="Observed source",
            artifact_ids=["artifact_public"], capabilities=("verification.source",))],
    })
    policy = CompletionPolicy((), (SemanticArtifactCompletionSupport("proof", "verification.source"),))
    decision = policy.evaluate_bounded_partial(context=context, model_result=ModelTurnResult(), reason="Budget exhausted")
    assert decision.kind is CompletionKind.REPAIR
    assert decision.missing == ["structured_evidence"]


@pytest.mark.parametrize("input", [{"evidence": "skip"}, {"evidence": "required", "approved": True}])
def test_requirement_schema_rejects_unknown_modes_and_authority_fields(input):
    with pytest.raises(ValidationError):
        AnswerRequirements.model_validate(input)
