from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

AgentTaskType = Literal[
    "chat",
    "product_help",
    "database_concept",
    "workspace_explanation",
    "schema_understanding",
    "semantic_analysis",
    "sql_generation",
    "sql_repair",
    "sql_optimization",
    "data_lookup",
    "result_analysis",
    "chart_suggestion",
    "ambiguous",
]

AgentGroundingLevel = Literal[
    "none",
    "workspace",
    "schema",
    "semantic",
    "data",
]

AgentExecutionMode = Literal[
    "none",
    "suggest_only",
    "user_requested_read",
    "agent_autonomous_read",
]

AgentToolGroup = Literal[
    "workspace",
    "environment",
    "schema",
    "semantic",
    "query_plan",
    "sql_generation",
    "sql_validation",
    "sql_repair",
    "execution",
    "result",
    "chart",
    "answer",
]


class AgentPlanDirective(BaseModel):
    """Structured plan produced by the LLM Planner node.

    This is NOT a keyword classifier. The Planner infers intent semantically
    from the user message and workspace context, then declares:
    - what kind of task this is
    - what grounding is required
    - which tool groups the ReAct model may use
    - whether SQL execution is permitted
    - whether clarification is needed
    - what success looks like (for the Progress Judge)
    """

    task_type: AgentTaskType = Field(
        description="Semantic task category inferred from user goal, not keywords."
    )
    grounding_level: AgentGroundingLevel = Field(
        description="Deepest grounding layer required: none → workspace → schema → semantic → data."
    )
    execution_mode: AgentExecutionMode = Field(
        description="Who requested / permits SQL execution: none, suggest_only, user_requested_read, agent_autonomous_read."
    )
    allowed_tool_groups: list[AgentToolGroup] = Field(
        description="Tool groups the ReAct model is permitted to call. An empty list means no tools (pure chat)."
    )
    should_call_tools: bool = Field(
        description="Whether the task requires any tool calls at all."
    )
    should_execute_sql: bool = Field(
        description="Whether the task may execute read-only SQL after validation."
    )
    needs_clarification: bool = Field(
        description="True when the user goal is ambiguous and cannot be safely inferred."
    )
    clarification_question: str | None = Field(
        default=None,
        description="The question to ask the user when needs_clarification is True.",
    )
    success_criteria: list[str] = Field(
        default_factory=list,
        description="Observable criteria the Progress Judge should check for completion.",
    )
    risk_notes: list[str] = Field(
        default_factory=list,
        description="Safety / risk notes for PolicyGate and the Progress Judge.",
    )
    reasoning_summary: str = Field(
        default="",
        description="Internal reasoning for debugging. Never shown to the user.",
    )
