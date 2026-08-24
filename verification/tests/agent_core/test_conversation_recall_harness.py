from __future__ import annotations

import json

from sqlalchemy.orm import sessionmaker

from engine.agent.events import LiveStreamHub
from engine.agent.loop import RunLoop
from engine.agent.repositories.session import SessionRepository
from engine.agent.turn import TurnStreamItem, TurnStreamKind, TurnTermination
from engine.tools.runtime.attempt import ResourceScopeRef
from engine.models import AgentMessage, AgentObservationRecord, AgentRun, AgentSession
from engine.tools.builtin.conversation import (
    ConversationReadTool,
    ConversationSearchTool,
)
from engine.tools.runtime import ToolRegistry


EARLY_DECISION = "最早决策：发布代号是苍穹协议，预算为内部机密。"


def _tool_call(*, call_id: str, name: str, arguments: dict):
    encoded = json.dumps(arguments, ensure_ascii=False)
    yield TurnStreamItem(
        kind=TurnStreamKind.TOOL_CALL_START,
        item_id=f"tool:{call_id}",
        revision=1,
        tool_call_index=0,
        tool_call_id=call_id,
        tool_name=name,
        arguments_delta=encoded,
    )
    yield TurnStreamItem(
        kind=TurnStreamKind.TOOL_CALL_END,
        item_id=f"tool:{call_id}",
        revision=2,
        tool_call_index=0,
    )
    yield TurnStreamItem(
        kind=TurnStreamKind.MODEL_OUTPUT_ITEM,
        item_id=f"tool:{call_id}",
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


class RecallHarnessModel:
    def __init__(self, call_number: int):
        self.call_number = call_number

    def stream(self, *, messages, tools, timeout_seconds=None, stream_timeouts=None, cancellation_probe=None):
        serialized = json.dumps(messages, ensure_ascii=False)
        tool_names = {tool["name"] for tool in tools}
        assert {"conversation_search", "conversation_read"} <= tool_names

        if self.call_number == 1:
            assert EARLY_DECISION not in serialized
            assert "omitted_message_count" in serialized
            yield from _tool_call(
                call_id="search-history",
                name="conversation_search",
                arguments={"query": "苍穹协议", "roles": ["user"], "limit": 5},
            )
            return

        if self.call_number == 2:
            search_output = next(
                item
                for item in messages
                if item.get("type") == "function_call_output"
                and item.get("call_id") == "search-history"
            )
            search_facts = json.loads(search_output["output"])["facts"]
            assert search_facts["matches"][0]["sequence"] == 1
            assert "苍穹协议" in search_facts["matches"][0]["snippet"]
            yield from _tool_call(
                call_id="read-history",
                name="conversation_read",
                arguments={"after_sequence": 0, "limit": 5},
            )
            return

        read_output = next(
            item
            for item in messages
            if item.get("type") == "function_call_output"
            and item.get("call_id") == "read-history"
        )
        read_facts = json.loads(read_output["output"])["facts"]
        assert read_facts["messages"][0]["content"] == EARLY_DECISION
        answer = "本轮最早决定的发布代号是“苍穹协议”。"
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
            content=answer,
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
            model_output_item={
                "type": "message",
                "role": "assistant",
                "content": answer,
            },
        )
        yield TurnStreamItem(
            kind=TurnStreamKind.FINISH,
            item_id="finish",
            revision=1,
            termination=TurnTermination.COMPLETED,
        )


def test_long_conversation_recalls_evicted_message_through_the_real_run_loop(
    db_session,
    test_resource,
) -> None:
    session_id = "session_recall_harness"
    db_session.add(
        AgentSession(
            id=session_id,
            title="Recall harness",
            message_sequence=30,
        )
    )
    db_session.flush()
    for sequence in range(1, 31):
        db_session.add(
            AgentMessage(
                id=f"recall_history_{sequence}",
                session_id=session_id,
                role="user" if sequence % 2 else "assistant",
                content=(
                    EARLY_DECISION if sequence == 1 else f"普通历史消息 {sequence}"
                ),
                status="completed",
                sequence=sequence,
            )
        )
    db_session.commit()

    sessions = SessionRepository(db_session)
    admission = sessions.admit(
        session_id=session_id,
        resource_refs=(ResourceScopeRef(kind="verification.resource", id=str(test_resource.id), version="1:1"),),
        content="本轮最早决定的发布代号是什么？",
        idempotency_key="recall-harness",
        llm_credential_id="credential",
        api_base=None,
        model_name="test",
        request_payload={},
    )
    lease = sessions.claim(session_id=session_id, owner="worker", ttl_seconds=120)
    assert lease is not None
    sessions.promote_next_input(lease=lease)
    db_session.commit()

    calls = {"count": 0}

    def model_factory(_settings):
        calls["count"] += 1
        return RecallHarnessModel(calls["count"])

    registry = (
        ToolRegistry()
        .register(ConversationSearchTool())
        .register(ConversationReadTool())
    )
    factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)
    RunLoop(
        session_factory=factory,
        model_factory=model_factory,
        registry=registry,
        live_stream=LiveStreamHub(),
    ).execute(lease=lease, run_id=admission.run_id)

    db_session.expire_all()
    run = db_session.get(AgentRun, admission.run_id)
    answer = db_session.get(AgentMessage, admission.assistant_message_id)
    assert run is not None and run.status == "completed"
    assert (
        answer is not None and answer.content == "本轮最早决定的发布代号是“苍穹协议”。"
    )
    assert calls["count"] == 3
    observations = (
        db_session.query(AgentObservationRecord)
        .filter_by(run_id=admission.run_id)
        .order_by(AgentObservationRecord.sequence)
        .all()
    )
    assert len(observations) == 2
    assert all(
        EARLY_DECISION not in str(item.model_output_json) for item in observations
    )
