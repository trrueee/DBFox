from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from engine.tools.sql_tools import (
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


class EmptyToolInput(BaseModel):
    """Tool that reads all context from agent state — no explicit arguments needed."""


class QuestionToolInput(BaseModel):
    """Tool that accepts an optional question override."""
    question: str | None = None


class SqlToolInput(BaseModel):
    """Tool that accepts a SQL string."""
    sql: str | None = None


class SqlExecutionInput(BaseModel):
    """Execute a validated SQL query."""
    sql: str | None = None
    question: str | None = None


class SqlRevisionInput(BaseModel):
    """Revise a SQL query that failed validation or execution."""
    sql: str | None = None
    safe_sql: str | None = None
    instruction: str | None = None
    user_instruction: str | None = None
    reason: str | None = None
    error: str | None = None


class SqlCandidateOutput(BaseModel):
    sql: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


class SqlSafetyOutput(BaseModel):
    can_execute: bool
    safe_sql: str | None = None
    requires_confirmation: bool = False


class SqlExecutionOutput(BaseModel):
    success: bool


# ---------------------------------------------------------------------------
# Environment tool inputs (explicit schemas for model-visible args)
# ---------------------------------------------------------------------------

class DescribeTableInput(BaseModel):
    """Describe a named table from the live datasource."""
    table_name: str = Field(..., description="The exact table name to describe, e.g. 'singer', 'orders'.")


class RefreshCatalogInput(BaseModel):
    """Refresh the schema catalog from the live datasource."""
    reason: str | None = Field(None, description="Why the catalog needs refreshing, e.g. 'schema.build_context returned zero tables'.")


class MemorySearchInput(BaseModel):
    """Search long-term memory for relevant context."""
    query: str = Field(..., description="What to search for, e.g. 'sales metric definition', 'singer table alias'.")
    scope: list[str] | None = Field(None, description="Where to search: 'user', 'project', 'datasource'.")
    memory_types: list[str] | None = Field(None, description="Filter by type: 'metric_definition', 'schema_alias', 'join_path', 'user_preference', 'successful_trajectory'.")


class MemoryWriteInput(BaseModel):
    """Write a new memory entry."""
    type: str = Field(..., description="Memory type: 'user_preference', 'schema_alias', 'metric_definition', 'join_path', 'project_rule'.")
    text: str = Field(..., description="Human-readable memory text. E.g. '销售额 = orders.total_amount where status is paid or completed.'")
    content: dict[str, Any] | None = Field(None, description="Structured content for this memory type.")


class MemoryDeleteInput(BaseModel):
    """Delete a memory entry."""
    memory_id: str = Field(..., description="The ID of the memory to delete.")
    reason: str | None = Field("user_requested", description="Why this memory is being deleted.")


def register_databox_tools() -> ToolRegistry:
    """Create and populate the ToolRegistry for DataBox Agent.

    Two-phase registration:
    1. Handlers are registered into HandlerRegistry (bridges YAML → code).
    2. ToolRegistry.load_all() loads YAML specs from builtin/user/project dirs
       and resolves handlers automatically.

    Any tool spec whose handler is missing from HandlerRegistry is skipped
    with a warning — no crashes.
    """
    from engine.tools.sandbox.tools import (
        FollowupLoadContextTool,
        SchemaBuildContextTool,
        QueryPlanBuildTool,
        SqlGenerateTool,
        SqlValidateTool,
        SqlExecuteReadonlyTool,
        SqlSkipExecutionTool,
        SqlReviseTool,
        ResultProfileTool,
        ChartSuggestTool,
        FollowupSuggestTool,
        AnswerSynthesizeTool,
    )
    from engine.agent_core.handler_registry import get_handler_registry

    handlers = get_handler_registry()

    # -- Escalate handler (always-available, never group-filtered) ------------
    handlers.force_register("escalate_tool_group", _escalate_tool_group)

    # -- Register handlers into HandlerRegistry --------------------------------
    # These are referenced by name from YAML tool specs.

    handlers.force_register("followup_load_context", _load_followup_context,
                      base_tool=FollowupLoadContextTool())
    handlers.force_register("schema_build_context", _schema_build_context,
                      base_tool=SchemaBuildContextTool())
    handlers.force_register("query_plan_build", _query_plan_build,
                      base_tool=QueryPlanBuildTool())
    handlers.force_register("sql_generate", _sql_generate,
                      base_tool=SqlGenerateTool())
    handlers.force_register("sql_validate", _sql_validate,
                      base_tool=SqlValidateTool())
    handlers.force_register("sql_execute_readonly", _sql_execute_readonly,
                      base_tool=SqlExecuteReadonlyTool())
    handlers.force_register("sql_skip_execution", _sql_skip_execution,
                      base_tool=SqlSkipExecutionTool())
    handlers.force_register("sql_revise", _sql_revise,
                      base_tool=SqlReviseTool())
    handlers.force_register("result_profile", _result_profile,
                      base_tool=ResultProfileTool())
    handlers.force_register("chart_suggest", _chart_suggest,
                      base_tool=ChartSuggestTool())
    handlers.force_register("followup_suggest", _followup_suggest,
                      base_tool=FollowupSuggestTool())
    handlers.force_register("answer_synthesize", _answer_synthesize,
                      base_tool=AnswerSynthesizeTool())

    # Environment handlers
    from engine.environment.tools import (
        environment_get_profile, schema_list_tables,
        schema_describe_table, schema_refresh_catalog,
    )
    handlers.force_register("environment_get_profile", environment_get_profile)
    handlers.force_register("schema_list_tables", schema_list_tables)
    handlers.force_register("schema_describe_table", schema_describe_table)
    handlers.force_register("schema_refresh_catalog", schema_refresh_catalog)

    # Semantic handler
    from engine.semantic.tools import semantic_resolve
    handlers.force_register("semantic_resolve", semantic_resolve)

    # Memory handlers
    from engine.tools.memory_tools import (
        memory_search, memory_write, memory_delete, memory_summarize_session,
    )
    handlers.force_register("memory_search", memory_search)
    handlers.force_register("memory_write", memory_write)
    handlers.force_register("memory_delete", memory_delete)
    handlers.force_register("memory_summarize_session", memory_summarize_session)

    # Workspace handler (single handler for all workspace tools)
    handlers.force_register("workspace_assist", _workspace_assist)

    # -- Build ToolRegistry from YAML specs + handlers ------------------------
    registry = ToolRegistry()
    registry.add_builtin_source()
    # Auto-discover user/project tools
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


def _tool(
    name: str,
    description: str,
    handler: Any,
    *,
    input_model: type[BaseModel] | None = None,
    output_model: type[BaseModel] | None = None,
    policy: ToolPolicy | None = None,
    base_tool: Any = None,
    metadata: dict[str, Any] | None = None,
    group: str = "",
    kind: str = "code",
    binding: ToolStateBinding | None = None,
    execution: ToolExecutionSpec | None = None,
) -> RegisteredTool:
    if name in TOOL_SCHEMAS:
        schemas = TOOL_SCHEMAS[name]
        explicit_input = schemas["input"]
        explicit_output = schemas["output"]
    else:
        explicit_input = None
        explicit_output = None

    rt = RegisteredTool(
        spec=ToolSpec(
            name=name,
            group=group,
            kind=kind,
            description=description,
            input_model=input_model,
            output_model=output_model,
            _input_schema=explicit_input,
            _output_schema=explicit_output,
            policy=policy or ToolPolicy(),
            binding=binding or ToolStateBinding(),
            execution=execution or ToolExecutionSpec(),
            metadata=metadata or {},
        ),
        handler=handler,
    )
    rt.base_tool = base_tool
    return rt


def _object_schema(
    description: str,
    properties: dict[str, Any] | None = None,
    *,
    required: list[str] | None = None,
    additional_properties: bool = False,
) -> dict[str, Any]:
    return {
        "type": "object",
        "description": description,
        "properties": properties or {},
        "required": required or [],
        "additionalProperties": additional_properties,
    }


def _prop(schema_type: str, description: str) -> dict[str, Any]:
    return {"type": schema_type, "description": description}


def _array_prop(description: str, items: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "type": "array",
        "description": description,
        "items": items or {"type": "object"},
    }


def _map_prop(description: str) -> dict[str, Any]:
    return {"type": "object", "description": description, "additionalProperties": True}


QUESTION_INPUT = _object_schema(
    "Optional question override. Omit it to use the latest user message from AgentRunRequest.",
    {"question": _prop("string", "Question to use for this tool call instead of the current request question.")},
)

NO_ARGS_INPUT = _object_schema("This tool reads all required inputs from current agent state.")

TOOL_SCHEMAS: dict[str, dict[str, dict[str, Any]]] = {
    "followup.load_context": {
        "input": QUESTION_INPUT,
        "output": _object_schema(
            "Normalized follow-up context from the prior run and referenced artifacts.",
            {
                "context_summary": _prop("string", "Compact summary of prior context."),
                "analysis_question": _prop("string", "Question rewritten for result analysis."),
                "schema_linking_question": _prop("string", "Question rewritten for schema linking."),
                "referenced_artifact_ids": _array_prop(
                    "Artifact ids referenced by the follow-up.",
                    {"type": "string"},
                ),
            },
            required=["context_summary", "analysis_question", "schema_linking_question"],
            additional_properties=True,
        ),
    },
    "schema.build_context": {
        "input": QUESTION_INPUT,
        "output": _object_schema(
            "Relevant schema context selected from synced local metadata.",
            {
                "schema_context": _prop("string", "Rendered schema context for SQL planning."),
                "candidate_tables": _array_prop("Tables considered relevant to the question."),
                "candidate_columns": _array_prop("Columns considered relevant to the question."),
                "selected_tables": _array_prop("Selected table names.", {"type": "string"}),
                "schema_linking_reasons": _array_prop("Reasons produced by schema linking."),
                "schema_context_size": _prop("integer", "Approximate rendered schema context size."),
                "original_schema_table_count": _prop("integer", "Total synced schema tables considered."),
                "selected_schema_table_count": _prop("integer", "Number of selected schema tables."),
                "mode": _prop("string", "Schema linking mode."),
            },
            required=["schema_context", "selected_tables", "mode"],
            additional_properties=True,
        ),
    },
    "query_plan.build": {
        "input": QUESTION_INPUT,
        "output": _object_schema(
            "Structured query plan used as a non-executing intermediate artifact.",
            {
                "analysis_goal": _prop("string", "Business question or analysis goal."),
                "metrics": _array_prop("Metric definitions to compute."),
                "dimensions": _array_prop("Dimensions to group or slice by."),
                "filters": _array_prop("Filters to apply."),
                "time_range": _map_prop("Inferred time range, if any."),
                "candidate_tables": _array_prop("Candidate source table names.", {"type": "string"}),
                "assumptions": _array_prop("Planning assumptions.", {"type": "string"}),
                "risk_notes": _array_prop("Planning risks or limitations.", {"type": "string"}),
                "raw_plan": _map_prop("Raw plan payload from semantic planning."),
            },
            required=["analysis_goal"],
            additional_properties=True,
        ),
    },
    "sql.generate": {
        "input": QUESTION_INPUT,
        "output": _object_schema(
            "Generated SQL candidate. This SQL is not executed by this tool.",
            {
                "sql": _prop("string", "SQL candidate to validate before execution."),
                "raw_sql": _prop("string", "Original model SQL before deterministic rewrites."),
                "model": _prop("string", "Model or renderer that produced the SQL."),
                "mode": _prop("string", "Generation mode."),
                "latency_ms": _prop("integer", "Generation latency in milliseconds."),
                "schema_validation_warnings": _array_prop("Schema validation warning strings.", {"type": "string"}),
                "rewrite_notes": _array_prop("Deterministic SQL rewrite notes.", {"type": "string"}),
                "metadata": _map_prop("Generation metadata."),
                "error": _prop("string", "Generation error when SQL could not be produced."),
            },
            required=[],
            additional_properties=True,
        ),
    },
    "sql.validate": {
        "input": _object_schema(
            "Validate SQL with TrustGate. If sql is omitted, the current state.sql is used.",
            {"sql": _prop("string", "SQL to validate. Prefer the current pending or generated SQL.")},
        ),
        "output": _object_schema(
            "TrustGate and guardrail validation result. Execution must use safe_sql from this result.",
            {
                "passed": _prop("boolean", "Whether validation passed."),
                "can_execute": _prop("boolean", "Whether PolicyGate may allow execution."),
                "safe_sql": _prop("string", "Validated SQL that execution must use."),
                "original_sql": _prop("string", "Original SQL supplied to validation."),
                "schema_warnings": _array_prop("Schema validation warnings.", {"type": "string"}),
                "guardrail": _map_prop("Guardrail check result."),
                "trust_gate": _map_prop("TrustGate result."),
                "execution_safety_decision": _map_prop("Serialized execution safety decision."),
                "requires_confirmation": _prop("boolean", "Whether human approval is required before execution."),
                "messages": _array_prop("Human-readable validation messages.", {"type": "string"}),
                "blocked_reasons": _array_prop("Reasons execution is blocked or gated.", {"type": "string"}),
                "revise_suggestion": _prop("string", "Revision guidance when validation cannot execute."),
            },
            required=["passed", "can_execute", "safe_sql", "requires_confirmation"],
            additional_properties=True,
        ),
    },
    "sql.execute_readonly": {
        "input": _object_schema(
            "Execute validated read-only SQL. PolicyGate ignores LLM-provided sql and uses state.safety.safe_sql.",
            {
                "sql": _prop("string", "Optional SQL preview; execution is gated by state.safety.safe_sql."),
                "question": _prop("string", "Optional question override for query history metadata."),
            },
        ),
        "output": _object_schema(
            "Readonly SQL execution result or execution failure metadata.",
            {
                "success": _prop("boolean", "Whether execution succeeded."),
                "columns": _array_prop("Returned column names.", {"type": "string"}),
                "rows": _array_prop("Sample result rows."),
                "rowCount": _prop("integer", "Total returned row count."),
                "latencyMs": _prop("integer", "Total execution latency in milliseconds."),
                "historyId": _prop("string", "Query history id."),
                "executionId": _prop("string", "Execution id."),
                "safetyDecision": _map_prop("Safety decision used by execution."),
                "truncated": _prop("boolean", "Whether returned rows were truncated."),
                "warnings": _array_prop("Execution warnings.", {"type": "string"}),
                "timing": _map_prop("Execution timing breakdown."),
                "error_type": _prop("string", "Failure exception class when execution fails."),
                "revise_suggestion": _prop("string", "Revision guidance when execution fails."),
            },
            required=["success"],
            additional_properties=True,
        ),
    },
    "sql.skip_execution": {
        "input": NO_ARGS_INPUT,
        "output": _object_schema(
            "Record that execution was intentionally skipped.",
            {"reason": _prop("string", "Why execution was skipped.")},
            required=["reason"],
            additional_properties=True,
        ),
    },
    "sql.revise": {
        "input": _object_schema(
            "Revise SQL without executing it. Prefer instruction/user_instruction for user-requested changes.",
            {
                "sql": _prop("string", "SQL to revise. If omitted, current state.sql or pending approval SQL is used."),
                "safe_sql": _prop("string", "Safe SQL preview from validation or pending approval."),
                "instruction": _prop("string", "User revision instruction."),
                "user_instruction": _prop("string", "User revision instruction alias."),
                "reason": _prop("string", "Reason for revision."),
                "error": _prop("string", "Validation or execution error to repair."),
            },
        ),
        "output": _object_schema(
            "SQL revision result. Revised SQL must be validated before execution.",
            {
                "can_fix": _prop("boolean", "Whether a deterministic revision is available."),
                "fixed_sql": _prop("string", "Revised SQL candidate, if available."),
                "reason": _prop("string", "Reason or instruction used for revision."),
                "changes": _array_prop("Changes applied to the SQL.", {"type": "string"}),
                "remaining_risks": _array_prop("Remaining risks after revision.", {"type": "string"}),
                "revise_suggestion": _prop("string", "Next-step revision guidance."),
                "blocked_sql": _prop("string", "Original SQL that was blocked or revised."),
            },
            required=["can_fix", "reason", "revise_suggestion"],
            additional_properties=True,
        ),
    },
    "result.profile": {
        "input": QUESTION_INPUT,
        "output": _object_schema(
            "Profile of a successful or skipped result set.",
            {
                "row_count": _prop("integer", "Number of result rows represented by the profile."),
                "column_profiles": _map_prop("Per-column profile summaries."),
                "detected_patterns": _array_prop("Detected patterns.", {"type": "string"}),
                "notable_facts": _array_prop("Evidence-backed notable facts.", {"type": "string"}),
                "anomalies": _array_prop("Detected anomalies.", {"type": "string"}),
                "limitations": _array_prop("Profile limitations.", {"type": "string"}),
            },
            required=["row_count"],
            additional_properties=True,
        ),
    },
    "chart.suggest": {
        "input": NO_ARGS_INPUT,
        "output": _object_schema(
            "Chart recommendation derived from execution columns and sampled rows.",
            {
                "type": _prop("string", "Suggested chart type."),
                "x": _prop("string", "Suggested x/category/time column."),
                "y": _prop("string", "Suggested y/measure column."),
                "reason": _prop("string", "Why this chart type was selected."),
            },
            required=["type", "reason"],
            additional_properties=True,
        ),
    },
    "followup.suggest": {
        "input": QUESTION_INPUT,
        "output": _object_schema(
            "Evidence-aware follow-up suggestions.",
            {"suggestions": _array_prop("Suggested follow-up actions or questions.")},
            required=["suggestions"],
            additional_properties=True,
        ),
    },
    "answer.synthesize": {
        "input": QUESTION_INPUT,
        "output": _object_schema(
            "Final answer synthesized from existing SQL, safety, execution, profile, and artifacts.",
            {
                "answer": _prop("string", "Natural-language answer."),
                "key_findings": _array_prop("Evidence-backed key findings.", {"type": "string"}),
                "evidence": _array_prop("Evidence references."),
                "caveats": _array_prop("Important caveats.", {"type": "string"}),
                "recommendations": _array_prop("Recommended next steps.", {"type": "string"}),
                "follow_up_questions": _array_prop("Suggested follow-up questions.", {"type": "string"}),
            },
            required=["answer"],
            additional_properties=True,
        ),
    },
}

WORKSPACE_OUTPUT_SCHEMA = _object_schema(
    "Workspace tool output payload.",
    {
        "intent": _prop("string", "The workspace tool intent."),
        "answer": _prop("string", "Natural-language explanation or answer."),
        "suggestions": _array_prop("Actionable suggestions for the user."),
        "proposed_sql": _prop("string", "Proposed SQL statement, if any."),
        "context_summary": _prop("string", "Summary of workspace context processed."),
        "safety_notes": _array_prop("Safety notes or guardrail findings.", {"type": "string"}),
    },
    required=["intent", "answer"],
    additional_properties=True,
)

for _name in [
    "workspace.explain_sql",
    "workspace.fix_sql",
    "workspace.optimize_sql",
    "workspace.rewrite_sql",
    "workspace.explain_result",
    "workspace.continue_from_artifact",
    "workspace.explain_schema",
]:
    TOOL_SCHEMAS[_name] = {
        "input": QUESTION_INPUT,
        "output": WORKSPACE_OUTPUT_SCHEMA,
    }


def _request(ctx: ToolContext, args: dict[str, Any]) -> AgentRunRequest:
    if not args.get("question"):
        return ctx.request
    return ctx.request.model_copy(update={"question": str(args["question"])})


def _load_followup_context(ctx: ToolContext, args: dict[str, Any]) -> ToolObservation:
    return load_followup_context_tool(_request(ctx, args))


def _schema_build_context(ctx: ToolContext, args: dict[str, Any]) -> ToolObservation:
    return build_schema_context_tool(ctx.db, _request(ctx, args))


def _query_plan_build(ctx: ToolContext, args: dict[str, Any]) -> ToolObservation:
    return build_query_plan_tool(ctx.db, _request(ctx, args), ctx.state_view.get("schema_context"))


def _sql_generate(ctx: ToolContext, args: dict[str, Any]) -> ToolObservation:
    return generate_sql_tool(
        ctx.db,
        _request(ctx, args),
        schema_context=ctx.state_view.get("schema_context"),
        query_plan=ctx.state_view.get("query_plan"),
    )


def _sql_validate(ctx: ToolContext, args: dict[str, Any]) -> ToolObservation:
    sql = args.get("sql") or ctx.state_view.get("sql")
    return validate_sql_tool(ctx.db, ctx.request.datasource_id, str(sql or ""))


def _sql_execute_readonly(ctx: ToolContext, args: dict[str, Any]) -> ToolObservation:
    raw_safety = ctx.state_view.get("safety")
    safety: dict[str, Any] = raw_safety if isinstance(raw_safety, dict) else {}
    state_safe_sql = str(safety.get("safe_sql") or "").strip()
    
    args_sql = str(args.get("sql") or "").strip()
    if args_sql and state_safe_sql:
        normalized_args_sql = " ".join(args_sql.lower().split())
        normalized_safe_sql = " ".join(state_safe_sql.lower().split())
        if normalized_args_sql != normalized_safe_sql:
            return ToolObservation(
                name="sql.execute_readonly",
                status="failed",
                input=args,
                error="Execution SQL parameter does not match the validated safety SQL.",
                latency_ms=0,
            )
            
    safe_sql = state_safe_sql or args_sql or ctx.state_view.get("sql")
    return execute_sql_tool(ctx.db, _request(ctx, args), str(safe_sql or ""), safety=safety)


def _sql_skip_execution(_ctx: ToolContext, _args: dict[str, Any]) -> ToolObservation:
    return skipped_execute_observation()


def _sql_revise(ctx: ToolContext, args: dict[str, Any]) -> ToolObservation:
    instruction = (
        args.get("instruction")
        or args.get("user_instruction")
        or args.get("reason")
        or args.get("error")
        or ctx.state_view.get("error")
        or "Revise the SQL according to the latest user request."
    )
    sql = (
        args.get("sql")
        or args.get("safe_sql")
        or ctx.state_view.get("sql")
        or _pending_approval_sql(dict(ctx.state_view))
    )
    return revise_sql_tool(
        sql=str(sql or ""),
        error=str(instruction),
        safety=ctx.state_view.get("safety") if isinstance(ctx.state_view.get("safety"), dict) else None,
        db=ctx.db,
        datasource_id=ctx.request.datasource_id,
    )


def _result_profile(ctx: ToolContext, args: dict[str, Any]) -> ToolObservation:
    return profile_result_tool(_request(ctx, args), ctx.state_view.get("query_plan"), ctx.state_view.get("execution"))


def _chart_suggest(ctx: ToolContext, _args: dict[str, Any]) -> ToolObservation:
    return suggest_chart_tool(ctx.state_view.get("execution"))


def _followup_suggest(ctx: ToolContext, args: dict[str, Any]) -> ToolObservation:
    return suggest_followups_tool(
        _request(ctx, args),
        ctx.state_view.get("sql"),
        ctx.state_view.get("safety"),
        ctx.state_view.get("execution"),
        ctx.state_view.get("result_profile"),
        ctx.state_view.get("chart_suggestion"),
    )


def _answer_synthesize(ctx: ToolContext, args: dict[str, Any]) -> ToolObservation:
    return answer_synthesizer_tool(
        req=_request(ctx, args),
        query_plan=ctx.state_view.get("query_plan"),
        sql=ctx.state_view.get("sql"),
        safety=ctx.state_view.get("safety"),
        execution=ctx.state_view.get("execution"),
        result_profile=ctx.state_view.get("result_profile"),
        suggestions=ctx.state_view.get("suggestions"),
        error=ctx.state_view.get("error"),
    )


def _workspace_assist(ctx: ToolContext, args: dict[str, Any]) -> ToolObservation:
    # Prefer _current_tool_name from the new ReAct graph; fall back to
    # pending_tool_call for backward compatibility with agent_kernel.
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
    # Workspace handlers use (input, ctx) arg order
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


def _pending_approval_sql(state: dict[str, Any]) -> str | None:
    approval = state.get("pending_approval")
    if not isinstance(approval, dict):
        return None

    requested = approval.get("requested_action")
    if not isinstance(requested, dict):
        return None

    direct_sql = _string_arg(requested.get("safe_sql")) or _string_arg(requested.get("sql"))
    if direct_sql:
        return direct_sql

    args = requested.get("args")
    if not isinstance(args, dict):
        return None

    return _string_arg(args.get("safe_sql")) or _string_arg(args.get("sql"))


def _escalate_tool_group(ctx: ToolContext, args: dict[str, Any]) -> ToolObservation:
    """Escalate: request additional tool group access.

    This is always available regardless of the current allowed_tool_groups.
    The Progress Judge reads this result and expands the active tool scope
    without going through a full replan cycle.
    """
    group = str(args.get("group", "")).strip()
    reason = str(args.get("reason", "")).strip()

    valid_groups = {
        "workspace", "environment", "schema", "semantic", "query_plan",
        "sql_generation", "sql_validation", "sql_repair", "execution",
        "result", "chart", "answer",
    }

    if group not in valid_groups:
        return ToolObservation(
            name="escalate.tool_group",
            status="failed",
            input=args,
            error=f"Unknown tool group '{group}'. Valid groups: {', '.join(sorted(valid_groups))}",
            latency_ms=0,
        )

    # Read current groups from state so we only add what's missing
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


def _string_arg(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None
