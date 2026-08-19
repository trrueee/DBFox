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
from engine.tools.runtime.attempt import ResourceScopeRef
from engine.models import (
    AgentArtifactRecord,
    AgentMessage,
    AgentRun,
    AgentSession,
    AgentTaskPlanRecord,
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
    def __init__(self, turn: int, *, table: str, filter_value: str) -> None:
        self.turn = turn
        self.table = table
        self.filter_value = filter_value

    def stream(self, *, messages, tools, timeout_seconds=None, cancellation_probe=None):
        del tools, timeout_seconds, cancellation_probe
        if self.turn == 1:
            yield from _tool_turn(
                "preview-call",
                "data_preview",
                {
                    "table": self.table,
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


class _PreviewRecoveryProvider:
    def __init__(self, turn: int) -> None:
        self.turn = turn

    def stream(self, *, messages, tools, timeout_seconds=None, cancellation_probe=None):
        del tools, timeout_seconds, cancellation_probe
        serialized = json.dumps(messages, ensure_ascii=False)
        if self.turn == 1:
            yield from _tool_turn(
                "bad-preview",
                "data_preview",
                {"table": "main.orders", "columns": ["missing"], "limit": 5},
            )
            return
        if self.turn == 2:
            assert "TOOL_INPUT_ERROR" in serialized
            assert "Column(s) not found in main.orders: missing" in serialized
            yield from _tool_turn(
                "inspect-orders",
                "schema_inspect",
                {"targets": ["main.orders"]},
            )
            return
        if self.turn == 3:
            inspect_output = next(
                item
                for item in messages
                if item.get("type") == "function_call_output"
                and item.get("call_id") == "inspect-orders"
            )
            observation = json.loads(str(inspect_output["output"]))
            assert observation["status"] == "succeeded"
            yield from _tool_turn(
                "corrected-preview",
                "data_preview",
                {"table": "main.orders", "columns": ["id", "status"], "limit": 5},
            )
            return
        corrected_output = next(
            item
            for item in messages
            if item.get("type") == "function_call_output"
            and item.get("call_id") == "corrected-preview"
        )
        observation = json.loads(str(corrected_output["output"]))
        assert observation["status"] == "succeeded"
        yield from _final_turn("已根据结构信息修正列名并完成预览。")


class _CatalogPivotAfterValidationProvider:
    """Prove that validation is not mistaken for the end of discovery."""

    def __init__(self, turn: int) -> None:
        self.turn = turn

    def stream(self, *, messages, tools, timeout_seconds=None, cancellation_probe=None):
        del timeout_seconds, cancellation_probe
        available = {
            str(item.get("name") or item.get("function", {}).get("name") or "")
            for item in tools
        }
        assert "schema_inspect" in available
        if self.turn == 1:
            yield from _tool_turn(
                "validate-orders",
                "sql_validate",
                {"sql": "SELECT COUNT(*) AS total FROM orders"},
            )
            return
        if self.turn == 2:
            serialized = json.dumps(messages, ensure_ascii=False)
            assert "validation_artifact_id" in serialized
            yield from _tool_turn(
                "inspect-customers",
                "schema_inspect",
                {"targets": ["main.customers"]},
            )
            return
        serialized = json.dumps(messages, ensure_ascii=False)
        assert "inspect-customers" in serialized
        yield from _final_turn("已在验证查询后继续检查关联表结构。")


class _PlanExecutionProvider:
    """Exercise the public plan as part of the production tool loop."""

    def __init__(self, turn: int) -> None:
        self.turn = turn

    def stream(self, *, messages, tools, timeout_seconds=None, cancellation_probe=None):
        del timeout_seconds, cancellation_probe
        available = {
            str(item.get("name") or item.get("function", {}).get("name") or "")
            for item in tools
        }
        assert {"update_plan", "data_preview"} <= available
        serialized = json.dumps(messages, ensure_ascii=False)
        if self.turn == 1:
            yield from _tool_turn(
                "plan-create",
                "update_plan",
                {
                    "objective": "预览订单并形成结论",
                    "steps": [
                        {"id": "preview", "title": "预览订单", "status": "in_progress"},
                        {"id": "conclude", "title": "形成结论", "status": "pending"},
                    ],
                    "summary": "先读取小样本。",
                },
            )
            return
        if self.turn == 2:
            assert "plan-create" in serialized
            yield from _tool_turn(
                "plan-preview",
                "data_preview",
                {"table": "main.orders", "columns": ["id", "status"], "limit": 5},
            )
            return
        if self.turn == 3:
            assert "plan-preview" in serialized
            yield from _tool_turn(
                "plan-progress",
                "update_plan",
                {
                    "objective": "预览订单并形成结论",
                    "steps": [
                        {"id": "preview", "title": "预览订单", "status": "completed"},
                        {"id": "conclude", "title": "形成结论", "status": "in_progress"},
                    ],
                    "summary": "样本读取完成，正在归纳。",
                },
            )
            return
        if self.turn == 4:
            assert "plan-progress" in serialized
            yield from _tool_turn(
                "plan-complete",
                "update_plan",
                {
                    "objective": "预览订单并形成结论",
                    "steps": [
                        {"id": "preview", "title": "预览订单", "status": "completed"},
                        {"id": "conclude", "title": "形成结论", "status": "completed"},
                    ],
                    "summary": "分析步骤均已完成。",
                },
            )
            return
        assert "plan-complete" in serialized
        yield from _final_turn("订单样本预览和结论整理均已完成。")


@pytest.mark.parametrize(
    ("case_id", "table", "filter_value", "expected_rows"),
    [
        ("matching", "orders", "completed", 1),
        ("qualified_name", "main.orders", "completed", 1),
        ("quote_injection", "orders", "completed' OR 1=1 --", 0),
    ],
)
def test_sqlite_harness_tool_loop_is_deterministic(
    db_session,
    test_datasource,
    case_id: str,
    table: str,
    filter_value: str,
    expected_rows: int,
) -> None:
    ensure_catalog(db_session, str(test_datasource.id))
    session_id = f"sqlite-harness-{case_id}"
    db_session.add(
        AgentSession(id=session_id, project_id=None,
            datasource_id=str(test_datasource.id),
            title=case_id,
        )
    )
    db_session.commit()
    sessions = SessionRepository(db_session)
    admission = sessions.admit(
        session_id=session_id,
        resource_refs=(ResourceScopeRef(kind="database", id=str(test_datasource.id), version=1),),
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
        return _SQLiteScenarioProvider(
            turn["value"],
            table=table,
            filter_value=filter_value,
        )

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
    if "." in table:
        assert 'FROM "main"."orders"' in str(payload["safeSql"])
    assert filter_value not in str(payload["safeSql"])
    assert payload["parameters"] == {"dbfox_p0": filter_value}
    result_artifact = (
        db_session.query(AgentArtifactRecord)
        .filter_by(run_id=admission.run_id, type="result_view")
        .one()
    )
    result_payload = load_object(str(result_artifact.payload_json))
    assert result_payload["returnedRows"] == expected_rows


def test_sqlite_harness_recovers_from_actionable_preview_input_error(
    db_session,
    test_datasource,
) -> None:
    ensure_catalog(db_session, str(test_datasource.id))
    session_id = "sqlite-harness-preview-recovery"
    db_session.add(
        AgentSession(id=session_id, project_id=None,
            datasource_id=str(test_datasource.id),
            title="preview-recovery",
        )
    )
    db_session.commit()
    sessions = SessionRepository(db_session)
    admission = sessions.admit(
        session_id=session_id,
        resource_refs=(ResourceScopeRef(kind="database", id=str(test_datasource.id), version=1),),
        content="预览订单；输入错误时先检查结构再修正。",
        idempotency_key="preview-recovery",
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
        return _PreviewRecoveryProvider(turn["value"])

    factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)
    RunLoop(
        session_factory=factory,
        model_factory=model_factory,
        live_stream=LiveStreamHub(),
    ).execute(lease=lease, run_id=admission.run_id)

    db_session.expire_all()
    run = db_session.get(AgentRun, admission.run_id)
    answer = db_session.get(AgentMessage, admission.assistant_message_id)
    invocations = (
        db_session.query(AgentToolInvocation)
        .filter_by(run_id=admission.run_id)
        .order_by(AgentToolInvocation.created_at)
        .all()
    )
    assert run is not None and run.status == "completed"
    assert answer is not None
    assert answer.content == "已根据结构信息修正列名并完成预览。"
    assert turn["value"] == 4
    assert [item.tool_name for item in invocations] == [
        "data_preview",
        "schema_inspect",
        "data_preview",
    ]
    assert invocations[0].status == "failed"
    assert invocations[0].error_code == "TOOL_INPUT_ERROR"
    assert invocations[1].status == "succeeded"
    assert invocations[2].status == "succeeded"


def test_sqlite_harness_keeps_catalog_available_for_multi_stage_pivot(
    db_session,
    test_datasource,
) -> None:
    ensure_catalog(db_session, str(test_datasource.id))
    session_id = "sqlite-harness-catalog-pivot"
    db_session.add(
        AgentSession(id=session_id, project_id=None,
            datasource_id=str(test_datasource.id),
            title="catalog-pivot",
        )
    )
    db_session.commit()
    sessions = SessionRepository(db_session)
    admission = sessions.admit(
        session_id=session_id,
        resource_refs=(ResourceScopeRef(kind="database", id=str(test_datasource.id), version=1),),
        content="先验证订单计数查询，再检查 customers 表结构。",
        idempotency_key="catalog-pivot",
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
        return _CatalogPivotAfterValidationProvider(turn["value"])

    factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)
    RunLoop(
        session_factory=factory,
        model_factory=model_factory,
        live_stream=LiveStreamHub(),
    ).execute(lease=lease, run_id=admission.run_id)

    db_session.expire_all()
    run = db_session.get(AgentRun, admission.run_id)
    invocations = (
        db_session.query(AgentToolInvocation)
        .filter_by(run_id=admission.run_id)
        .order_by(AgentToolInvocation.created_at)
        .all()
    )
    assert run is not None and run.status == "completed"
    assert turn["value"] == 3
    assert [item.tool_name for item in invocations] == [
        "sql_validate",
        "schema_inspect",
    ]


def test_sqlite_harness_persists_and_executes_a_multi_stage_plan(
    db_session,
    test_datasource,
) -> None:
    ensure_catalog(db_session, str(test_datasource.id))
    session_id = "sqlite-harness-plan-execution"
    db_session.add(
        AgentSession(id=session_id, project_id=None,
            datasource_id=str(test_datasource.id),
            title="plan-execution",
        )
    )
    db_session.commit()
    sessions = SessionRepository(db_session)
    admission = sessions.admit(
        session_id=session_id,
        resource_refs=(ResourceScopeRef(kind="database", id=str(test_datasource.id), version=1),),
        content="制定计划，预览订单并形成结论。",
        idempotency_key="plan-execution",
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
        return _PlanExecutionProvider(turn["value"])

    factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)
    RunLoop(
        session_factory=factory,
        model_factory=model_factory,
        live_stream=LiveStreamHub(),
    ).execute(lease=lease, run_id=admission.run_id)

    db_session.expire_all()
    run = db_session.get(AgentRun, admission.run_id)
    plan = (
        db_session.query(AgentTaskPlanRecord)
        .filter_by(run_id=admission.run_id)
        .one()
    )
    invocations = (
        db_session.query(AgentToolInvocation)
        .filter_by(run_id=admission.run_id)
        .order_by(AgentToolInvocation.created_at)
        .all()
    )
    steps = json.loads(str(plan.steps_json))
    assert run is not None and run.status == "completed"
    assert turn["value"] == 5
    assert plan.version == 3
    assert plan.status == "completed"
    assert [step["id"] for step in steps] == ["preview", "conclude"]
    assert [step["status"] for step in steps] == ["completed", "completed"]
    assert [item.tool_name for item in invocations] == [
        "update_plan",
        "data_preview",
        "update_plan",
        "update_plan",
    ]
