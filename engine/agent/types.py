from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


AgentStepStatus = Literal["success", "failed", "skipped"]


class AgentRunRequest(BaseModel):
    datasource_id: str
    question: str
    api_key: str | None = None
    api_base: str | None = None
    model_name: str | None = None
    optimize_rag: bool = True
    execute: bool = True
    max_steps: int = Field(default=6, ge=1, le=20)


class AgentStep(BaseModel):
    name: str
    status: AgentStepStatus
    input: dict[str, Any] | None = None
    output: dict[str, Any] | None = None
    error: str | None = None
    latency_ms: int


class QueryPlan(BaseModel):
    analysis_goal: str
    metrics: list[dict[str, Any]] = Field(default_factory=list)
    dimensions: list[dict[str, Any]] = Field(default_factory=list)
    filters: list[dict[str, Any]] = Field(default_factory=list)
    time_range: dict[str, Any] | None = None
    candidate_tables: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    risk_notes: list[str] = Field(default_factory=list)
    raw_plan: dict[str, Any] | None = None


class SQLCandidate(BaseModel):
    sql: str
    raw_sql: str | None = None
    model: str | None = None
    mode: str | None = None
    latency_ms: int = 0
    schema_validation_warnings: list[str] = Field(default_factory=list)
    rewrite_notes: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ToolObservation(BaseModel):
    name: str
    status: AgentStepStatus
    input: dict[str, Any] | None = None
    output: dict[str, Any] | None = None
    error: str | None = None
    latency_ms: int


class AgentError(BaseModel):
    code: str
    message: str
    details: dict[str, Any] | None = None
    revise_suggestion: str | None = None


class AgentRunResponse(BaseModel):
    success: bool
    question: str
    query_plan: dict[str, Any] | None = None
    sql: str | None = None
    safety: dict[str, Any] | None = None
    execution: dict[str, Any] | None = None
    explanation: str | None = None
    chart_suggestion: dict[str, Any] | None = None
    steps: list[AgentStep] = Field(default_factory=list)
    error: str | None = None
