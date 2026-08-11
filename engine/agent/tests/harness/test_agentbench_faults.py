from __future__ import annotations

import json
import time

from sqlalchemy.orm import sessionmaker

from engine.agent.events import LiveStreamHub
from engine.agent.loop import RunLoop
from engine.agent.repositories.run import RunRepository
from engine.agent.repositories.session import SessionRepository
from engine.agent.turn import TurnStreamItem, TurnStreamKind, TurnTermination
from engine.models import AgentMessage, AgentRun, AgentSession, AgentToolInvocation
from engine.tools.runtime import ToolRegistry
from engine.tools.runtime.base import (
    BaseTool,
    ToolExecutionSpec,
    ToolInputModel,
    ToolOutputModel,
    ToolPresentation,
)
from engine.tools.runtime.semantics import ToolSemanticSpec


def _final_turn(content: str):
    yield TurnStreamItem(
        kind=TurnStreamKind.ANSWER_START,
        item_id="answer",
        revision=1,
        output_index=0,
    )
    yield TurnStreamItem(
        kind=TurnStreamKind.ANSWER_DELTA,
        item_id="answer",
        revision=2,
        content=content,
    )
    yield TurnStreamItem(
        kind=TurnStreamKind.ANSWER_END,
        item_id="answer",
        revision=3,
        output_index=0,
        message_status="completed",
    )
    yield TurnStreamItem(
        kind=TurnStreamKind.MODEL_OUTPUT_ITEM,
        item_id="answer",
        revision=4,
        output_index=0,
        model_output_item={"type": "message", "role": "assistant", "content": content},
    )
    yield TurnStreamItem(
        kind=TurnStreamKind.FINISH,
        item_id="finish",
        revision=1,
        termination=TurnTermination.COMPLETED,
    )


def _tool_turn(call_id: str, name: str):
    encoded = "{}"
    yield TurnStreamItem(
        kind=TurnStreamKind.TOOL_CALL_START,
        item_id="tool",
        revision=1,
        tool_call_index=0,
        tool_call_id=call_id,
        tool_name=name,
        arguments_delta=encoded,
    )
    yield TurnStreamItem(
        kind=TurnStreamKind.TOOL_CALL_END,
        item_id="tool",
        revision=2,
        tool_call_index=0,
    )
    yield TurnStreamItem(
        kind=TurnStreamKind.MODEL_OUTPUT_ITEM,
        item_id="tool",
        revision=3,
        output_index=0,
        model_output_item={
            "type": "function_call",
            "call_id": call_id,
            "name": name,
            "arguments": encoded,
        },
    )
    yield TurnStreamItem(
        kind=TurnStreamKind.FINISH,
        item_id="finish",
        revision=1,
        termination=TurnTermination.COMPLETED,
    )


def _admit(db_session, test_datasource, case_id: str):
    session_id = f"agentbench-fault-{case_id}"
    db_session.add(
        AgentSession(
            id=session_id,
            datasource_id=str(test_datasource.id),
            title=case_id,
        )
    )
    db_session.commit()
    sessions = SessionRepository(db_session)
    admission = sessions.admit(
        session_id=session_id,
        datasource_id=str(test_datasource.id),
        datasource_generation=1,
        content=f"fault scenario {case_id}",
        idempotency_key=case_id,
        llm_credential_id="deterministic-fixture",
        api_base=None,
        model_name="scripted",
        request_payload={"agentbench": True},
    )
    lease = sessions.claim(session_id=session_id, owner="agentbench", ttl_seconds=120)
    assert lease is not None
    sessions.promote_next_input(lease=lease)
    db_session.commit()
    return admission, lease


class _EmptyInput(ToolInputModel):
    pass


class _EmptyOutput(ToolOutputModel):
    count: int = 0


class _TimeoutTool(BaseTool[_EmptyInput, _EmptyOutput]):
    name = "agentbench_timeout"
    group = "query"
    description = "AgentBench-only deterministic timeout fixture."
    input_model = _EmptyInput
    output_model = _EmptyOutput
    presentation = ToolPresentation(title="Timeout fixture", category="query")
    execution = ToolExecutionSpec(timeout_seconds=1, capabilities=("database_read",))
    semantics = ToolSemanticSpec(contributes_progress=True)

    def run(self, tool_input, context):
        del tool_input, context
        time.sleep(1.2)
        return _EmptyOutput()


class _NoProgressTool(BaseTool[_EmptyInput, _EmptyOutput]):
    name = "agentbench_no_progress"
    group = "query"
    description = "AgentBench-only repeated empty observation fixture."
    input_model = _EmptyInput
    output_model = _EmptyOutput
    presentation = ToolPresentation(title="No progress fixture", category="query")
    execution = ToolExecutionSpec(capabilities=("database_read",))
    semantics = ToolSemanticSpec(contributes_progress=True)

    def run(self, tool_input, context):
        del tool_input, context
        return _EmptyOutput()


def test_retryable_provider_failure_recovers_through_the_real_run_loop(
    db_session,
    test_datasource,
) -> None:
    admission, lease = _admit(db_session, test_datasource, "provider-429")
    calls = {"count": 0}

    class Provider:
        def stream(self, **_kwargs):
            calls["count"] += 1
            if calls["count"] == 1:
                yield TurnStreamItem(
                    kind=TurnStreamKind.ERROR,
                    item_id="error",
                    revision=1,
                    error_code="MODEL_PROVIDER_RATE_LIMITED",
                    error_message="rate limited",
                    error_retryable=True,
                    retry_after_seconds=0,
                )
                return
            yield from _final_turn("已在可重试故障后恢复。")

    factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)
    RunLoop(
        session_factory=factory,
        model_factory=lambda _settings: Provider(),
        live_stream=LiveStreamHub(),
    ).execute(lease=lease, run_id=admission.run_id)
    db_session.expire_all()
    run = db_session.get(AgentRun, admission.run_id)
    assert run is not None and run.status == "completed"
    assert calls["count"] == 2
    assert int(run.provider_retry_count) == 1


def test_partial_stream_failure_never_commits_partial_text(
    db_session,
    test_datasource,
) -> None:
    admission, lease = _admit(db_session, test_datasource, "stream-interrupt")

    class Provider:
        def stream(self, **_kwargs):
            yield TurnStreamItem(
                kind=TurnStreamKind.ANSWER_START,
                item_id="answer",
                revision=1,
                output_index=0,
            )
            yield TurnStreamItem(
                kind=TurnStreamKind.ANSWER_DELTA,
                item_id="answer",
                revision=2,
                content="不应成为最终答案",
            )
            yield TurnStreamItem(
                kind=TurnStreamKind.ERROR,
                item_id="error",
                revision=1,
                error_code="MODEL_PROVIDER_STREAM_FAILED",
                error_message="stream interrupted",
                error_retryable=False,
            )

    factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)
    RunLoop(
        session_factory=factory,
        model_factory=lambda _settings: Provider(),
        live_stream=LiveStreamHub(),
    ).execute(lease=lease, run_id=admission.run_id)
    db_session.expire_all()
    run = db_session.get(AgentRun, admission.run_id)
    answer = db_session.get(AgentMessage, admission.assistant_message_id)
    assert run is not None and run.status == "failed"
    assert answer is not None and "不应成为最终答案" not in str(answer.content or "")


def test_durable_cancel_before_provider_call_is_terminal_and_model_is_not_called(
    db_session,
    test_datasource,
) -> None:
    admission, lease = _admit(db_session, test_datasource, "user-cancel")
    RunRepository(db_session).request_cancel(run_id=admission.run_id)
    db_session.commit()
    called = {"value": False}

    def model_factory(_settings):
        called["value"] = True
        raise AssertionError("cancelled Run must not call the Provider")

    factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)
    RunLoop(
        session_factory=factory,
        model_factory=model_factory,
        live_stream=LiveStreamHub(),
    ).execute(lease=lease, run_id=admission.run_id)
    db_session.expire_all()
    run = db_session.get(AgentRun, admission.run_id)
    assert run is not None and run.status == "cancelled"
    assert called["value"] is False


def test_tool_timeout_is_visible_to_the_next_model_turn_and_never_late_commits(
    db_session,
    test_datasource,
) -> None:
    admission, lease = _admit(db_session, test_datasource, "tool-timeout")
    calls = {"count": 0}

    class Provider:
        def stream(self, *, messages, **_kwargs):
            calls["count"] += 1
            if calls["count"] == 1:
                yield from _tool_turn("timeout-call", "agentbench_timeout")
                return
            payload = json.dumps(messages, ensure_ascii=False)
            assert "TOOL_TIMEOUT" in payload
            yield from _final_turn("工具超时，未取得可验证结果。")

    registry = ToolRegistry().register(_TimeoutTool())
    factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)
    loop = RunLoop(
        session_factory=factory,
        model_factory=lambda _settings: Provider(),
        registry=registry,
        live_stream=LiveStreamHub(),
    )
    loop.execute(lease=lease, run_id=admission.run_id)
    loop.close()
    db_session.expire_all()
    invocation = (
        db_session.query(AgentToolInvocation).filter_by(run_id=admission.run_id).one()
    )
    assert invocation.status == "failed"
    assert invocation.error_code == "TOOL_TIMEOUT"


def test_repeated_identical_empty_observations_stop_within_the_tool_budget(
    db_session,
    test_datasource,
) -> None:
    admission, lease = _admit(db_session, test_datasource, "no-progress")
    calls = {"count": 0}

    class Provider:
        def stream(self, **_kwargs):
            calls["count"] += 1
            yield from _tool_turn(
                f"no-progress-{calls['count']}",
                "agentbench_no_progress",
            )

    registry = ToolRegistry().register(_NoProgressTool())
    factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)
    loop = RunLoop(
        session_factory=factory,
        model_factory=lambda _settings: Provider(),
        registry=registry,
        live_stream=LiveStreamHub(),
    )
    loop.execute(lease=lease, run_id=admission.run_id)
    loop.close()
    db_session.expire_all()
    invocations = (
        db_session.query(AgentToolInvocation).filter_by(run_id=admission.run_id).all()
    )
    run = db_session.get(AgentRun, admission.run_id)
    assert run is not None and run.status in {"failed", "completed"}
    assert len(invocations) <= 4
