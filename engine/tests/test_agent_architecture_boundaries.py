from __future__ import annotations

from engine.agent.planner import _infer_intent
from engine.agent.types import AgentErrorOutput, AgentRunRequest
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


def test_agent_error_output_is_typed() -> None:
    payload = AgentErrorOutput(
        error_type="OperationalError",
        tool_name="sql.execute_readonly",
        step_name="execute_sql",
        traceback="traceback text",
        retryable=True,
        retry_reason="transient_database_or_connection_error",
    ).model_dump(mode="json")

    assert payload["error_type"] == "OperationalError"
    assert payload["retryable"] is True
    assert payload["retry_reason"] == "transient_database_or_connection_error"


def test_imports_and_aliases() -> None:
    # 1. lifecycle.py can import
    import engine.agent_kernel.lifecycle as lf
    # 2. New modules can import
    import engine.agent_kernel.intent_fallback as fallback
    import engine.agent_kernel.reference_resolver as resolver
    import engine.agent_kernel.critics as critics
    import engine.agent_kernel.plan_templates as plan_templates

    assert lf.understand_node is not None
    # 5. classify_intent compatibility alias is available
    assert lf.classify_intent is fallback.classify_intent_fallback
    assert fallback.classify_intent is fallback.classify_intent_fallback


def test_understand_node_source_without_api_key() -> None:
    # 3. understand_node has source=rule_fallback when no api_key
    from engine.agent_kernel.lifecycle import understand_node
    state: KernelState = {
        "messages": [{"role": "user", "content": "hello"}],
    }
    result = understand_node(state)
    assert result["agent_intent"]["source"] == "rule_fallback"


def test_understand_node_source_with_llm(monkeypatch) -> None:
    # 4. understand_node mock LLM success has source=llm
    from engine.agent_kernel.lifecycle import understand_node

    class FakeResponse:
        status_code = 200
        def raise_for_status(self): pass
        def json(self):
            return {
                "choices": [
                    {
                        "message": {
                            "content": '{"intent": "new_data_question", "confidence": "high", "reason": "test", "needs_execution": true}'
                        }
                    }
                ]
            }

    monkeypatch.setattr("engine.agent_kernel.intent_classifier.httpx.post", lambda *_args, **_kwargs: FakeResponse())

    state: KernelState = {
        "messages": [{"role": "user", "content": "how many users?"}],
        "api_key": "sk-test",
    }
    result = understand_node(state)
    assert result["agent_intent"]["source"] == "llm"


def test_resolve_reference_priority() -> None:
    # 6. resolve_reference selected_sql priority remains unchanged
    from engine.agent_kernel.reference_resolver import resolve_reference
    state: KernelState = {
        "messages": [{"role": "user", "content": "this query"}],
        "workspace_context": {
            "selected_sql": "SELECT * FROM users",
            "pending_approval_id": "appr-abc",
        },
        "sql": "SELECT * FROM orders",
    }
    ref = resolve_reference(state)
    assert ref["kind"] == "sql"
    assert ref["source"] == "workspace_context"
    assert ref["sql_preview"] == "SELECT * FROM users"


def test_critique_sql_scenarios() -> None:
    # 7. critique_sql allows reasonable SQL
    from engine.agent_kernel.critics import critique_sql
    state: KernelState = {
        "messages": [{"role": "user", "content": "total revenue"}],
        "sql": "SELECT SUM(amount) FROM sales",
        "query_plan": {"metrics": ["revenue"]},
        "last_tool_name": "sql.generate",
    }
    crit = critique_sql(state)
    assert crit["needs_revision"] is False

    # 8. critique_sql still flags aggregate metrics with missing GROUP BY
    state_bad: KernelState = {
        "messages": [{"role": "user", "content": "total revenue by country"}],
        "sql": "SELECT country, SUM(amount) FROM sales",
        "query_plan": {"metrics": ["revenue"], "dimensions": ["country"]},
        "last_tool_name": "sql.generate",
    }
    crit_bad = critique_sql(state_bad)
    assert crit_bad["needs_revision"] is True
    assert any("GROUP BY" in issue for issue in crit_bad["issues"])


def test_critique_answer_skipped_execution() -> None:
    # 9. critique_answer still corrects when execution is skipped but data claims are present
    from engine.agent_kernel.critics import critique_answer, corrected_answer
    state: KernelState = {
        "answer": {"answer": "There are 100 rows."},
        "execute": False,
        "execution": {"success": False, "reason": "execute=false"},
    }
    crit = critique_answer(state)
    assert crit["needs_correction"] is True
    assert crit["execution_skipped"] is True

    corrected = corrected_answer(state["answer"], crit)
    assert "Execution was disabled" in corrected["answer"]


def test_plan_route_structure() -> None:
    # 10. plan_route for new_data_question still includes sql.generate
    from engine.agent_kernel.plan_templates import plan_route
    state: KernelState = {
        "messages": [{"role": "user", "content": "GMV"}],
    }
    plan = plan_route(state)
    assert "sql.generate" in plan["route"]

