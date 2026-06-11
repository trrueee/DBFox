from __future__ import annotations

import time
from typing import Any, List, Optional

from pydantic import BaseModel, Field

from engine.tools.sandbox.base import BaseTool, ExecutionContext
from engine.agent_core.types import AgentRunRequest

# --- Input/Output Pydantic Models ---

class EmptyToolInput(BaseModel):
    pass

class QuestionToolInput(BaseModel):
    question: Optional[str] = None

class FollowupLoadContextInput(BaseModel):
    question: Optional[str] = None
    follow_up_context: Optional[dict[str, Any]] = None

class FollowupLoadContextOutput(BaseModel):
    context_summary: Optional[str] = None
    analysis_question: str
    schema_linking_question: str
    referenced_artifact_ids: List[str] = Field(default_factory=list)

class SchemaBuildContextInput(BaseModel):
    question: Optional[str] = None
    optimize_rag: bool = True
    follow_up_context: Optional[dict[str, Any]] = None

class SchemaBuildContextOutput(BaseModel):
    schema_context: str
    candidate_tables: List[dict[str, Any]] = Field(default_factory=list)
    candidate_columns: List[str] = Field(default_factory=list)
    selected_tables: List[str] = Field(default_factory=list)
    schema_linking_reasons: List[dict[str, Any]] = Field(default_factory=list)
    schema_context_size: int = 0
    original_schema_table_count: int = 0
    selected_schema_table_count: int = 0
    mode: str

class QueryPlanBuildInput(BaseModel):
    question: Optional[str] = None
    schema_context: Optional[dict[str, Any]] = None

class QueryPlanBuildOutput(BaseModel):
    analysis_goal: str
    metrics: List[dict[str, Any]] = Field(default_factory=list)
    dimensions: List[dict[str, Any]] = Field(default_factory=list)
    filters: List[dict[str, Any]] = Field(default_factory=list)
    time_range: Optional[dict[str, Any]] = None
    candidate_tables: List[str] = Field(default_factory=list)
    assumptions: List[str] = Field(default_factory=list)
    risk_notes: List[str] = Field(default_factory=list)
    raw_plan: dict[str, Any] = Field(default_factory=dict)

class SqlGenerateInput(BaseModel):
    question: Optional[str] = None
    schema_context: Optional[dict[str, Any]] = None
    query_plan: Optional[dict[str, Any]] = None
    follow_up_context: Optional[dict[str, Any]] = None

class SqlCandidateOutput(BaseModel):
    sql: Optional[str] = None
    raw_sql: Optional[str] = None
    model: Optional[str] = None
    mode: Optional[str] = None
    latency_ms: int = 0
    schema_validation_warnings: List[str] = Field(default_factory=list)
    rewrite_notes: List[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

class SqlValidateInput(BaseModel):
    sql: Optional[str] = None

class SqlSafetyOutput(BaseModel):
    passed: bool
    can_execute: bool
    safe_sql: Optional[str] = None
    original_sql: str
    schema_warnings: List[str] = Field(default_factory=list)
    guardrail: dict[str, Any] = Field(default_factory=dict)
    trust_gate: dict[str, Any] = Field(default_factory=dict)
    execution_safety_decision: dict[str, Any] = Field(default_factory=dict)
    requires_confirmation: bool = False
    messages: List[str] = Field(default_factory=list)
    blocked_reasons: List[str] = Field(default_factory=list)
    revise_suggestion: Optional[str] = None

class SqlExecutionInput(BaseModel):
    sql: Optional[str] = None
    question: Optional[str] = None
    safety: Optional[dict[str, Any]] = None

class SqlExecutionOutput(BaseModel):
    success: bool
    columns: List[str] = Field(default_factory=list)
    rows: List[dict[str, Any]] = Field(default_factory=list)
    rowCount: int = 0
    latencyMs: int = 0
    historyId: Optional[str] = None
    executionId: Optional[str] = None
    safetyDecision: Optional[dict[str, Any]] = None
    truncated: bool = False
    warnings: List[str] = Field(default_factory=list)
    timing: dict[str, Any] = Field(default_factory=dict)
    error_type: Optional[str] = None
    revise_suggestion: Optional[str] = None

class SqlSkipExecutionOutput(BaseModel):
    reason: str

class SqlRevisionInput(BaseModel):
    sql: Optional[str] = None
    error: Optional[str] = None
    safety: Optional[dict[str, Any]] = None
    instruction: Optional[str] = None
    user_instruction: Optional[str] = None
    reason: Optional[str] = None

class SqlRevisionOutput(BaseModel):
    can_fix: bool
    fixed_sql: Optional[str] = None
    reason: str
    changes: List[str] = Field(default_factory=list)
    remaining_risks: List[str] = Field(default_factory=list)
    revise_suggestion: str
    blocked_sql: Optional[str] = None

class ResultProfileInput(BaseModel):
    question: Optional[str] = None
    query_plan: Optional[dict[str, Any]] = None
    execution: Optional[dict[str, Any]] = None

class ResultProfileOutput(BaseModel):
    row_count: int
    column_profiles: dict[str, Any] = Field(default_factory=dict)
    detected_patterns: List[str] = Field(default_factory=list)
    notable_facts: List[str] = Field(default_factory=list)
    anomalies: List[str] = Field(default_factory=list)
    limitations: List[str] = Field(default_factory=list)

class ChartSuggestInput(BaseModel):
    execution: Optional[dict[str, Any]] = None

class ChartSuggestOutput(BaseModel):
    type: str
    x: Optional[str] = None
    y: Optional[str] = None
    reason: str
    title: Optional[str] = None
    unit: Optional[str] = None
    series: List[dict[str, Any]] = Field(default_factory=list)

class FollowupSuggestInput(BaseModel):
    question: Optional[str] = None
    sql: Optional[str] = None
    safety: Optional[dict[str, Any]] = None
    execution: Optional[dict[str, Any]] = None
    result_profile: Optional[dict[str, Any]] = None
    chart_suggestion: Optional[dict[str, Any]] = None

class FollowupSuggestOutput(BaseModel):
    suggestions: List[dict[str, Any]] = Field(default_factory=list)

class AnswerSynthesizeInput(BaseModel):
    question: Optional[str] = None
    query_plan: Optional[dict[str, Any]] = None
    sql: Optional[str] = None
    safety: Optional[dict[str, Any]] = None
    execution: Optional[dict[str, Any]] = None
    result_profile: Optional[dict[str, Any]] = None
    chart_suggestion: Optional[dict[str, Any]] = None
    suggestions: Optional[List[dict[str, Any]]] = None
    error: Optional[str] = None

class AnswerSynthesizeOutput(BaseModel):
    answer: str
    key_findings: List[str] = Field(default_factory=list)
    evidence: List[dict[str, Any]] = Field(default_factory=list)
    caveats: List[str] = Field(default_factory=list)
    recommendations: List[str] = Field(default_factory=list)
    follow_up_questions: List[str] = Field(default_factory=list)
    display_plan: List[dict[str, Any]] = Field(default_factory=list)


# Helper function to construct a dummy request for the legacy tools
def _dummy_request(
    context: ExecutionContext,
    question: Optional[str],
    follow_up_context: Optional[dict[str, Any]] = None,
) -> AgentRunRequest:
    req = AgentRunRequest(
        datasource_id=context.datasource_id,
        question=question or "",
        session_id=context.thread_id,
        api_key=context.api_key,
        api_base=context.api_base,
        model_name=context.model_name,
    )
    if follow_up_context:
        try:
            from engine.agent_core.types import AgentFollowUpContext
            req.follow_up_context = AgentFollowUpContext.model_validate(follow_up_context)
        except Exception:
            pass
    return req


# --- BaseTool Subclasses ---

class FollowupLoadContextTool(BaseTool[FollowupLoadContextInput, FollowupLoadContextOutput]):
    name = "followup.load_context"
    description = "Load and normalize follow-up context."
    input_schema = FollowupLoadContextInput
    output_schema = FollowupLoadContextOutput

    def _run(self, tool_input: FollowupLoadContextInput, context: ExecutionContext) -> FollowupLoadContextOutput:
        from engine.tools.sql_tools import load_followup_context_tool
        req = _dummy_request(context, tool_input.question, tool_input.follow_up_context)
        obs = load_followup_context_tool(req)
        return FollowupLoadContextOutput.model_validate(obs.output or {})


class SchemaBuildContextTool(BaseTool[SchemaBuildContextInput, SchemaBuildContextOutput]):
    name = "schema.build_context"
    description = "Build relevant schema context for a data question."
    input_schema = SchemaBuildContextInput
    output_schema = SchemaBuildContextOutput

    def _run(self, tool_input: SchemaBuildContextInput, context: ExecutionContext) -> SchemaBuildContextOutput:
        from engine.tools.sql_tools import build_schema_context_tool
        req = _dummy_request(context, tool_input.question, tool_input.follow_up_context)
        req.optimize_rag = tool_input.optimize_rag
        obs = build_schema_context_tool(context.db_session, req)
        return SchemaBuildContextOutput.model_validate(obs.output or {})


class QueryPlanBuildTool(BaseTool[QueryPlanBuildInput, QueryPlanBuildOutput]):
    name = "query_plan.build"
    description = "Build a structured query plan from schema context."
    input_schema = QueryPlanBuildInput
    output_schema = QueryPlanBuildOutput

    def _run(self, tool_input: QueryPlanBuildInput, context: ExecutionContext) -> QueryPlanBuildOutput:
        from engine.tools.sql_tools import build_query_plan_tool
        req = _dummy_request(context, tool_input.question)
        obs = build_query_plan_tool(context.db_session, req, schema_context=tool_input.schema_context)
        return QueryPlanBuildOutput.model_validate(obs.output or {})


class SqlGenerateTool(BaseTool[SqlGenerateInput, SqlCandidateOutput]):
    name = "sql.generate"
    description = "Generate a SQL candidate without executing it."
    input_schema = SqlGenerateInput
    output_schema = SqlCandidateOutput

    def _run(self, tool_input: SqlGenerateInput, context: ExecutionContext) -> SqlCandidateOutput:
        from engine.tools.sql_tools import generate_sql_tool
        req = _dummy_request(context, tool_input.question, tool_input.follow_up_context)
        obs = generate_sql_tool(
            context.db_session,
            req,
            schema_context=tool_input.schema_context,
            query_plan=tool_input.query_plan,
        )
        out = dict(obs.output or {})
        if "latencyMs" in out:
            out["latency_ms"] = out.pop("latencyMs")
        if "schemaValidationWarnings" in out:
            out["schema_validation_warnings"] = out.pop("schemaValidationWarnings")
        return SqlCandidateOutput.model_validate(out)


class SqlValidateTool(BaseTool[SqlValidateInput, SqlSafetyOutput]):
    name = "sql.validate"
    description = "Validate SQL with TrustGate and guardrail checks."
    input_schema = SqlValidateInput
    output_schema = SqlSafetyOutput

    def _run(self, tool_input: SqlValidateInput, context: ExecutionContext) -> SqlSafetyOutput:
        from engine.tools.sql_tools import validate_sql_tool
        obs = validate_sql_tool(context.db_session, context.datasource_id, tool_input.sql or "")
        return SqlSafetyOutput.model_validate(obs.output or {})


class SqlExecuteReadonlyTool(BaseTool[SqlExecutionInput, SqlExecutionOutput]):
    name = "sql.execute_readonly"
    description = "Execute previously validated read-only SQL."
    input_schema = SqlExecutionInput
    output_schema = SqlExecutionOutput

    def _run(self, tool_input: SqlExecutionInput, context: ExecutionContext) -> SqlExecutionOutput:
        from engine.tools.sql_tools import execute_sql_tool
        req = _dummy_request(context, tool_input.question)
        safety = tool_input.safety or {}
        sql = tool_input.sql or safety.get("safe_sql") or ""
        obs = execute_sql_tool(context.db_session, req, str(sql), safety=tool_input.safety)
        return SqlExecutionOutput.model_validate(obs.output or {})


class SqlSkipExecutionTool(BaseTool[EmptyToolInput, SqlSkipExecutionOutput]):
    name = "sql.skip_execution"
    description = "Record that SQL execution was skipped."
    input_schema = EmptyToolInput
    output_schema = SqlSkipExecutionOutput

    def _run(self, tool_input: EmptyToolInput, context: ExecutionContext) -> SqlSkipExecutionOutput:
        from engine.tools.sql_tools import skipped_execute_observation
        obs = skipped_execute_observation()
        return SqlSkipExecutionOutput.model_validate(obs.output or {})


class SqlReviseTool(BaseTool[SqlRevisionInput, SqlRevisionOutput]):
    name = "sql.revise"
    description = "Revise SQL after validation or execution error."
    input_schema = SqlRevisionInput
    output_schema = SqlRevisionOutput

    def _run(self, tool_input: SqlRevisionInput, context: ExecutionContext) -> SqlRevisionOutput:
        from engine.tools.sql_tools import revise_sql_tool
        instruction = (
            tool_input.instruction
            or tool_input.user_instruction
            or tool_input.reason
            or tool_input.error
            or "Revise the SQL according to the latest user request."
        )
        safety = tool_input.safety or {}
        sql = tool_input.sql or safety.get("safe_sql") or ""
        obs = revise_sql_tool(
            sql=str(sql),
            error=instruction,
            safety=tool_input.safety,
            db=context.db_session,
            datasource_id=context.datasource_id,
        )
        return SqlRevisionOutput.model_validate(obs.output or {})


class ResultProfileTool(BaseTool[ResultProfileInput, ResultProfileOutput]):
    name = "result.profile"
    description = "Profile query results and notable facts."
    input_schema = ResultProfileInput
    output_schema = ResultProfileOutput

    def _run(self, tool_input: ResultProfileInput, context: ExecutionContext) -> ResultProfileOutput:
        from engine.tools.sql_tools import profile_result_tool
        req = _dummy_request(context, tool_input.question)
        obs = profile_result_tool(req, tool_input.query_plan, tool_input.execution)
        return ResultProfileOutput.model_validate(obs.output or {})


class ChartSuggestTool(BaseTool[ChartSuggestInput, ChartSuggestOutput]):
    name = "chart.suggest"
    description = "Suggest a chart from query results."
    input_schema = ChartSuggestInput
    output_schema = ChartSuggestOutput

    def _run(self, tool_input: ChartSuggestInput, context: ExecutionContext) -> ChartSuggestOutput:
        from engine.agent_core.chart_builder import suggest_plotly_chart
        return ChartSuggestOutput.model_validate(suggest_plotly_chart(tool_input.execution))


class FollowupSuggestTool(BaseTool[FollowupSuggestInput, FollowupSuggestOutput]):
    name = "followup.suggest"
    description = "Suggest evidence-aware follow-up questions."
    input_schema = FollowupSuggestInput
    output_schema = FollowupSuggestOutput

    def _run(self, tool_input: FollowupSuggestInput, context: ExecutionContext) -> FollowupSuggestOutput:
        from engine.tools.sql_tools import suggest_followups_tool
        req = _dummy_request(context, tool_input.question)
        obs = suggest_followups_tool(
            req,
            tool_input.sql,
            tool_input.safety,
            tool_input.execution,
            tool_input.result_profile,
            tool_input.chart_suggestion,
        )
        return FollowupSuggestOutput.model_validate(obs.output or {})


class AnswerSynthesizeTool(BaseTool[AnswerSynthesizeInput, AnswerSynthesizeOutput]):
    name = "answer.synthesize"
    description = "Synthesize the final evidence-grounded answer."
    input_schema = AnswerSynthesizeInput
    output_schema = AnswerSynthesizeOutput

    def _run(self, tool_input: AnswerSynthesizeInput, context: ExecutionContext) -> AnswerSynthesizeOutput:
        from engine.agent_core.types import FollowUpSuggestion, ResultProfile
        from engine.agent_core.answer import synthesize_agent_answer

        profile = ResultProfile.model_validate(tool_input.result_profile) if tool_input.result_profile else None
        parsed_suggestions = [
            FollowUpSuggestion.model_validate(item)
            for item in (tool_input.suggestions or [])
            if isinstance(item, dict)
        ]
        answer = synthesize_agent_answer(
            question=tool_input.question or "",
            query_plan=tool_input.query_plan,
            sql=tool_input.sql,
            safety=tool_input.safety,
            execution=tool_input.execution,
            result_profile=profile,
            suggestions=parsed_suggestions,
            error=tool_input.error,
            chart_suggestion=tool_input.chart_suggestion,
        )
        return AnswerSynthesizeOutput.model_validate(answer.model_dump(mode="json"))
