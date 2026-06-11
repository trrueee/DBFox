from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage

from engine.agent.graph.state import DataBoxAgentState
from engine.agent.graph.routes import route_model_output
from engine.agent.planning.deterministic_router import build_deterministic_plan
from engine.agent_core.types import AgentRunRequest
from engine.agent.nodes.progress_node import (
    _deterministic_progress_fastpath,
    _enrich_progress_result,
)
from engine.agent.nodes.finalize_node import finalize_answer
from engine.agent.nodes.policy_node import apply_policy
from engine.tools.databox_tools import register_databox_tools


def _state(question: str, **overrides: object) -> DataBoxAgentState:
    state: DataBoxAgentState = {
        "messages": [HumanMessage(content=question)],
        "datasource_id": "ds-1",
        "execute": False,
        "status": "running",
        "step_count": 0,
        "max_steps": 20,
    }
    state.update(overrides)  # type: ignore[typeddict-item]
    return state


class TestDeterministicPlannerRouter:
    def test_schema_question_routes_to_schema_only(self):
        directive = build_deterministic_plan(
            _state("show me the columns in the orders table")
        )

        assert directive.task_type == "schema_understanding"
        assert directive.grounding_level == "schema"
        assert directive.execution_mode == "suggest_only"
        assert directive.should_call_tools is True
        assert directive.should_execute_sql is False
        assert directive.selected_skill_ids == ["schema_exploration"]
        assert "schema" in directive.allowed_tool_groups
        assert "sql_generation" not in directive.allowed_tool_groups
        assert "execution" not in directive.allowed_tool_groups

    def test_data_lookup_without_execute_does_not_open_execution(self):
        directive = build_deterministic_plan(
            _state("count orders by status and show top 10")
        )

        assert directive.task_type == "data_lookup"
        assert directive.execution_mode == "suggest_only"
        assert directive.should_execute_sql is False
        assert "schema" in directive.allowed_tool_groups
        assert "sql_generation" in directive.allowed_tool_groups
        assert "sql_validation" in directive.allowed_tool_groups
        assert "result" in directive.allowed_tool_groups
        assert "execution" not in directive.allowed_tool_groups

    def test_data_lookup_with_execute_opens_execution(self):
        directive = build_deterministic_plan(
            _state("count orders by status", execute=True)
        )

        assert directive.task_type == "data_lookup"
        assert directive.execution_mode == "user_requested_read"
        assert directive.should_execute_sql is True
        assert "execution" in directive.allowed_tool_groups

    def test_workspace_error_routes_to_sql_repair(self):
        directive = build_deterministic_plan(
            _state(
                "fix this SQL error",
                workspace_context={
                    "active_sql": "select missing_column from orders",
                    "last_error": "column missing_column not found",
                },
            )
        )

        assert directive.task_type == "sql_repair"
        assert directive.grounding_level == "workspace"
        assert "workspace" in directive.allowed_tool_groups
        assert "sql_repair" in directive.allowed_tool_groups
        assert "sql_validation" in directive.allowed_tool_groups

    def test_chart_question_adds_chart_tools(self):
        directive = build_deterministic_plan(
            _state("plot monthly revenue trend", execute=True)
        )

        assert directive.task_type == "chart_suggestion"
        assert directive.should_execute_sql is True
        assert "chart" in directive.allowed_tool_groups
        assert "execution" in directive.allowed_tool_groups


class TestDeterministicProgressFastpath:
    def test_dict_ai_message_with_tool_calls_does_not_complete(self):
        state = _state(
            "count orders",
            messages=[
                {"role": "user", "content": "count orders"},
                {
                    "role": "assistant",
                    "content": "I will inspect the schema.",
                    "tool_calls": [
                        {
                            "name": "schema_build_context",
                            "args": {"question": "count orders"},
                            "id": "call_1",
                        }
                    ],
                },
            ],
        )

        assert route_model_output(state) == "policy"
        assert _deterministic_progress_fastpath(state) is None

    def test_policy_reads_dict_ai_message_tool_calls(self):
        state = _state(
            "count orders",
            messages=[
                {"role": "user", "content": "count orders"},
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "name": "schema_build_context",
                            "args": {"question": "count orders"},
                            "id": "call_1",
                        }
                    ],
                },
            ],
            allowed_tool_groups=["schema"],
            execution_mode="suggest_only",
        )
        config = {
            "configurable": {
                "thread_id": "thread-1",
                "registry": register_databox_tools(),
                "db": None,
                "request": AgentRunRequest(
                    datasource_id="ds-1",
                    question="count orders",
                    execute=False,
                ),
            }
        }

        result = apply_policy(state, config)

        assert result["allowed_tool_calls"] == [
            {
                "name": "schema.build_context",
                "args": {"question": "count orders"},
                "id": "call_1",
            }
        ]

    def test_model_text_without_tool_calls_completes(self):
        result = _deterministic_progress_fastpath(
            _state(
                "hello",
                messages=[HumanMessage(content="hello"), AIMessage(content="Hi there.")],
            )
        )

        assert result is not None
        assert result["progress_decision"]["status"] == "complete"

    def test_successful_tool_observation_continues_to_model(self):
        result = _deterministic_progress_fastpath(
            _state(
                "count orders",
                last_tool_results=[
                    {
                        "name": "build_schema_context",
                        "status": "success",
                        "input": {"question": "count orders"},
                        "output": {"selected_tables": ["orders"]},
                        "error": None,
                        "latency_ms": 1,
                    }
                ],
            )
        )

        assert result is not None
        assert result["progress_decision"]["status"] == "continue"

    def test_failed_status_finalizes_as_failed(self):
        result = _deterministic_progress_fastpath(
            _state("count orders", status="failed", error="Agent exceeded max_steps.")
        )

        assert result is not None
        assert result["status"] == "failed"
        assert result["progress_decision"]["status"] == "failed"

    def test_enrich_progress_uses_dict_user_message_for_visible_goal(self):
        enriched = _enrich_progress_result(
            {
                "progress_decision": {
                    "status": "continue",
                    "reason_summary": "Continue with schema lookup.",
                }
            },
            {
                "messages": [{"role": "user", "content": "count orders by status"}],
                "plan_directive": {},
            },
        )

        assert enriched["visible_plan"]["goal"] == "count orders by status"

    def test_finalize_reads_dict_ai_message_content(self):
        result = finalize_answer(
            {
                "messages": [
                    {"role": "user", "content": "hello"},
                    {"role": "assistant", "content": "Hi from a checkpoint."},
                ],
                "artifacts": [],
                "trace_events": [],
            },
            {},
        )

        assert result["status"] == "completed"
        assert result["answer"]["answer"] == "Hi from a checkpoint."
