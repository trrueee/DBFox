from __future__ import annotations

from engine.agent.planner import _infer_intent
from engine.agent.types import AgentRunRequest
from engine.agent_kernel.controller import decide_next_action
from engine.agent.executor import _is_retryable_exception


def test_controller_returns_structured_wait_approval_decision() -> None:
    decision = decide_next_action(
        state={
            "pending_approval": {
                "id": "appr-1",
                "status": "pending",
                "risk_level": "warning",
                "reason": "Manual review required.",
                "requested_action": {"tool_name": "sql.execute_readonly", "args": {}},
            }
        },
        available_tools=[],
    )

    assert decision.action == "wait_approval"
    assert decision.approval_context is not None
    assert decision.approval_context.approval_id == "appr-1"
    assert decision.approval_context.tool_name == "sql.execute_readonly"
    assert decision.final_answer is None


def test_fallback_planner_does_not_force_fix_for_negated_request() -> None:
    req = AgentRunRequest(datasource_id="ds-1", question="分析为什么这个 SQL 无法优化，不需要你修复它")
    context_bundle = {
        "workspace": {
            "active_sql": "SELECT * FROM orders",
            "last_error": "unknown column",
        }
    }

    assert _infer_intent(req, context_bundle) == "analysis"


def test_executor_marks_transient_database_errors_retryable() -> None:
    assert _is_retryable_exception(RuntimeError("database lock wait timeout")) is True
    assert _is_retryable_exception(ValueError("invalid input")) is False
