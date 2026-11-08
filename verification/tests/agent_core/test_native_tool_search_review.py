"""Independent protocol/authority review; no live model or successful tool stub."""
from __future__ import annotations

import json
from threading import Event

import httpx
from openai import AsyncOpenAI
from pydantic import Field
import pytest
from sqlalchemy.orm import sessionmaker

from engine.agent.completion import CompletionGate
from engine.agent.coordinator import SessionCoordinator
from engine.agent.definition import AgentDefinition
from engine.agent.loop import RunLoop
from engine.agent.providers.openai import OpenAIModelAdapter
from engine.agent.repositories.session import SessionRepository
from engine.agent.turn import TurnStreamCancelled
from engine.models import AgentRun, AgentSession, AgentToolInvocation
from engine.runtime_composition import build_default_completion_policy, default_context_contributors
from engine.tools.materialization import ToolVersionMismatch, materialize_tools, require_current_tool
from engine.tools.runtime import BaseTool, ToolInputModel, ToolOutputModel, ToolPolicy, ToolPresentation, ToolRegistry


class ReviewInput(ToolInputModel):
    value: str


class OversizedInput(ToolInputModel):
    value: str = Field(description="parameter contract " * 8_000)


class ReviewOutput(ToolOutputModel):
    value: str


class ReviewProbe(BaseTool[ReviewInput, ReviewOutput]):
    name = "review_probe"
    group = "review"
    description = "Independent probe requiring explicit approval."
    input_model = ReviewInput
    output_model = ReviewOutput
    presentation = ToolPresentation(title="Review probe", category="explore")
    policy = ToolPolicy(requires_approval=True)

    def run(self, tool_input, context):
        raise AssertionError("Search must never grant execution permission")


def _stream_response(items, tools):
    events = []
    for index, item in enumerate(items):
        events.extend([
            {"type": "response.output_item.added", "output_index": index, "item": {**item, "status": "in_progress"}},
            {"type": "response.output_item.done", "output_index": index, "item": item},
        ])
    events.append({"type": "response.completed", "response": {
        "id": "resp_review", "object": "response", "created_at": 0, "model": "gpt-5.4",
        "status": "completed", "output": items, "parallel_tool_calls": False,
        "tool_choice": "auto", "tools": tools,
    }})
    body = "".join(f"event: {event['type']}\ndata: {json.dumps({**event, 'sequence_number': index})}\n\n"
                   for index, event in enumerate(events))
    return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=body)


def _coordinator(db_session, registry, handler, *, model="gpt-5.4", limits=None):
    from engine.agent.run import RunLimits
    factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)
    db_session.add(AgentSession(id="review-session", title="Independent search review"))
    db_session.commit()
    admission = SessionRepository(db_session).admit(
        session_id="review-session", resource_refs=(), content="Inspect the approved probe.",
        idempotency_key="review", llm_credential_id="fixture", api_base=None,
        model_name=model, request_payload={},
    )
    db_session.commit()

    def adapter(settings):
        return OpenAIModelAdapter(client=AsyncOpenAI(
            api_key="test-only", base_url="https://native-review.invalid/v1",
            http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)), max_retries=0,
        ), model_name=settings.model_name, owns_client=True)

    loop = RunLoop(session_factory=factory, model_factory=adapter, registry=registry,
                   definition=AgentDefinition(allowed_tool_groups=("review",), limits=limits or RunLimits()),
                   context_contributors=default_context_contributors(),
                   completion=CompletionGate(build_default_completion_policy()))
    return SessionCoordinator(session_factory=factory, run_loop=loop), admission.run_id


@pytest.mark.parametrize("forged", [False, True], ids=["approval-still-required", "search-cannot-invent-authority"])
def test_hosted_search_does_not_grant_execution_authority(db_session, forged):
    requests = []
    name = "unregistered_review_tool" if forged else "review_probe"

    def handler(request):
        payload = json.loads(request.content)
        requests.append(payload)
        if len(requests) == 1:
            schema = {"type": "function", "name": name, "description": "Loaded probe",
                      "parameters": {"type": "object", "properties": {"value": {"type": "string"}},
                                     "required": ["value"], "additionalProperties": False}, "strict": True}
            items = [
                {"id": "review_search", "type": "tool_search_call", "execution": "server", "call_id": None,
                 "status": "completed", "arguments": {"paths": [name]}},
                {"id": "review_search_output", "type": "tool_search_output", "execution": "server",
                 "call_id": None, "status": "completed", "tools": [schema]},
                {"id": "review_function", "type": "function_call", "call_id": "review_call", "name": name,
                 "status": "completed", "arguments": '{"value":"do not execute"}'},
            ]
        else:
            assert len(requests) == 2
            items = [{"id": "review_answer", "type": "message", "role": "assistant", "status": "completed",
                      "phase": "final_answer", "content": [{"type": "output_text", "text": "The requested tool is unavailable; no operation ran.",
                                                               "annotations": [], "logprobs": []}]}]
        return _stream_response(items, payload["tools"])

    coordinator, run_id = _coordinator(db_session, ToolRegistry().register(ReviewProbe()), handler)
    try:
        coordinator._drain_session("review-session", Event())
    finally:
        coordinator.stop()
    db_session.expire_all()
    invocation = db_session.query(AgentToolInvocation).filter_by(run_id=run_id).one()
    run = db_session.get(AgentRun, run_id)
    if forged:
        assert invocation.error_code == "UNKNOWN_TOOL"
        assert invocation.status != "succeeded"
        assert len(requests) == 2
    else:
        assert run.status == "waiting_approval"
        assert invocation.status == "waiting_approval"
        assert len(requests) == 1


def test_unsupported_model_schema_overflow_is_terminalized_by_coordinator(db_session):
    class LargeProbe(ReviewProbe):
        input_model = OversizedInput

    requests = []

    def handler(request):
        requests.append(request)
        raise AssertionError("Overflow must fail before provider admission")

    from engine.agent.run import RunLimits
    coordinator, run_id = _coordinator(db_session, ToolRegistry().register(LargeProbe()), handler, model="gpt-4o-mini", limits=RunLimits(max_prompt_tokens=32_768))
    try:
        coordinator._drain_session("review-session", Event())
    finally:
        coordinator.stop()
    db_session.expire_all()
    run = db_session.get(AgentRun, run_id)
    assert run.status == "failed"
    assert run.error_code == "AGENT_CONTEXT_BUDGET_EXCEEDED"
    assert requests == []
    sessions = SessionRepository(db_session)
    lease = sessions.claim(session_id="review-session", owner="next-worker", ttl_seconds=30)
    assert lease is not None
    sessions.release(lease=lease)
    db_session.commit()


def test_native_search_request_cancel_is_not_replayed_or_downgraded():
    cancelled = Event()
    requests = []

    def handler(request):
        requests.append(request.url.path)
        cancelled.set()
        return _stream_response([], [{"type": "tool_search"}])

    client = AsyncOpenAI(api_key="test-only", base_url="https://native-review.invalid/v1",
                         http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)), max_retries=0)
    adapter = OpenAIModelAdapter(client=client, model_name="gpt-5.4", owns_client=True)
    with pytest.raises(TurnStreamCancelled):
        list(adapter.stream(messages=[], tools=[{"type": "tool_search"}], cancellation_probe=cancelled.is_set))
    assert requests == ["/v1/responses"]


@pytest.mark.parametrize("change", ["disabled", "upgraded"])
def test_loaded_schema_cannot_replace_current_implementation_fence(change):
    original = ToolRegistry().register(ReviewProbe(), owner="review.owner", package_digest="a" * 64)
    frozen = materialize_tools(original, execution_mode="default")
    name = frozen.tools[0].name
    loaded_history = {"type": "tool_search_output", "execution": "server", "call_id": None,
                      "status": "completed", "tools": frozen.provider_schemas()}
    preserved = json.dumps(loaded_history, sort_keys=True)
    current = ToolRegistry()
    if change == "upgraded":
        # Same wire name and schema, new installed package: old durable call must fail.
        current.register(ReviewProbe(), owner="review.owner", package_digest="b" * 64)
    with pytest.raises(ToolVersionMismatch):
        require_current_tool(current, frozen, name=name, contract_hash=frozen.tools[0].contract_hash,
                             owner_id="review.owner", package_digest="a" * 64)
    assert json.dumps(loaded_history, sort_keys=True) == preserved
    # Provider projection operates on current materialization, never loaded history.
    projected = OpenAIModelAdapter.prepare_tools(model_name="gpt-5.4", tools=materialize_tools(
        current, execution_mode="default").provider_schemas())
    assert any(tool.get("name") == name for tool in projected) is (change == "upgraded")
