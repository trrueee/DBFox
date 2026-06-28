"""Tests for the analysis agent flow — chart.suggest.

Covers:
- Safe tool groups include analysis tools
- Escalate accepts analysis groups
- Builtin registry loads analysis tools
- Databinding stores analysis outputs
- Tool group map includes analysis groups
- Progress guard prevents premature finalization
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from engine.agent_core.types import ToolObservation


# ---------------------------------------------------------------------------
# Phase 1: Tool specs and groups
# ---------------------------------------------------------------------------

class TestSafeToolGroups:
    def test_full_safe_groups_include_analysis_tools(self):
        from engine.agent.app.service import FULL_SAFE_TOOL_GROUPS
        assert "chart" in FULL_SAFE_TOOL_GROUPS
        assert "answer" not in FULL_SAFE_TOOL_GROUPS

    def test_full_safe_groups_still_include_db_groups(self):
        from engine.agent.app.service import FULL_SAFE_TOOL_GROUPS
        for group in ["environment", "schema", "db"]:
            assert group in FULL_SAFE_TOOL_GROUPS
        assert "memory" not in FULL_SAFE_TOOL_GROUPS


class TestEscalateGroups:
    def test_escalate_accepts_chart_group(self):
        from engine.tools.dbfox_tools import EscalateTool
        from engine.tools.runtime.context import ToolRunContext

        result = EscalateTool().run(
            EscalateTool.input_model(group="chart", reason="test"),
            ToolRunContext(state={"allowed_tool_groups": ["db"]}),
        )
        assert result.model_dump(mode="json")["group"] == "chart"

    def test_escalate_rejects_answer_group(self):
        from engine.tools.dbfox_tools import EscalateTool
        from engine.tools.runtime.context import ToolRunContext

        with pytest.raises(RuntimeError, match="Unknown tool group 'answer'"):
            EscalateTool().run(
                EscalateTool.input_model(group="answer", reason="test"),
                ToolRunContext(state={"allowed_tool_groups": ["db"]}),
            )


class TestBuiltinRegistry:
    def test_registry_loads_analysis_tools(self):
        from engine.tools.dbfox_tools import register_dbfox_tools
        registry = register_dbfox_tools()
        chart = registry.get("chart.suggest")
        assert chart is not None
        assert chart.spec.group == "chart"
        assert registry.get("answer.synthesize") is None

    def test_analysis_tools_are_exposed_with_model_safe_aliases(self):
        from engine.agent.tools.registry_bridge import build_langchain_tools
        from engine.tools.dbfox_tools import register_dbfox_tools

        registry = register_dbfox_tools()
        tools = build_langchain_tools(registry, allowed_groups=["result", "chart", "answer"])
        tool_names = {tool.name for tool in tools}

        assert "chart_suggest" in tool_names
        assert "answer_synthesize" not in tool_names
        assert all("." not in name for name in tool_names)


class TestToolGroupMap:
    def test_tool_to_group_chart_suggest(self):
        from engine.tools.runtime.registry import tool_to_group
        assert tool_to_group("chart.suggest") == "chart"


# ---------------------------------------------------------------------------
# Phase 2: State binding
# ---------------------------------------------------------------------------

class TestDatabinding:
    def test_chart_suggest_applier(self):
        from engine.agent_core.databinding import apply_tool_result_to_state
        obs = ToolObservation(name="chart.suggest", status="success", output={"type": "bar"}, latency_ms=1)
        result = apply_tool_result_to_state(state={}, tool_name="chart.suggest", observation=obs)
        assert result["chart_suggestion"] == {"type": "bar"}

    def test_analysis_tools_in_artifact_set(self):
        from engine.tools.runtime.state_reducer import ARTIFACT_TOOLS
        assert "chart.suggest" in ARTIFACT_TOOLS

    def test_successful_db_query_clears_stale_error_state(self):
        from engine.agent_core.databinding import apply_tool_result_to_state

        state = {
            "error": "TrustGate blocked execution because schema validation found unknown tables or columns.",
            "last_error_telemetry": {"error_type": "GuardrailValidationError"},
            "last_failed_tool_call": {"tool_name": "db.query", "args": {"sql": "SELECT bad FROM audit_logs"}},
        }
        obs = ToolObservation(
            name="db.query",
            status="success",
            output={
                "status": "success",
                "returned_rows": 1,
                "rows": [{"total_logs": "3024"}],
                "safe_sql": "SELECT COUNT(*) AS total_logs FROM audit_logs LIMIT 1000",
            },
            latency_ms=1,
        )

        result = apply_tool_result_to_state(state=state, tool_name="db.query", observation=obs)

        assert result["error"] is None
        assert result["last_error_telemetry"] is None
        assert result["last_failed_tool_call"] is None


# ---------------------------------------------------------------------------
# Phase 4: Deterministic guard
# ---------------------------------------------------------------------------

class TestProgressGuard:
    def test_guard_does_not_block_single_query_without_profile(self):
        """With relaxed guard, a single db.query without analysis does NOT trigger
        the analysis guard. The model is free to stop tool calls and enter answer."""
        from engine.agent.progress.fast_path import deterministic_progress_fastpath
        state = {
            "status": "running",
            "step_count": 3,
            "max_steps": 20,
            "execution": {"success": True, "rowCount": 10},
            "answer": None,
            "messages": [],
            "last_tool_results": [],
        }
        result = deterministic_progress_fastpath(state)
        # Guard should not fire for single query at low step count
        if result is not None:
            assert "profiling" not in result["progress_decision"].get("reason_summary", "").lower()

    def test_guard_blocks_cycling_queries_without_profile(self):
        """Relaxed guard fires when model calls db.query >=2 times without
        analysis or answer, AND step_count > 4."""
        from engine.agent.progress.fast_path import deterministic_progress_fastpath
        state = {
            "status": "running",
            "step_count": 6,
            "max_steps": 20,
            "execution": {"success": True, "rowCount": 10},
            "answer": None,
            "messages": [],
            "last_tool_results": [
                {"name": "db.query", "status": "success"},
                {"name": "db.query", "status": "success"},
            ],
        }
        result = deterministic_progress_fastpath(state)
        assert result is not None
        assert result["progress_decision"]["status"] == "continue"
        assert "answer.synthesize" not in result["progress_decision"]["next_action_hint"]
        assert "summarize the current conclusion" in result["progress_decision"]["next_action_hint"]
        assert "停止调用工具" not in result["progress_decision"]["next_action_hint"]

    def test_guard_allows_finalize_with_answer(self):
        from engine.agent.progress.fast_path import deterministic_progress_fastpath
        state = {
            "status": "running",
            "step_count": 5,
            "max_steps": 20,
            "execution": {"success": True, "rowCount": 10},
            "answer": {"answer": "The total is 42."},
            "messages": [],
            "last_tool_results": [],
        }
        result = deterministic_progress_fastpath(state)
        assert result is not None
        assert result["progress_decision"]["status"] == "complete"

    def test_guard_blocks_cycling_queries_even_at_max_steps(self):
        """Relaxed guard still fires at max_steps when model is cycling queries
        without analysis — the analysis guard check precedes the max_steps check."""
        from engine.agent.progress.fast_path import deterministic_progress_fastpath
        state = {
            "status": "running",
            "step_count": 20,
            "max_steps": 20,
            "execution": {"success": True, "rowCount": 0},
            "answer": None,
            "messages": [],
            "last_tool_results": [
                {"name": "db.query", "status": "success"},
                {"name": "db.query", "status": "success"},
            ],
        }

        result = deterministic_progress_fastpath(state)

        assert result is not None
        assert result["progress_decision"]["status"] == "continue"
        assert "answer.synthesize" not in result["progress_decision"]["next_action_hint"]
        assert "summarize the current conclusion" in result["progress_decision"]["next_action_hint"]
        assert "停止调用工具" not in result["progress_decision"]["next_action_hint"]
        assert "error" not in result

    def test_guard_final_text_wins_over_max_steps_without_error(self):
        from langchain_core.messages import AIMessage, HumanMessage
        from engine.agent.progress.fast_path import deterministic_progress_fastpath

        state = {
            "status": "running",
            "step_count": 20,
            "max_steps": 20,
            "messages": [
                HumanMessage(content="How many orders?"),
                AIMessage(content="There are 42 orders."),
            ],
        }

        result = deterministic_progress_fastpath(state)

        assert result is not None
        assert result["progress_decision"]["status"] == "ready_for_answer"
        assert "error" not in result

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

class TestSystemPrompt:
    def test_prompt_no_longer_says_stop(self):
        from engine.agent.model.system_prompt import SYSTEM_PROMPT
        assert "STOP and answer" not in SYSTEM_PROMPT
        assert "chart.suggest" in SYSTEM_PROMPT
        assert "answer.synthesize" not in SYSTEM_PROMPT
        assert "最终回答阶段" not in SYSTEM_PROMPT
        assert "answer-stage" not in SYSTEM_PROMPT
        assert "answer-ready context" not in SYSTEM_PROMPT
        assert "write one short Chinese sentence saying" not in SYSTEM_PROMPT

    def test_prompt_preserves_old_agentic_analysis_tone(self):
        from engine.agent.model.system_prompt import SYSTEM_PROMPT

        assert "You are DBFox, an autonomous data analysis agent." in SYSTEM_PROMPT
        assert "Producing a grounded final answer." in SYSTEM_PROMPT
        assert "respond directly with a brief answer" in SYSTEM_PROMPT
        assert "You decide when to answer." in SYSTEM_PROMPT
        assert "**5. Answer.**" in SYSTEM_PROMPT
        assert "think like a data engineer" in SYSTEM_PROMPT
        assert "data speaks through analysis, not raw rows" in SYSTEM_PROMPT

    def test_prompt_requires_text_with_tool_calls(self):
        """The prompt must instruct the model to include Chinese text alongside tool calls.
        Without this, Qwen returns empty content when tools are bound."""
        from engine.agent.model.system_prompt import SYSTEM_PROMPT

        assert "Stage Narration" in SYSTEM_PROMPT
        assert "one short Chinese sentence" in SYSTEM_PROMPT
        assert "Do not narrate every tiny internal step" in SYSTEM_PROMPT
        assert "Never send an empty message" in SYSTEM_PROMPT
        assert "Always speak" not in SYSTEM_PROMPT

    def test_prompt_requires_semantic_expansion_for_schema_search(self):
        from engine.agent.model.system_prompt import SYSTEM_PROMPT

        assert "semantic search expressions" in SYSTEM_PROMPT
        assert "Do not search only the user's literal words" in SYSTEM_PROMPT
        assert "call db.search separately" in SYSTEM_PROMPT
        assert "same step when possible" in SYSTEM_PROMPT
        assert "Before the first db.search" in SYSTEM_PROMPT
        assert "state your semantic search plan in Chinese" in SYSTEM_PROMPT
        assert "issue at least two db.search calls" in SYSTEM_PROMPT
        assert "Chinese synonyms" in SYSTEM_PROMPT
        assert "English schema terms" in SYSTEM_PROMPT
        assert "abbreviations" in SYSTEM_PROMPT
        assert "possible table or column names" in SYSTEM_PROMPT
        assert "Never claim a table was found unless it appears in a tool result" in SYSTEM_PROMPT

    def test_prompt_requires_followup_sql_after_raw_preview_for_analysis(self):
        from engine.agent.model.system_prompt import SYSTEM_PROMPT

        assert "After db.preview" in SYSTEM_PROMPT
        assert "follow-up analytical SQL" in SYSTEM_PROMPT
        assert "do not synthesize analytical conclusions from raw preview rows" in SYSTEM_PROMPT
