"""Agent Core harness tests through the real durable model/tool loop.

Capability DLC behavior is verified in the System and Bench suites. These
tests deliberately use a tiny namespaced test tool so Core stays domain-free.
"""

from __future__ import annotations

import json
import threading
import time

from sqlalchemy.orm import sessionmaker

from engine.agent.completion import CompletionGate
from engine.agent.definition import AgentDefinition
from engine.agent.events import LiveStreamHub
from engine.agent.loop import RunLoop
from engine.agent.repositories.session import SessionRepository
from engine.agent.resource_refs import ProjectResourceDescriptor
from engine.agent.turn import TurnStreamItem, TurnStreamKind, TurnTermination
from engine.models import (
    AgentObservationRecord,
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
        content="Exercise the real Agent loop.",
        idempotency_key=session_id,
        llm_credential_id="verification-credential",
        api_base=None,
        model_name="verification-model",
        request_payload={},
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
        completion=CompletionGate(build_default_completion_policy()),
        definition=AgentDefinition(allowed_tool_groups=("verification",)),
        live_stream=LiveStreamHub(),
        resource_providers=resource_providers,
        resource_resolver=resource_resolver,
    ).execute(lease=lease, run_id=admission.run_id)
    db_session.expire_all()
    return admission.run_id


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
