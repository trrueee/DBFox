from __future__ import annotations

import json

import pytest
from sqlalchemy.orm import sessionmaker

from engine.agent.events import LiveStreamHub
from engine.agent.loop import RunLoop
from engine.agent.repositories.session import SessionRepository
from engine.agent.turn import TurnStreamItem, TurnStreamKind, TurnTermination
from engine.environment.schema_catalog_sync import ensure_catalog
from engine.json_codec import load_object
from engine.models import AgentArtifactRecord, AgentMessage, AgentRun, AgentSession


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
        model_output_item={
            "type": "message",
            "role": "assistant",
            "content": content,
        },
    )
    yield TurnStreamItem(
        kind=TurnStreamKind.FINISH,
        item_id="finish",
        revision=1,
        termination=TurnTermination.COMPLETED,
    )


class _SQLiteScenarioProvider:
    def __init__(self, turn: int, *, filter_value: str) -> None:
        self.turn = turn
        self.filter_value = filter_value

    def stream(self, *, messages, tools, timeout_seconds=None, cancellation_probe=None):
        del tools, timeout_seconds, cancellation_probe
        if self.turn == 1:
            yield from _tool_turn(
                "preview-call",
                "data_preview",
                {
                    "table": "orders",
                    "columns": ["id", "status"],
                    "limit": 5,
                    "where": {
                        "column": "status",
                        "op": "=",
                        "value": self.filter_value,
                    },
                },
            )
            return
        assert any(
            item.get("type") == "function_call_output"
            and item.get("call_id") == "preview-call"
            for item in messages
        )
        yield from _final_turn("数据预览已经完成。")


@pytest.mark.parametrize(
    ("case_id", "filter_value", "expected_rows"),
    [
        ("matching", "completed", 1),
        ("quote_injection", "completed' OR 1=1 --", 0),
    ],
)
def test_sqlite_harness_tool_loop_is_deterministic(
    db_session,
    test_datasource,
    case_id: str,
    filter_value: str,
    expected_rows: int,
) -> None:
    ensure_catalog(db_session, str(test_datasource.id))
    session_id = f"sqlite-harness-{case_id}"
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
        content="预览 completed 订单",
        idempotency_key=case_id,
        llm_credential_id="deterministic-fixture",
        api_base=None,
        model_name="scripted",
        request_payload={},
    )
    lease = sessions.claim(session_id=session_id, owner="harness", ttl_seconds=120)
    assert lease is not None
    sessions.promote_next_input(lease=lease)
    db_session.commit()

    turn = {"value": 0}

    def model_factory(_settings):
        turn["value"] += 1
        return _SQLiteScenarioProvider(turn["value"], filter_value=filter_value)

    factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)
    RunLoop(
        session_factory=factory,
        model_factory=model_factory,
        live_stream=LiveStreamHub(),
    ).execute(lease=lease, run_id=admission.run_id)

    db_session.expire_all()
    run = db_session.get(AgentRun, admission.run_id)
    answer = db_session.get(AgentMessage, admission.assistant_message_id)
    sql_artifact = (
        db_session.query(AgentArtifactRecord)
        .filter_by(run_id=admission.run_id, type="sql")
        .one()
    )
    payload = load_object(str(sql_artifact.payload_json))
    assert run is not None and run.status == "completed"
    assert answer is not None and answer.content.startswith("数据预览已经完成。")
    assert turn["value"] == 2
    assert filter_value not in str(payload["safeSql"])
    assert payload["parameters"] == {"dbfox_p0": filter_value}
    result_artifact = (
        db_session.query(AgentArtifactRecord)
        .filter_by(run_id=admission.run_id, type="result_view")
        .one()
    )
    result_payload = load_object(str(result_artifact.payload_json))
    assert result_payload["returnedRows"] == expected_rows
