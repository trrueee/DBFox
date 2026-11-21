"""Agent Core harness tests through the real durable model/tool loop.

Capability DLC behavior is verified in the System and Bench suites. These
tests deliberately use a tiny namespaced test tool so Core stays domain-free.
"""

from __future__ import annotations

import json
import threading
import time
import pytest

from sqlalchemy.orm import sessionmaker

from engine.agent.artifact import ArtifactDraft, ArtifactType
from engine.agent.completion import (
    CompletionGate,
    CompletionPolicy,
    SemanticArtifactCompletionSupport,
    SemanticCitationConstraint,
)
from engine.agent.definition import AgentDefinition
from engine.agent.events import LiveStreamHub
from engine.agent.loop import RunLoop
from engine.agent.repositories.session import SessionRepository
from engine.agent.repositories.approval import ApprovalRepository
from engine.agent.repositories.question import QuestionRepository
from engine.agent.question import QuestionAnswer
from engine.tools.builtin.control import RequestClarificationCommand, SubmitAnswerCommand
from engine.agent.resource_refs import ProjectResourceDescriptor
from engine.agent.turn import TurnStreamItem, TurnStreamKind, TurnTermination
from engine.models import (
    AgentObservationRecord,
    AgentArtifactRecord,
    AgentApproval,
    AgentQuestionRequest,
    AgentTurn,
    AgentRun,
    AgentSession,
    AgentSessionInput,
    AgentToolInvocation,
    Project,
)
from engine.resource import ResourceScopeRef
from engine.tools.runtime import (
    BaseTool,
    ToolExecutionSpec,
    ToolInputModel,
    ToolOutputModel,
    ToolPolicy,
    ToolPresentation,
    ToolRegistry,
)
from engine.tools.runtime.result import ToolOutcome
from engine.tools.runtime.semantics import ToolSemanticSpec
from engine.tools.runtime.attempt import CompositeResourceResolver
from engine.runtime_composition import (
    build_default_completion_policy,
    default_context_contributors,
)
from verification.testkit.synthetic_resources import (
    SYNTHETIC_RESOURCE_KIND,
    ResourceProbeTool,
)


class EchoInput(ToolInputModel):
    value: str
    delay_seconds: float = 0


class EchoOutput(ToolOutputModel):
    value: str


_EVENT_LOCK = threading.Lock()
_EVENTS: list[tuple[str, str, float]] = []


class EchoTool(BaseTool[EchoInput, EchoOutput]):
    name = "verification_echo"
    group = "verification"
    description = "Return a bounded value for Agent Core loop verification."
    input_model = EchoInput
    output_model = EchoOutput
    presentation = ToolPresentation(title="Echo", category="explore")
    execution = ToolExecutionSpec(concurrency="parallel_safe", timeout_seconds=2)

    def run(self, tool_input, context):
        del context
        with _EVENT_LOCK:
            _EVENTS.append((tool_input.value, "start", time.perf_counter()))
        if tool_input.delay_seconds:
            time.sleep(tool_input.delay_seconds)
        with _EVENT_LOCK:
            _EVENTS.append((tool_input.value, "end", time.perf_counter()))
        return EchoOutput(value=tool_input.value)


class ApprovalTool(EchoTool):
    name = "verification_approval"
    policy = ToolPolicy(requires_approval=True)


class EvidenceTool(EchoTool):
    name = "verification_evidence"
    semantics = ToolSemanticSpec(produces=("verification.evidence",))

    def run(self, tool_input, context):
        del context
        return ToolOutcome(
            output=EchoOutput(value=tool_input.value),
            artifacts=(ArtifactDraft(
                key="proof", type=ArtifactType.MARKDOWN, title="Verified value",
                payload={"content": tool_input.value},
            ),),
        )


@pytest.mark.parametrize("approve_first", [True, False])
def test_two_approval_calls_resume_as_one_complete_native_response_batch(db_session, approve_first):
    with _EVENT_LOCK:
        _EVENTS.clear()

    def calls():
        yield from _tool_turn("write-first", "verification_approval", {"value": "first"}, finish=False)
        yield from _tool_turn("write-second", "verification_approval", {"value": "second"}, index=1)

    registry = ToolRegistry().register(ApprovalTool())
    run_id = _execute(db_session, scripts=(calls,), registry=registry)
    requests = db_session.query(AgentApproval).filter_by(run_id=run_id).order_by(AgentApproval.created_at).all()
    assert len(requests) == 2
    approvals = ApprovalRepository(db_session)
    approvals.resolve(approval_id=requests[0].id, expected_version=0, approved=approve_first, actor="user")
    db_session.commit()
    assert db_session.get(AgentRun, run_id).status == "waiting_approval"
    assert _EVENTS == []
    approvals.resolve(approval_id=requests[1].id, expected_version=0, approved=True, actor="user")
    db_session.commit()
    sessions = SessionRepository(db_session)
    lease = sessions.claim(session_id="agent-core-loop", owner="resume")
    assert lease is not None
    sessions.bind_run(lease=lease, run_id=run_id)
    db_session.commit()
    RunLoop(
        session_factory=sessionmaker(bind=db_session.get_bind(), expire_on_commit=False),
        model_factory=lambda _settings: ScriptedModel(lambda: _answer_turn("Authorized actions completed.")),
        registry=registry, context_contributors=default_context_contributors(),
        completion=CompletionGate(build_default_completion_policy()),
        definition=AgentDefinition(allowed_tool_groups=("verification",)), live_stream=LiveStreamHub(),
    ).execute(lease=lease, run_id=run_id)
    db_session.expire_all()
    assert db_session.get(AgentRun, run_id).status == "completed"
    outputs = db_session.query(AgentObservationRecord).filter_by(run_id=run_id).all()
    assert len(outputs) == 2
    assert sorted(item.status for item in outputs) == (["succeeded", "succeeded"] if approve_first else ["rejected", "succeeded"])
    last_turn = db_session.query(AgentTurn).filter_by(run_id=run_id).order_by(AgentTurn.sequence.desc()).first()
    batch = json.loads(last_turn.context_snapshot_json)["response_batches"][-1]["items"]
    assert {item["call_id"] for item in batch if item["type"] == "function_call"} == {"write-first", "write-second"}
    assert {item["call_id"] for item in batch if item["type"] == "function_call_output"} == {"write-first", "write-second"}
    assert len([event for event in _EVENTS if event[1] == "start"]) == (2 if approve_first else 1)


@pytest.mark.parametrize("kinds", [("question", "question"), ("approval", "question"), ("question", "approval")])
@pytest.mark.parametrize("reverse_answers", [False, True])
def test_native_batch_waits_for_each_question_and_approval(db_session, kinds, reverse_answers):
    with _EVENT_LOCK:
        _EVENTS.clear()

    def calls():
        for index, kind in enumerate(kinds):
            name = "request_clarification" if kind == "question" else "verification_approval"
            arguments = (
                {"question": f"Which period {index}?", "reason": "The reporting period is missing."}
                if kind == "question" else {"value": f"action-{index}"}
            )
            yield from _tool_turn(f"interaction-{index}", name, arguments, index=index, finish=index == 1)

    registry = ToolRegistry().register(ApprovalTool()).register(RequestClarificationCommand())
    run_id = _execute(db_session, scripts=(calls,), registry=registry, allowed_tool_groups=("verification", "control"))
    assert db_session.get(AgentRun, run_id).status == "waiting_input"
    questions = db_session.query(AgentQuestionRequest).filter_by(run_id=run_id).all()
    approvals = db_session.query(AgentApproval).filter_by(run_id=run_id).all()
    assert len(questions) == kinds.count("question")
    assert len(approvals) == kinds.count("approval")
    requests = sorted(
        [*(('question', row) for row in questions), *(('approval', row) for row in approvals)],
        key=lambda entry: entry[1].created_at,
        reverse=reverse_answers,
    )
    for index, (kind, request) in enumerate(requests):
        if kind == "question":
            QuestionRepository(db_session).resolve(
                question_id=request.id, expected_version=0,
                answer=QuestionAnswer(text=f"Answer to {request.question}"), actor="user",
            )
        else:
            ApprovalRepository(db_session).resolve(
                approval_id=request.id, expected_version=0, approved=True, actor="user",
            )
        db_session.commit()
        remaining = requests[index + 1:]
        expected = (
            "waiting_input" if any(kind == "question" for kind, _ in remaining)
            else "waiting_approval" if remaining else "running"
        )
        assert db_session.get(AgentRun, run_id).status == expected
        assert _EVENTS == []

    sessions = SessionRepository(db_session)
    lease = sessions.claim(session_id="agent-core-loop", owner="resume")
    assert lease is not None
    sessions.bind_run(lease=lease, run_id=run_id)
    db_session.commit()
    RunLoop(
        session_factory=sessionmaker(bind=db_session.get_bind(), expire_on_commit=False),
        model_factory=lambda _settings: ScriptedModel(lambda: _answer_turn("All requested interactions completed.")),
        registry=registry, context_contributors=default_context_contributors(),
        completion=CompletionGate(build_default_completion_policy()),
        definition=AgentDefinition(allowed_tool_groups=("verification", "control")), live_stream=LiveStreamHub(),
    ).execute(lease=lease, run_id=run_id)
    db_session.expire_all()
    assert db_session.get(AgentRun, run_id).status == "completed"
    outputs = db_session.query(AgentObservationRecord).filter_by(run_id=run_id).all()
    assert len(outputs) == 2
    assert all(item.status == "succeeded" for item in outputs)
    last_turn = db_session.query(AgentTurn).filter_by(run_id=run_id).order_by(AgentTurn.sequence.desc()).first()
    batch = json.loads(last_turn.context_snapshot_json)["response_batches"][-1]["items"]
    assert {item["call_id"] for item in batch if item["type"] == "function_call_output"} == {"interaction-0", "interaction-1"}
    assert len([event for event in _EVENTS if event[1] == "start"]) == kinds.count("approval")


def _tool_turn(call_id: str, name: str, arguments: dict, *, index: int = 0, finish: bool = True):
    encoded = json.dumps(arguments)
    yield TurnStreamItem(
        kind=TurnStreamKind.TOOL_CALL_START,
        item_id=f"tool:{call_id}",
        revision=1,
        tool_call_index=index,
        tool_call_id=call_id,
        tool_name=name,
        arguments_delta=encoded,
    )
    yield TurnStreamItem(
        kind=TurnStreamKind.TOOL_CALL_END,
        item_id=f"tool:{call_id}",
        revision=2,
        tool_call_index=index,
    )
    yield TurnStreamItem(
        kind=TurnStreamKind.MODEL_OUTPUT_ITEM,
        item_id=f"tool:{call_id}",
        revision=3,
        output_index=index,
        model_output_item={
            "type": "function_call",
            "call_id": call_id,
            "name": name,
            "arguments": encoded,
        },
    )
    if finish:
        yield TurnStreamItem(
            kind=TurnStreamKind.FINISH,
            item_id="finish",
            revision=1,
            termination=TurnTermination.COMPLETED,
        )


def _answer_turn(text: str):
    yield TurnStreamItem(kind=TurnStreamKind.ANSWER_START, item_id="answer", revision=1, output_index=0)
    yield TurnStreamItem(kind=TurnStreamKind.ANSWER_DELTA, item_id="answer", revision=2, output_index=0, content=text)
    yield TurnStreamItem(
        kind=TurnStreamKind.ANSWER_END,
        item_id="answer",
        revision=3,
        output_index=0,
        phase="final_answer",
        message_status="completed",
    )
    yield TurnStreamItem(
        kind=TurnStreamKind.MODEL_OUTPUT_ITEM,
        item_id="answer",
        revision=4,
        output_index=0,
        model_output_item={"type": "message", "role": "assistant", "content": text},
    )
    yield TurnStreamItem(
        kind=TurnStreamKind.FINISH,
        item_id="finish",
        revision=1,
        termination=TurnTermination.COMPLETED,
    )


class ScriptedModel:
    def __init__(self, script):
        self.script = script

    def stream(self, **_kwargs):
        yield from self.script()


@pytest.mark.parametrize("owner", ["verification.first", "verification.second"])
def test_rejected_local_name_can_be_corrected_without_executing_an_alias(db_session, owner):
    with _EVENT_LOCK:
        _EVENTS.clear()
    registry = ToolRegistry()
    for candidate_owner in ("verification.first", "verification.second"):
        registry.register(EchoTool(), owner=candidate_owner)
    canonical = next(
        name for name in registry.tool_names() if registry.owner_of(name) == owner
    )

    def corrected_call():
        db_session.expire_all()
        observation = db_session.query(AgentObservationRecord).one()
        payload = json.loads(observation.model_output_json)
        assert payload["error_code"] == "UNKNOWN_TOOL"
        assert canonical in payload["summary"]
        assert "PRIVATE_REJECTED_ARGUMENT" not in observation.model_output_json
        assert _EVENTS == []
        yield from _tool_turn("corrected", canonical, {"value": "executed once"})

    run_id = _execute(
        db_session,
        registry=registry,
        scripts=(
            lambda: _tool_turn("local-alias", "verification_echo", {"value": "PRIVATE_REJECTED_ARGUMENT"}),
            corrected_call,
            lambda: _answer_turn("The requested observation is complete."),
        ),
    )
    invocations = db_session.query(AgentToolInvocation).filter_by(run_id=run_id).all()
    assert sorted(item.status for item in invocations) == ["rejected", "succeeded"]
    assert next(item for item in invocations if item.status == "rejected").input_json == "{}"
    assert [(value, event) for value, event, _ in _EVENTS if event == "start"] == [("executed once", "start")]
    assert db_session.get(AgentRun, run_id).status == "completed"


@pytest.mark.parametrize("user_request", ["Summarize the file evidence.", "Report the verified change.", "解释这个已观察的结果，并引用来源。"])
def test_admitted_delivery_requires_native_citations_without_repeating_capability_work(db_session, user_request):
    def submit():
        db_session.expire_all()
        artifact = db_session.query(AgentArtifactRecord).one()
        turn = db_session.query(AgentTurn).order_by(AgentTurn.sequence.desc()).first()
        snapshot = json.loads(turn.context_snapshot_json)
        assert snapshot["answer_requirements"] == {"evidence": "when_observed"}
        assert artifact.id in snapshot["citable_artifact_ids"]
        assert snapshot["has_observed_public_artifacts"] is True
        assert "structured_evidence" in snapshot["run_focus"]["missing"]
        assert snapshot["prompt_budget"]["answer_requirements_tokens"] > 0
        yield from _tool_turn("deliver", "submit_answer", {"parts": [{"text": "Observed outcome: ready.", "citations": [artifact.id]}]})

    registry = ToolRegistry().register(EvidenceTool()).register(SubmitAnswerCommand(), owner="dbfox.core", provider_name="submit_answer")
    run_id = _execute(db_session, request=user_request,
        request_payload={"answer_requirements": {"evidence": "when_observed"}},
        registry=registry, allowed_tool_groups=("verification", "control"), scripts=(
            lambda: _tool_turn("observe", "verification_evidence", {"value": "ready"}),
            lambda: _answer_turn("The work is complete; the source was observed."), submit,
        ))
    run = db_session.get(AgentRun, run_id)
    assert run.status == "completed"
    assert len(json.loads(run.result_json)["answer"]["evidence"]) == 1
    assert db_session.query(AgentToolInvocation).filter_by(run_id=run_id, tool_name="verification_evidence").count() == 1


def test_required_evidence_cannot_be_replaced_by_no_source_completion_at_budget(db_session):
    from engine.agent.run import RunLimits
    run_id = _execute(db_session,
        request_payload={"answer_requirements": {"evidence": "required"}},
        registry=ToolRegistry(), limits=RunLimits(max_turns=2, finalization_turn_reserve=0),
        scripts=(lambda: _answer_turn("Done without an observation."), lambda: _answer_turn("Still claiming completion.")))
    assert db_session.get(AgentRun, run_id).status == "failed"


def test_internal_observations_do_not_require_a_public_citation(db_session):
    from engine.agent.artifact import ArtifactVisibility

    class InternalTool(EvidenceTool):
        name = "verification_internal"

        def run(self, tool_input, context):
            return ToolOutcome(output=EchoOutput(value=tool_input.value), artifacts=(ArtifactDraft(
                key="internal", type=ArtifactType.MARKDOWN, title="Internal detail",
                payload={"content": tool_input.value}, visibility=ArtifactVisibility.INTERNAL,
            ),))

    def answer():
        db_session.expire_all()
        turn = db_session.query(AgentTurn).order_by(AgentTurn.sequence.desc()).first()
        snapshot = json.loads(turn.context_snapshot_json)
        assert snapshot["citable_artifact_ids"] == []
        assert snapshot["has_observed_public_artifacts"] is False
        yield from _answer_turn("A bounded explanation without claiming a public source.")

    run_id = _execute(db_session, registry=ToolRegistry().register(InternalTool()),
        request_payload={"answer_requirements": {"evidence": "when_observed"}}, scripts=(
            lambda: _tool_turn("internal", "verification_internal", {"value": "metadata"}), answer,
        ))
    assert db_session.get(AgentRun, run_id).status == "completed"


def test_final_transaction_rejects_an_answer_swapped_after_the_completion_gate(db_session, monkeypatch):
    from engine.agent.answer_submission import AnswerSubmission
    original = RunLoop._complete
    attempts = []

    def complete(self, lease, run_id, result, **kwargs):
        if not attempts:
            tampered = result.model_copy(update={"submitted_answer": AnswerSubmission.model_validate({"parts": [
                {"text": "A different answer after validation.", "citations": list(result.submitted_answer.cited_artifact_ids)},
            ]})})
            accepted = original(self, lease, run_id, tampered, **kwargs)
            attempts.append(accepted)
            return accepted
        return original(self, lease, run_id, result, **kwargs)

    def finish():
        db_session.expire_all()
        artifact = db_session.query(AgentArtifactRecord).one()
        yield from _tool_turn(f"deliver-{len(attempts)}", "submit_answer", {"parts": [{"text": "The observed outcome.", "citations": [artifact.id]}]})

    monkeypatch.setattr(RunLoop, "_complete", complete)
    registry = ToolRegistry().register(EvidenceTool()).register(SubmitAnswerCommand(), owner="dbfox.core", provider_name="submit_answer")
    run_id = _execute(db_session,
        request_payload={"answer_requirements": {"evidence": "when_observed"}},
        registry=registry, allowed_tool_groups=("verification", "control"), scripts=(
            lambda: _tool_turn("observe", "verification_evidence", {"value": "outcome"}), finish, finish,
        ))
    assert attempts == [False]
    run = db_session.get(AgentRun, run_id)
    assert run.status == "completed"
    assert json.loads(run.result_json)["answer"]["text"].startswith("The observed outcome.")


def test_structured_answer_uses_real_observation_and_canonical_evidence(db_session):
    from engine.agent.repositories.run import RunRepository
    from engine.models import AgentEvidenceRecord, AgentRunItemRecord

    def finish():
        db_session.expire_all()
        artifact = db_session.query(AgentArtifactRecord).filter_by(title="Verified value").one()
        yield from _tool_turn("deliver", "submit_answer", {"parts": [
            {"text": "**Verified count: 12.**", "citations": [artifact.id]},
            {"text": "\n\nThis is an interpretation, not another measurement."},
            {"text": "\n\nThe saved result remains available.", "citations": [artifact.id]},
        ]})

    registry = ToolRegistry().register(EvidenceTool()).register(SubmitAnswerCommand(), owner="dbfox.core", provider_name="submit_answer")
    run_id = _execute(db_session, scripts=(
        lambda: _tool_turn("measure", "verification_evidence", {"value": "12"}), finish,
    ), registry=registry, allowed_tool_groups=("verification", "control"))
    run = db_session.get(AgentRun, run_id)
    assert run.status == "completed"
    answer = json.loads(run.result_json)["answer"]
    assert answer["text"].startswith("**Verified count: 12.**{{cite:artifact_")
    assert [item["label"] for item in answer["evidence"]] == [
        "**Verified count: 12.**", "The saved result remains available.",
    ]
    assert db_session.query(AgentEvidenceRecord).filter_by(run_id=run_id).count() == 2
    invocation = db_session.query(AgentToolInvocation).filter_by(run_id=run_id, tool_name="submit_answer").one()
    assert invocation.status == "succeeded"
    turn = db_session.get(AgentTurn, invocation.turn_id)
    assert json.loads(turn.tool_calls_json)[0]["name"] == "submit_answer"
    assert json.loads(turn.response_items_json)[0]["type"] == "function_call"
    assert not db_session.query(AgentRunItemRecord).filter(
        AgentRunItemRecord.id.like(f"message:{run_id}:{turn.id}:%")
    ).all()  # The Runtime publishes its canonical final answer, not a fake streamed message.
    restored = RunRepository(db_session).latest_completed_answer(run_id)
    assert restored.submitted_answer is not None
    assert restored.answer_text == answer["text"]


@pytest.mark.parametrize("invalid", ["missing_source", "raw_markup", "fabricated_authority", "mixed_batch"])
def test_invalid_structured_submission_is_rejected_then_repairable(db_session, invalid):
    def bad():
        payload = {"parts": [{"text": "Claim.", "citations": ["artifact_missing"]}]}
        if invalid == "raw_markup":
            payload = {"parts": [{"text": "Claim.{{cite:artifact_missing}}"}]}
        elif invalid == "fabricated_authority":
            payload = {"parts": [{"text": "Claim."}], "success": True}
        elif invalid == "mixed_batch":
            payload = {"parts": [{"text": "Premature answer."}]}
        yield from _tool_turn("bad", "submit_answer", payload, finish=invalid != "mixed_batch")
        if invalid == "mixed_batch":
            yield from _tool_turn("work", "verification_echo", {"value": "actual work"}, index=1)

    def repair():
        db_session.expire_all()
        rejected = db_session.query(AgentToolInvocation).filter_by(provider_call_id="bad").one()
        assert rejected.status == "rejected"
        assert db_session.get(AgentRun, rejected.run_id).status != "completed"
        yield from _tool_turn("good", "submit_answer", {"parts": [{"text": "A bounded explanation without invented resource facts."}]})

    registry = ToolRegistry().register(EchoTool()).register(SubmitAnswerCommand(), owner="dbfox.core", provider_name="submit_answer")
    run_id = _execute(db_session, scripts=(bad, repair), registry=registry, allowed_tool_groups=("verification", "control"))
    assert db_session.get(AgentRun, run_id).status == "completed"
    assert json.loads(db_session.get(AgentRun, run_id).result_json)["answer"]["evidence"] == []


def test_submission_cannot_complete_an_unfinished_plan(db_session):
    from engine.tools.builtin.control import UpdatePlanCommand

    def repair():
        db_session.expire_all()
        run = db_session.query(AgentRun).one()
        assert run.status == "running"
        assert "settled_plan" in run.result_json
        yield from _tool_turn("settle", "update_plan", {
            "objective": "Explain a concept", "steps": [{"id": "explain", "title": "Explain", "status": "completed"}],
        })

    registry = ToolRegistry().register(UpdatePlanCommand(), owner="dbfox.core", provider_name="update_plan").register(
        SubmitAnswerCommand(), owner="dbfox.core", provider_name="submit_answer",
    )
    run_id = _execute(db_session, scripts=(
        lambda: _tool_turn("plan", "update_plan", {
            "objective": "Explain a concept", "steps": [{"id": "explain", "title": "Explain", "status": "pending"}],
        }),
        lambda: _tool_turn("premature", "submit_answer", {"parts": [{"text": "A concept explanation."}]}),
        repair,
        lambda: _tool_turn("final", "submit_answer", {"parts": [{"text": "The concept explained."}]}),
    ), registry=registry, allowed_tool_groups=("control",))
    assert db_session.get(AgentRun, run_id).status == "completed"


def test_structured_submission_cannot_reference_another_session(db_session):
    registry = ToolRegistry().register(EvidenceTool()).register(SubmitAnswerCommand(), owner="dbfox.core", provider_name="submit_answer")
    _execute(db_session, session_id="other-session", registry=registry, scripts=(
        lambda: _tool_turn("source", "verification_evidence", {"value": "private result"}),
        lambda: _answer_turn("The result was created."),
    ))
    artifact = db_session.query(AgentArtifactRecord).one()

    def repair():
        db_session.expire_all()
        assert db_session.query(AgentToolInvocation).filter_by(provider_call_id="foreign").one().status == "rejected"
        yield from _answer_turn("I cannot use that source in this session.")

    run_id = _execute(db_session, session_id="current-session", registry=registry,
        allowed_tool_groups=("verification", "control"), scripts=(
            lambda: _tool_turn("foreign", "submit_answer", {"parts": [{"text": "A claim.", "citations": [artifact.id]}]}),
            repair,
        ))
    assert json.loads(db_session.get(AgentRun, run_id).result_json)["answer"]["evidence"] == []


def test_submission_survives_a_worker_stop_before_terminalization(db_session, monkeypatch):
    from engine.agent.repositories.run import RunRepository

    class WorkerStopped(Exception):
        pass

    def stop_before_completion(self, *args, **kwargs):
        raise WorkerStopped()

    with monkeypatch.context() as patch:
        patch.setattr(RunLoop, "_complete", stop_before_completion)
        with pytest.raises(WorkerStopped):
            _execute(db_session, registry=ToolRegistry().register(
                SubmitAnswerCommand(), owner="dbfox.core", provider_name="submit_answer",
            ), allowed_tool_groups=("control",), scripts=(
                lambda: _tool_turn("candidate", "submit_answer", {"parts": [{"text": "A complete explanation."}]}),
            ))
    db_session.expire_all()
    run = db_session.query(AgentRun).one()
    assert run.status == "running"
    recovered = RunRepository(db_session).latest_completed_answer(str(run.id))
    assert recovered.answer_text == "A complete explanation."
    assert recovered.submitted_answer is not None
    assert not recovered.messages and not recovered.tool_calls
    assert db_session.query(AgentToolInvocation).filter_by(run_id=run.id).count() == 1


def test_cancellation_after_submission_cannot_publish_success(db_session, monkeypatch):
    original = RunLoop._complete

    def cancel_then_complete(self, lease, run_id, result, **kwargs):
        row = db_session.get(AgentRun, run_id)
        row.cancel_requested = True
        db_session.commit()
        return original(self, lease, run_id, result, **kwargs)

    monkeypatch.setattr(RunLoop, "_complete", cancel_then_complete)
    # The checkpoint after the rejected final transaction owns cancellation.
    run_id = _execute(db_session, registry=ToolRegistry().register(
        SubmitAnswerCommand(), owner="dbfox.core", provider_name="submit_answer",
    ), allowed_tool_groups=("control",), scripts=(
        lambda: _tool_turn("candidate", "submit_answer", {"parts": [{"text": "A complete explanation."}]}),
    ))
    assert db_session.get(AgentRun, run_id).status == "cancelled"


def _execute(
    db_session,
    *,
    scripts,
    registry,
    session_id="agent-core-loop",
    project_id=None,
    resource_refs=None,
    resource_providers=(),
    resource_resolver=None,
    allowed_tool_groups=("verification",),
    limits=None,
    completion=None,
    request="Exercise the real Agent loop.",
    request_payload=None,
):
    if project_id is not None:
        db_session.add(Project(id=project_id, name=f"Project {project_id}"))
        db_session.commit()
    db_session.add(
        AgentSession(id=session_id, project_id=project_id, title="Agent Core loop")
    )
    db_session.commit()
    sessions = SessionRepository(db_session)
    admission = sessions.admit(
        session_id=session_id,
        resource_refs=(
            resource_refs
            if resource_refs is not None
            else (
                ResourceScopeRef(
                    kind="verification.resource",
                    id="resource-1",
                    version=1,
                ),
            )
        ),
        content=request,
        idempotency_key=session_id,
        llm_credential_id="verification-credential",
        api_base=None,
        model_name="verification-model",
        request_payload=request_payload or {},
    )
    lease = sessions.claim(session_id=session_id, owner="verification-worker", ttl_seconds=120)
    assert lease is not None
    sessions.promote_next_input(lease=lease)
    db_session.commit()
    queue = list(scripts)

    def model_factory(_settings):
        return ScriptedModel(queue.pop(0))

    RunLoop(
        session_factory=sessionmaker(bind=db_session.get_bind(), expire_on_commit=False),
        model_factory=model_factory,
        registry=registry,
        context_contributors=default_context_contributors(),
        completion=completion or CompletionGate(build_default_completion_policy()),
        definition=AgentDefinition(allowed_tool_groups=allowed_tool_groups, **({"limits": limits} if limits is not None else {})),
        live_stream=LiveStreamHub(),
        resource_providers=resource_providers,
        resource_resolver=resource_resolver,
    ).execute(lease=lease, run_id=admission.run_id)
    db_session.expire_all()
    return admission.run_id


@pytest.mark.parametrize("valid_final_answer", [False, True])
def test_stalled_answer_gets_one_finalization_attempt_without_repeating_work(
    db_session, valid_final_answer,
):
    def finish():
        db_session.expire_all()
        artifact = db_session.query(AgentArtifactRecord).filter_by(title="Verified value").one()
        turn = db_session.query(AgentTurn).order_by(AgentTurn.sequence.desc()).first()
        focus = json.loads(turn.context_snapshot_json)["run_focus"]
        assert focus["kind"] == "synthesize"
        assert artifact.id in focus["reason"]
        assert "verification_evidence" not in turn.tool_materialization_json
        text = "Verified value: 12."
        if valid_final_answer:
            text += "{{cite:" + artifact.id + "}}"
        yield from _answer_turn(text)

    run_id = _execute(
        db_session,
        scripts=(
            lambda: _tool_turn("proof", "verification_evidence", {"value": "12"}),
            lambda: _answer_turn("Verified value: 12."),
            lambda: _answer_turn("Verified value: 12."),
            finish,
        ),
        registry=ToolRegistry().register(EvidenceTool()),
        completion=CompletionGate(CompletionPolicy(
            constraints=(SemanticCitationConstraint("proof-citation", "verification.evidence"),),
            supports=(SemanticArtifactCompletionSupport("proof-support", "verification.evidence"),),
        )),
    )
    run = db_session.get(AgentRun, run_id)
    assert run.status == ("completed" if valid_final_answer else "failed")
    if not valid_final_answer:
        assert run.error_code == "AGENT_NO_PROGRESS"
        # A resumed worker derives the same monotonic phase from Run.focus.
        assert json.loads(run.result_json)["focus"]["kind"] == "synthesize"
    invocation = db_session.query(AgentToolInvocation).filter_by(run_id=run_id).one()
    assert invocation.status == "succeeded"
    assert db_session.query(AgentArtifactRecord).filter_by(run_id=run_id, title="Verified value").count() == 1
    assert db_session.query(AgentTurn).filter_by(run_id=run_id).count() == 4


@pytest.mark.parametrize("goal", [
    "Compute and verify the requested result.",
    "Modify the project and verify the change.",
    "检查来源，核实结论并报告。",
])
def test_declared_work_is_completed_before_the_real_loop_can_deliver(db_session, goal):
    from engine.tools.builtin.control import UpdatePlanCommand
    registry = ToolRegistry().register(EvidenceTool()).register(
        UpdatePlanCommand(), owner="dbfox.core", provider_name="update_plan",
    )
    steps = [
        {"id": "perform", "title": "Perform the requested work", "status": "in_progress", "evidence_required": True},
        {"id": "report", "title": "Verify and report", "status": "pending"},
    ]

    def perform():
        db_session.expire_all()
        turn = db_session.query(AgentTurn).order_by(AgentTurn.sequence.desc()).first()
        snapshot = json.loads(turn.context_snapshot_json)
        assert snapshot["task_plan"]["version"] == 1
        assert snapshot["task_plan"]["steps"][1]["status"] == "pending"
        assert snapshot["prompt_budget"]["task_plan_tokens"] > 0
        yield from _tool_turn("proof", "verification_evidence", {"value": "12"})

    def settle_plan():
        db_session.expire_all()
        artifact = db_session.query(AgentArtifactRecord).filter_by(title="Verified value").one()
        yield from _tool_turn("settle", "update_plan", {"objective": goal, "steps": [
            {**steps[0], "status": "completed", "artifact_ids": [artifact.id]},
            {**steps[1], "status": "completed"},
        ]})

    def answer():
        db_session.expire_all()
        artifact = db_session.query(AgentArtifactRecord).filter_by(title="Verified value").one()
        yield from _answer_turn("The verified result is 12.{{cite:" + artifact.id + "}}")

    run_id = _execute(
        db_session, registry=registry, request=goal, allowed_tool_groups=("verification", "control"),
        scripts=(lambda: _tool_turn("declare", "update_plan", {"objective": goal, "steps": steps}),
                 lambda: _answer_turn("Everything is complete."), perform, settle_plan, answer),
    )
    assert db_session.get(AgentRun, run_id).status == "completed"
    assert db_session.query(AgentTurn).filter_by(run_id=run_id).count() == 5
    assert db_session.query(AgentToolInvocation).filter_by(run_id=run_id, tool_name="verification_evidence").count() == 1


@pytest.mark.parametrize("after_successful_tool", [False, True])
def test_context_budget_failure_is_durable_before_or_after_resource_discovery(
    db_session, after_successful_tool,
):
    registry = ToolRegistry().register(EchoTool())
    for index in range(96):
        class DiscoverableTool(ResourceProbeTool):
            name = f"verification_budget_probe_{index}"
            description = "Bounded context test schema. " * 32

        registry.register(DiscoverableTool([]))

    def provider(db, _project_id):
        if after_successful_tool and not db.query(AgentToolInvocation).filter_by(
            status="succeeded",
        ).first():
            return ()
        return (
            ProjectResourceDescriptor(
                kind=SYNTHETIC_RESOURCE_KIND, id="new-resource", version=1,
                name="Newly discoverable resource",
            ),
        )

    def call():
        yield from _tool_turn("saved-call", "verification_echo", {"value": "saved"})

    from engine.agent.run import RunLimits
    run_id = _execute(
        db_session,
        scripts=(call,) if after_successful_tool else (),
        registry=registry,
        project_id="budget-project", resource_refs=(), resource_providers=(provider,),
        limits=RunLimits(max_prompt_tokens=32_768),
    )
    run = db_session.get(AgentRun, run_id)
    assert run.status == "failed"
    assert run.error_code == "AGENT_CONTEXT_BUDGET_EXCEEDED"
    assert "停用不需要的扩展" in run.error_message
    assert "Bounded context test schema" not in run.error_message
    turns = db_session.query(AgentTurn).filter_by(run_id=run_id).all()
    invocations = db_session.query(AgentToolInvocation).filter_by(run_id=run_id).all()
    observations = db_session.query(AgentObservationRecord).filter_by(run_id=run_id).all()
    assert len(turns) == len(invocations) == len(observations) == int(after_successful_tool)
    assert all(turn.status == "completed" for turn in turns)
    assert all(invocation.status == "succeeded" for invocation in invocations)
    assert all(observation.status == "succeeded" for observation in observations)


def test_repeated_plan_rewording_stops_the_real_loop_without_task_evidence(db_session):
    from engine.tools.builtin.control import UpdatePlanCommand

    def change_plan(index):
        def call():
            yield from _tool_turn(f"plan-{index}", "update_plan", {
                "objective": f"Reworded objective {index}",
                "steps": [{"id": f"replacement-{index}", "title": f"Different phrasing {index}", "status": "in_progress"}],
                "summary": f"Intending to work {index}",
            })
        return call

    run_id = _execute(db_session, scripts=tuple(change_plan(i) for i in range(5)),
                      registry=ToolRegistry().register(UpdatePlanCommand()), allowed_tool_groups=("control",))
    run = db_session.get(AgentRun, run_id)
    assert run.status == "failed"
    assert run.error_code == "AGENT_NO_PROGRESS"
    assert db_session.query(AgentToolInvocation).filter_by(run_id=run_id, status="succeeded").count() == 3


def test_real_loop_persists_tool_observation_then_terminal_answer(db_session):
    def call():
        yield from _tool_turn("call-1", "verification_echo", {"value": "observed"})

    run_id = _execute(
        db_session,
        scripts=(call, lambda: _answer_turn("The capability observation completed.")),
        registry=ToolRegistry().register(EchoTool()),
    )
    run = db_session.get(AgentRun, run_id)
    invocation = db_session.query(AgentToolInvocation).filter_by(run_id=run_id).one()
    observation = db_session.query(AgentObservationRecord).filter_by(run_id=run_id).one()
    assert run is not None and run.status == "completed"
    assert invocation.status == "succeeded"
    assert observation.status == "succeeded"


def test_real_loop_parallelizes_only_parallel_safe_calls(db_session):
    with _EVENT_LOCK:
        _EVENTS.clear()

    def calls():
        yield from _tool_turn("call-a", "verification_echo", {"value": "A", "delay_seconds": 0.15}, index=0, finish=False)
        yield from _tool_turn("call-b", "verification_echo", {"value": "B", "delay_seconds": 0.15}, index=1)

    _execute(
        db_session,
        scripts=(calls, lambda: _answer_turn("Both observations completed.")),
        registry=ToolRegistry().register(EchoTool()),
        session_id="agent-core-parallel",
    )
    with _EVENT_LOCK:
        starts = {value: stamp for value, phase, stamp in _EVENTS if phase == "start"}
    assert abs(starts["A"] - starts["B"]) < 0.1


def test_real_loop_suspends_before_approval_tool_execution(db_session):
    with _EVENT_LOCK:
        _EVENTS.clear()

    def call():
        yield from _tool_turn("approval-1", "verification_approval", {"value": "blocked"})

    run_id = _execute(
        db_session,
        scripts=(call,),
        registry=ToolRegistry().register(ApprovalTool()),
        session_id="agent-core-approval",
    )
    run = db_session.get(AgentRun, run_id)
    invocation = db_session.query(AgentToolInvocation).filter_by(run_id=run_id).one()
    assert run is not None and run.status == "waiting_approval"
    assert invocation.status == "waiting_approval"
    assert _EVENTS == []


def test_project_resource_discovery_materializes_domain_tool_and_binds_invocation_authority(
    db_session,
):
    access_log: list[str] = []

    def provider(_db, project_id):
        assert project_id == "project-auto-resource"
        return (
            ProjectResourceDescriptor(
                kind=SYNTHETIC_RESOURCE_KIND,
                id="resource-a",
                version=7,
                name="Resource A",
            ),
        )

    def call():
        yield from _tool_turn(
            "resource-call",
            "verification_resource_probe",
            {"resource_id": "resource-a"},
        )

    resolver = (
        CompositeResourceResolver()
        .register(
            SYNTHETIC_RESOURCE_KIND,
            lambda ref: {"id": ref.id, "value": f"value:{ref.id}"},
        )
        .freeze()
    )
    run_id = _execute(
        db_session,
        scripts=(call, lambda: _answer_turn("Resource A was read.")),
        registry=ToolRegistry().register(ResourceProbeTool(access_log)),
        session_id="agent-core-auto-resource",
        project_id="project-auto-resource",
        resource_refs=(),
        resource_providers=(provider,),
        resource_resolver=resolver,
    )

    run = db_session.get(AgentRun, run_id)
    admitted_input = db_session.query(AgentSessionInput).filter_by(run_id=run_id).one()
    invocation = db_session.query(AgentToolInvocation).filter_by(run_id=run_id).one()
    assert run is not None and run.status == "completed"
    assert admitted_input.resource_refs_json == "[]"
    assert invocation.resource_refs_json == (
        '[{"id":"resource-a","kind":"verification.resource","version":7}]'
    )
    assert access_log == ["resource-a"]


def test_project_resource_invocation_rejects_identity_outside_discovery_ceiling(
    db_session,
):
    access_log: list[str] = []

    def provider(_db, _project_id):
        return (
            ProjectResourceDescriptor(
                kind=SYNTHETIC_RESOURCE_KIND,
                id="resource-a",
                version=1,
                name="Resource A",
            ),
        )

    def call():
        yield from _tool_turn(
            "resource-call-denied",
            "verification_resource_probe",
            {"resource_id": "resource-b"},
        )

    run_id = _execute(
        db_session,
        scripts=(call, lambda: _answer_turn("Resource B is unavailable.")),
        registry=ToolRegistry().register(ResourceProbeTool(access_log)),
        session_id="agent-core-resource-denied",
        project_id="project-resource-denied",
        resource_refs=(),
        resource_providers=(provider,),
        resource_resolver=CompositeResourceResolver().freeze(),
    )

    invocation = db_session.query(AgentToolInvocation).filter_by(run_id=run_id).one()
    assert invocation.status == "rejected"
    assert invocation.resource_refs_json == "[]"
    assert access_log == []
