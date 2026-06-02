from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


AgentStepStatus = Literal["success", "failed", "skipped"]
AgentArtifactType = Literal[
    "query_plan",
    "sql",
    "safety",
    "table",
    "chart",
    "insight",
    "recommendation",
    "error",
]
AgentPresentationMode = Literal["inline", "dock", "both", "hidden"]
AgentRuntimeEventType = Literal[
    "agent.run.started",
    "agent.step.started",
    "agent.step.completed",
    "agent.artifact.created",
    "agent.answer.completed",
    "agent.run.completed",
    "agent.run.failed",
]


class AgentContextArtifact(BaseModel):
    id: str
    type: AgentArtifactType
    title: str
    summary: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class AgentFollowUpContext(BaseModel):
    session_id: str | None = None
    parent_run_id: str | None = None
    previous_question: str | None = None
    previous_answer: str | None = None
    artifacts: list[AgentContextArtifact] = Field(default_factory=list)


class AgentRunRequest(BaseModel):
    datasource_id: str
    question: str
    session_id: str | None = None
    parent_run_id: str | None = None
    follow_up_context: AgentFollowUpContext | None = None
    api_key: str | None = None
    api_base: str | None = None
    model_name: str | None = None
    optimize_rag: bool = True
    execute: bool = True
    max_steps: int = Field(default=12, ge=1, le=20)


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


class ReviseResult(BaseModel):
    can_fix: bool
    fixed_sql: str | None = None
    reason: str
    changes: list[str] = Field(default_factory=list)
    remaining_risks: list[str] = Field(default_factory=list)
    revise_suggestion: str
    blocked_sql: str | None = None


class AgentArtifactPresentation(BaseModel):
    mode: AgentPresentationMode
    priority: int = 100
    collapsed: bool = False


class AgentArtifact(BaseModel):
    id: str
    type: AgentArtifactType
    title: str
    payload: dict[str, Any] = Field(default_factory=dict)
    presentation: AgentArtifactPresentation
    refs: dict[str, Any] = Field(default_factory=dict)


class FollowUpSuggestion(BaseModel):
    label: str
    question: str
    reason: str
    action_type: Literal["ask", "chart", "export", "save_golden_sql"]


class AnswerEvidence(BaseModel):
    artifact_id: str
    label: str
    value: str | int | float | None = None


class AgentAnswer(BaseModel):
    answer: str
    key_findings: list[str] = Field(default_factory=list)
    evidence: list[AnswerEvidence] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    follow_up_questions: list[str] = Field(default_factory=list)


class AgentMessageBlock(BaseModel):
    block_id: str | None = None
    sequence: int | None = None
    type: Literal["text", "artifact_ref", "answer", "suggestions"]
    content: str | None = None
    artifact_id: str | None = None
    display: Literal["compact", "full"] | None = None
    answer: AgentAnswer | None = None
    suggestions: list[FollowUpSuggestion] = Field(default_factory=list)


class ColumnProfile(BaseModel):
    kind: Literal["numeric", "category", "time", "unknown"]
    count: int
    null_count: int = 0
    distinct_count: int = 0
    sample_values: list[Any] = Field(default_factory=list)
    min: float | str | None = None
    max: float | str | None = None
    sum: float | None = None
    avg: float | None = None
    top_values: list[dict[str, Any]] = Field(default_factory=list)


class ResultProfile(BaseModel):
    row_count: int
    column_profiles: dict[str, ColumnProfile] = Field(default_factory=dict)
    detected_patterns: list[str] = Field(default_factory=list)
    notable_facts: list[str] = Field(default_factory=list)
    anomalies: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class AgentVisibleEvent(BaseModel):
    event_id: str | None = None
    sequence: int | None = None
    created_at_ms: int | None = None
    type: Literal[
        "agent.narration.delta",
        "agent.narration.completed",
        "agent.artifact.created",
        "agent.answer.delta",
        "agent.answer.completed",
        "agent.suggestions.created",
    ]
    content: str | None = None
    artifact: AgentArtifact | None = None
    answer: AgentAnswer | None = None
    suggestions: list[FollowUpSuggestion] = Field(default_factory=list)


class AgentTraceEvent(BaseModel):
    event_id: str | None = None
    sequence: int | None = None
    created_at_ms: int | None = None
    type: Literal["agent.trace.step_started", "agent.trace.step_completed"]
    step_id: str
    name: str
    status: AgentStepStatus | None = None
    input: dict[str, Any] | None = None
    output: dict[str, Any] | None = None
    error: str | None = None
    latency_ms: int | None = None


class AgentError(BaseModel):
    code: str
    message: str
    details: dict[str, Any] | None = None
    revise_suggestion: str | None = None


class AgentRunResponse(BaseModel):
    run_id: str
    session_id: str
    parent_run_id: str | None = None
    success: bool
    question: str
    context_summary: str | None = None
    referenced_artifact_ids: list[str] = Field(default_factory=list)
    query_plan: dict[str, Any] | None = None
    sql: str | None = None
    safety: dict[str, Any] | None = None
    execution: dict[str, Any] | None = None
    explanation: str | None = None
    chart_suggestion: dict[str, Any] | None = None
    result_profile: ResultProfile | None = None
    answer: AgentAnswer | None = None
    suggestions: list[FollowUpSuggestion] = Field(default_factory=list)
    artifacts: list[AgentArtifact] = Field(default_factory=list)
    message_blocks: list[AgentMessageBlock] = Field(default_factory=list)
    events: list[AgentVisibleEvent] = Field(default_factory=list)
    trace_events: list[AgentTraceEvent] = Field(default_factory=list)
    steps: list[AgentStep] = Field(default_factory=list)
    error: str | None = None


class AgentRuntimeEvent(BaseModel):
    event_id: str
    run_id: str
    sequence: int
    created_at_ms: int
    type: AgentRuntimeEventType
    step: dict[str, Any] | None = None
    artifact: AgentArtifact | None = None
    answer: AgentAnswer | None = None
    response: AgentRunResponse | None = None
    error: str | None = None
