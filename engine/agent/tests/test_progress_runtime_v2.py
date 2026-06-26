from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage

from engine.agent.graph.state import DBFoxAgentState
from engine.agent.model.context_builder import build_context_message, build_progress_guidance_message
from engine.agent.progress.fast_path import (
    deterministic_progress_fastpath,
    check_sql_repair_fastpath as _check_sql_repair_fastpath,
)
from engine.agent.progress.lens_formatter import enrich_progress_result as _enrich_progress_result
from engine.agent.planning.schemas import AgentPlanDirective
from engine.agent.progress.clarification_policy import (
    should_progress_clarify,
)
from engine.agent.progress.schemas import ProgressDecision
from engine.agent.context_pack import ContextPack, build_context_pack, build_streaming_context_summary, render_ui_summary
from engine.agent.app.event_mapper import context_update_event, trace_to_events
from engine.agent.graph.replan_policy import allow_replan, compute_max_replans
from engine.agent.graph.routes import route_progress_output
from engine.agent.repair.sql_repair import classify_sql_failure, plan_sql_repair
from engine.agent.app.response_builder import _merge_context_summaries
from engine.agent.nodes.prepare_repair_node import prepare_repair


class TestProgressDecisionSchema:
    def test_v2_fields_present(self):
        decision = ProgressDecision(
            status="continue",
            next_action_hint="Check refund trend",
            missing_evidence=["refund trend"],
            user_visible_update="Checking refund rate changes.",
            recovery_strategy="Use sql.validate after schema lookup.",
        )
        dumped = decision.model_dump(mode="json")
        assert dumped["next_action_hint"] == "Check refund trend"
        assert dumped["missing_evidence"] == ["refund trend"]
        assert dumped["user_visible_update"] == "Checking refund rate changes."


class TestClarificationPolicy:

    def test_progress_clarify_blocked_for_schema_errors(self):
        assert should_progress_clarify(
            failure_layer="schema",
            root_cause="column foo not found",
            progress_status="clarify",
        ) is False

class TestSqlRepairModule:
    def test_classifies_missing_column(self):
        assert classify_sql_failure(error_text="column refund_amount not found") == "missing_column"

    def test_classifies_syntax_error(self):
        assert classify_sql_failure(error_text="syntax error near FROM") == "syntax_error"

    def test_plan_includes_repair_trace_fields(self):
        result = _check_sql_repair_fastpath({
            "messages": [HumanMessage(content="q")],
            "revision_count": 0,
            "sql": "SELECT foo FROM orders",
            "execution": {"success": False, "error": "column foo not found in orders"},
        })
        assert result is not None
        assert result.get("repair_trace")
        assert result["repair_trace"][0]["type"] == "agent.repair.attempted"
        assert result["repair_trace"][0]["error_class"] == "missing_column"
        assert result["repair_trace"][0]["root_cause"] == "column foo not found in orders"
        assert result["repair_trace"][0]["failed_sql"] == "SELECT foo FROM orders"

    def test_repair_trace_event_exposes_root_cause_to_runtime_event(self):
        def emit(event_type, **kwargs):
            return {"type": event_type, **kwargs}

        events = list(trace_to_events(emit, {
            "type": "agent.repair.attempted",
            "attempt": 1,
            "error_class": "missing_column",
            "failed_sql": "SELECT foo FROM orders",
            "root_cause": "column foo not found in orders",
            "recovery_strategy": "Use schema.describe_table and fuzzy-match similar columns, then generate corrected SQL and call sql.validate.",
            "user_visible_update": "Column not found — looking up schema to fix the query.",
        }))

        assert events
        step = events[0]["step"]
        assert step["error_class"] == "missing_column"
        assert step["failed_sql"] == "SELECT foo FROM orders"
        assert step["root_cause"] == "column foo not found in orders"
        assert "schema.describe_table" in step["recovery_strategy"]

    def test_repair_trace_uses_validated_sql_when_generation_sql_missing(self):
        result = _check_sql_repair_fastpath({
            "messages": [HumanMessage(content="q")],
            "revision_count": 0,
            "safety": {"safe_sql": "SELECT safe_foo FROM orders"},
            "execution": {"success": False, "error": "column safe_foo not found in orders"},
        })

        assert result is not None
        assert result["repair_trace"][0]["failed_sql"] == "SELECT safe_foo FROM orders"

    def test_repair_guidance_uses_current_sql_lifecycle_tools(self):
        result = _check_sql_repair_fastpath({
            "messages": [HumanMessage(content="q")],
            "revision_count": 0,
            "execution": {"success": False, "error": "syntax error near FROM"},
        })

        assert result is not None
        decision = result["progress_decision"]
        guidance = " ".join(
            str(decision.get(key) or "")
            for key in ("reason_summary", "recovery_strategy", "next_action_hint", "user_visible_update")
        )
        legacy_groups = {"sql_repair", "sql_generation", "sql_validation", "execution"}
        assert "sql.revise" not in guidance
        assert "sql.validate" in guidance
        assert not legacy_groups.intersection(decision["next_tool_groups"])
        assert "sql" in decision["next_tool_groups"]

    def test_permission_denied_no_retry_budget(self):
        plan = plan_sql_repair({
            "revision_count": 0,
            "execution": {"success": False, "error": "permission denied for table orders"},
        })
        assert plan is not None
        assert plan.error_class == "permission_denied"
        assert plan.retry_budget == 0

    def test_requires_confirmation_does_not_trigger_sql_repair(self):
        result = _check_sql_repair_fastpath({
            "messages": [HumanMessage(content="q")],
            "revision_count": 0,
            "safety": {
                "can_execute": True,
                "requires_confirmation": True,
                "safe_sql": "SELECT id FROM users LIMIT 10",
                "blocked_reasons": [],
            },
        })

        assert result is None

    def test_legacy_confirmation_blocker_does_not_trigger_sql_repair(self):
        result = _check_sql_repair_fastpath({
            "messages": [HumanMessage(content="q")],
            "revision_count": 0,
            "safety": {
                "can_execute": False,
                "requires_confirmation": True,
                "safe_sql": "SELECT id FROM users LIMIT 10",
                "blocked_reasons": ["requires_confirmation"],
            },
        })

        assert result is None


class TestStreamingContext:
    def test_build_context_message_includes_conversation_memory_refs(self):
        message = build_context_message({
            "conversation_summary": "用户之前分析了注册趋势。",
            "sql_ref_index": [
                {
                    "purpose": "registration trend",
                    "safe_sql": "SELECT month, COUNT(*) FROM users GROUP BY month",
                    "tables": ["users"],
                    "columns": ["month", "count"],
                }
            ],
            "artifact_ref_index": [
                {
                    "artifact_id": "result_view_1",
                    "source_sql_artifact_id": "sql_1",
                    "columns": ["month", "count"],
                }
            ],
        })

        assert "Conversation Memory" in message.content
        assert "用户之前分析了注册趋势" in message.content
        assert "registration trend" in message.content
        assert "SELECT month, COUNT(*) FROM users GROUP BY month" in message.content
        assert "result_view_1" in message.content

    def test_build_context_message_includes_recent_turns_from_session_memory(self):
        message = build_context_message({
            "recent_turns": [
                {
                    "question": "统计工具调用次数",
                    "answer": "广告文案生成调用最多。",
                    "sql_fingerprints": ["fp_tool_usage"],
                    "artifact_ids": ["result_tool_usage"],
                }
            ],
        })

        assert "Recent turns" in message.content
        assert "统计工具调用次数" in message.content
        assert "广告文案生成调用最多" in message.content
        assert "fp_tool_usage" in message.content
        assert "result_tool_usage" in message.content

    def test_build_context_message_includes_datasource_reusable_sql_candidates(self):
        message = build_context_message({
            "reusable_sql_candidates": [
                {
                    "question": "统计工具调用",
                    "purpose": "tool invocation count",
                    "safe_sql": "SELECT COUNT(*) AS usage_count FROM ai_tool_invocations",
                    "tables": ["ai_tool_invocations"],
                    "columns": ["usage_count"],
                    "usage_count": 3,
                }
            ],
        })

        assert "Datasource Reusable SQL" in message.content
        assert "tool invocation count" in message.content
        assert "SELECT COUNT(*) AS usage_count FROM ai_tool_invocations" in message.content
        assert "usage_count=3" in message.content

    def test_build_streaming_context_summary(self):
        summary = build_streaming_context_summary({
            "context_pack": {"ui_summary": "Using 2 schema tables"},
            "visible_plan": {"current_focus": "Checking refunds"},
            "repair_mode": True,
        })
        assert "2 schema tables" in summary
        assert "Checking refunds" in summary
        assert "Repair mode" in summary

    def test_repair_expands_tool_groups(self):
        enriched = _enrich_progress_result({
            "progress_decision": {
                "status": "continue",
                "recovery_strategy": "sql.validate",
                "next_tool_groups": ["sql", "schema"],
            },
        }, {
            "messages": [HumanMessage(content="q")],
            "allowed_tool_groups": ["db"],
            "revision_count": 0,
        })
        assert enriched.get("repair_mode") is True
        assert "sql" in enriched.get("allowed_tool_groups", [])
        assert "schema" in enriched.get("allowed_tool_groups", [])

    def test_context_update_exposes_semantic_references(self):
        sequence = 0

        def emit(event_type, **kwargs):
            nonlocal sequence
            sequence += 1
            return {"type": event_type, "sequence": sequence, **kwargs}

        event, _ = context_update_event(
            emit,
            {
                "context_pack": {"ui_summary": "Using semantic context"},
                "semantic_resolution": {
                    "semantic_aliases_used": [
                        {"alias": "新注册用户", "target": "users.created_at", "source": "db"}
                    ]
                },
            },
            "",
        )

        assert event is not None
        task_lens = event["step"]["task_lens"]
        assert "memory_references" not in task_lens
        assert task_lens["semantic_references"] == [
            {"label": "新注册用户", "summary": "users.created_at", "source": "db"}
        ]


class TestModelNodeStepLimit:
    def test_allows_post_query_analysis_after_max_steps(self, monkeypatch):
        from unittest.mock import MagicMock

        from engine.agent.nodes import model_node

        calls: list[dict[str, object]] = []

        class FakeModel:
            def bind_tools(self, tools):
                return self

            def invoke(self, messages, config):
                calls.append({"message_count": len(messages), "config": config})
                return AIMessage(content="继续分析查询结果。")

        monkeypatch.setattr(model_node, "get_chat_model", lambda **kwargs: FakeModel())
        registry = MagicMock()
        registry.get.return_value = None

        result = model_node.call_model(
            {
                "messages": [HumanMessage(content="分析用户使用小红书工具的详率")],
                "status": "running",
                "step_count": 20,
                "max_steps": 20,
                "execution": {"success": True, "rowCount": 0},
                "answer": None,
                "allowed_tool_groups": [],
            },
            {
                "configurable": {
                    "thread_id": "run-1",
                    "model_name": "test-model",
                    "api_key": "sk-test",
                    "api_base": "http://example.test/v1",
                    "registry": registry,
                    "db": MagicMock(),
                    "request": MagicMock(),
                }
            },
        )

        assert calls
        assert result["trace_events"][0]["type"] == "agent.model.completed"
        assert "error" not in result

    def test_model_node_does_not_expose_legacy_memory_context(self, monkeypatch):
        from unittest.mock import MagicMock

        from engine.agent.nodes import model_node

        captured: dict[str, object] = {}

        class FakeModel:
            def bind_tools(self, tools):
                return self

            def invoke(self, messages, config):
                captured["messages"] = messages
                return AIMessage(content="继续。")

        monkeypatch.setattr(model_node, "get_chat_model", lambda **kwargs: FakeModel())
        registry = MagicMock()
        registry.get.return_value = None

        result = model_node.call_model(
            {
                "messages": [HumanMessage(content="分析 GMV")],
                "status": "running",
                "step_count": 0,
                "max_steps": 20,
                "allowed_tool_groups": [],
            },
            {
                "configurable": {
                    "thread_id": "run-1",
                    "model_name": "test-model",
                    "api_key": "sk-test",
                    "api_base": "http://example.test/v1",
                    "registry": registry,
                    "db": MagicMock(),
                    "request": MagicMock(),
                }
            },
        )

        assert "memory_context" not in result
        assert "memory_references" not in result
        rendered = "\n".join(getattr(message, "content", "") for message in captured["messages"])
        assert "Relevant Memory Context" not in rendered


class TestContextSummaryMerge:
    def test_merges_ui_summary_and_response(self):
        merged = _merge_context_summaries(
            state={
                "context_pack": {"ui_summary": "Using 2 schema tables, SQL editor"},
                "visible_plan": {"current_focus": "Checking refunds"},
            },
            response_summary="Question: Why did sales drop?",
        )
        assert "Using 2 schema tables" in merged
        assert "Focus: Checking refunds" in merged
        assert "Question:" in merged


class TestSqlRepairFastpath:
    def _state(self, **kwargs) -> DBFoxAgentState:
        base: DBFoxAgentState = {
            "messages": [HumanMessage(content="Why did sales drop?")],
            "revision_count": 0,
            "plan_directive": {"reasoning_summary": "Analyze sales drop"},
        }
        base.update(kwargs)  # type: ignore[typeddict-item]
        return base

    def test_missing_column_triggers_continue_repair(self):
        result = _check_sql_repair_fastpath(self._state(
            execution={"success": False, "error": "column refund_amount not found in orders"},
        ))
        assert result is not None
        decision = result["progress_decision"]
        assert decision["status"] == "continue"
        assert decision["failure_layer"] == "schema"
        assert "schema" in decision["next_tool_groups"]

    def test_empty_result_triggers_continue_not_fail(self):
        result = _check_sql_repair_fastpath(self._state(
            execution={"success": True, "rowCount": 0},
        ))
        assert result is not None
        assert result["progress_decision"]["status"] == "continue"
        assert result["progress_decision"]["failure_layer"] == "result_analysis"

    def test_repair_budget_exhausted_returns_none(self):
        result = _check_sql_repair_fastpath(self._state(
            revision_count=3,
            execution={"success": False, "error": "syntax error near FROM"},
        ))
        assert result is None

    def test_enrich_adds_visible_plan(self):
        enriched = _enrich_progress_result({
            "progress_decision": {
                "status": "continue",
                "user_visible_update": "Checking refunds.",
                "next_action_hint": "Analyze refund trend",
                "missing_evidence": ["refund trend"],
            },
        }, self._state())
        assert enriched["visible_plan"]["current_focus"] == "Checking refunds."
        assert enriched["visible_plan"]["goal"] == "Analyze sales drop"


class TestContextPackV1:
    def test_builds_rich_workspace_context(self):
        pack = build_context_pack({
            "datasource_id": "ds-1",
            "messages": [HumanMessage(content="Why did sales drop in June?")],
            "workspace_context": {
                "datasource_id": "ds-1",
                "selected_sql": "SELECT * FROM orders",
                "selected_table_names": ["orders", "refunds"],
                "selected_column_refs": ["orders.total_amount", "refunds.reason"],
                "open_sql_tabs": [{"id": "t1", "title": "orders.sql", "sql": "SELECT 1"}],
                "last_query_result_preview": {"row_count": 12},
            },
            "plan_directive": {
                "task_type": "data_lookup",
                "execution_mode": "user_requested_read",
                "success_criteria": ["Explain sales drop with evidence"],
            },
            "artifacts": [
                {"type": "sql", "title": "sales_trend.sql", "semantic_id": "sql-1"},
            ],
        })
        assert pack.workspace.selected_tables == ["orders", "refunds"]
        assert pack.workspace.selected_columns == ["orders.total_amount", "refunds.reason"]
        assert pack.intent.original_question == "Why did sales drop in June?"
        assert pack.intent.task_type == "data_lookup"
        assert "sql:sales_trend.sql" in pack.recent_activity.artifact_summaries[0]
        assert "workspace table" in pack.ui_summary

    def test_render_ui_summary(self):
        pack = build_context_pack({
            "datasource_id": "ds-1",
            "workspace_context": {"selected_table_names": ["orders"]},
            "sql": "SELECT 1",
        })
        summary = render_ui_summary(pack)
        assert "orders" in summary or "workspace" in summary.lower()

    def test_non_chartable_suggestion_does_not_set_chart_type(self):
        pack = build_context_pack({
            "chart_suggestion": {"type": "none", "chartable": False, "series": []},
        })

        assert pack.result.chart_type is None

    def test_legacy_schema_key_still_validates(self):
        pack = ContextPack.model_validate({
            "schema": {"selected_tables": ["orders", "refunds"]},
        })
        assert pack.schema_context.selected_tables == ["orders", "refunds"]

    def test_streaming_summary_includes_task_lens_focus(self):
        summary = build_streaming_context_summary({
            "context_pack": {"ui_summary": "Using 2 schema tables"},
            "visible_plan": {"current_focus": "Checking refund trend"},
        })
        assert "Checking refund trend" in summary


class TestAdaptiveReplan:
    def test_complex_task_gets_higher_budget(self):
        state = {
            "plan_directive": {"task_type": "data_lookup"},
            "progress_decision": {"failure_layer": "schema"},
        }
        assert compute_max_replans(state, state["progress_decision"]) >= 3

    def test_replan_allowed_within_adaptive_budget(self):
        state = {
            "plan_directive": {"task_type": "data_lookup"},
            "replan_count": 2,
            "progress_decision": {"status": "replan", "retry_budget": 1, "failure_layer": "schema"},
        }
        assert allow_replan(state, state["progress_decision"]) is True
        assert route_progress_output(state) == "model"

    def test_replan_blocked_when_budget_exhausted(self):
        state = {
            "plan_directive": {"task_type": "chat"},
            "replan_count": 2,
            "progress_decision": {"status": "replan", "retry_budget": 1},
        }
        assert allow_replan(state, state["progress_decision"]) is False
        assert route_progress_output(state) == "finalize"


class TestPrepareRepairNode:
    def test_prepares_repair_stats_and_trace(self):
        state: DBFoxAgentState = {
            "progress_decision": {
                "status": "continue",
                "recovery_strategy": "lookup_schema_then_revise_sql",
                "next_tool_groups": ["schema", "sql"],
            },
            "allowed_tool_groups": ["db"],
            "repair_trace": [
                {
                    "type": "agent.repair.attempted",
                    "error_class": "missing_column",
                    "user_visible_update": "Column foo not found — checking schema.",
                }
            ],
            "revision_count": 2,
            "repair_mode": True,
        }
        result = prepare_repair(state, {})
        assert result["repair_mode"] is True
        assert "schema" in result["allowed_tool_groups"]
        assert result["repair_stats"]["attempts"] == 2
        assert result["repair_stats"]["last_error_class"] == "missing_column"
        assert result["trace_events"][0]["type"] == "agent.repair.prepared"


class TestModelProgressInjection:
    def test_injects_supervisor_guidance(self):
        msg = build_progress_guidance_message({
            "progress_decision": {
                "status": "continue",
                "next_action_hint": "Check refund rate",
                "missing_evidence": ["refund trend"],
                "recovery_strategy": "sql.validate after schema lookup",
            },
        })
        assert msg is not None
        content = msg.content
        assert "Next action" in content
        assert "refund rate" in content
        assert "Missing evidence" in content

    def test_repair_mode_guidance_uses_current_sql_lifecycle(self):
        msg = build_progress_guidance_message({
            "repair_mode": True,
            "progress_decision": {
                "status": "continue",
                "recovery_strategy": "Regenerate the SQL and validate it.",
            },
        })

        assert msg is not None
        content = str(msg.content)
        assert "sql.revise" not in content
        assert "sql.validate" in content
        assert "sql.execute_readonly" in content

    def test_skips_when_complete(self):
        assert build_progress_guidance_message({
            "progress_decision": {"status": "complete"},
        }) is None


class TestLoopPrevention:
    def _state(self, **kwargs) -> DBFoxAgentState:
        base: DBFoxAgentState = {
            "messages": [HumanMessage(content="Why did sales drop?")],
            "revision_count": 0,
            "plan_directive": {"reasoning_summary": "Analyze sales drop"},
        }
        base.update(kwargs)  # type: ignore[typeddict-item]
        return base

    def test_repeated_empty_db_search_triggers_clarify(self):
        state = self._state(
            tool_call_history=[
                {"name": "db.search", "input": {"query": "sales"}, "status": "success", "results_count": 0},
                {"name": "db.search", "input": {"query": "sales"}, "status": "success", "results_count": 0},
            ]
        )
        result = deterministic_progress_fastpath(state)
        assert result is not None
        assert result["status"] == "waiting_user"
        assert result["progress_decision"]["status"] == "clarify"
        assert result["progress_decision"]["should_ask_user"] is True
        assert result["progress_decision"]["should_finalize"] is True

    def test_repeated_schema_describe_table_not_found_triggers_clarify(self):
        state = self._state(
            tool_call_history=[
                {"name": "schema.describe_table", "input": {"table_name": "orders"}, "status": "failed", "error": "table not found"},
                {"name": "schema.describe_table", "input": {"table_name": "orders"}, "status": "failed", "error": "table not found"},
            ]
        )
        result = deterministic_progress_fastpath(state)
        assert result is not None
        assert result["status"] == "waiting_user"
        assert result["progress_decision"]["status"] == "clarify"

    def test_repeated_sql_execution_error_triggers_stop(self):
        state = self._state(
            tool_call_history=[
                {"name": "sql.execute_readonly", "input": {"sql": "SELECT * FROM orders"}, "status": "failed", "error": "syntax error"},
                {"name": "sql.execute_readonly", "input": {"sql": "SELECT * FROM orders"}, "status": "failed", "error": "syntax error"},
            ]
        )
        result = deterministic_progress_fastpath(state)
        assert result is not None
        assert result["status"] == "failed"
        assert result["progress_decision"]["status"] == "failed"
        assert "syntax error" in result["error"]

    def test_one_empty_search_does_not_trigger_loop(self):
        state = self._state(
            tool_call_history=[
                {"name": "db.search", "input": {"query": "sales"}, "status": "success", "results_count": 0},
            ]
        )
        result = deterministic_progress_fastpath(state)
        if result is not None:
            assert result.get("status") != "waiting_user"

    def test_repeated_db_preview_with_same_args_triggers_stop(self):
        state = self._state(
            tool_call_history=[
                {"name": "db.preview", "input": {"table": "orders", "limit": 5}, "status": "success"},
                {"name": "db.preview", "input": {"table": "orders", "limit": 5}, "status": "success"},
            ]
        )
        result = deterministic_progress_fastpath(state)
        assert result is not None
        assert result["status"] == "failed"
        assert result["progress_decision"]["status"] == "failed"
        assert "db.preview" in result["error"]

    def test_repeated_sql_validate_with_same_args_triggers_stop(self):
        state = self._state(
            tool_call_history=[
                {"name": "sql.validate", "input": {"sql": "SELECT * FROM orders"}, "status": "success"},
                {"name": "sql.validate", "input": {"sql": "SELECT * FROM orders"}, "status": "success"},
            ]
        )
        result = deterministic_progress_fastpath(state)
        assert result is not None
        assert result["status"] == "failed"
        assert result["progress_decision"]["status"] == "failed"
        assert "sql.validate" in result["error"]

    def test_useful_db_search_continues_normally(self):
        state = self._state(
            tool_call_history=[
                {"name": "db.search", "input": {"query": "sales"}, "status": "success", "results_count": 5},
                {"name": "db.search", "input": {"query": "sales"}, "status": "success", "results_count": 5},
            ]
        )
        result = deterministic_progress_fastpath(state)
        if result is not None:
            assert result.get("status") != "waiting_user"

