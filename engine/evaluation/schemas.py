"""Agent Eval data models — JSON-based eval cases with per-layer expectations.

These are complementary to engine.schemas.agent_eval (DB-backed golden tasks).
The schemas here are for local, file-based eval cases that can be synced to
LangSmith datasets.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


EvalCategory = Literal[
    "chat",
    "schema",
    "semantic",
    "sql_generation",
    "data_lookup",
    "result_analysis",
    "policy",
    "replan",
    "artifact",
]


class AgentEvalInput(BaseModel):
    """Input for a single eval case."""

    question: str = Field(description="User question to send to the agent.")
    workspace_context: dict[str, Any] | None = Field(
        default=None,
        description="Optional workspace context (selected tables, SQL, etc.).",
    )
    datasource_fixture: str | None = Field(
        default=None,
        description="Datasource fixture name for the test, e.g. 'spider_singer'.",
    )
    project_semantics_fixture: str | None = Field(
        default=None,
        description="Semantic terms fixture name, e.g. 'ecommerce_basic'.",
    )


class PlannerExpectation(BaseModel):
    """Expected planner output assertions."""

    task_type: str | None = Field(default=None, description="Expected AgentPlanDirective.task_type.")
    execution_mode: str | None = Field(default=None)
    should_call_tools: bool | None = Field(default=None)
    should_execute_sql: bool | None = Field(default=None)
    allowed_tool_groups_contains: list[str] = Field(default_factory=list)
    allowed_tool_groups_not_contains: list[str] = Field(default_factory=list)


class TrajectoryExpectation(BaseModel):
    """Expected tool-call trajectory assertions."""

    must_call: list[str] = Field(
        default_factory=list,
        description="Tools that must be called (glob patterns, e.g. 'schema.*', 'sql.validate').",
    )
    must_not_call: list[str] = Field(
        default_factory=list,
        description="Tools that must NOT be called.",
    )
    must_call_order: list[str] = Field(
        default_factory=list,
        description="Tools that must be called in this relative order.",
    )


class PolicyExpectation(BaseModel):
    """Expected policy behavior assertions."""

    must_block: list[str] = Field(default_factory=list, description="Tool names that policy must block.")
    must_require_approval: list[str] = Field(default_factory=list, description="Tool names requiring approval.")
    must_not_execute_sql: bool = Field(default=False)


class SQLExpectation(BaseModel):
    """Expected SQL output assertions."""

    must_validate_before_execute: bool = Field(default=True)
    contains_keywords: list[str] = Field(default_factory=list)
    not_contains_keywords: list[str] = Field(default_factory=list)
    must_be_readonly: bool = Field(default=True)


class ArtifactExpectation(BaseModel):
    """Expected artifact assertions."""

    must_include_types: list[str] = Field(default_factory=list, description="e.g. ['sql', 'table', 'chart'].")
    must_not_include_types: list[str] = Field(default_factory=list)
    min_artifact_count: int | None = None


class AnswerExpectation(BaseModel):
    """Expected answer assertions (LLM-as-judge or deterministic)."""

    must_be_helpful: bool = Field(default=True)
    must_not_claim_database_access: bool = Field(default=False)
    must_be_grounded: bool = Field(default=True)
    expected_phrases: list[str] = Field(default_factory=list)
    forbidden_phrases: list[str] = Field(default_factory=list)


class SemanticExpectation(BaseModel):
    """Expected semantic resolution assertions."""

    must_resolve_metric: str | None = Field(default=None)
    must_resolve_dimension: str | None = Field(default=None)
    must_resolve_time_dimension: bool = Field(default=False)
    must_include_filter: str | None = Field(default=None)
    must_not_infer_unverified_metric_as_verified: bool = Field(default=False)


class AgentEvalExpectation(BaseModel):
    """Expected outcomes for a single eval case."""

    planner: PlannerExpectation | None = None
    trajectory: TrajectoryExpectation | None = None
    policy: PolicyExpectation | None = None
    sql: SQLExpectation | None = None
    artifacts: ArtifactExpectation | None = None
    answer: AnswerExpectation | None = None
    semantic: SemanticExpectation | None = None


class AgentEvalCase(BaseModel):
    """A single agent evaluation case."""

    id: str = Field(description="Unique case ID, e.g. 'chat_left_join_no_tools'.")
    category: EvalCategory
    description: str = Field(default="", description="What this case tests.")
    input: AgentEvalInput
    expected: AgentEvalExpectation
    metadata: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)


class AgentEvalCaseResult(BaseModel):
    """Result of evaluating a single case."""

    case_id: str
    passed: bool
    failures: list[str] = Field(default_factory=list)
    actual_plan_directive: dict[str, Any] | None = None
    actual_tools_called: list[str] = Field(default_factory=list)
    actual_artifacts: list[str] = Field(default_factory=list)
    actual_answer: str | None = None
    trace_summary: str = ""
