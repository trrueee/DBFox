from __future__ import annotations

from typing import Any, Callable

from pydantic import BaseModel, ConfigDict, Field

from engine.agent_core.answer import synthesize_agent_answer
from engine.agent_core.chart_builder import suggest_plotly_chart
from engine.agent_core.result_profiler import profile_result
from engine.agent_core.types import AgentAnswer, ResultProfile, ToolObservation
from engine.tools.db_tools import (
    db_inspect,
    db_observe,
    db_query,
    db_remember,
    db_search,
)
from engine.tools.memory_tools import (
    memory_delete,
    memory_search,
    memory_summarize_session,
    memory_write,
)
from engine.tools.runtime import (
    ArtifactSpec,
    BaseTool,
    ToolContext,
    ToolExecutionSpec,
    ToolPolicy,
    ToolRegistry,
    ToolRunContext,
    ToolStateSpec,
)
from engine.tools.safe_preview import db_preview


class EmptyInput(BaseModel):
    pass


class LooseOutput(BaseModel):
    model_config = ConfigDict(extra="allow")


class SearchInput(BaseModel):
    query: str
    limit: int | None = None


class InspectInput(BaseModel):
    target: str


class PreviewInput(BaseModel):
    table: str
    columns: list[str] | None = None
    limit: int | None = None
    where: Any | None = None
    order_by: str | None = None


class QueryInput(BaseModel):
    sql: str
    question: str | None = None


class RememberInput(BaseModel):
    model_config = ConfigDict(extra="allow")


class EscalateInput(BaseModel):
    group: str
    reason: str = ""


class ResultProfileInput(BaseModel):
    execution_result: dict[str, Any] | None = None
    question: str | None = None


class ChartSuggestInput(BaseModel):
    force: bool | None = None


class AnswerSynthesizeInput(BaseModel):
    question: str | None = None


class _ObservationFunctionTool(BaseTool[BaseModel, LooseOutput]):
    input_model: type[BaseModel] = EmptyInput
    output_model = LooseOutput
    policy = ToolPolicy()
    execution = ToolExecutionSpec()
    state = ToolStateSpec()
    artifacts = ArtifactSpec()
    _handler: Callable[[ToolContext, dict[str, Any]], ToolObservation]

    def run(self, tool_input: BaseModel, context: ToolRunContext) -> LooseOutput:
        old_context = ToolContext(
            db=context.db_session,
            request=context.request,
            state_view=dict(context.state),
        )
        observation = self._handler(old_context, tool_input.model_dump(mode="json", exclude_none=True))
        if observation.status != "success":
            raise RuntimeError(observation.error or f"{self.name} failed")
        return LooseOutput.model_validate(observation.output or {})


class EscalateTool(BaseTool[EscalateInput, LooseOutput]):
    name = "escalate.tool_group"
    group = "control"
    description = "Request access to an additional tool group."
    input_model = EscalateInput
    output_model = LooseOutput
    policy = ToolPolicy()
    execution = ToolExecutionSpec()
    state = ToolStateSpec(consumes=("allowed_tool_groups",))
    artifacts = ArtifactSpec()

    def run(self, tool_input: EscalateInput, context: ToolRunContext) -> LooseOutput:
        valid_groups = {
            "environment",
            "schema",
            "db",
            "semantic",
            "memory",
            "execution",
            "result",
            "chart",
            "answer",
        }
        group = tool_input.group.strip()
        reason = tool_input.reason.strip()
        if group not in valid_groups:
            raise RuntimeError(f"Unknown tool group '{group}'. Valid groups: {', '.join(sorted(valid_groups))}")
        current_groups = list(context.state.get("allowed_tool_groups") or [])
        if group in current_groups:
            return LooseOutput.model_validate({
                "escalated": False,
                "group": group,
                "reason": reason,
                "message": f"Group '{group}' is already available.",
            })
        return LooseOutput.model_validate({
            "escalated": True,
            "group": group,
            "reason": reason,
            "escalated_tool_groups": current_groups + [group],
        })


class DbObserveTool(_ObservationFunctionTool):
    name = "db.observe"
    group = "db"
    description = "Look at the local database map: schemas, table summaries, domains, primary keys, and relationships."
    input_model = EmptyInput
    _handler = staticmethod(db_observe)
    state = ToolStateSpec(produces=("database_map",))


class DbSearchTool(_ObservationFunctionTool):
    name = "db.search"
    group = "db"
    description = "Search the local database index for tables and columns by names, comments, aliases, and semantic hints."
    input_model = SearchInput
    _handler = staticmethod(db_search)
    state = ToolStateSpec(produces=("db_search_results",))


class DbInspectTool(_ObservationFunctionTool):
    name = "db.inspect"
    group = "db"
    description = "Inspect one live database object in real time."
    input_model = InspectInput
    _handler = staticmethod(db_inspect)
    state = ToolStateSpec(produces=("db_inspection",), clear_on_success=("error", "last_error_telemetry", "last_failed_tool_call"), merge_strategy="new")


class DbPreviewTool(_ObservationFunctionTool):
    name = "db.preview"
    group = "db"
    description = "Preview a small masked sample from a table."
    input_model = PreviewInput
    _handler = staticmethod(db_preview)
    policy = ToolPolicy(side_effect="read", risk_level="safe")
    state = ToolStateSpec(produces=("db_preview",), clear_on_success=("error", "last_error_telemetry", "last_failed_tool_call"))
    artifacts = ArtifactSpec(emit=True, artifact_types=("table",))


class DbQueryTool(_ObservationFunctionTool):
    name = "db.query"
    group = "db"
    description = "Safely execute read-only SELECT SQL through TrustGate and guardrails."
    input_model = QueryInput
    _handler = staticmethod(db_query)
    policy = ToolPolicy(side_effect="read", risk_level="warning")
    state = ToolStateSpec(produces=("execution",), clear_on_success=("error", "last_error_telemetry", "last_failed_tool_call"))
    artifacts = ArtifactSpec(emit=True, artifact_types=("table",))


class DbRememberTool(_ObservationFunctionTool):
    name = "db.remember"
    group = "db"
    description = "Record useful schema or business semantics for future searches."
    input_model = RememberInput
    _handler = staticmethod(db_remember)
    policy = ToolPolicy(side_effect="write", risk_level="warning")
    state = ToolStateSpec(merge_strategy="new")


class ResultProfileTool(BaseTool[ResultProfileInput, ResultProfile]):
    name = "result.profile"
    group = "result"
    description = "Compute a statistical profile of the latest query result."
    input_model = ResultProfileInput
    output_model = ResultProfile
    policy = ToolPolicy()
    execution = ToolExecutionSpec()
    state = ToolStateSpec(consumes=("execution",), produces=("result_profile",), merge_strategy="new")
    artifacts = ArtifactSpec(emit=True, artifact_types=("insight",))

    def run(self, tool_input: ResultProfileInput, context: ToolRunContext) -> ResultProfile:
        execution = tool_input.execution_result or context.state.get("execution")
        if not isinstance(execution, dict) or not execution.get("success"):
            raise RuntimeError("No successful execution result available. Run db.query first.")
        question = tool_input.question or getattr(context.request, "question", "") or ""
        return profile_result(
            question=question,
            columns=list(execution.get("columns") or []),
            rows=list(execution.get("rows") or []),
            execution_success=True,
        )


class ChartSuggestTool(BaseTool[ChartSuggestInput, LooseOutput]):
    name = "chart.suggest"
    group = "chart"
    description = "Suggest a deterministic chart for the current query result."
    input_model = ChartSuggestInput
    output_model = LooseOutput
    policy = ToolPolicy()
    execution = ToolExecutionSpec()
    state = ToolStateSpec(consumes=("execution",), produces=("chart_suggestion",), merge_strategy="new")
    artifacts = ArtifactSpec(emit=True, artifact_types=("chart",))

    def run(self, tool_input: ChartSuggestInput, context: ToolRunContext) -> LooseOutput:
        execution = context.state.get("execution")
        if not isinstance(execution, dict) or not execution.get("success"):
            raise RuntimeError("No successful execution result available for chart suggestion.")
        return LooseOutput.model_validate(suggest_plotly_chart(execution))


class AnswerSynthesizeTool(BaseTool[AnswerSynthesizeInput, AgentAnswer]):
    name = "answer.synthesize"
    group = "answer"
    description = "Synthesize a structured final answer from query, profile, chart, and safety state."
    input_model = AnswerSynthesizeInput
    output_model = AgentAnswer
    policy = ToolPolicy()
    execution = ToolExecutionSpec()
    state = ToolStateSpec(
        consumes=("query_plan", "sql", "safety", "execution", "result_profile", "suggestions", "error"),
        produces=("answer", "final_answer"),
        merge_strategy="always_new",
    )
    artifacts = ArtifactSpec(emit=True, artifact_types=("insight", "recommendation"))

    def run(self, tool_input: AnswerSynthesizeInput, context: ToolRunContext) -> AgentAnswer:
        result_profile = context.state.get("result_profile")
        if isinstance(result_profile, dict):
            result_profile = ResultProfile.model_validate(result_profile)
        question = tool_input.question or getattr(context.request, "question", "") or ""
        return synthesize_agent_answer(
            question=question,
            query_plan=context.state.get("query_plan"),
            sql=context.state.get("sql"),
            safety=context.state.get("safety"),
            execution=context.state.get("execution"),
            result_profile=result_profile,
            suggestions=context.state.get("suggestions"),
            error=context.state.get("error"),
        )


def _wrap_observation_tool(
    *,
    name: str,
    group: str,
    description: str,
    handler: Callable[[ToolContext, dict[str, Any]], ToolObservation],
    input_model: type[BaseModel] = EmptyInput,
    consumes: tuple[str, ...] = (),
    produces: tuple[str, ...] = (),
    side_effect: str = "none",
    risk_level: str = "safe",
) -> BaseTool:
    return type(
        f"{name.replace('.', '_').title().replace('_', '')}Tool",
        (_ObservationFunctionTool,),
        {
            "name": name,
            "group": group,
            "description": description,
            "input_model": input_model,
            "_handler": staticmethod(handler),
            "policy": ToolPolicy(side_effect=side_effect, risk_level=risk_level),
            "state": ToolStateSpec(consumes=consumes, produces=produces),
        },
    )()


def register_dbfox_tools() -> ToolRegistry:
    from engine.environment.tools import (
        environment_get_profile,
        schema_describe_table,
        schema_list_tables,
        schema_refresh_catalog,
    )
    from engine.semantic.tools import semantic_resolve

    registry = ToolRegistry()
    registry.register(EscalateTool())
    registry.register(_wrap_observation_tool(
        name="environment.get_profile",
        group="environment",
        description="Get datasource environment profile.",
        handler=environment_get_profile,
        produces=("environment_profile", "database_map"),
    ))
    registry.register(_wrap_observation_tool(
        name="schema.list_tables",
        group="schema",
        description="List live datasource tables.",
        handler=schema_list_tables,
    ))
    registry.register(_wrap_observation_tool(
        name="schema.describe_table",
        group="schema",
        description="Describe a named live datasource table.",
        handler=schema_describe_table,
    ))
    registry.register(_wrap_observation_tool(
        name="schema.refresh_catalog",
        group="schema",
        description="Refresh the local schema catalog from the live datasource.",
        handler=schema_refresh_catalog,
    ))
    registry.register(_wrap_observation_tool(
        name="semantic.resolve",
        group="semantic",
        description="Resolve business semantics for the current question.",
        handler=semantic_resolve,
        consumes=("datasource_id", "question", "workspace_context"),
        produces=("semantic_resolution",),
    ))
    registry.register(DbObserveTool())
    registry.register(DbSearchTool())
    registry.register(DbInspectTool())
    registry.register(DbPreviewTool())
    registry.register(DbQueryTool())
    registry.register(DbRememberTool())
    registry.register(ResultProfileTool())
    registry.register(ChartSuggestTool())
    registry.register(AnswerSynthesizeTool())
    registry.register(_wrap_observation_tool(
        name="memory.search",
        group="memory",
        description="Search long-term memory for relevant context.",
        handler=memory_search,
        consumes=("datasource_id", "user_id", "project_id", "thread_id", "session_id"),
    ))
    registry.register(_wrap_observation_tool(
        name="memory.write",
        group="memory",
        description="Write a new long-term memory entry.",
        handler=memory_write,
        consumes=("datasource_id", "user_id", "project_id", "thread_id", "session_id"),
        side_effect="write",
        risk_level="warning",
    ))
    registry.register(_wrap_observation_tool(
        name="memory.delete",
        group="memory",
        description="Delete a long-term memory entry.",
        handler=memory_delete,
        consumes=("datasource_id", "user_id", "project_id", "thread_id", "session_id"),
        side_effect="write",
        risk_level="warning",
    ))
    registry.register(_wrap_observation_tool(
        name="memory.summarize_session",
        group="memory",
        description="Summarize the current session for future recall.",
        handler=memory_summarize_session,
        consumes=("datasource_id", "user_id", "project_id", "thread_id", "session_id"),
    ))
    return registry
