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


def register_databox_tools() -> ToolRegistry:
    from engine.agent.sandbox.tools import (
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

    registry = ToolRegistry()

    registry.register(_tool("followup.load_context", "Load and normalize follow-up context.", _load_followup_context, input_model=EmptyToolInput, base_tool=FollowupLoadContextTool(), metadata={"next_route": "profile_result"}))
    registry.register(_tool("schema.build_context", "Build relevant schema context for a data question.", _schema_build_context, input_model=QuestionToolInput, base_tool=SchemaBuildContextTool(), metadata={"next_route": "generate_sql"}))
    registry.register(_tool("query_plan.build", "Build a structured query plan from schema context.", _query_plan_build, input_model=EmptyToolInput, base_tool=QueryPlanBuildTool(), metadata={"next_route": "generate_sql"}))
    registry.register(_tool("sql.generate", "Generate a SQL candidate without executing it.", _sql_generate, input_model=EmptyToolInput, output_model=SqlCandidateOutput, base_tool=SqlGenerateTool(), metadata={"next_route": "sql_critic"}))
    registry.register(_tool("sql.validate", "Validate SQL with TrustGate and guardrail checks.", _sql_validate, input_model=SqlToolInput, output_model=SqlSafetyOutput, base_tool=SqlValidateTool(), metadata={"next_route": "validation_route"}))
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
            base_tool=SqlExecuteReadonlyTool(),
            metadata={"next_route": "execution_result_route"},
        )
    )
    registry.register(_tool("sql.skip_execution", "Record that SQL execution was skipped.", _sql_skip_execution, input_model=EmptyToolInput, output_model=SqlExecutionOutput, base_tool=SqlSkipExecutionTool(), metadata={"next_route": "execution_result_route"}))
    registry.register(_tool("sql.revise", "Revise SQL after validation or execution error.", _sql_revise, input_model=SqlRevisionInput, base_tool=SqlReviseTool(), metadata={"next_route": "sql_critic"}))
    registry.register(_tool("result.profile", "Profile query results and notable facts.", _result_profile, input_model=EmptyToolInput, base_tool=ResultProfileTool(), metadata={"next_route": "chart_suggest"}))
    registry.register(_tool("chart.suggest", "Suggest a chart from query results.", _chart_suggest, input_model=EmptyToolInput, base_tool=ChartSuggestTool(), metadata={"next_route": "followup_suggest"}))
    registry.register(_tool("followup.suggest", "Suggest evidence-aware follow-up questions.", _followup_suggest, input_model=EmptyToolInput, base_tool=FollowupSuggestTool(), metadata={"next_route": "synthesize_answer"}))
    registry.register(_tool("answer.synthesize", "Synthesize the final evidence-grounded answer.", _answer_synthesize, input_model=EmptyToolInput, base_tool=AnswerSynthesizeTool(), metadata={"next_route": "answer"}))
    workspace_tools = {tool.spec.name: tool for tool in build_workspace_tools()}
    for tool_name in WORKSPACE_TOOL_NAMES:
        workspace_tool = workspace_tools[tool_name]
        registry.register(_tool(tool_name, workspace_tool.spec.description, _workspace_assist, input_model=QuestionToolInput, metadata={"next_route": "answer"}))

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
) -> RegisteredTool:
    if name in TOOL_SCHEMAS:
        schemas = TOOL_SCHEMAS[name]
        input_schema = schemas["input"]
        output_schema = schemas["output"]
    else:
        input_schema = input_model.model_json_schema() if input_model is not None else {"type": "object"}
        output_schema = output_model.model_json_schema() if output_model is not None else {"type": "object"}

    rt = RegisteredTool(
        spec=ToolSpec(
            name=name,
            description=description,
            input_schema=input_schema,
            output_schema=output_schema,
            input_model=input_model,
            output_model=output_model,
            policy=policy or ToolPolicy(),
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
            
    safe_sql = state_safe_sql or args_sql or ctx.state.get("sql")
    return execute_sql_tool(ctx.db, _request(ctx, args), str(safe_sql or ""), safety=safety)


def _sql_skip_execution(_ctx: ToolContext, _args: dict[str, Any]) -> ToolObservation:
    return skipped_execute_observation()


def _sql_revise(ctx: ToolContext, args: dict[str, Any]) -> ToolObservation:
    instruction = (
        args.get("instruction")
        or args.get("user_instruction")
        or args.get("reason")
        or args.get("error")
        or ctx.state.get("error")
        or "Revise the SQL according to the latest user request."
    )
    sql = (
        args.get("sql")
        or args.get("safe_sql")
        or ctx.state.get("sql")
        or _pending_approval_sql(ctx.state)
    )
    return revise_sql_tool(
        sql=str(sql or ""),
        error=str(instruction),
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
    # Prefer _current_tool_name from the new ReAct graph; fall back to
    # pending_tool_call for backward compatibility with agent_kernel.
    tool_name = str(ctx.state.get("_current_tool_name") or "")
    if not tool_name:
        pending_call = ctx.state.get("pending_tool_call")
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


def _string_arg(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None
