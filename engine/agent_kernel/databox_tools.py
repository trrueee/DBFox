from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from engine.agent.registry import AgentToolContext
from engine.agent.tools import (
    answer_synthesizer_tool,
    build_query_plan_tool,
    build_schema_context_tool,
    execute_sql_tool,
    generate_sql_tool,
    load_followup_context_tool,
    profile_result_tool,
    revise_sql_tool,
    skipped_execute_observation,
    suggest_chart_tool,
    suggest_followups_tool,
    validate_sql_tool,
)
from engine.agent.types import AgentRunRequest, ToolObservation
from engine.agent.workspace_context import build_agent_context_bundle
from engine.agent.workspace_tools import WORKSPACE_TOOL_NAMES, build_workspace_tools
from engine.agent_kernel.tool_registry import (
    RegisteredTool,
    ToolContext,
    ToolPolicy,
    ToolRegistry,
    ToolSpec,
)


class EmptyToolInput(BaseModel):
    pass


class QuestionToolInput(BaseModel):
    question: str | None = None


class SqlToolInput(BaseModel):
    sql: str | None = None


class SqlExecutionInput(BaseModel):
    sql: str | None = None
    question: str | None = None


class SqlRevisionInput(BaseModel):
    sql: str | None = None
    error: str | None = None


class SqlCandidateOutput(BaseModel):
    sql: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class SqlSafetyOutput(BaseModel):
    can_execute: bool
    safe_sql: str | None = None
    requires_confirmation: bool = False


class SqlExecutionOutput(BaseModel):
    success: bool


def register_databox_tools() -> ToolRegistry:
    registry = ToolRegistry()

    registry.register(_tool("followup.load_context", "Load and normalize follow-up context.", _load_followup_context, input_model=EmptyToolInput))
    registry.register(_tool("schema.build_context", "Build relevant schema context for a data question.", _schema_build_context, input_model=QuestionToolInput))
    registry.register(_tool("query_plan.build", "Build a structured query plan from schema context.", _query_plan_build, input_model=EmptyToolInput))
    registry.register(_tool("sql.generate", "Generate a SQL candidate without executing it.", _sql_generate, input_model=EmptyToolInput, output_model=SqlCandidateOutput))
    registry.register(_tool("sql.validate", "Validate SQL with TrustGate and guardrail checks.", _sql_validate, input_model=SqlToolInput, output_model=SqlSafetyOutput))
    registry.register(
        _tool(
            "sql.execute_readonly",
            "Execute previously validated read-only SQL.",
            _sql_execute_readonly,
            input_model=SqlExecutionInput,
            output_model=SqlExecutionOutput,
            policy=ToolPolicy(
                risk_level="warning",
                side_effect="read",
                requires_validated_sql=True,
            ),
        )
    )
    registry.register(_tool("sql.skip_execution", "Record that SQL execution was skipped.", _sql_skip_execution, input_model=EmptyToolInput, output_model=SqlExecutionOutput))
    registry.register(_tool("sql.revise", "Revise SQL after validation or execution error.", _sql_revise, input_model=SqlRevisionInput))
    registry.register(_tool("result.profile", "Profile query results and notable facts.", _result_profile, input_model=EmptyToolInput))
    registry.register(_tool("chart.suggest", "Suggest a chart from query results.", _chart_suggest, input_model=EmptyToolInput))
    registry.register(_tool("followup.suggest", "Suggest evidence-aware follow-up questions.", _followup_suggest, input_model=EmptyToolInput))
    registry.register(_tool("answer.synthesize", "Synthesize the final evidence-grounded answer.", _answer_synthesize, input_model=EmptyToolInput))
    workspace_tools = {tool.spec.name: tool for tool in build_workspace_tools()}
    for tool_name in WORKSPACE_TOOL_NAMES:
        workspace_tool = workspace_tools[tool_name]
        registry.register(_tool(tool_name, workspace_tool.spec.description, _workspace_assist, input_model=QuestionToolInput))

    return registry


def _tool(
    name: str,
    description: str,
    handler: Any,
    *,
    input_model: type[BaseModel] | None = None,
    output_model: type[BaseModel] | None = None,
    policy: ToolPolicy | None = None,
) -> RegisteredTool:
    input_schema = input_model.model_json_schema() if input_model is not None else {"type": "object"}
    output_schema = output_model.model_json_schema() if output_model is not None else {"type": "object"}
    return RegisteredTool(
        spec=ToolSpec(
            name=name,
            description=description,
            input_schema=input_schema,
            output_schema=output_schema,
            input_model=input_model,
            output_model=output_model,
            policy=policy or ToolPolicy(),
        ),
        handler=handler,
    )


def _request(ctx: ToolContext, args: dict[str, Any]) -> AgentRunRequest:
    if not args.get("question"):
        return ctx.request
    return ctx.request.model_copy(update={"question": str(args["question"])})


def _load_followup_context(ctx: ToolContext, args: dict[str, Any]) -> ToolObservation:
    return load_followup_context_tool(_request(ctx, args))


def _schema_build_context(ctx: ToolContext, args: dict[str, Any]) -> ToolObservation:
    return build_schema_context_tool(ctx.db, _request(ctx, args))


def _query_plan_build(ctx: ToolContext, args: dict[str, Any]) -> ToolObservation:
    return build_query_plan_tool(ctx.db, _request(ctx, args), ctx.state.get("schema_context"))


def _sql_generate(ctx: ToolContext, args: dict[str, Any]) -> ToolObservation:
    return generate_sql_tool(
        ctx.db,
        _request(ctx, args),
        schema_context=ctx.state.get("schema_context"),
        query_plan=ctx.state.get("query_plan"),
    )


def _sql_validate(ctx: ToolContext, args: dict[str, Any]) -> ToolObservation:
    sql = args.get("sql") or ctx.state.get("sql")
    return validate_sql_tool(ctx.db, ctx.request.datasource_id, str(sql or ""))


def _sql_execute_readonly(ctx: ToolContext, args: dict[str, Any]) -> ToolObservation:
    raw_safety = ctx.state.get("safety")
    safety: dict[str, Any] = raw_safety if isinstance(raw_safety, dict) else {}
    safe_sql = args.get("sql") or safety.get("safe_sql") or ctx.state.get("sql")
    return execute_sql_tool(ctx.db, _request(ctx, args), str(safe_sql or ""), safety=safety)


def _sql_skip_execution(_ctx: ToolContext, _args: dict[str, Any]) -> ToolObservation:
    return skipped_execute_observation()


def _sql_revise(ctx: ToolContext, args: dict[str, Any]) -> ToolObservation:
    return revise_sql_tool(
        sql=str(args.get("sql") or ctx.state.get("sql") or ""),
        error=str(args.get("error") or ctx.state.get("error") or "SQL needs revision."),
        safety=ctx.state.get("safety") if isinstance(ctx.state.get("safety"), dict) else None,
        db=ctx.db,
        datasource_id=ctx.request.datasource_id,
    )


def _result_profile(ctx: ToolContext, args: dict[str, Any]) -> ToolObservation:
    return profile_result_tool(_request(ctx, args), ctx.state.get("query_plan"), ctx.state.get("execution"))


def _chart_suggest(ctx: ToolContext, _args: dict[str, Any]) -> ToolObservation:
    return suggest_chart_tool(ctx.state.get("execution"))


def _followup_suggest(ctx: ToolContext, args: dict[str, Any]) -> ToolObservation:
    return suggest_followups_tool(
        _request(ctx, args),
        ctx.state.get("sql"),
        ctx.state.get("safety"),
        ctx.state.get("execution"),
        ctx.state.get("result_profile"),
        ctx.state.get("chart_suggestion"),
    )


def _answer_synthesize(ctx: ToolContext, args: dict[str, Any]) -> ToolObservation:
    return answer_synthesizer_tool(
        req=_request(ctx, args),
        query_plan=ctx.state.get("query_plan"),
        sql=ctx.state.get("sql"),
        safety=ctx.state.get("safety"),
        execution=ctx.state.get("execution"),
        result_profile=ctx.state.get("result_profile"),
        suggestions=ctx.state.get("suggestions"),
        error=ctx.state.get("error"),
    )


def _workspace_assist(ctx: ToolContext, args: dict[str, Any]) -> ToolObservation:
    pending_call = ctx.state.get("pending_tool_call")
    tool_name = ""
    if isinstance(pending_call, dict):
        tool_name = str(pending_call.get("tool_name") or "")
    workspace_tool = {tool.spec.name: tool for tool in build_workspace_tools()}[tool_name]
    req = _request(ctx, args)
    bundle = build_agent_context_bundle(ctx.db, req)
    intent = tool_name.removeprefix("workspace.")
    observation = workspace_tool.execute(
        {"intent": intent, "context_bundle": bundle},
        AgentToolContext(db=ctx.db, request=req),
    )
    if tool_name == "workspace.explain_sql" and observation.output:
        workspace = req.workspace_context
        sql = str((workspace.selected_sql if workspace else None) or (workspace.active_sql if workspace else None) or "").strip()
        if sql and sql not in str(observation.output.get("answer") or ""):
            output = dict(observation.output)
            output["answer"] = f"{output.get('answer')}\n\nSQL:\n```sql\n{sql}\n```"
            return observation.model_copy(update={"output": output})
    return observation
