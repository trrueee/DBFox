"""Tests for the analysis agent flow — result.profile, chart.suggest, answer.synthesize.

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
        assert "result" in FULL_SAFE_TOOL_GROUPS
        assert "chart" in FULL_SAFE_TOOL_GROUPS
        assert "answer" in FULL_SAFE_TOOL_GROUPS

    def test_full_safe_groups_still_include_db_groups(self):
        from engine.agent.app.service import FULL_SAFE_TOOL_GROUPS
        for group in ["environment", "schema", "db", "semantic", "memory"]:
            assert group in FULL_SAFE_TOOL_GROUPS


class TestEscalateGroups:
    def test_escalate_accepts_result_group(self):
        from engine.tools.databox_tools import _escalate_tool_group
        ctx = MagicMock()
        ctx.state_view = {"allowed_tool_groups": ["db"]}
        result = _escalate_tool_group(ctx, {"group": "result", "reason": "test"})
        assert result.status == "success"
        assert result.output["escalated"] is True

    def test_escalate_accepts_chart_group(self):
        from engine.tools.databox_tools import _escalate_tool_group
        ctx = MagicMock()
        ctx.state_view = {"allowed_tool_groups": ["db"]}
        result = _escalate_tool_group(ctx, {"group": "chart", "reason": "test"})
        assert result.status == "success"

    def test_escalate_accepts_answer_group(self):
        from engine.tools.databox_tools import _escalate_tool_group
        ctx = MagicMock()
        ctx.state_view = {"allowed_tool_groups": ["db"]}
        result = _escalate_tool_group(ctx, {"group": "answer", "reason": "test"})
        assert result.status == "success"


class TestBuiltinRegistry:
    def test_registry_loads_analysis_tools(self):
        from engine.tools.databox_tools import register_databox_tools
        registry = register_databox_tools()
        for name in ["result.profile", "chart.suggest", "answer.synthesize"]:
            tool = registry.get(name)
            assert tool is not None, f"{name} not found in registry"
            assert tool.spec.group in ("result", "chart", "answer")

    def test_analysis_tools_are_exposed_with_model_safe_aliases(self):
        from engine.agent.tools.registry_bridge import build_langchain_tools
        from engine.tools.databox_tools import register_databox_tools

        registry = register_databox_tools()
        tools = build_langchain_tools(registry, allowed_groups=["result", "chart", "answer"])
        tool_names = {tool.name for tool in tools}

        assert "result_profile" in tool_names
        assert "chart_suggest" in tool_names
        assert "answer_synthesize" in tool_names
        assert all("." not in name for name in tool_names)


class TestToolGroupMap:
    def test_tool_to_group_result_profile(self):
        from engine.agent_core.tool_registry import tool_to_group
        assert tool_to_group("result.profile") == "result"

    def test_tool_to_group_chart_suggest(self):
        from engine.agent_core.tool_registry import tool_to_group
        assert tool_to_group("chart.suggest") == "chart"

    def test_tool_to_group_answer_synthesize(self):
        from engine.agent_core.tool_registry import tool_to_group
        assert tool_to_group("answer.synthesize") == "answer"


# ---------------------------------------------------------------------------
# Phase 2: State binding
# ---------------------------------------------------------------------------

class TestDatabinding:
    def test_result_profile_applier(self):
        from engine.agent_core.databinding import apply_tool_result_to_state
        obs = ToolObservation(name="result.profile", status="success", output={"row_count": 5}, latency_ms=1)
        result = apply_tool_result_to_state(state={}, tool_name="result.profile", observation=obs)
        assert result["result_profile"] == {"row_count": 5}

    def test_chart_suggest_applier(self):
        from engine.agent_core.databinding import apply_tool_result_to_state
        obs = ToolObservation(name="chart.suggest", status="success", output={"type": "bar"}, latency_ms=1)
        result = apply_tool_result_to_state(state={}, tool_name="chart.suggest", observation=obs)
        assert result["chart_suggestion"] == {"type": "bar"}

    def test_answer_synthesize_applier(self):
        from engine.agent_core.databinding import apply_tool_result_to_state
        answer_data = {"answer": "test", "key_findings": []}
        obs = ToolObservation(name="answer.synthesize", status="success", output=answer_data, latency_ms=1)
        result = apply_tool_result_to_state(state={}, tool_name="answer.synthesize", observation=obs)
        assert result["answer"] == answer_data
        assert result["final_answer"] == answer_data

    def test_analysis_tools_in_artifact_set(self):
        from engine.agent_core.databinding import _ARTIFACT_TOOLS
        assert "result.profile" in _ARTIFACT_TOOLS
        assert "chart.suggest" in _ARTIFACT_TOOLS
        assert "answer.synthesize" in _ARTIFACT_TOOLS


class TestAnalysisHandlers:
    def test_answer_synthesize_uses_request_question_when_arg_missing(self):
        from engine.agent_core.tool_registry import ToolContext
        from engine.tools.databox_tools import _answer_synthesize_handler

        request = MagicMock()
        request.question = "How many orders are there?"
        ctx = ToolContext(
            db=MagicMock(),
            request=request,
            state_view={
                "execution": {
                    "success": True,
                    "rowCount": 1,
                    "columns": ["order_count"],
                    "rows": [{"order_count": 42}],
                },
                "result_profile": {
                    "row_count": 1,
                    "notable_facts": ["order_count is 42."],
                    "limitations": [],
                    "anomalies": [],
                },
                "suggestions": [],
            },
        )

        result = _answer_synthesize_handler(ctx, {})

        assert result.status == "success"
        assert "How many orders are there?" in result.output["answer"]
        assert "{'order_count'" not in result.output["answer"]
        assert "42" in result.output["answer"]


# ---------------------------------------------------------------------------
# Phase 5: Deterministic guard
# ---------------------------------------------------------------------------

class TestProgressGuard:
    def test_guard_continues_after_query_without_profile(self):
        from engine.agent.progress.fast_path import deterministic_progress_fastpath
        state = {
            "status": "running",
            "step_count": 3,
            "max_steps": 20,
            "execution": {"success": True, "rowCount": 10},
            "result_profile": None,
            "answer": None,
            "messages": [],
            "last_tool_results": [],
        }
        result = deterministic_progress_fastpath(state)
        assert result is not None
        assert result["progress_decision"]["status"] == "continue"
        assert "profiling" in result["progress_decision"]["reason_summary"].lower()

    def test_guard_allows_finalize_with_answer(self):
        from engine.agent.progress.fast_path import deterministic_progress_fastpath
        state = {
            "status": "running",
            "step_count": 5,
            "max_steps": 20,
            "execution": {"success": True, "rowCount": 10},
            "result_profile": {"row_count": 10},
            "answer": {"answer": "The total is 42."},
            "messages": [],
            "last_tool_results": [],
        }
        result = deterministic_progress_fastpath(state)
        assert result is not None
        assert result["progress_decision"]["status"] == "complete"

    def test_guard_allows_finalize_with_profile_no_answer(self):
        """With profile but no answer, guard does not block — model decides."""
        from engine.agent.progress.fast_path import deterministic_progress_fastpath
        state = {
            "status": "running",
            "step_count": 5,
            "max_steps": 20,
            "execution": {"success": True, "rowCount": 10},
            "result_profile": {"row_count": 10},
            "answer": None,
            "messages": [],
            "last_tool_results": [],
        }
        result = deterministic_progress_fastpath(state)
        # Should fall through to the last_tool_results check or None
        # Guard should NOT fire because result_profile exists
        if result is not None:
            assert result["progress_decision"]["status"] != "continue" or "profiling" not in result["progress_decision"].get("reason_summary", "").lower()


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

class TestSystemPrompt:
    def test_prompt_no_longer_says_stop(self):
        from engine.agent.model.system_prompt import SYSTEM_PROMPT
        assert "STOP and answer" not in SYSTEM_PROMPT
        assert "result.profile" in SYSTEM_PROMPT
        assert "chart.suggest" in SYSTEM_PROMPT
        assert "answer.synthesize" in SYSTEM_PROMPT
