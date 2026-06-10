from __future__ import annotations

from typing import Any

from engine.agent_core.tool_registry import (
    RegisteredTool, ToolContext, ToolExecutionSpec,
    ToolHandler, ToolPolicy, ToolRegistry, ToolSpec, ToolStateBinding,
)
from engine.tools.sql_tools import (
    answer_synthesizer_tool,
    build_query_plan_tool,
    build_schema_context_tool,
    execute_sql_tool,
    generate_sql_tool,
    load_followup_context_tool,
    profile_result_tool,
    revise_sql_tool,
    suggest_chart_tool,
    suggest_followups_tool,
    validate_sql_tool,
)
from engine.agent_core.types import ToolObservation
from engine.tools.workspace_tools import WORKSPACE_TOOL_NAMES


DEFAULT_AGENT_TOOL_NAMES = [
    "followup.load_context",
    "schema.build_context",
    "query_plan.build",
    "sql.generate_candidate",
    "sql.validate",
    "sql.revise",
    "sql.execute_readonly",
    "result.profile",
    "chart.suggest",
    "followup.suggest",
    "answer.synthesize",
    *WORKSPACE_TOOL_NAMES,
]


def build_default_tool_registry() -> ToolRegistry:
    registry = ToolRegistry()
    for tool in _default_tools():
        registry.register(tool)
    return registry


def _default_tools() -> list[RegisteredTool]:
    tools = [
        _tool("followup.load_context", "Load and normalize follow-up context.", _load_followup_context),
        _tool("schema.build_context", "Build semantic schema context for the request.", _build_schema_context),
        _tool("query_plan.build", "Build a fixed query plan from semantic context.", _build_query_plan),
        _tool("sql.generate_candidate", "Generate a SQL candidate from the query plan.", _generate_sql_candidate),
        _tool("sql.validate", "Validate SQL with DataBox trust and guardrail checks.", _validate_sql),
        _tool("sql.revise", "Produce deterministic SQL revision guidance.", _revise_sql),
        _tool(
            "sql.execute_readonly",
            "Execute already validated read-only SQL.",
            _execute_sql,
            risk_level="warning",
            requires_approval=False,
            idempotent=False,
        ),
        _tool("result.profile", "Profile the result set for answer synthesis.", _profile_result),
        _tool("chart.suggest", "Suggest an Agent chart artifact from the result set.", _suggest_chart),
        _tool("followup.suggest", "Suggest evidence-aware follow-up questions.", _suggest_followups),
        _tool("answer.synthesize", "Synthesize the final evidence-grounded answer.", _answer_synthesizer),
    ]
    # Workspace tools — registered as pass-through handlers for fixture use
    for ws_name in WORKSPACE_TOOL_NAMES:
        tools.append(_tool(
            ws_name, f"Workspace tool: {ws_name}",
            lambda _ctx, _args, n=ws_name: ToolObservation(
                name=n, status="success", input=_args,
                output={"intent": n.removeprefix("workspace."), "answer": "fixture answer"},
                latency_ms=0,
            ),
        ))
    return tools


def _tool(
    name: str,
    description: str,
    handler: ToolHandler,
    *,
    risk_level: str = "safe",
    requires_approval: bool = False,
    idempotent: bool = True,
) -> RegisteredTool:
    return RegisteredTool(
        spec=ToolSpec(
            name=name,
            description=description,
            policy=ToolPolicy(risk_level=risk_level, requires_approval=requires_approval),
            execution=ToolExecutionSpec(idempotent=idempotent),
        ),
        handler=handler,
    )


def _state(ctx: ToolContext) -> Any:
    """Return state_view as an attribute-accessible wrapper."""
    from types import SimpleNamespace
    d = dict(ctx.state_view)
    return SimpleNamespace(**{k: v for k, v in d.items() if k.isidentifier()})


def _load_followup_context(_input: dict[str, Any], ctx: ToolContext) -> ToolObservation:
    return load_followup_context_tool(ctx.request)


def _build_schema_context(_input: dict[str, Any], ctx: ToolContext) -> ToolObservation:
    return build_schema_context_tool(ctx.db, ctx.request)


def _build_query_plan(_input: dict[str, Any], ctx: ToolContext) -> ToolObservation:
    return build_query_plan_tool(ctx.db, ctx.request, _state(ctx).schema_metadata)


def _generate_sql_candidate(_input: dict[str, Any], ctx: ToolContext) -> ToolObservation:
    state = _state(ctx)
    return generate_sql_tool(
        ctx.db,
        ctx.request,
        schema_context=state.schema_metadata,
        query_plan=state.query_plan,
    )


def _validate_sql(input: dict[str, Any], ctx: ToolContext) -> ToolObservation:
    state = _state(ctx)
    sql = str(input.get("sql") or state.sql or "")
    return validate_sql_tool(ctx.db, ctx.request.datasource_id, sql)


def _revise_sql(input: dict[str, Any], ctx: ToolContext) -> ToolObservation:
    state = _state(ctx)
    return revise_sql_tool(
        str(input.get("sql") or state.sql or ""),
        str(input.get("error") or "SQL revision requested."),
        input.get("safety") if isinstance(input.get("safety"), dict) else state.safety,
        db=ctx.db,
        datasource_id=ctx.request.datasource_id,
    )


def _execute_sql(input: dict[str, Any], ctx: ToolContext) -> ToolObservation:
    state = _state(ctx)
    sql = str(input.get("sql") or state.sql or "")
    safety = input.get("safety") if isinstance(input.get("safety"), dict) else state.safety
    return execute_sql_tool(ctx.db, ctx.request, sql, safety=safety)


def _profile_result(_input: dict[str, Any], ctx: ToolContext) -> ToolObservation:
    state = _state(ctx)
    return profile_result_tool(ctx.request, state.query_plan, state.execution)


def _suggest_chart(_input: dict[str, Any], ctx: ToolContext) -> ToolObservation:
    return suggest_chart_tool(_state(ctx).execution)


def _suggest_followups(_input: dict[str, Any], ctx: ToolContext) -> ToolObservation:
    state = _state(ctx)
    return suggest_followups_tool(
        ctx.request,
        state.sql,
        state.safety,
        state.execution,
        state.result_profile,
        state.chart_suggestion,
    )


def _answer_synthesizer(_input: dict[str, Any], ctx: ToolContext) -> ToolObservation:
    state = _state(ctx)
    return answer_synthesizer_tool(
        ctx.request,
        query_plan=state.query_plan,
        sql=state.sql,
        safety=state.safety,
        execution=state.execution,
        result_profile=state.result_profile,
        suggestions=state.suggestions,
        error=state.error,
    )
