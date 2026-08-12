import json
import re

from sqlalchemy.orm import sessionmaker

from engine.agent.context import ContextArtifact, ContextObservation, ContextSnapshot
from engine.agent.events import LiveStreamHub
from engine.agent.definition import AgentDefinition
from engine.agent.loop import RunLoop, _relevant_tool_groups
from engine.agent.repositories.artifact import ArtifactRepository
from engine.agent.repositories.run import RunRepository
from engine.agent.repositories.session import SessionRepository
from engine.agent.run import RunLimits
from engine.agent.turn import TurnStreamItem, TurnStreamKind, TurnTermination
from engine.app.safe_errors import FixedErrorCode, fixed_error_message
from engine.llm.config import LlmConfigurationError
from engine.models import (
    AgentEvidenceRecord,
    AgentMessage,
    AgentObservationRecord,
    AgentRun,
    AgentRunItemRecord,
    AgentSession,
    AgentToolInvocation,
    AgentTurn,
)
from engine.tools.builtin.query import SqlExecuteReadonlyTool, SqlValidateTool
from engine.tools.builtin.artifacts import query_result_draft, sql_validation_drafts
from engine.tools.builtin.contracts import QueryResultOutput, SqlValidateOutput
from engine.tools.runtime import (
    ToolOutcome,
    ToolRegistry,
)
from engine.tools.runtime.semantics import ToolSemanticCapability


def _tool_context(**updates):
    values = {
        "session_id": "session",
        "run_id": "run",
        "context_epoch": 0,
        "messages": [],
        "sources": [],
        "hash": "hash",
    }
    values.update(updates)
    return ContextSnapshot(**values)


def test_tool_disclosure_only_hides_result_without_durable_prerequisites():
    configured = {"control", "conversation", "catalog", "query", "result"}
    assert _relevant_tool_groups(configured, _tool_context()) == {
        "control",
        "conversation",
        "catalog",
        "query",
    }


def test_tool_disclosure_restores_recall_and_result_groups_from_context():
    configured = {"control", "conversation", "catalog", "query", "result"}
    context = _tool_context(
        conversation_archive={"omitted_message_count": 3},
        selected_artifacts=[
            ContextArtifact(
                id="artifact_result",
                type="result_view",
                title="Result",
            )
        ],
    )
    assert _relevant_tool_groups(configured, context) == configured


def test_tool_disclosure_keeps_catalog_after_executable_validation():
    configured = {"control", "conversation", "catalog", "query", "result"}
    context = _tool_context(
        observations=[
            ContextObservation(
                id="observation",
                tool_name="sql_validate",
                status="succeeded",
                summary="Validated",
                facts={"can_execute": True},
                capabilities=(ToolSemanticCapability.VALIDATED_QUERY.value,),
            )
        ]
    )
    assert _relevant_tool_groups(configured, context) == {
        "control",
        "conversation",
        "catalog",
        "query",
    }


def test_tool_disclosure_restores_result_from_session_memory():
    configured = {"control", "conversation", "catalog", "query", "result"}
    context = _tool_context(
        session_memory={
            "stable_context": {
                "evidence_references": [
                    {"artifact_id": "artifact_result_from_previous_run"}
                ]
            }
        }
    )

    assert _relevant_tool_groups(configured, context) == configured


def test_tool_disclosure_restores_result_for_failed_run_recovery():
    configured = {"control", "conversation", "catalog", "query", "result"}
    context = _tool_context(
        previous_run_outcome={
            "status": "failed",
            "tool_outcomes": [
                {
                    "tool": "sql_execute_readonly",
                    "status": "succeeded",
                    "artifact_ids": ["artifact_result_before_failure"],
                    "artifacts": [
                        {
                            "id": "artifact_result_before_failure",
                            "type": "result_view",
                        }
                    ],
                }
            ],
        }
    )

    assert _relevant_tool_groups(configured, context) == configured


def test_tool_disclosure_does_not_treat_non_result_artifact_as_result():
    configured = {"control", "conversation", "catalog", "query", "result"}
    context = _tool_context(
        previous_run_outcome={
            "status": "failed",
            "tool_outcomes": [
                {
                    "tool": "sql_validate",
                    "status": "succeeded",
                    "artifact_ids": ["artifact_sql_only"],
                    "artifacts": [
                        {"id": "artifact_sql_only", "type": "sql"},
                    ],
                }
            ],
        }
    )

    assert _relevant_tool_groups(configured, context) == {
        "control",
        "conversation",
        "catalog",
        "query",
    }


class ValidateTool(SqlValidateTool):
    def run(self, tool_input, context):
        output = SqlValidateOutput(
            can_execute=True,
            requires_confirmation=False,
            safe_sql=tool_input.sql,
            original_sql=tool_input.sql,
            risk_level="safe",
            blocked_reasons=[],
            messages=[],
            execution_safety_decision={
                "datasource_id": context.request.datasource_id,
                "policy": "agent_readonly",
                "original_sql": tool_input.sql,
                "safe_sql": tool_input.sql,
                "passed": True,
                "can_execute": True,
                "requires_confirmation": False,
                "risk_level": "safe",
                "guardrail": {},
                "schema_warnings": [],
                "scope_state": {},
                "blocked_reasons": [],
                "messages": [],
            },
        )
        return ToolOutcome(
            output=output,
            artifacts=sql_validation_drafts(
                context.db_session,
                context.request.datasource_id,
                output,
            ),
        )


class ExecuteTool(SqlExecuteReadonlyTool):
    def run(self, tool_input, context):
        validated = ArtifactRepository(context.db_session).require_validated_sql(
            session_id=context.request.session_id,
            run_id=context.request.run_id,
            sql_artifact_id=tool_input.validation_artifact_id,
        )
        output = QueryResultOutput(
            status="success",
            success=True,
            row_count=1,
            columns=["total"],
            column_types=["integer"],
            returned_rows=1,
            truncated=False,
            rows=[{"total": 42}],
            safe_sql=validated.safe_sql,
            execution_time_ms=1,
            warnings=[],
            audit={},
            latency_ms=1,
        )
        return ToolOutcome(
            output=output,
            artifacts=(
                query_result_draft(
                    context.db_session,
                    context.request.datasource_id,
                    tool_input.validation_artifact_id,
                    context.request.datasource_generation,
                    output,
                ),
            ),
        )


class FailingExecuteTool(ExecuteTool):
    def run(self, tool_input, context):
        raise RuntimeError("execution failed")


def test_model_configuration_failure_settles_turn_and_fails_run(
    db_session,
    test_datasource,
) -> None:
    db_session.add(
        AgentSession(
            id="session_missing_llm_credential",
            datasource_id=str(test_datasource.id),
            title="Missing credential",
        )
    )
    db_session.commit()
    sessions = SessionRepository(db_session)
    admission = sessions.admit(
        session_id="session_missing_llm_credential",
        datasource_id=str(test_datasource.id),
        datasource_generation=1,
        content="分析订单",
        idempotency_key="missing-llm-credential",
        llm_credential_id="deleted-credential-reference",
        api_base=None,
        model_name="test",
        request_payload={},
    )
    lease = sessions.claim(
        session_id="session_missing_llm_credential",
        owner="worker",
        ttl_seconds=120,
    )
    assert lease is not None
    sessions.promote_next_input(lease=lease)
    db_session.commit()

    private_detail = "vault secret reference must not be rendered"

    def missing_credential_factory(_settings):
        raise LlmConfigurationError(
            private_detail,
            code="LLM_CREDENTIAL_NOT_FOUND",
        )

    factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)
    RunLoop(
        session_factory=factory,
        model_factory=missing_credential_factory,
        registry=ToolRegistry(),
        live_stream=LiveStreamHub(),
    ).execute(lease=lease, run_id=admission.run_id)

    db_session.expire_all()
    run = db_session.get(AgentRun, admission.run_id)
    turn = (
        db_session.query(AgentTurn).filter(AgentTurn.run_id == admission.run_id).one()
    )
    expected_message = fixed_error_message(FixedErrorCode.LLM_CREDENTIAL_NOT_FOUND)
    assert run is not None
    assert run.status == "failed"
    assert run.error_code == "LLM_CREDENTIAL_NOT_FOUND"
    assert run.error_message == expected_message
    assert private_detail not in str(run.error_message)
    assert turn.status == "failed"
    assert turn.error_code == "LLM_CREDENTIAL_NOT_FOUND"
    assert turn.error_message == expected_message


class ScriptedModel:
    def __init__(self, call_number):
        self.call_number = call_number

    def stream(self, *, messages, tools, timeout_seconds=None, cancellation_probe=None):
        if self.call_number == 1:
            yield TurnStreamItem(
                kind=TurnStreamKind.ANSWER_START,
                item_id="answer",
                revision=1,
                output_index=0,
                phase="commentary",
            )
            yield TurnStreamItem(
                kind=TurnStreamKind.ANSWER_DELTA,
                item_id="answer",
                revision=2,
                content="先验证并执行聚合查询。",
            )
            yield TurnStreamItem(
                kind=TurnStreamKind.ANSWER_END,
                item_id="answer",
                revision=3,
                output_index=0,
                phase="commentary",
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
                    "phase": "commentary",
                    "content": "先验证并执行聚合查询。",
                },
            )
            for index, (call_id, name, arguments) in enumerate(
                [
                    (
                        "validate",
                        "sql_validate",
                        {"sql": "select count(*) as total from orders"},
                    ),
                ]
            ):
                yield TurnStreamItem(
                    kind=TurnStreamKind.TOOL_CALL_START,
                    item_id=f"tool:{index}",
                    revision=1,
                    tool_call_index=index,
                    tool_call_id=call_id,
                    tool_name=name,
                    arguments_delta=json.dumps(arguments),
                )
                yield TurnStreamItem(
                    kind=TurnStreamKind.TOOL_CALL_END,
                    item_id=f"tool:{index}",
                    revision=2,
                    tool_call_index=index,
                )
                yield TurnStreamItem(
                    kind=TurnStreamKind.MODEL_OUTPUT_ITEM,
                    item_id=f"tool:{index}",
                    revision=3,
                    output_index=index + 1,
                    model_output_item={
                        "type": "function_call",
                        "call_id": call_id,
                        "name": name,
                        "arguments": json.dumps(arguments),
                    },
                )
            yield TurnStreamItem(
                kind=TurnStreamKind.FINISH,
                item_id="finish",
                revision=1,
                termination=TurnTermination.COMPLETED,
            )
        elif self.call_number == 2:
            prompt_content = json.dumps(messages, ensure_ascii=False)
            validation_match = re.search(
                r"validation_artifact_id.{0,80}?(artifact_[A-Za-z0-9_-]+)",
                prompt_content,
            )
            assert validation_match is not None
            yield TurnStreamItem(
                kind=TurnStreamKind.TOOL_CALL_START,
                item_id="tool:0",
                revision=1,
                tool_call_index=0,
                tool_call_id="execute",
                tool_name="sql_execute_readonly",
                arguments_delta=json.dumps(
                    {
                        "validation_artifact_id": validation_match.group(1),
                    }
                ),
            )
            yield TurnStreamItem(
                kind=TurnStreamKind.TOOL_CALL_END,
                item_id="tool:0",
                revision=2,
                tool_call_index=0,
            )
            execute_arguments = {
                "validation_artifact_id": validation_match.group(1),
            }
            yield TurnStreamItem(
                kind=TurnStreamKind.MODEL_OUTPUT_ITEM,
                item_id="tool:0",
                revision=3,
                output_index=0,
                model_output_item={
                    "type": "function_call",
                    "call_id": "execute",
                    "name": "sql_execute_readonly",
                    "arguments": json.dumps(execute_arguments),
                },
            )
            yield TurnStreamItem(
                kind=TurnStreamKind.FINISH,
                item_id="finish",
                revision=1,
                termination=TurnTermination.COMPLETED,
            )
        else:
            prompt_content = json.dumps(messages, ensure_ascii=False)
            assert re.search(r"artifact_[A-Za-z0-9_-]+", prompt_content)
            execute_output = next(
                item
                for item in messages
                if item.get("type") == "function_call_output"
                and item.get("call_id") == "execute"
            )
            assert json.loads(execute_output["output"])["facts"]["rows"] == [
                {"total": "42"}
            ]
            yield TurnStreamItem(
                kind=TurnStreamKind.ANSWER_START,
                item_id="commentary",
                revision=1,
                output_index=0,
                phase="commentary",
            )
            yield TurnStreamItem(
                kind=TurnStreamKind.ANSWER_DELTA,
                item_id="commentary",
                revision=2,
                content="正在整理可验证结论。",
            )
            yield TurnStreamItem(
                kind=TurnStreamKind.ANSWER_END,
                item_id="commentary",
                revision=3,
                output_index=0,
                phase="commentary",
                message_status="completed",
            )
            content = "共有 42 条订单。"
            yield TurnStreamItem(
                kind=TurnStreamKind.ANSWER_START,
                item_id="answer",
                revision=1,
                output_index=1,
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
                output_index=1,
                message_status="completed",
            )
            yield TurnStreamItem(
                kind=TurnStreamKind.MODEL_OUTPUT_ITEM,
                item_id="answer",
                revision=4,
                output_index=1,
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


class ToolBudgetModel:
    def __init__(self, call_number):
        self.call_number = call_number

    def stream(self, *, messages, tools, timeout_seconds=None, cancellation_probe=None):
        if self.call_number <= 2:
            yield from ScriptedModel(self.call_number).stream(
                messages=messages,
                tools=tools,
                timeout_seconds=timeout_seconds,
                cancellation_probe=cancellation_probe,
            )
            return
        yield TurnStreamItem(
            kind=TurnStreamKind.TOOL_CALL_START,
            item_id="tool:0",
            revision=1,
            tool_call_index=0,
            tool_call_id="repeat-validate",
            tool_name="sql_validate",
            arguments_delta=json.dumps({"sql": "select count(*) as total from orders"}),
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
                "call_id": "repeat-validate",
                "name": "sql_validate",
                "arguments": json.dumps(
                    {"sql": "select count(*) as total from orders"}
                ),
            },
        )
        yield TurnStreamItem(
            kind=TurnStreamKind.FINISH,
            item_id="finish",
            revision=1,
            termination=TurnTermination.COMPLETED,
        )


class BudgetAnswerModel:
    def stream(self, *, messages, tools, timeout_seconds=None, cancellation_probe=None):
        content = "已完成当前预算内的分析。"
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
            kind=TurnStreamKind.USAGE,
            item_id="usage",
            revision=1,
            usage={
                "input_tokens": 6,
                "output_tokens": 4,
                "total_tokens": 10,
            },
        )
        yield TurnStreamItem(
            kind=TurnStreamKind.FINISH,
            item_id="finish",
            revision=1,
            termination=TurnTermination.COMPLETED,
        )


class MalformedCitationRepairModel:
    def __init__(self, call_number: int) -> None:
        self.call_number = call_number

    def stream(self, *, messages, tools, timeout_seconds=None, cancellation_probe=None):
        content = (
            "当前数据源包含 4 张表。{{cite:artifact_result_???}}"
            if self.call_number == 1
            else "当前数据源包含 4 张表。"
        )
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


class CommentaryAndQuestionModel:
    def stream(self, *, messages, tools, timeout_seconds=None, cancellation_probe=None):
        yield TurnStreamItem(
            kind=TurnStreamKind.ANSWER_START,
            item_id="answer",
            revision=1,
            output_index=0,
            phase="commentary",
        )
        yield TurnStreamItem(
            kind=TurnStreamKind.ANSWER_DELTA,
            item_id="answer",
            revision=2,
            content="我先确认统计口径，再继续读取数据。",
        )
        yield TurnStreamItem(
            kind=TurnStreamKind.ANSWER_END,
            item_id="answer",
            revision=3,
            output_index=0,
            phase="commentary",
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
                "phase": "commentary",
                "content": "我先确认统计口径，再继续读取数据。",
            },
        )
        calls = [
            (
                "question",
                "request_clarification",
                {
                    "question": "按哪个时间口径统计？",
                    "reason": "不同时间口径会改变结果。",
                    "options": [],
                    "allow_free_text": True,
                },
            ),
        ]
        for index, (call_id, name, arguments) in enumerate(calls):
            yield TurnStreamItem(
                kind=TurnStreamKind.TOOL_CALL_START,
                item_id=f"tool:{index}",
                revision=1,
                tool_call_index=index,
                tool_call_id=call_id,
                tool_name=name,
                arguments_delta=json.dumps(arguments, ensure_ascii=False),
            )
            yield TurnStreamItem(
                kind=TurnStreamKind.TOOL_CALL_END,
                item_id=f"tool:{index}",
                revision=2,
                tool_call_index=index,
            )
            yield TurnStreamItem(
                kind=TurnStreamKind.MODEL_OUTPUT_ITEM,
                item_id=f"tool:{index}",
                revision=3,
                output_index=index + 1,
                model_output_item={
                    "type": "function_call",
                    "call_id": call_id,
                    "name": name,
                    "arguments": json.dumps(arguments, ensure_ascii=False),
                },
            )
        yield TurnStreamItem(
            kind=TurnStreamKind.FINISH,
            item_id="finish",
            revision=1,
            termination=TurnTermination.COMPLETED,
        )


def test_native_assistant_commentary_precedes_durable_question_tool_call(
    db_session,
    test_datasource,
):
    db_session.add(
        AgentSession(
            id="session_commentary",
            datasource_id=str(test_datasource.id),
            title="Commentary",
        )
    )
    db_session.commit()
    sessions = SessionRepository(db_session)
    admission = sessions.admit(
        session_id="session_commentary",
        datasource_id=str(test_datasource.id),
        datasource_generation=1,
        content="分析订单",
        idempotency_key="commentary",
        llm_credential_id="credential",
        api_base=None,
        model_name="test",
        request_payload={},
    )
    lease = sessions.claim(
        session_id="session_commentary", owner="worker", ttl_seconds=120
    )
    assert lease is not None
    sessions.promote_next_input(lease=lease)
    db_session.commit()

    factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)
    loop = RunLoop(
        session_factory=factory,
        model_factory=lambda _settings: CommentaryAndQuestionModel(),
    )
    loop.execute(lease=lease, run_id=admission.run_id)

    db_session.expire_all()
    db_session.query(AgentTurn).filter_by(run_id=admission.run_id).one()
    run = db_session.get(AgentRun, admission.run_id)
    item_payloads = [
        json.loads(str(row.item_json))
        for row in db_session.query(AgentRunItemRecord)
        .filter_by(run_id=admission.run_id)
        .order_by(AgentRunItemRecord.sequence)
    ]
    assert any(
        item["type"] == "message"
        and item["payload"].get("phase") == "commentary"
        and item["payload"].get("content") == "我先确认统计口径，再继续读取数据。"
        for item in item_payloads
    )
    assert run.status == "waiting_input"
    invocation = (
        db_session.query(AgentToolInvocation).filter_by(run_id=admission.run_id).one()
    )
    assert invocation.provider_call_id == "question"
    assert invocation.tool_name == "request_clarification"
    assert invocation.status == "waiting_input"
    assert loop.tool_dispatcher.tool_budget_usage(db_session, admission.run_id) == 0
    assert any(
        item["type"] == "function_call"
        and item["payload"]["call_id"] == "question"
        and item["status"] == "waiting"
        for item in item_payloads
    )


def test_explicit_run_loop_closes_tool_artifact_evidence_and_answer_cycle(
    db_session, test_datasource
):
    db_session.add(
        AgentSession(
            id="session_loop", datasource_id=str(test_datasource.id), title="Loop"
        )
    )
    db_session.commit()
    sessions = SessionRepository(db_session)
    admission = sessions.admit(
        session_id="session_loop",
        datasource_id=str(test_datasource.id),
        datasource_generation=1,
        content="统计订单数量",
        idempotency_key="loop",
        llm_credential_id="credential",
        api_base=None,
        model_name="test",
        request_payload={},
    )
    lease = sessions.claim(session_id="session_loop", owner="worker", ttl_seconds=120)
    assert lease is not None
    sessions.promote_next_input(lease=lease)
    db_session.commit()

    calls = {"count": 0}

    def model_factory(_settings):
        calls["count"] += 1
        return ScriptedModel(calls["count"])

    registry = ToolRegistry().register(ValidateTool()).register(ExecuteTool())
    factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)
    live = LiveStreamHub()
    subscription = live.subscribe(admission.run_id)
    RunLoop(
        session_factory=factory,
        model_factory=model_factory,
        registry=registry,
        live_stream=live,
    ).execute(lease=lease, run_id=admission.run_id)

    db_session.expire_all()
    run = db_session.get(AgentRun, admission.run_id)
    answer = db_session.get(AgentMessage, admission.assistant_message_id)
    assert run.status == "completed"
    assert answer.content.startswith("共有 42 条订单。\n\n来源：{{cite:artifact_")
    assert db_session.query(AgentEvidenceRecord).filter_by(run_id=run.id).count() == 1
    assert calls["count"] == 3
    assert all(
        '"total":"42"' not in str(turn.context_snapshot_json)
        for turn in db_session.query(AgentTurn).filter_by(run_id=run.id)
    )
    assert all(
        '"total":"42"' not in str(row.model_output_json)
        for row in db_session.query(AgentObservationRecord).filter_by(run_id=run.id)
    )
    timeline = [
        json.loads(str(row.item_json))
        for row in db_session.query(AgentRunItemRecord)
        .filter_by(run_id=run.id)
        .order_by(AgentRunItemRecord.sequence)
    ]
    visible_types = [item["type"] for item in timeline]
    assert visible_types == [
        "message",
        "message",
        "function_call",
        "function_call_output",
        "function_call",
        "function_call_output",
        "message",
        "message",
    ]
    assert timeline[1]["payload"]["phase"] == "commentary"
    assert timeline[-1]["payload"]["phase"] is None
    assert timeline[-1]["payload"]["completion_disposition"] == "complete"
    recovered = RunRepository(db_session).latest_completed_answer(str(run.id))
    assert [message.phase for message in recovered.messages] == ["commentary", None]
    assert recovered.answer_text == "共有 42 条订单。"
    assert timeline[2]["payload"]["call_id"] == timeline[3]["payload"]["call_id"]
    assert subscription.receive(timeout=0.01).content == "先验证并执行聚合查询。"
    assert subscription.receive(timeout=0.01).content == "正在整理可验证结论。"
    assert subscription.receive(timeout=0.01).content == "共有 42 条订单。"


def test_run_loop_repairs_malformed_citation_before_terminal_commit(
    db_session, test_datasource
):
    db_session.add(
        AgentSession(
            id="session_citation_repair",
            datasource_id=str(test_datasource.id),
            title="Citation repair",
        )
    )
    db_session.commit()
    sessions = SessionRepository(db_session)
    admission = sessions.admit(
        session_id="session_citation_repair",
        datasource_id=str(test_datasource.id),
        datasource_generation=1,
        content="当前数据源有多少张表？",
        idempotency_key="citation-repair",
        llm_credential_id="credential",
        api_base=None,
        model_name="test",
        request_payload={},
    )
    lease = sessions.claim(
        session_id="session_citation_repair", owner="worker", ttl_seconds=120
    )
    assert lease is not None
    sessions.promote_next_input(lease=lease)
    db_session.commit()

    calls = {"count": 0}

    def model_factory(_settings):
        calls["count"] += 1
        return MalformedCitationRepairModel(calls["count"])

    factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)
    RunLoop(
        session_factory=factory,
        model_factory=model_factory,
        registry=ToolRegistry(),
        live_stream=LiveStreamHub(),
    ).execute(lease=lease, run_id=admission.run_id)

    db_session.expire_all()
    run = db_session.get(AgentRun, admission.run_id)
    answer = db_session.get(AgentMessage, admission.assistant_message_id)
    assert run is not None and run.status == "completed"
    assert answer is not None and answer.content == "当前数据源包含 4 张表。"
    assert "{{cite:" not in answer.content
    assert calls["count"] == 2
    assert db_session.query(AgentTurn).filter_by(run_id=run.id).count() == 2


def test_result_rows_are_transient_and_never_enter_durable_facts() -> None:
    secret = "transient-sensitive-cell"
    output = {
        "rows": [{"token": secret}],
        "series": [{"label": secret, "value": 1}],
        "columns": ["token"],
        "rowCount": 1,
        "safe_sql": "SELECT token FROM secrets",
    }
    projection = SqlExecuteReadonlyTool().project_observation(
        status="success",
        output=output,
        artifacts=[],
    )
    durable = projection.facts
    assert secret not in json.dumps(durable)
    assert secret in json.dumps(projection.provider_payload)
    assert durable["row_count"] == 1
    assert durable["column_count"] == 1
    assert durable["columns"] == ["token"]
    assert "safe_sql" not in durable


def test_sql_validation_keeps_execution_authority_in_artifacts_not_observation_facts() -> (
    None
):
    decision = {
        "decision_id": "safety-1",
        "datasource_id": "ds-1",
        "policy": "agent_readonly",
        "original_sql": "SELECT 1",
        "safe_sql": "SELECT 1 LIMIT 500",
        "passed": True,
        "can_execute": True,
        "requires_confirmation": False,
        "risk_level": "safe",
        "guardrail": {"result": "pass", "reasons": []},
        "schema_warnings": [],
        "scope_state": {},
        "blocked_reasons": [],
        "messages": [],
        "created_at": "2026-07-25T00:00:00Z",
    }
    durable = (
        SqlValidateTool()
        .project_observation(
            status="success",
            output={
                "can_execute": True,
                "requires_confirmation": False,
                "safe_sql": decision["safe_sql"],
                "original_sql": decision["original_sql"],
                "risk_level": "safe",
                "blocked_reasons": [],
                "messages": [],
                "execution_safety_decision": decision,
            },
            artifacts=[],
        )
        .facts
    )

    assert durable["can_execute"] is True
    assert "execution_safety_decision" not in durable
    assert "safe_sql" not in durable


def test_failed_tool_does_not_publish_capabilities_or_progress(
    db_session,
    test_datasource,
) -> None:
    db_session.add(
        AgentSession(
            id="session_failed_semantics",
            datasource_id=str(test_datasource.id),
            title="Failed semantics",
        )
    )
    db_session.commit()
    sessions = SessionRepository(db_session)
    admission = sessions.admit(
        session_id="session_failed_semantics",
        datasource_id=str(test_datasource.id),
        datasource_generation=1,
        content="统计订单数量",
        idempotency_key="failed-semantics",
        llm_credential_id="credential",
        api_base=None,
        model_name="test",
        request_payload={},
    )
    lease = sessions.claim(
        session_id="session_failed_semantics",
        owner="worker",
        ttl_seconds=120,
    )
    assert lease is not None
    sessions.promote_next_input(lease=lease)
    db_session.commit()

    factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)
    calls = {"count": 0}

    def model_factory(_settings):
        calls["count"] += 1
        return ScriptedModel(calls["count"])

    RunLoop(
        session_factory=factory,
        model_factory=model_factory,
        registry=ToolRegistry().register(ValidateTool()).register(FailingExecuteTool()),
        definition=AgentDefinition(limits=RunLimits(max_turns=2)),
        live_stream=LiveStreamHub(),
    ).execute(lease=lease, run_id=admission.run_id)

    observation = (
        db_session.query(AgentObservationRecord)
        .join(
            AgentToolInvocation,
            AgentToolInvocation.id == AgentObservationRecord.tool_invocation_id,
        )
        .filter(
            AgentObservationRecord.run_id == admission.run_id,
            AgentToolInvocation.tool_name == "sql_execute_readonly",
        )
        .one()
    )
    assert observation.status == "failed"
    assert json.loads(observation.semantic_capabilities_json) == []
    assert observation.contributes_progress is False


def test_tool_budget_returns_bounded_partial_when_verified_result_exists(
    db_session, test_datasource
):
    db_session.add(
        AgentSession(
            id="session_tool_budget",
            datasource_id=str(test_datasource.id),
            title="Budget",
        )
    )
    db_session.commit()
    sessions = SessionRepository(db_session)
    admission = sessions.admit(
        session_id="session_tool_budget",
        datasource_id=str(test_datasource.id),
        datasource_generation=1,
        content="统计订单数量",
        idempotency_key="tool-budget",
        llm_credential_id="credential",
        api_base=None,
        model_name="test",
        request_payload={},
    )
    lease = sessions.claim(
        session_id="session_tool_budget", owner="worker", ttl_seconds=120
    )
    sessions.promote_next_input(lease=lease)
    db_session.commit()

    calls = {"count": 0}

    def model_factory(_settings):
        calls["count"] += 1
        return ToolBudgetModel(calls["count"])

    factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)
    RunLoop(
        session_factory=factory,
        model_factory=model_factory,
        registry=ToolRegistry().register(ValidateTool()).register(ExecuteTool()),
        definition=AgentDefinition(limits=RunLimits(max_tool_invocations=2)),
        live_stream=LiveStreamHub(),
    ).execute(lease=lease, run_id=admission.run_id)

    db_session.expire_all()
    run = db_session.get(AgentRun, admission.run_id)
    result = json.loads(run.result_json)
    assert run.status == "completed"
    assert result["completion_disposition"] == "bounded_partial"
    assert result["limitation_codes"] == ["TOOL_BUDGET_REACHED"]
    assert "已达到工具调用上限" in result["answer"]["caveats"][0]


def test_token_budget_preserves_the_settled_final_answer(db_session, test_datasource):
    db_session.add(
        AgentSession(
            id="session_token_budget",
            datasource_id=str(test_datasource.id),
            title="Token Budget",
        )
    )
    db_session.commit()
    sessions = SessionRepository(db_session)
    admission = sessions.admit(
        session_id="session_token_budget",
        datasource_id=str(test_datasource.id),
        datasource_generation=1,
        content="给出当前可完成的分析",
        idempotency_key="token-budget",
        llm_credential_id="credential",
        api_base=None,
        model_name="test",
        request_payload={},
    )
    lease = sessions.claim(
        session_id="session_token_budget",
        owner="worker",
        ttl_seconds=120,
    )
    assert lease is not None
    sessions.promote_next_input(lease=lease)
    db_session.commit()

    factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)
    RunLoop(
        session_factory=factory,
        model_factory=lambda _settings: BudgetAnswerModel(),
        registry=ToolRegistry(),
        definition=AgentDefinition(limits=RunLimits(token_budget=5)),
        live_stream=LiveStreamHub(),
    ).execute(lease=lease, run_id=admission.run_id)

    db_session.expire_all()
    run = db_session.get(AgentRun, admission.run_id)
    result = json.loads(run.result_json)
    assert run.status == "completed"
    assert result["completion_disposition"] == "bounded_partial"
    assert result["limitation_codes"] == ["TOKEN_BUDGET_REACHED"]
    assert result["answer"]["text"] == "已完成当前预算内的分析。"
