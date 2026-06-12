from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from engine.tools.db_tools import (
    db_inspect,
    db_observe,
    db_preview,
    db_query,
    db_remember,
    db_search,
)
from engine.agent_core.types import AgentRunRequest, ToolObservation
from engine.agent_core.workspace_context import build_agent_context_bundle
from engine.tools.workspace_tools import WORKSPACE_HANDLERS, WORKSPACE_TOOL_NAMES
from engine.agent_core.tool_registry import (
    RegisteredTool,
    ToolContext,
    ToolExecutionSpec,
    ToolPolicy,
    ToolRegistry,
    ToolSpec,
    ToolStateBinding,
)


class QuestionToolInput(BaseModel):
    """Tool that accepts an optional question override."""
    question: str | None = None


# ---------------------------------------------------------------------------
# Environment tool inputs
# ---------------------------------------------------------------------------

class DescribeTableInput(BaseModel):
    """Describe a named table from the live datasource."""
    table_name: str = Field(..., description="The exact table name to describe, e.g. 'singer', 'orders'.")


class RefreshCatalogInput(BaseModel):
    """Refresh the schema catalog from the live datasource."""
    reason: str | None = Field(None, description="Why the catalog needs refreshing.")


class MemorySearchInput(BaseModel):
    """Search long-term memory for relevant context."""
    query: str = Field(..., description="What to search for.")
    scope: list[str] | None = Field(None, description="Where to search: 'user', 'project', 'datasource'.")
    memory_types: list[str] | None = Field(None, description="Filter by type.")


class MemoryWriteInput(BaseModel):
    """Write a new memory entry."""
    type: str = Field(..., description="Memory type.")
    text: str = Field(..., description="Human-readable memory text.")
    content: dict[str, Any] | None = Field(None, description="Structured content.")


class MemoryDeleteInput(BaseModel):
    """Delete a memory entry."""
    memory_id: str = Field(..., description="The ID of the memory to delete.")
    reason: str | None = Field("user_requested", description="Why this memory is being deleted.")


# ---------------------------------------------------------------------------
# registration
# ---------------------------------------------------------------------------


def register_databox_tools() -> ToolRegistry:
    """Create and populate the ToolRegistry for DataBox Agent.

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

    # -- Workspace ---------------------------------------------------------
    handlers.force_register("workspace_assist", _workspace_assist)

    # -- Build registry from YAML specs + handlers -------------------------
    registry = ToolRegistry()
    registry.add_builtin_source()
    try:
        from pathlib import Path
        registry.add_user_source(Path.home() / ".databox" / "tools", priority=10)
        cwd = Path.cwd()
        project_dir = cwd / ".databox" / "tools"
        if project_dir.is_dir():
            registry.add_user_source(project_dir, priority=20)
    except Exception:
        pass
    registry.load_all()

    return registry


# ---- Workspace handler ------------------------------------------------------


def _workspace_assist(ctx: ToolContext, args: dict[str, Any]) -> ToolObservation:
    tool_name = str(ctx.state_view.get("_current_tool_name") or "")
    if not tool_name:
        pending_call = ctx.state_view.get("pending_tool_call")
        if isinstance(pending_call, dict):
            tool_name = str(pending_call.get("tool_name") or "")
    handler = WORKSPACE_HANDLERS.get(tool_name)
    if handler is None:
        return ToolObservation(
            name=tool_name, status="failed",
            input=args, error=f"Unknown workspace tool: {tool_name}", latency_ms=0,
        )
    req = _request(ctx, args)
    bundle = build_agent_context_bundle(ctx.db, req)
    intent = tool_name.removeprefix("workspace.")
    observation = handler(
        {"intent": intent, "context_bundle": bundle},
        ctx,
    )
    if tool_name == "workspace.explain_sql" and observation.output:
        workspace = req.workspace_context
        sql = str((workspace.selected_sql if workspace else None) or (workspace.active_sql if workspace else None) or "").strip()
        if sql and sql not in str(observation.output.get("answer") or ""):
            output = dict(observation.output)
            output["answer"] = f"{output.get('answer')}\n\nSQL:\n```sql\n{sql}\n```"
            return observation.model_copy(update={"output": output})
    return observation


# ---- Escalate ---------------------------------------------------------------


def _escalate_tool_group(ctx: ToolContext, args: dict[str, Any]) -> ToolObservation:
    """Request additional tool group access."""
    group = str(args.get("group", "")).strip()
    reason = str(args.get("reason", "")).strip()

    valid_groups = {
        "workspace", "environment", "schema", "db", "semantic",
        "memory", "execution",
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


# ---- helpers ----------------------------------------------------------------


def _request(ctx: ToolContext, args: dict[str, Any]) -> AgentRunRequest:
    if not args.get("question"):
        return ctx.request
    return ctx.request.model_copy(update={
        "question": str(args["question"]),
        "follow_up_context": None,
    })
