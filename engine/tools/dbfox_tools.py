from __future__ import annotations

import time
from typing import Any

from engine.tools.db_tools import (
    db_inspect,
    db_observe,
    db_query,
    db_remember,
    db_search,
)
from engine.tools.safe_preview import db_preview
from engine.agent_core.types import ToolObservation
from engine.agent_core.tool_registry import ToolContext, ToolRegistry
from engine.agent_core.result_profiler import profile_result
from engine.agent_core.chart_builder import suggest_plotly_chart
from engine.agent_core.answer import synthesize_agent_answer


# ---------------------------------------------------------------------------
# registration
# ---------------------------------------------------------------------------


def register_dbfox_tools() -> ToolRegistry:
    """Create and populate the ToolRegistry for DBFox Agent.

    Handlers registered here bridge YAML specs to Python code.
    """
    from engine.agent_core.handler_registry import get_handler_registry

    handlers = get_handler_registry()

    # -- Control handler (always-available, never group-filtered) ----------
    handlers.force_register("escalate_tool_group", _escalate_tool_group)

    # -- db.* tools --------------------------------------------------------
    handlers.force_register("db_observe", db_observe)
    handlers.force_register("db_search", db_search)
    handlers.force_register("db_inspect", db_inspect)
    handlers.force_register("db_preview", db_preview)
    handlers.force_register("db_query", db_query)
    handlers.force_register("db_remember", db_remember)

    # -- Environment tools -------------------------------------------------
    from engine.environment.tools import (
        environment_get_profile, schema_list_tables,
        schema_describe_table, schema_refresh_catalog,
    )
    handlers.force_register("environment_get_profile", environment_get_profile)
    handlers.force_register("schema_list_tables", schema_list_tables)
    handlers.force_register("schema_describe_table", schema_describe_table)
    handlers.force_register("schema_refresh_catalog", schema_refresh_catalog)

    # -- Semantic ----------------------------------------------------------
    from engine.semantic.tools import semantic_resolve
    handlers.force_register("semantic_resolve", semantic_resolve)

    # -- Memory ------------------------------------------------------------
    from engine.tools.memory_tools import (
        memory_search, memory_write, memory_delete, memory_summarize_session,
    )
    handlers.force_register("memory_search", memory_search)
    handlers.force_register("memory_write", memory_write)
    handlers.force_register("memory_delete", memory_delete)
    handlers.force_register("memory_summarize_session", memory_summarize_session)

    # -- Analysis tools ---------------------------------------------------
    handlers.force_register("analyze_data_handler", _analyze_data_handler)
    handlers.force_register("chart_suggest_handler", _chart_suggest_handler)


    # -- Build registry from YAML specs + handlers -------------------------
    registry = ToolRegistry()
    registry.add_builtin_source()
    try:
        from pathlib import Path
        registry.add_user_source(Path.home() / ".dbfox" / "tools", priority=10)
        cwd = Path.cwd()
        project_dir = cwd / ".dbfox" / "tools"
        if project_dir.is_dir():
            registry.add_user_source(project_dir, priority=20)
    except Exception:
        pass
    registry.load_all()

    return registry


# ---- Escalate ---------------------------------------------------------------


def _escalate_tool_group(ctx: ToolContext, args: dict[str, Any]) -> ToolObservation:
    """Request additional tool group access."""
    group = str(args.get("group", "")).strip()
    reason = str(args.get("reason", "")).strip()

    valid_groups = {
        "environment", "schema", "db", "semantic",
        "memory", "execution", "result", "chart", "answer",
    }

    if group not in valid_groups:
        return ToolObservation(
            name="escalate.tool_group",
            status="failed",
            input=args,
            error=f"Unknown tool group '{group}'. Valid groups: {', '.join(sorted(valid_groups))}",
            latency_ms=0,
        )

    current_groups: list[str] = list(ctx.state_view.get("allowed_tool_groups") or [])
    if group in current_groups:
        return ToolObservation(
            name="escalate.tool_group",
            status="success",
            input=args,
            output={"escalated": False, "group": group,
                    "reason": reason, "message": f"Group '{group}' is already available."},
            latency_ms=0,
        )

    new_groups = current_groups + [group]
    return ToolObservation(
        name="escalate.tool_group",
        status="success",
        input=args,
        output={
            "escalated": True,
            "group": group,
            "reason": reason,
            "escalated_tool_groups": new_groups,
        },
        latency_ms=0,
    )


# ---- Analysis tool handlers ------------------------------------------------


def _analyze_data_handler(ctx: ToolContext, args: dict[str, Any]) -> ToolObservation:
    """Compute statistical profile from execution results.

    Dual-path data access:
    1. Explicit: model passes execution_result in args (clean, self-contained)
    2. Implicit: falls back to ctx.state_view.get("execution") (zero-arg convenience)
    """
    execution = args.get("execution_result") or ctx.state_view.get("execution")
    if not execution or not execution.get("success"):
        return ToolObservation(
            name="analyze_data",
            status="failed",
            input=args,
            error="No successful execution result available. Run db.query first.",
            latency_ms=0,
        )
    start = time.monotonic()
    try:
        question = args.get("question") or (ctx.request.question if ctx.request else "") or ""
        columns = list(execution.get("columns") or [])
        rows = list(execution.get("rows") or [])
        data_profile = profile_result(
            question=question,
            columns=columns,
            rows=rows,
            execution_success=True,
        )
        latency = int((time.monotonic() - start) * 1000)
        return ToolObservation(
            name="analyze_data",
            status="success",
            input=args,
            output=data_profile.model_dump(mode="json"),
            latency_ms=latency,
        )
    except Exception as exc:
        latency = int((time.monotonic() - start) * 1000)
        return ToolObservation(
            name="analyze_data",
            status="failed",
            input=args,
            error=str(exc),
            latency_ms=latency,
        )

def _chart_suggest_handler(ctx: ToolContext, args: dict[str, Any]) -> ToolObservation:
    """Suggest a chart type for the current result set."""
    execution = ctx.state_view.get("execution")
    if not execution or not execution.get("success"):
        return ToolObservation(
            name="chart.suggest",
            status="failed",
            input=args,
            error="No successful execution result available for chart suggestion.",
            latency_ms=0,
        )
    start = time.monotonic()
    try:
        suggestion = suggest_plotly_chart(execution)
        latency = int((time.monotonic() - start) * 1000)
        return ToolObservation(
            name="chart.suggest",
            status="success",
            input=args,
            output=suggestion,
            latency_ms=latency,
        )
    except Exception as exc:
        latency = int((time.monotonic() - start) * 1000)
        return ToolObservation(
            name="chart.suggest",
            status="failed",
            input=args,
            error=str(exc),
            latency_ms=latency,
        )


# ---- helpers ----------------------------------------------------------------


# helpers kept minimal; handler functions are imported from dedicated tool modules
