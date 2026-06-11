from __future__ import annotations

from langchain_core.messages import HumanMessage

from engine.agent.graph.state import DataBoxAgentState
from engine.agent.model.context_builder import build_progress_guidance_message
from engine.agent.nodes.progress_node import _check_sql_repair_fastpath, _enrich_progress_result
from engine.agent.nodes.planner_node import _apply_clarification_policy
from engine.agent.planning.schemas import AgentPlanDirective
from engine.agent.progress.clarification_policy import (
    is_clarification_allowed,
    should_progress_clarify,
)
from engine.agent.progress.schemas import ProgressDecision
from engine.agent.context_pack import ContextPack, build_context_pack, build_streaming_context_summary, render_ui_summary
from engine.agent.nodes.progress_node import _enrich_progress_result
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
            recovery_strategy="Use sql.revise after schema lookup.",
        )
        dumped = decision.model_dump(mode="json")
        assert dumped["next_action_hint"] == "Check refund trend"
        assert dumped["missing_evidence"] == ["refund trend"]
        assert dumped["user_visible_update"] == "Checking refund rate changes."


class TestClarificationPolicy:
    def test_suppresses_unknown_table_clarification(self):
        directive = AgentPlanDirective(
            task_type="ambiguous",
            grounding_level="schema",
            execution_mode="user_requested_read",
            allowed_tool_groups=[],
            should_call_tools=False,
            should_execute_sql=True,
            needs_clarification=True,
            clarification_question="Which table should I query?",
            reasoning_summary="Unknown table name",
        )
        allowed, reason = is_clarification_allowed(directive, {"datasource_id": "ds-1"})
        assert allowed is False
        assert reason == "self_recoverable_gap"

    def test_allows_missing_active_entity(self):
        directive = AgentPlanDirective(
            task_type="result_analysis",
            grounding_level="workspace",
            execution_mode="none",
            allowed_tool_groups=["workspace"],
            should_call_tools=True,
            should_execute_sql=False,
            needs_clarification=True,
            clarification_question="Which table did you mean?",
            reasoning_summary="User asked to analyze this table",
        )
        allowed, _ = is_clarification_allowed(directive, {"datasource_id": "ds-1", "workspace_context": {}})
        assert allowed is True

    def test_progress_clarify_blocked_for_schema_errors(self):
        assert should_progress_clarify(
            failure_layer="schema",
            root_cause="column foo not found",
            progress_status="clarify",
        ) is False

    def test_planner_policy_overrides_unknown_table(self):
        directive = AgentPlanDirective(
            task_type="ambiguous",
            grounding_level="none",
            execution_mode="user_requested_read",
            allowed_tool_groups=[],
            should_call_tools=False,
            should_execute_sql=True,
            needs_clarification=True,
            clarification_question="Which table?",
            reasoning_summary="Unknown table name",
        )
        updated = _apply_clarification_policy(directive, {"datasource_id": "ds-1"})
        assert updated.needs_clarification is False
        assert "schema" in updated.allowed_tool_groups
        assert updated.task_type == "data_lookup"


class TestSqlRepairModule:
    def test_classifies_missing_column(self):
        assert classify_sql_failure(error_text="column refund_amount not found") == "missing_column"

    def test_classifies_syntax_error(self):
        assert classify_sql_failure(error_text="syntax error near FROM") == "syntax_error"

    def test_plan_includes_repair_trace_fields(self):
        result = _check_sql_repair_fastpath({
            "messages": [HumanMessage(content="q")],
            "revision_count": 0,
            "execution": {"success": False, "error": "column foo not found in orders"},
        })
        assert result is not None
        assert result.get("repair_trace")
        assert result["repair_trace"][0]["type"] == "agent.repair.attempted"
        assert result["repair_trace"][0]["error_class"] == "missing_column"

    def test_permission_denied_no_retry_budget(self):
        plan = plan_sql_repair({
            "revision_count": 0,
            "execution": {"success": False, "error": "permission denied for table orders"},
        })
        assert plan is not None
        assert plan.error_class == "permission_denied"
        assert plan.retry_budget == 0


class TestStreamingContext:
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
                "recovery_strategy": "sql.revise",
                "next_tool_groups": ["sql_repair", "schema"],
            },
        }, {
            "messages": [HumanMessage(content="q")],
            "allowed_tool_groups": ["sql_generation"],
            "revision_count": 0,
        })
        assert enriched.get("repair_mode") is True
        assert "sql_repair" in enriched.get("allowed_tool_groups", [])
        assert "schema" in enriched.get("allowed_tool_groups", [])


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
    def _state(self, **kwargs) -> DataBoxAgentState:
        base: DataBoxAgentState = {
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
        assert route_progress_output(state) == "planner"

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
        state: DataBoxAgentState = {
            "progress_decision": {
                "status": "continue",
                "recovery_strategy": "lookup_schema_then_revise_sql",
                "next_tool_groups": ["schema", "sql_generation"],
            },
            "allowed_tool_groups": ["sql_generation"],
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
                "recovery_strategy": "sql.revise after schema lookup",
            },
        })
        assert msg is not None
        content = msg.content
        assert "Next action" in content
        assert "refund rate" in content
        assert "Missing evidence" in content

    def test_skips_when_complete(self):
        assert build_progress_guidance_message({
            "progress_decision": {"status": "complete"},
        }) is None
