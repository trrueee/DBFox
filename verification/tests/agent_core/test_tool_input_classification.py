from __future__ import annotations

import json

from sqlalchemy.orm import sessionmaker

from engine.agent.events import LiveStreamHub
from engine.agent.loop import RunLoop
from engine.agent.repositories.session import SessionRepository
from engine.agent.turn import TurnStreamItem, TurnStreamKind, TurnTermination
from engine.tools.runtime.attempt import ResourceScopeRef
from engine.models import (
    AgentMessage,
    AgentObservationRecord,
    AgentRun,
    AgentSession,
    AgentToolInvocation,
)


def _tool_turn(call_id: str, name: str, arguments: dict[str, object]):
    encoded = json.dumps(arguments, ensure_ascii=False)
    yield TurnStreamItem(
        kind=TurnStreamKind.TOOL_CALL_START,
        item_id="tool:0",
        revision=1,
        tool_call_index=0,
        tool_call_id=call_id,
        tool_name=name,
        arguments_delta=encoded,
    )
    yield TurnStreamItem(
        kind=TurnStreamKind.TOOL_CALL_END,
        item_id="tool:0",
        revision=2,
        tool_call_index=0,
    )
    yield TurnStreamItem(
        kind=TurnStreamKind.MODEL_OUTPUT_ITEM,
        item_id="tool:0",
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


def _final_turn(content: str):
    yield TurnStreamItem(
        kind=TurnStreamKind.ANSWER_START,
        item_id="answer",
        revision=1,
        output_index=0,
        phase="final_answer",
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
        phase="final_answer",
        message_status="completed",
    )
    yield TurnStreamItem(
        kind=TurnStreamKind.MODEL_OUTPUT_ITEM,
        item_id="answer",
        revision=4,
        output_index=0,
        model_output_item={
            "type": "message",
            "role": "assistant",
            "phase": "final_answer",
            "content": content,
        },
    )
    yield TurnStreamItem(
        kind=TurnStreamKind.FINISH,
        item_id="finish",
        revision=1,
        termination=TurnTermination.COMPLETED,
    )


class _InvalidThenRecoverProvider:
    def __init__(self, turn: int) -> None:
        self.turn = turn

    def stream(self, *, messages, tools, timeout_seconds=None, cancellation_probe=None):
        del tools, timeout_seconds, cancellation_probe
        if self.turn == 1:
            yield from _tool_turn("empty-plan", "update_plan", {})
            return

        output = next(
            item
            for item in messages
            if item.get("type") == "function_call_output"
            and item.get("call_id") == "empty-plan"
        )
        observation = json.loads(str(output["output"]))
        assert observation["status"] == "rejected"
        assert observation["error_code"] == "TOOL_INPUT_INVALID"
        assert "objective (missing)" in observation["summary"]
        assert "steps (missing)" in observation["summary"]
        yield from _final_turn("参数不完整，已停止该工具调用。")


class _UnavailablePlanArtifactThenRecoverProvider:
    def __init__(self, turn: int) -> None:
        self.turn = turn

    def stream(self, *, messages, tools, timeout_seconds=None, cancellation_probe=None):
        del tools, timeout_seconds, cancellation_probe
        if self.turn == 1:
            yield from _tool_turn(
                "unavailable-plan-artifact",
                "update_plan",
                {
                    "objective": "复用尚未读取的结果",
                    "steps": [
                        {
                            "id": "reuse",
                            "title": "复用结果",
                            "status": "completed",
                            "evidence_required": True,
                            "artifact_ids": ["artifact-not-observed"],
                        }
                    ],
                },
            )
            return

        output = next(
            item
            for item in messages
            if item.get("type") == "function_call_output"
            and item.get("call_id") == "unavailable-plan-artifact"
        )
        observation = json.loads(str(output["output"]))
        assert observation["status"] == "rejected"
        assert observation["error_code"] == "TOOL_INPUT_INVALID"
        assert "Inspect the saved result" in observation["summary"]
        yield from _final_turn("该结果尚未读取，因此没有写入分析计划。")


def test_invalid_tool_arguments_have_a_distinct_durable_classification(
    db_session,
    test_resource,
) -> None:
    session_id = "tool-input-invalid"
    db_session.add(
        AgentSession(
            id=session_id,
            title="Tool input classification",
        )
    )
    db_session.commit()
    sessions = SessionRepository(db_session)
    admission = sessions.admit(
        session_id=session_id,
        resource_refs=(ResourceScopeRef(kind="verification.resource", id=str(test_resource.id), version="1:1"),),
        content="制定一个分析计划。",
        idempotency_key="tool-input-invalid",
        llm_credential_id="deterministic-fixture",
        api_base=None,
        model_name="scripted",
        request_payload={},
    )
    lease = sessions.claim(session_id=session_id, owner="test", ttl_seconds=120)
    assert lease is not None
    sessions.promote_next_input(lease=lease)
    db_session.commit()

    turn = {"value": 0}

    def model_factory(_settings):
        turn["value"] += 1
        return _InvalidThenRecoverProvider(turn["value"])

    factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)
    RunLoop(
        session_factory=factory,
        model_factory=model_factory,
        live_stream=LiveStreamHub(),
    ).execute(lease=lease, run_id=admission.run_id)

    db_session.expire_all()
    run = db_session.get(AgentRun, admission.run_id)
    answer = db_session.get(AgentMessage, admission.assistant_message_id)
    invocation = (
        db_session.query(AgentToolInvocation).filter_by(run_id=admission.run_id).one()
    )
    observation = (
        db_session.query(AgentObservationRecord)
        .filter_by(run_id=admission.run_id)
        .one()
    )

    assert run is not None and run.status == "completed"
    assert answer is not None and answer.content == "参数不完整，已停止该工具调用。"
    assert turn["value"] == 2
    assert invocation.status == "rejected"
    assert invocation.error_code == "TOOL_INPUT_INVALID"
    assert observation.error_code == "TOOL_INPUT_INVALID"
    assert "objective (missing)" in str(observation.model_output_json)


def test_control_command_domain_input_error_does_not_fail_the_run(
    db_session,
    test_resource,
) -> None:
    session_id = "control-domain-input-invalid"
    db_session.add(
        AgentSession(
            id=session_id,
            title="Control input classification",
        )
    )
    db_session.commit()
    sessions = SessionRepository(db_session)
    admission = sessions.admit(
        session_id=session_id,
        resource_refs=(ResourceScopeRef(kind="verification.resource", id=str(test_resource.id), version="1:1"),),
        content="把之前的结果写入计划。",
        idempotency_key="control-domain-input-invalid",
        llm_credential_id="deterministic-fixture",
        api_base=None,
        model_name="scripted",
        request_payload={},
    )
    lease = sessions.claim(session_id=session_id, owner="test", ttl_seconds=120)
    assert lease is not None
    sessions.promote_next_input(lease=lease)
    db_session.commit()

    turn = {"value": 0}

    def model_factory(_settings):
        turn["value"] += 1
        return _UnavailablePlanArtifactThenRecoverProvider(turn["value"])

    factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)
    RunLoop(
        session_factory=factory,
        model_factory=model_factory,
        live_stream=LiveStreamHub(),
    ).execute(lease=lease, run_id=admission.run_id)

    db_session.expire_all()
    run = db_session.get(AgentRun, admission.run_id)
    answer = db_session.get(AgentMessage, admission.assistant_message_id)
    invocation = (
        db_session.query(AgentToolInvocation).filter_by(run_id=admission.run_id).one()
    )
    observation = (
        db_session.query(AgentObservationRecord)
        .filter_by(run_id=admission.run_id)
        .one()
    )

    assert run is not None and run.status == "completed"
    assert answer is not None
    assert answer.content == "该结果尚未读取，因此没有写入分析计划。"
    assert turn["value"] == 2
    assert invocation.status == "rejected"
    assert invocation.error_code == "TOOL_INPUT_INVALID"
    assert observation.error_code == "TOOL_INPUT_INVALID"
