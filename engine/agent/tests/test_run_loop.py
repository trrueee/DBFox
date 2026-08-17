import json
import re
import threading
import time

import pytest
from sqlalchemy.orm import sessionmaker

from engine.agent.context import ContextArtifact, ContextObservation, ContextSnapshot
from engine.agent.artifact import ArtifactDraft, ArtifactType
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
    AgentArtifactRecord,
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
from engine.tools.builtin.results import ResultInspectTool
from engine.tools.builtin.control import UpdatePlanCommand
from engine.tools.builtin.artifacts import query_result_draft, sql_validation_drafts
from engine.tools.builtin.contracts import QueryResultOutput, SqlValidateOutput
from engine.tools.runtime import (
    BaseTool,
    ToolInputModel,
    ToolOutputModel,
    ToolPolicy,
    ToolOutcome,
    ToolExecutionSpec,
    ToolPresentation,
    ToolRegistry,
)
from engine.tools.runtime.observation import ToolObservationProjection
from engine.tools.runtime.semantics import ToolSemanticCapability


def _tool_turn(
    call_id: str,
    name: str,
    arguments: dict[str, object],
    *,
    tool_call_index: int = 0,
    output_index: int = 0,
    finish: bool = True,
):
    encoded = json.dumps(arguments, ensure_ascii=False)
    yield TurnStreamItem(
        kind=TurnStreamKind.TOOL_CALL_START,
        item_id=f"tool:{call_id}",
        revision=1,
        tool_call_index=tool_call_index,
        tool_call_id=call_id,
        tool_name=name,
        arguments_delta=encoded,
    )
    yield TurnStreamItem(
        kind=TurnStreamKind.TOOL_CALL_END,
        item_id=f"tool:{call_id}",
        revision=2,
        tool_call_index=tool_call_index,
    )
    yield TurnStreamItem(
        kind=TurnStreamKind.MODEL_OUTPUT_ITEM,
        item_id=f"tool:{call_id}",
        revision=3,
        output_index=output_index,
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
            "run_id": "failed-run",
            "status": "failed",
            "public_message": "上一次运行失败。",
            "recovery": "复用已完成结果。",
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
            "run_id": "failed-run",
            "status": "failed",
            "public_message": "上一次运行失败。",
            "recovery": "复用已完成结果。",
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


class InvalidArtifactInput(ToolInputModel):
    pass


class InvalidArtifactOutput(ToolOutputModel):
    status: str


class InvalidArtifactTool(BaseTool[InvalidArtifactInput, InvalidArtifactOutput]):
    name = "invalid_artifact"
    group = "query"
    description = "Emit an invalid Artifact draft for settlement contract testing."
    input_model = InvalidArtifactInput
    output_model = InvalidArtifactOutput
    presentation = ToolPresentation(
        title="Create invalid Artifact",
        category="visualize",
        visibility="summary",
    )

    def run(self, tool_input, context):
        return ToolOutcome(
            output=InvalidArtifactOutput(status="generated"),
            artifacts=(
                ArtifactDraft(
                    key="valid_sql",
                    type=ArtifactType.SQL,
                    title="Valid SQL",
                    payload={
                        "sql": "SELECT 1",
                        "safeSql": "SELECT 1",
                        "dialect": "sqlite",
                        "queryFingerprint": "fingerprint",
                    },
                ),
                ArtifactDraft(
                    key="invalid_chart",
                    type=ArtifactType.CHART,
                    title="Invalid chart",
                    payload={
                        "sourceResultArtifactId": "artifact_result",
                        "chartType": "bar",
                        "x": "day",
                        "y": ["total"],
                        "aggregation": "none",
                        "title": "Daily total",
                        "unexpected": "not allowed",
                    },
                ),
            ),
        )

    def project_observation(self, *, status, output, artifacts):
        if status != "success":
            return ToolObservationProjection(summary="图表产物合同校验失败。")
        return ToolObservationProjection(summary="图表产物已生成。")


_PARALLEL_TOOL_LOCK = threading.Lock()
_PARALLEL_TOOL_EVENTS: list[tuple[str, str, float]] = []


def _record_parallel_tool_event(phase: str, marker: str) -> None:
    with _PARALLEL_TOOL_LOCK:
        _PARALLEL_TOOL_EVENTS.append((marker, phase, time.perf_counter()))


def _consume_parallel_tool_events() -> list[tuple[str, str, float]]:
    with _PARALLEL_TOOL_LOCK:
        events = list(_PARALLEL_TOOL_EVENTS)
        _PARALLEL_TOOL_EVENTS.clear()
    return events


class ParallelSafeInput(ToolInputModel):
    marker: str
    delay_seconds: float = 0.2


class ParallelSafeOutput(ToolOutputModel):
    marker: str
    status: str


class ParallelSafeTool(BaseTool[ParallelSafeInput, ParallelSafeOutput]):
    # A concrete test helper needs a valid Tool ID even though only its named
    # subclasses are registered in the runtime.
    name = "parallel_safe_test_base"
    group = "catalog"
    description = "Slow test tool for parallel dispatch assertions."
    input_model = ParallelSafeInput
    output_model = ParallelSafeOutput
    presentation = ToolPresentation(
        title="Parallel safe test",
        category="query",
        visibility="summary",
    )
    execution = ToolExecutionSpec(concurrency="parallel_safe", timeout_seconds=2)

    def run(self, tool_input, context):
        del context
        _record_parallel_tool_event("start", tool_input.marker)
        time.sleep(tool_input.delay_seconds)
        _record_parallel_tool_event("end", tool_input.marker)
        return ToolOutcome(
            output=ParallelSafeOutput(
                marker=tool_input.marker,
                status="ok",
            ),
        )


class ParallelSafeToolA(ParallelSafeTool):
    name = "parallel_safe_test_a"


class ParallelSafeToolB(ParallelSafeTool):
    name = "parallel_safe_test_b"


class ParallelSafeToolC(ParallelSafeTool):
    name = "parallel_safe_test_c"
    execution = ToolExecutionSpec(concurrency="sequential", timeout_seconds=2)


class BudgetCountInput(ToolInputModel):
    marker: str


class BudgetCountOutput(ToolOutputModel):
    marker: str


class BudgetCountTool(BaseTool[BudgetCountInput, BudgetCountOutput]):
    group = "catalog"
    name = "budget_count_tool"
    description = "Count for budget-admission regression."
    input_model = BudgetCountInput
    output_model = BudgetCountOutput
    presentation = ToolPresentation(
        title="Budget count",
        category="query",
        visibility="summary",
    )
    execution = ToolExecutionSpec(timeout_seconds=1)

    def run(self, tool_input, context):
        del context
        _record_parallel_tool_event("start", tool_input.marker)
        _record_parallel_tool_event("end", tool_input.marker)
        return ToolOutcome(
            output=BudgetCountOutput(
                marker=tool_input.marker,
            ),
        )


class ApprovalAwareInput(ToolInputModel):
    marker: str


class ApprovalAwareOutput(ToolOutputModel):
    marker: str


class ApprovalAwareTool(BaseTool[ApprovalAwareInput, ApprovalAwareOutput]):
    name = "approval_required_tool"
    group = "catalog"
    description = "Tool requiring approval that must stop dispatch before execution."
    input_model = ApprovalAwareInput
    output_model = ApprovalAwareOutput
    policy = ToolPolicy(requires_approval=True)
    presentation = ToolPresentation(
        title="Approval required test",
        category="manage",
        visibility="summary",
    )
    execution = ToolExecutionSpec(timeout_seconds=1)

    def run(self, tool_input, context):
        del context
        _record_parallel_tool_event("start", tool_input.marker)
        _record_parallel_tool_event("end", tool_input.marker)
        return ToolOutcome(
            output=ApprovalAwareOutput(
                marker=tool_input.marker,
            ),
        )


class ParallelSafeModel:
    def __init__(self, call_number: int):
        self.call_number = call_number

    def stream(self, *, messages, tools, timeout_seconds=None, cancellation_probe=None):
        del timeout_seconds, cancellation_probe
        if self.call_number == 1:
            available = {
                str(item.get("name") or item.get("function", {}).get("name") or "")
                for item in tools
            }
            assert "parallel_safe_test_a" in available
            assert "parallel_safe_test_b" in available
            yield from _tool_turn(
                "parallel-safe-a",
                "parallel_safe_test_a",
                {"marker": "A", "delay_seconds": 0.2},
                tool_call_index=0,
                output_index=0,
                finish=False,
            )
            yield from _tool_turn(
                "parallel-safe-b",
                "parallel_safe_test_b",
                {"marker": "B", "delay_seconds": 0.2},
                tool_call_index=1,
                output_index=1,
                finish=False,
            )
            yield TurnStreamItem(
                kind=TurnStreamKind.FINISH,
                item_id="finish",
                revision=1,
                termination=TurnTermination.COMPLETED,
            )
            return

        assert self.call_number == 2
        yield TurnStreamItem(
            kind=TurnStreamKind.ANSWER_START,
            item_id="answer",
            revision=1,
            output_index=0,
        )
        content = "两个工具并行执行完成。"
        yield TurnStreamItem(
            kind=TurnStreamKind.ANSWER_DELTA,
            item_id="answer",
            revision=2,
            content=content,
            output_index=0,
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
                "content": content,
            },
        )
        yield TurnStreamItem(
            kind=TurnStreamKind.USAGE,
            item_id="usage",
            revision=1,
            usage={"input_tokens": 10, "output_tokens": 8, "total_tokens": 18},
        )
        yield TurnStreamItem(
            kind=TurnStreamKind.FINISH,
            item_id="finish",
            revision=1,
            termination=TurnTermination.COMPLETED,
        )


class ParallelBatchBarrierModel:
    def __init__(self, call_number: int):
        self.call_number = call_number

    def stream(self, *, messages, tools, timeout_seconds=None, cancellation_probe=None):
        del messages, timeout_seconds, cancellation_probe
        if self.call_number == 1:
            available = {str(item.get("name") or "") for item in tools}
            assert {
                "parallel_safe_test_a",
                "parallel_safe_test_b",
                "parallel_safe_test_c",
            }.issubset(available)
            yield from _tool_turn(
                "barrier-a",
                "parallel_safe_test_a",
                {"marker": "A", "delay_seconds": 0.2},
                tool_call_index=0,
                output_index=0,
                finish=False,
            )
            yield from _tool_turn(
                "barrier-b",
                "parallel_safe_test_b",
                {"marker": "B", "delay_seconds": 0.2},
                tool_call_index=1,
                output_index=1,
                finish=False,
            )
            yield from _tool_turn(
                "barrier-c",
                "parallel_safe_test_c",
                {"marker": "C", "delay_seconds": 0.2},
                tool_call_index=2,
                output_index=2,
                finish=False,
            )
            yield from _tool_turn(
                "barrier-d",
                "parallel_safe_test_a",
                {"marker": "D", "delay_seconds": 0.2},
                tool_call_index=3,
                output_index=3,
                finish=False,
            )
            yield from _tool_turn(
                "barrier-e",
                "parallel_safe_test_b",
                {"marker": "E", "delay_seconds": 0.2},
                tool_call_index=4,
                output_index=4,
            )
            return

        assert self.call_number == 2
        yield from _final_turn("A/B/C/D/E 执行路径已完成。")


class ApprovalAwareModel:
    def __init__(self, call_number: int):
        self.call_number = call_number

    def stream(self, *, messages, tools, timeout_seconds=None, cancellation_probe=None):
        del messages, timeout_seconds, cancellation_probe
        if self.call_number == 1:
            available = {str(item.get("name") or "") for item in tools}
            assert {
                "parallel_safe_test_a",
                "approval_required_tool",
                "parallel_safe_test_b",
            }.issubset(available)
            yield from _tool_turn(
                "approval-a",
                "parallel_safe_test_a",
                {"marker": "A", "delay_seconds": 0.2},
                tool_call_index=0,
                output_index=0,
                finish=False,
            )
            yield from _tool_turn(
                "approval-b",
                "approval_required_tool",
                {"marker": "B"},
                tool_call_index=1,
                output_index=1,
                finish=False,
            )
            yield from _tool_turn(
                "approval-c",
                "parallel_safe_test_b",
                {"marker": "C", "delay_seconds": 0.2},
                tool_call_index=2,
                output_index=2,
            )
            return

        assert self.call_number == 2
        yield from _final_turn("该测试仅在等待审批时检查提交行为。")


class ParallelOutcomeOrderModel:
    def __init__(self, call_number: int):
        self.call_number = call_number

    def stream(self, *, messages, tools, timeout_seconds=None, cancellation_probe=None):
        del messages, timeout_seconds, cancellation_probe
        if self.call_number == 1:
            yield from _tool_turn(
                "order-a",
                "parallel_safe_test_a",
                {"marker": "A", "delay_seconds": 0.30},
                tool_call_index=0,
                output_index=0,
                finish=False,
            )
            yield from _tool_turn(
                "order-b",
                "parallel_safe_test_b",
                {"marker": "B", "delay_seconds": 0.02},
                tool_call_index=1,
                output_index=1,
            )
            return
        assert self.call_number == 2
        yield from _final_turn("并发完成顺序测试。")


class ParallelFailureInput(ToolInputModel):
    marker: str


class ParallelFailureOutput(ToolOutputModel):
    marker: str


class ParallelFailingTool(BaseTool[ParallelFailureInput, ParallelFailureOutput]):
    name = "parallel_fail_test"
    group = "catalog"
    description = "Intentionally failing parallel-safe tool."
    input_model = ParallelFailureInput
    output_model = ParallelFailureOutput
    execution = ToolExecutionSpec(concurrency="parallel_safe", timeout_seconds=2)
    presentation = ToolPresentation(
        title="Parallel failing test",
        category="query",
        visibility="summary",
    )

    def run(self, tool_input, context):
        del context
        _record_parallel_tool_event("start", tool_input.marker)
        raise RuntimeError(f"intentional failure: {tool_input.marker}")


class ParallelMixedFailureModel:
    def __init__(self, call_number: int):
        self.call_number = call_number

    def stream(self, *, messages, tools, timeout_seconds=None, cancellation_probe=None):
        del messages, timeout_seconds, cancellation_probe
        if self.call_number == 1:
            assert {
                "parallel_fail_test",
                "parallel_safe_test_b",
            }.issubset({str(item.get("name") or item.get("function", {}).get("name") or "") for item in tools})
            yield from _tool_turn(
                "mixed-fail-a",
                "parallel_fail_test",
                {"marker": "A"},
                tool_call_index=0,
                output_index=0,
                finish=False,
            )
            yield from _tool_turn(
                "mixed-success-b",
                "parallel_safe_test_b",
                {"marker": "B", "delay_seconds": 0.12},
                tool_call_index=1,
                output_index=1,
            )
            return
        assert self.call_number == 2
        yield from _final_turn("并发失败隔离测试。")


def test_parallel_safe_tool_calls_are_dispatched_as_linear_barrier_batches(
    db_session,
    test_datasource,
) -> None:
    _consume_parallel_tool_events()

    session_id = "session_parallel_barrier_dispatch"
    db_session.add(
        AgentSession(
            id=session_id,
            datasource_id=str(test_datasource.id),
            title="Parallel barrier dispatch",
        )
    )
    db_session.commit()
    sessions = SessionRepository(db_session)
    admission = sessions.admit(
        session_id=session_id,
        datasource_id=str(test_datasource.id),
        datasource_generation=1,
        content="请在允许并行时并发执行，顺序调用顺序保护。"
        " 验证并行、安全屏障与并发顺序。",
        idempotency_key="parallel-barrier",
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
        return ParallelBatchBarrierModel(calls["count"])

    factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)
    RunLoop(
        session_factory=factory,
        model_factory=model_factory,
        registry=ToolRegistry()
        .register(ParallelSafeToolA())
        .register(ParallelSafeToolB())
        .register(ParallelSafeToolC()),
        definition=AgentDefinition(),
        live_stream=LiveStreamHub(),
    ).execute(lease=lease, run_id=admission.run_id)

    events = _consume_parallel_tool_events()
    starts = {marker: ts for marker, phase, ts in events if phase == "start"}
    ends = {marker: ts for marker, phase, ts in events if phase == "end"}
    assert set(starts.keys()) == {"A", "B", "C", "D", "E"}
    assert set(ends.keys()) == {"A", "B", "C", "D", "E"}
    assert abs(starts["A"] - starts["B"]) < 0.12

    first_barrier_end = max(ends["A"], ends["B"])
    assert starts["C"] >= first_barrier_end
    second_barrier_end = ends["C"]
    assert starts["D"] >= second_barrier_end
    assert starts["E"] >= second_barrier_end
    assert abs(starts["D"] - starts["E"]) < 0.12

    db_session.expire_all()
    run = db_session.get(AgentRun, admission.run_id)
    assert run is not None
    assert run.status == "completed"

    invocations = (
        db_session.query(AgentToolInvocation)
        .filter_by(run_id=admission.run_id)
        .order_by(AgentToolInvocation.created_at)
        .all()
    )
    assert len(invocations) == 5
    assert all(invocation.status == "succeeded" for invocation in invocations)


def test_parallel_settlement_is_stable_in_provider_call_order(
    db_session,
    test_datasource,
) -> None:
    session_id = "session_parallel_order_settlement"
    db_session.add(
        AgentSession(
            id=session_id,
            datasource_id=str(test_datasource.id),
            title="Parallel settlement order",
        )
    )
    db_session.commit()
    sessions = SessionRepository(db_session)
    admission = sessions.admit(
        session_id=session_id,
        datasource_id=str(test_datasource.id),
        datasource_generation=1,
        content="并发工具应按调用顺序沉淀观察。",
        idempotency_key="parallel-order-settle",
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
        return ParallelOutcomeOrderModel(calls["count"])

    factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)
    RunLoop(
        session_factory=factory,
        model_factory=model_factory,
        registry=ToolRegistry()
        .register(ParallelSafeToolA())
        .register(ParallelSafeToolB()),
        definition=AgentDefinition(),
        live_stream=LiveStreamHub(),
    ).execute(lease=lease, run_id=admission.run_id)

    db_session.expire_all()
    observations = (
        db_session.query(AgentObservationRecord)
        .join(
            AgentToolInvocation,
            AgentObservationRecord.tool_invocation_id == AgentToolInvocation.id,
        )
        .filter(AgentToolInvocation.run_id == admission.run_id)
        .order_by(AgentObservationRecord.sequence)
        .all()
    )
    assert len(observations) == 2
    assert all(item.status == "succeeded" for item in observations)

    invocation_ids = [
        obs.tool_invocation_id
        for obs in observations
    ]
    invocation_by_id = {
        invocation.id: invocation
        for invocation in db_session.query(AgentToolInvocation)
        .filter(AgentToolInvocation.run_id == admission.run_id)
        .all()
    }
    assert [
        invocation_by_id[invocation_id].provider_call_id for invocation_id in invocation_ids
    ] == ["order-a", "order-b"]


def test_parallel_failed_tool_does_not_block_sibling_settlement(
    db_session,
    test_datasource,
) -> None:
    _consume_parallel_tool_events()

    session_id = "session_parallel_batch_failure"
    db_session.add(
        AgentSession(
            id=session_id,
            datasource_id=str(test_datasource.id),
            title="Parallel mixed failure",
        )
    )
    db_session.commit()
    sessions = SessionRepository(db_session)
    admission = sessions.admit(
        session_id=session_id,
        datasource_id=str(test_datasource.id),
        datasource_generation=1,
        content="并行时一项失败不应阻断另一项。",
        idempotency_key="parallel-batch-failure",
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
        return ParallelMixedFailureModel(calls["count"])

    factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)
    RunLoop(
        session_factory=factory,
        model_factory=model_factory,
        registry=ToolRegistry()
        .register(ParallelFailingTool())
        .register(ParallelSafeToolB()),
        definition=AgentDefinition(),
        live_stream=LiveStreamHub(),
    ).execute(lease=lease, run_id=admission.run_id)

    events = _consume_parallel_tool_events()
    assert {marker for marker, phase, _ in events} == {"A", "B"}

    db_session.expire_all()
    run = db_session.get(AgentRun, admission.run_id)
    assert run is not None
    assert run.status == "completed"

    invocations = (
        db_session.query(AgentToolInvocation)
        .filter_by(run_id=admission.run_id)
        .order_by(AgentToolInvocation.created_at)
        .all()
    )
    assert len(invocations) == 2
    assert [invocation.status for invocation in invocations] == [
        "failed",
        "succeeded",
    ]
    observations = (
        db_session.query(AgentObservationRecord)
        .join(
            AgentToolInvocation,
            AgentObservationRecord.tool_invocation_id == AgentToolInvocation.id,
        )
        .filter(AgentToolInvocation.run_id == admission.run_id)
        .order_by(AgentObservationRecord.sequence)
        .all()
    )
    assert [obs.tool_invocation_id for obs in observations] == [
        invocations[0].id,
        invocations[1].id,
    ]


def test_approval_required_call_halts_dispatch_before_execution(
    db_session,
    test_datasource,
) -> None:
    _consume_parallel_tool_events()

    session_id = "session_approval_halts_dispatch"
    db_session.add(
        AgentSession(
            id=session_id,
            datasource_id=str(test_datasource.id),
            title="Approval halts execution",
        )
    )
    db_session.commit()
    sessions = SessionRepository(db_session)
    admission = sessions.admit(
        session_id=session_id,
        datasource_id=str(test_datasource.id),
        datasource_generation=1,
        content="先执行一个并行安全工具，再请求审批。",
        idempotency_key="approval-halts-dispatch",
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
        return ApprovalAwareModel(calls["count"])

    factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)
    RunLoop(
        session_factory=factory,
        model_factory=model_factory,
        registry=ToolRegistry()
        .register(ParallelSafeToolA())
        .register(ApprovalAwareTool())
        .register(ParallelSafeToolB()),
        definition=AgentDefinition(allowed_tool_groups=("catalog",)),
        live_stream=LiveStreamHub(),
    ).execute(lease=lease, run_id=admission.run_id)

    events = _consume_parallel_tool_events()
    assert events == []

    invocations = (
        db_session.query(AgentToolInvocation)
        .filter_by(run_id=admission.run_id)
        .order_by(AgentToolInvocation.created_at)
        .all()
    )
    assert len(invocations) == 3
    assert invocations[0].tool_name == "parallel_safe_test_a"
    assert invocations[0].status == "requested"
    assert invocations[1].tool_name == "approval_required_tool"
    assert invocations[1].status == "waiting_approval"
    assert invocations[2].tool_name == "parallel_safe_test_b"
    assert invocations[2].status == "requested"

    db_session.expire_all()
    run = db_session.get(AgentRun, admission.run_id)
    assert run is not None and run.status == "waiting_approval"


def test_tool_budget_preallocates_and_limits_execution_count(
    db_session,
    test_datasource,
) -> None:
    _consume_parallel_tool_events()

    session_id = "session_tool_budget_prealloc"
    db_session.add(
        AgentSession(
            id=session_id,
            datasource_id=str(test_datasource.id),
            title="Tool budget preallocation",
        )
    )
    db_session.commit()
    sessions = SessionRepository(db_session)
    admission = sessions.admit(
        session_id=session_id,
        datasource_id=str(test_datasource.id),
        datasource_generation=1,
        content="预算上限为两次，但模型一次输出三次工具调用。",
        idempotency_key="tool-budget-prealloc",
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
        return BudgetPreallocationModel(calls["count"])

    factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)
    RunLoop(
        session_factory=factory,
        model_factory=model_factory,
        registry=ToolRegistry().register(BudgetCountTool()),
        definition=AgentDefinition(limits=RunLimits(max_tool_invocations=2)),
        live_stream=LiveStreamHub(),
    ).execute(lease=lease, run_id=admission.run_id)

    events = _consume_parallel_tool_events()
    start_markers = {marker for marker, phase, _ in events if phase == "start"}
    end_markers = {marker for marker, phase, _ in events if phase == "end"}
    assert start_markers == {"A", "B"}
    assert end_markers == {"A", "B"}

    invocations = (
        db_session.query(AgentToolInvocation)
        .filter_by(run_id=admission.run_id)
        .all()
    )
    assert len(invocations) == 2
    assert all(invocation.tool_name == "budget_count_tool" for invocation in invocations)
    markers = sorted(
        json.loads(invocation.input_json or "{}").get("marker", "")
        for invocation in invocations
    )
    assert markers == ["A", "B"]

    db_session.expire_all()
    run = db_session.get(AgentRun, admission.run_id)
    # The two tool calls produce no verifiable deliverable, so the completion
    # gate must not fabricate a bounded-partial result merely because work was
    # performed before the tool budget was exhausted.
    assert run is not None and run.status == "failed"
    assert run.error_code == "AGENT_TOOL_BUDGET"


class BudgetPreallocationModel:
    def __init__(self, call_number: int):
        self.call_number = call_number

    def stream(self, *, messages, tools, timeout_seconds=None, cancellation_probe=None):
        del tools, timeout_seconds, cancellation_probe
        assert self.call_number == 1
        for index, marker in enumerate(["A", "B", "C"]):
            yield from _tool_turn(
                f"budget-{index}",
                "budget_count_tool",
                {"marker": marker},
                tool_call_index=index,
                output_index=index,
                finish=index == 2,
            )


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
            result_artifact_id = next(
                artifact_id
                for artifact_id in json.loads(execute_output["output"])["artifact_ids"]
                if str(artifact_id).startswith("artifact_")
            )
            content = f"共有 42 条订单。{{{{cite:{result_artifact_id}}}}}"
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


class InvalidArtifactContractModel:
    def __init__(self, call_number: int):
        self.call_number = call_number

    def stream(self, *, messages, tools, timeout_seconds=None, cancellation_probe=None):
        if self.call_number == 1:
            arguments = {}
            yield TurnStreamItem(
                kind=TurnStreamKind.TOOL_CALL_START,
                item_id="tool:invalid",
                revision=1,
                tool_call_index=0,
                tool_call_id="invalid-artifact-call",
                tool_name="invalid_artifact",
                arguments_delta=json.dumps(arguments),
            )
            yield TurnStreamItem(
                kind=TurnStreamKind.TOOL_CALL_END,
                item_id="tool:invalid",
                revision=2,
                tool_call_index=0,
            )
            yield TurnStreamItem(
                kind=TurnStreamKind.MODEL_OUTPUT_ITEM,
                item_id="tool:invalid",
                revision=3,
                output_index=0,
                model_output_item={
                    "type": "function_call",
                    "call_id": "invalid-artifact-call",
                    "name": "invalid_artifact",
                    "arguments": json.dumps(arguments),
                },
            )
        else:
            function_output = next(
                item
                for item in messages
                if item.get("type") == "function_call_output"
                and item.get("call_id") == "invalid-artifact-call"
            )
            observation = json.loads(function_output["output"])
            assert observation == {
                "status": "failed",
                "summary": "工具输出未通过合同校验。",
                "facts": {},
                "artifact_ids": [],
                "retryable": False,
                "error_code": "TOOL_OUTPUT_CONTRACT_FAILED",
                "error_message": "Tool output did not match its declared contract.",
            }
            content = "图表未能生成，但本轮仍可继续处理。"
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


class StalledAfterResultModel:
    """Produce one durable Result, then three completed-but-empty model turns."""

    def __init__(self, call_number: int):
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
            kind=TurnStreamKind.FINISH,
            item_id="finish",
            revision=1,
            termination=TurnTermination.COMPLETED,
        )


class ResumePreviousResultModel:
    def __init__(self, call_number: int, *, result_artifact_id: str):
        self.call_number = call_number
        self.result_artifact_id = result_artifact_id

    def stream(self, *, messages, tools, timeout_seconds=None, cancellation_probe=None):
        del timeout_seconds, cancellation_probe
        serialized = json.dumps(messages, ensure_ascii=False)
        if self.call_number == 1:
            available = {
                str(item.get("name") or item.get("function", {}).get("name") or "")
                for item in tools
            }
            assert "result_inspect" in available
            assert "bounded_partial" in serialized
            assert self.result_artifact_id in serialized
            yield from _tool_turn(
                "resume-result",
                "result_inspect",
                {
                    "result_artifact_id": self.result_artifact_id,
                    "page": 1,
                    "page_size": 5,
                },
            )
            return

        output = next(
            item
            for item in messages
            if item.get("type") == "function_call_output"
            and item.get("call_id") == "resume-result"
        )
        observation = json.loads(str(output["output"]))
        assert observation["status"] == "succeeded"
        assert observation["facts"]["returned_rows"] == 1
        assert list(observation["facts"]["rows"][0]) == ["total"]
        yield from _final_turn(
            "继续完成：共有 42 条订单，已复用上次保存的结果工件。"
            f"{{{{cite:{self.result_artifact_id}}}}}"
        )


class FinalizationReserveModel:
    def __init__(
        self,
        call_number: int,
        *,
        state: dict[str, str],
    ) -> None:
        self.call_number = call_number
        self.state = state

    def stream(self, *, messages, tools, timeout_seconds=None, cancellation_probe=None):
        if self.call_number <= 2:
            yield from ScriptedModel(self.call_number).stream(
                messages=messages,
                tools=tools,
                timeout_seconds=timeout_seconds,
                cancellation_probe=cancellation_probe,
            )
            return

        available = {str(item.get("name") or "") for item in tools}
        assert available == {"result_inspect", "update_plan"}
        serialized = json.dumps(messages, ensure_ascii=False)
        assert "synthesize" in serialized
        if self.call_number == 3:
            execute_output = next(
                item
                for item in messages
                if item.get("type") == "function_call_output"
                and item.get("call_id") == "execute"
            )
            observation = json.loads(str(execute_output["output"]))
            result_artifact_id = next(
                artifact_id
                for artifact_id in observation["artifact_ids"]
                if str(artifact_id).startswith("artifact_")
            )
            self.state["result_artifact_id"] = str(result_artifact_id)
            yield from _tool_turn(
                "settle-final-plan",
                "update_plan",
                {
                    "objective": "统计订单数量并给出可验证结论",
                    "steps": [
                        {
                            "id": "count",
                            "title": "统计订单数量",
                            "status": "completed",
                            "evidence_required": True,
                            "artifact_ids": [result_artifact_id],
                        }
                    ],
                    "summary": "查询已完成，正在形成最终回答。",
                },
            )
            return

        result_artifact_id = self.state["result_artifact_id"]
        yield from _final_turn(
            f"当前结果共有 42 条订单。{{{{cite:{result_artifact_id}}}}}"
        )


class UnavailableToolDuringFinalizationModel:
    """Ignore the narrowed tool list once, then recover from its observation."""

    def __init__(
        self,
        call_number: int,
        *,
        state: dict[str, str],
    ) -> None:
        self.call_number = call_number
        self.state = state

    def stream(self, *, messages, tools, timeout_seconds=None, cancellation_probe=None):
        if self.call_number <= 2:
            yield from ScriptedModel(self.call_number).stream(
                messages=messages,
                tools=tools,
                timeout_seconds=timeout_seconds,
                cancellation_probe=cancellation_probe,
            )
            return

        available = {str(item.get("name") or "") for item in tools}
        assert available == {"result_inspect", "update_plan"}
        serialized = json.dumps(messages, ensure_ascii=False)
        assert "synthesize" in serialized
        if self.call_number == 3:
            execute_output = next(
                item
                for item in messages
                if item.get("type") == "function_call_output"
                and item.get("call_id") == "execute"
            )
            observation = json.loads(str(execute_output["output"]))
            result_artifact_id = next(
                artifact_id
                for artifact_id in observation["artifact_ids"]
                if str(artifact_id).startswith("artifact_")
            )
            self.state["result_artifact_id"] = str(result_artifact_id)
            yield from _tool_turn(
                "unavailable-during-finalization",
                "sql_execute_readonly",
                {"validation_artifact_id": "artifact_not_available"},
            )
            return

        if self.call_number == 4:
            unavailable_output = next(
                item
                for item in messages
                if item.get("type") == "function_call_output"
                and item.get("call_id") == "unavailable-during-finalization"
            )
            observation = json.loads(str(unavailable_output["output"]))
            assert observation["status"] == "rejected"
            assert observation["error_code"] == "UNKNOWN_TOOL"
            result_artifact_id = self.state["result_artifact_id"]
            yield from _tool_turn(
                "settle-plan-after-unavailable-call",
                "update_plan",
                {
                    "objective": "统计订单数量并给出可验证结论",
                    "steps": [
                        {
                            "id": "count",
                            "title": "统计订单数量",
                            "status": "completed",
                            "evidence_required": True,
                            "artifact_ids": [result_artifact_id],
                        }
                    ],
                    "summary": "查询已完成，正在形成最终回答。",
                },
            )
            return

        result_artifact_id = self.state["result_artifact_id"]
        yield from _final_turn(
            f"当前结果共有 42 条订单。{{{{cite:{result_artifact_id}}}}}"
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
    assert answer.content.startswith("共有 42 条订单。{{cite:artifact_")
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
    assert recovered.turn_id is not None
    assert [message.phase for message in recovered.messages] == ["commentary", None]
    assert recovered.answer_text.startswith("共有 42 条订单。{{cite:artifact_")
    assert timeline[2]["payload"]["call_id"] == timeline[3]["payload"]["call_id"]
    assert subscription.receive(timeout=0.01).content == "先验证并执行聚合查询。"
    assert subscription.receive(timeout=0.01).content == "正在整理可验证结论。"
    assert subscription.receive(timeout=0.01).content.startswith(
        "共有 42 条订单。{{cite:artifact_"
    )


def test_invalid_artifact_batch_settles_as_tool_contract_failure_without_failing_run(
    db_session,
    test_datasource,
):
    db_session.add(
        AgentSession(
            id="session_invalid_artifact_contract",
            datasource_id=str(test_datasource.id),
            title="Invalid Artifact Contract",
        )
    )
    db_session.commit()
    sessions = SessionRepository(db_session)
    admission = sessions.admit(
        session_id="session_invalid_artifact_contract",
        datasource_id=str(test_datasource.id),
        datasource_generation=1,
        content="生成图表",
        idempotency_key="invalid-artifact-contract",
        llm_credential_id="credential",
        api_base=None,
        model_name="test",
        request_payload={},
    )
    lease = sessions.claim(
        session_id="session_invalid_artifact_contract",
        owner="worker",
        ttl_seconds=120,
    )
    assert lease is not None
    sessions.promote_next_input(lease=lease)
    db_session.commit()

    calls = {"count": 0}

    def model_factory(_settings):
        calls["count"] += 1
        return InvalidArtifactContractModel(calls["count"])

    factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)
    RunLoop(
        session_factory=factory,
        model_factory=model_factory,
        registry=ToolRegistry().register(InvalidArtifactTool()),
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
        .filter_by(tool_invocation_id=invocation.id)
        .one()
    )

    assert run is not None and run.status == "completed"
    assert answer is not None
    assert answer.content == "图表未能生成，但本轮仍可继续处理。"
    assert invocation.status == "failed"
    assert invocation.error_code == "TOOL_OUTPUT_CONTRACT_FAILED"
    assert observation.status == "failed"
    assert observation.error_code == "TOOL_OUTPUT_CONTRACT_FAILED"
    assert json.loads(observation.artifact_ids_json) == []
    assert (
        db_session.query(AgentArtifactRecord).filter_by(run_id=admission.run_id).count()
        == 0
    )
    assert calls["count"] == 2


def test_unexpected_artifact_persistence_failure_still_escapes_run_loop(
    db_session,
    test_datasource,
    monkeypatch,
):
    db_session.add(
        AgentSession(
            id="session_artifact_storage_failure",
            datasource_id=str(test_datasource.id),
            title="Artifact Storage Failure",
        )
    )
    db_session.commit()
    sessions = SessionRepository(db_session)
    admission = sessions.admit(
        session_id="session_artifact_storage_failure",
        datasource_id=str(test_datasource.id),
        datasource_generation=1,
        content="生成图表",
        idempotency_key="artifact-storage-failure",
        llm_credential_id="credential",
        api_base=None,
        model_name="test",
        request_payload={},
    )
    lease = sessions.claim(
        session_id="session_artifact_storage_failure",
        owner="worker",
        ttl_seconds=120,
    )
    assert lease is not None
    sessions.promote_next_input(lease=lease)
    db_session.commit()

    def fail_storage(*_args, **_kwargs):
        raise RuntimeError("database write unavailable")

    monkeypatch.setattr(ArtifactRepository, "persist_drafts", fail_storage)
    factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)
    with pytest.raises(RuntimeError, match="database write unavailable"):
        RunLoop(
            session_factory=factory,
            model_factory=lambda _settings: InvalidArtifactContractModel(1),
            registry=ToolRegistry().register(InvalidArtifactTool()),
            live_stream=LiveStreamHub(),
        ).execute(lease=lease, run_id=admission.run_id)


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


def test_parallel_safe_tool_calls_are_dispatched_concurrently(
    db_session,
    test_datasource,
) -> None:
    _consume_parallel_tool_events()

    session_id = "session_parallel_dispatch"
    db_session.add(
        AgentSession(
            id=session_id,
            datasource_id=str(test_datasource.id),
            title="Parallel dispatch",
        )
    )
    db_session.commit()
    sessions = SessionRepository(db_session)
    admission = sessions.admit(
        session_id=session_id,
        datasource_id=str(test_datasource.id),
        datasource_generation=1,
        content="启动两个并行工具调用。",
        idempotency_key="parallel-safe",
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
        return ParallelSafeModel(calls["count"])

    factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)
    RunLoop(
        session_factory=factory,
        model_factory=model_factory,
        registry=ToolRegistry().register(ParallelSafeToolA()).register(
            ParallelSafeToolB()
        ),
        definition=AgentDefinition(),
        live_stream=LiveStreamHub(),
    ).execute(lease=lease, run_id=admission.run_id)

    events = _consume_parallel_tool_events()
    start_times = [ts for _, phase, ts in events if phase == "start"]
    assert len(start_times) == 2
    assert max(start_times) - min(start_times) < 0.12

    db_session.expire_all()
    run = db_session.get(AgentRun, admission.run_id)
    assert run is not None
    assert run.status == "completed"
    answer = db_session.get(AgentMessage, admission.assistant_message_id)
    assert answer is not None and "并行执行" in answer.content

    invocations = (
        db_session.query(AgentToolInvocation)
        .filter_by(run_id=admission.run_id)
        .order_by(AgentToolInvocation.created_at)
        .all()
    )
    assert len(invocations) == 2
    assert {invocation.tool_name for invocation in invocations} == {
        "parallel_safe_test_a",
        "parallel_safe_test_b",
    }
    assert all(invocation.status == "succeeded" for invocation in invocations)


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
    assert "已保留" in result["answer"]["text"]
    assert "后续运行可以复用已有结果" in result["answer"]["text"]
    assert "来源：" not in result["answer"]["text"]
    assert (
        db_session.query(AgentEvidenceRecord)
        .filter_by(run_id=admission.run_id)
        .count()
        == 0
    )


def test_finalization_reserve_synthesizes_before_the_hard_tool_limit(
    db_session,
    test_datasource,
) -> None:
    session_id = "session-finalization-reserve"
    db_session.add(
        AgentSession(
            id=session_id,
            datasource_id=str(test_datasource.id),
            title="Finalization reserve",
        )
    )
    db_session.commit()
    sessions = SessionRepository(db_session)
    admission = sessions.admit(
        session_id=session_id,
        datasource_id=str(test_datasource.id),
        datasource_generation=1,
        content="统计订单数量并给出可验证结论",
        idempotency_key="finalization-reserve",
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
    model_state: dict[str, str] = {}

    def model_factory(_settings):
        calls["count"] += 1
        return FinalizationReserveModel(calls["count"], state=model_state)

    registry = (
        ToolRegistry()
        .register(ValidateTool())
        .register(ExecuteTool())
        .register(ResultInspectTool())
        .register(UpdatePlanCommand())
    )
    factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)
    RunLoop(
        session_factory=factory,
        model_factory=model_factory,
        registry=registry,
        definition=AgentDefinition(
            limits=RunLimits(
                max_turns=8,
                max_tool_invocations=4,
                finalization_turn_reserve=2,
                finalization_tool_reserve=2,
            )
        ),
        live_stream=LiveStreamHub(),
    ).execute(lease=lease, run_id=admission.run_id)

    db_session.expire_all()
    run = db_session.get(AgentRun, admission.run_id)
    answer = db_session.get(AgentMessage, admission.assistant_message_id)
    turns = (
        db_session.query(AgentTurn)
        .filter_by(run_id=admission.run_id)
        .order_by(AgentTurn.sequence)
        .all()
    )
    assert run is not None and run.status == "completed"
    assert answer is not None and answer.content.startswith("当前结果共有 42 条订单")
    assert calls["count"] == 4
    assert len(turns) == 4
    for turn in turns[-2:]:
        snapshot = json.loads(str(turn.context_snapshot_json))
        assert snapshot["run_focus"]["kind"] == "synthesize"
        materialization = json.loads(str(turn.tool_materialization_json))
        assert {item["name"] for item in materialization["tools"]} == {
            "result_inspect",
            "update_plan",
        }


def test_unavailable_tool_during_finalization_is_rejected_without_failing_run(
    db_session,
    test_datasource,
) -> None:
    session_id = "session-finalization-unavailable-tool"
    db_session.add(
        AgentSession(
            id=session_id,
            datasource_id=str(test_datasource.id),
            title="Finalization unavailable tool",
        )
    )
    db_session.commit()
    sessions = SessionRepository(db_session)
    admission = sessions.admit(
        session_id=session_id,
        datasource_id=str(test_datasource.id),
        datasource_generation=1,
        content="统计订单数量并给出可验证结论",
        idempotency_key="finalization-unavailable-tool",
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
    model_state: dict[str, str] = {}

    def model_factory(_settings):
        calls["count"] += 1
        return UnavailableToolDuringFinalizationModel(
            calls["count"],
            state=model_state,
        )

    registry = (
        ToolRegistry()
        .register(ValidateTool())
        .register(ExecuteTool())
        .register(ResultInspectTool())
        .register(UpdatePlanCommand())
    )
    factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)
    RunLoop(
        session_factory=factory,
        model_factory=model_factory,
        registry=registry,
        definition=AgentDefinition(
            limits=RunLimits(
                max_turns=8,
                max_tool_invocations=4,
                finalization_turn_reserve=2,
                finalization_tool_reserve=2,
            )
        ),
        live_stream=LiveStreamHub(),
    ).execute(lease=lease, run_id=admission.run_id)

    db_session.expire_all()
    run = db_session.get(AgentRun, admission.run_id)
    answer = db_session.get(AgentMessage, admission.assistant_message_id)
    rejected = (
        db_session.query(AgentToolInvocation)
        .filter_by(
            run_id=admission.run_id,
            provider_call_id="unavailable-during-finalization",
        )
        .one()
    )
    assert run is not None and run.status == "completed"
    assert answer is not None and answer.content.startswith("当前结果共有 42 条订单")
    assert rejected.status == "rejected"
    assert rejected.error_code == "UNKNOWN_TOOL"
    assert calls["count"] == 5


def test_no_progress_returns_bounded_partial_when_verified_result_exists(
    db_session, test_datasource
):
    db_session.add(
        AgentSession(
            id="session_no_progress_result",
            datasource_id=str(test_datasource.id),
            title="No progress with durable result",
        )
    )
    db_session.commit()
    sessions = SessionRepository(db_session)
    admission = sessions.admit(
        session_id="session_no_progress_result",
        datasource_id=str(test_datasource.id),
        datasource_generation=1,
        content="统计订单数量并给出结论",
        idempotency_key="no-progress-result",
        llm_credential_id="credential",
        api_base=None,
        model_name="test",
        request_payload={},
    )
    lease = sessions.claim(
        session_id="session_no_progress_result", owner="worker", ttl_seconds=120
    )
    assert lease is not None
    sessions.promote_next_input(lease=lease)
    db_session.commit()

    calls = {"count": 0}

    def model_factory(_settings):
        calls["count"] += 1
        return StalledAfterResultModel(calls["count"])

    factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)
    RunLoop(
        session_factory=factory,
        model_factory=model_factory,
        registry=ToolRegistry().register(ValidateTool()).register(ExecuteTool()),
        definition=AgentDefinition(limits=RunLimits(max_turns=8, max_stalled_turns=2)),
        live_stream=LiveStreamHub(),
    ).execute(lease=lease, run_id=admission.run_id)

    db_session.expire_all()
    run = db_session.get(AgentRun, admission.run_id)
    assert run is not None and run.status == "completed"
    result = json.loads(run.result_json)
    assert result["completion_disposition"] == "bounded_partial"
    assert result["limitation_codes"] == ["NO_PROGRESS"]
    assert "已保留" in result["answer"]["text"]
    assert "来源：" not in result["answer"]["text"]
    assert (
        db_session.query(AgentEvidenceRecord)
        .filter_by(run_id=admission.run_id)
        .count()
        == 0
    )
    assert calls["count"] == 5


def test_next_run_resumes_a_bounded_partial_from_the_previous_result_artifact(
    db_session, test_datasource
):
    session_id = "session_bounded_partial_resume"
    db_session.add(
        AgentSession(
            id=session_id,
            datasource_id=str(test_datasource.id),
            title="Bounded partial resume",
        )
    )
    db_session.commit()
    sessions = SessionRepository(db_session)
    first = sessions.admit(
        session_id=session_id,
        datasource_id=str(test_datasource.id),
        datasource_generation=1,
        content="统计订单数量；达到预算后保留结果。",
        idempotency_key="bounded-partial-first",
        llm_credential_id="credential",
        api_base=None,
        model_name="test",
        request_payload={},
    )
    lease = sessions.claim(session_id=session_id, owner="worker", ttl_seconds=120)
    assert lease is not None
    assert sessions.promote_next_input(lease=lease) == first.run_id
    db_session.commit()

    registry = (
        ToolRegistry()
        .register(ValidateTool())
        .register(ExecuteTool())
        .register(ResultInspectTool())
    )
    factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)
    first_calls = {"count": 0}

    def first_model_factory(_settings):
        first_calls["count"] += 1
        return ToolBudgetModel(first_calls["count"])

    RunLoop(
        session_factory=factory,
        model_factory=first_model_factory,
        registry=registry,
        definition=AgentDefinition(limits=RunLimits(max_tool_invocations=2)),
        live_stream=LiveStreamHub(),
    ).execute(lease=lease, run_id=first.run_id)

    db_session.expire_all()
    first_run = db_session.get(AgentRun, first.run_id)
    assert first_run is not None
    assert json.loads(str(first_run.result_json))["completion_disposition"] == (
        "bounded_partial"
    )
    result_artifact = (
        db_session.query(AgentArtifactRecord)
        .filter_by(run_id=first.run_id, type="result_view")
        .one()
    )

    second = sessions.admit(
        session_id=session_id,
        datasource_id=str(test_datasource.id),
        datasource_generation=1,
        content="继续，直接复用上次已经保存的结果完成回答。",
        idempotency_key="bounded-partial-second",
        llm_credential_id="credential",
        api_base=None,
        model_name="test",
        request_payload={},
    )
    assert sessions.promote_next_input(lease=lease) == second.run_id
    db_session.commit()
    second_calls = {"count": 0}

    def second_model_factory(_settings):
        second_calls["count"] += 1
        return ResumePreviousResultModel(
            second_calls["count"],
            result_artifact_id=str(result_artifact.id),
        )

    RunLoop(
        session_factory=factory,
        model_factory=second_model_factory,
        registry=registry,
        live_stream=LiveStreamHub(),
    ).execute(lease=lease, run_id=second.run_id)

    db_session.expire_all()
    second_run = db_session.get(AgentRun, second.run_id)
    answer = db_session.get(AgentMessage, second.assistant_message_id)
    invocations = (
        db_session.query(AgentToolInvocation)
        .filter(AgentToolInvocation.run_id.in_([first.run_id, second.run_id]))
        .order_by(AgentToolInvocation.created_at)
        .all()
    )
    assert second_run is not None and second_run.status == "completed"
    assert answer is not None and answer.content.startswith("继续完成：共有 42 条订单")
    assert f"{{{{cite:{result_artifact.id}}}}}" in answer.content
    evidence = (
        db_session.query(AgentEvidenceRecord)
        .filter_by(run_id=second.run_id, artifact_id=result_artifact.id)
        .one()
    )
    assert evidence.session_id == session_id
    assert [item.tool_name for item in invocations] == [
        "sql_validate",
        "sql_execute_readonly",
        "result_inspect",
    ]
    assert invocations[-1].status == "succeeded"


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
