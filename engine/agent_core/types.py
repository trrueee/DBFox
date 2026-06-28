from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


AgentStepStatus = Literal["success", "failed", "skipped"]
AgentArtifactType = Literal[
    "agent_plan",
    "query_plan",
    "sql",
    "sql_suggestion",
    "safety",
    "result_view",
    "chart",
    "error",
]

# Artifact categorization for frontend rendering
EVIDENCE_ARTIFACT_TYPES: frozenset[str] = frozenset({"result_view", "chart", "sql"})
PROCESS_ARTIFACT_TYPES: frozenset[str] = frozenset({
    "query_plan", "sql_suggestion", "safety", "agent_plan", "error",
})
AgentPresentationMode = Literal["inline", "dock", "both", "hidden"]
AgentRuntimeEventType = Literal[
    "agent.run.started",
    "agent.step.started",
    "agent.step.completed",
    "agent.progress.update",
    "agent.context.update",
    "agent.artifact.created",
    "agent.artifact.delta",
    "agent.answer.delta",
    "agent.answer.completed",
    "agent.run.completed",
    "agent.run.failed",
    "agent.run.cancelled",
    "agent.approval.required",
    "agent.approval.resolved",
    "agent.checkpoint.saved",
    "agent.run.waiting_approval",
    "agent.run.resumed",
]

AgentApprovalStatus = Literal["pending", "approved", "rejected", "expired"]
AgentApprovalDecision = Literal["approved", "rejected"]
AgentApprovalRiskLevel = Literal["safe", "warning", "danger"]



class AgentApprovalRecord(BaseModel):
    id: str
    run_id: str
    session_id: str
    step_name: str
    tool_name: str | None = None
    status: AgentApprovalStatus
    risk_level: AgentApprovalRiskLevel
    reason: str | None = None
    policy_decision: dict[str, Any]
    requested_action: dict[str, Any] | None = None
    created_at: datetime
    expires_at: datetime | None = None
    decided_at: datetime | None = None
    decided_by: str | None = None
    decision_note: str | None = None


class AgentApprovalDecisionRequest(BaseModel):
    decision: AgentApprovalDecision
    note: str | None = None


class AgentResumeRequest(BaseModel):
    approval_id: str | None = None


class AgentCheckpointRecord(BaseModel):
    id: str
    run_id: str
    session_id: str
    checkpoint_index: int
    status: str
    current_step_name: str | None = None
    next_step_name: str | None = None
    created_at: datetime


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


class AgentWorkspaceContext(BaseModel):
    project_id: str | None = None
    datasource_id: str
    active_sql: str | None = None
    selected_sql: str | None = None
    last_query_result_preview: dict[str, Any] | None = None
    last_error: str | None = None
    selected_table_ids: list[str] = Field(default_factory=list)
    selected_table_names: list[str] = Field(default_factory=list)
    selected_column_refs: list[str] = Field(default_factory=list)
    selected_artifact_id: str | None = None
    recent_agent_run_id: str | None = None
    pending_approval_id: str | None = None
    pending_approval_status: str | None = None
    pending_approval_reason: str | None = None
    open_sql_tabs: list[dict[str, Any]] = Field(default_factory=list)
    editor_annotations: list[dict[str, Any]] = Field(default_factory=list)
    semantic_context: dict[str, Any] = Field(default_factory=dict)




class AgentRunRequest(BaseModel):
    datasource_id: str
    question: str
    session_id: str | None = None
    conversation_id: str | None = None
    user_message_id: str | None = None
    assistant_message_id: str | None = None
    parent_run_id: str | None = None
    follow_up_context: AgentFollowUpContext | None = None
    api_key: str | None = None
    api_base: str | None = None
    model_name: str | None = None
    workspace_context: AgentWorkspaceContext | None = None
    optimize_rag: bool = True
    execute: bool = True
    max_steps: int = Field(default=50, ge=1, le=60)
    semantic_mode: Literal["off", "shadow", "retry"] = "off"
    execution_mode: Literal["none", "suggest_only", "user_requested_read", "agent_autonomous_read"] | None = None


class AgentErrorOutput(BaseModel):
    error_type: str
    tool_name: str
    step_name: str
    traceback: str | None = None
    retryable: bool = False
    retry_reason: str | None = None


class AgentStep(BaseModel):
    name: str
    status: AgentStepStatus
    input: dict[str, Any] | None = None
    output: dict[str, Any] | None = None
    error: str | None = None
    latency_ms: int



class SQLCandidate(BaseModel):
    sql: str | None = None
    raw_sql: str | None = None
    model: str | None = None
    mode: str | None = None
    latency_ms: int = 0
    schema_validation_warnings: list[str] = Field(default_factory=list)
    rewrite_notes: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


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
    semantic_id: str | None = None
    type: AgentArtifactType
    title: str
    payload: dict[str, Any] = Field(default_factory=dict)
    presentation: AgentArtifactPresentation
    refs: dict[str, Any] = Field(default_factory=dict)
    produced_by_step: str | None = None
    depends_on: list[str] = Field(default_factory=list)


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
    conversation_id: str | None = None
    user_message_id: str | None = None
    assistant_message_id: str | None = None
    parent_run_id: str | None = None
    success: bool
    status: str | None = None
    question: str
    context_summary: str | None = None
    referenced_artifact_ids: list[str] = Field(default_factory=list)
    query_plan: dict[str, Any] | None = None
    sql: str | None = None
    safety: dict[str, Any] | None = None
    execution: dict[str, Any] | None = None
    explanation: str | None = None
    chart_suggestion: dict[str, Any] | None = None
    answer: AgentAnswer | None = None
    suggestions: list[FollowUpSuggestion] = Field(default_factory=list)
    artifacts: list[AgentArtifact] = Field(default_factory=list)
    message_blocks: list[AgentMessageBlock] = Field(default_factory=list)
    events: list[AgentVisibleEvent] = Field(default_factory=list)
    trace_events: list[AgentTraceEvent] = Field(default_factory=list)
    steps: list[AgentStep] = Field(default_factory=list)
    error: str | None = None
    approval: AgentApprovalRecord | None = None
    checkpoint: AgentCheckpointRecord | None = None
    approval_context: dict[str, Any] | None = None
    canvas: AgentRunCanvas | None = None


class AgentRuntimeEvent(BaseModel):
    event_id: str
    run_id: str
    conversation_id: str | None = None
    message_id: str | None = None
    user_message_id: str | None = None
    assistant_message_id: str | None = None
    sequence: int
    created_at_ms: int
    type: AgentRuntimeEventType
    step: dict[str, Any] | None = None
    artifact: AgentArtifact | None = None
    artifact_delta: dict[str, Any] | None = None
    # artifact_delta format: {"artifact_id": str, "payload_merge": dict}
    # payload_merge list fields → append, scalar fields → replace
    content: str | None = None
    answer: AgentAnswer | None = None
    response: AgentRunResponse | None = None
    approval: AgentApprovalRecord | None = None
    checkpoint: AgentCheckpointRecord | None = None
    error: str | None = None
    approval_context: dict[str, Any] | None = None


# ═══════════════════════════════════════════════════════════════════════════════
# Agent Run Canvas — P5 frontend card data contracts
# ═══════════════════════════════════════════════════════════════════════════════


class TaskLensCard(BaseModel):
    """Live task focus — driven by Progress Judge, not a step-by-step plan."""

    goal: str = ""
    current_focus: str = ""
    next_likely: str = ""
    missing_evidence: list[str] = Field(default_factory=list)


class PlanCard(BaseModel):
    """What the agent plans to do — intent, scope, success definition."""

    task_type: str = ""  # data_lookup, schema_understanding, sql_repair...
    intent_summary: str = ""  # one-line: "Query GMV for last month"
    execution_mode: str = ""  # suggest_only, user_requested_read, agent_autonomous_read
    selected_skills: list[str] = Field(default_factory=list)  # skill ids
    allowed_tool_groups: list[str] = Field(default_factory=list)
    forbidden_tool_groups: list[str] = Field(default_factory=list)
    success_criteria: list[str] = Field(default_factory=list)
    risk_notes: list[str] = Field(default_factory=list)
    grounding_level: str = ""  # none → workspace → schema → semantic → data
    plan_timestamp: str = ""


class ActivityStep(BaseModel):
    """Single entry in the Activity Timeline."""

    sequence: int = 0
    step_name: str = ""  # db.search, sql.validate...
    tool_name: str = ""  # db.search, sql.validate...
    title: str = ""  # human-readable: "Built schema context"
    status: str = "pending"  # pending | running | success | failed | skipped | blocked
    latency_ms: int = 0
    summary: str = ""  # compact result summary for the timeline
    error: str | None = None
    input_summary: str | None = None  # e.g. "table: orders"
    output_summary: str | None = None  # e.g. "3 tables selected"


class EvidenceItem(BaseModel):
    """A single piece of evidence backing the answer."""

    source: str = ""  # "tool_result", "schema_catalog", "memory", "sql_execution"
    label: str = ""  # human-readable: "orders table (3,421 rows)"
    artifact_id: str | None = None
    value_summary: str | None = None  # compact: "total_amount SUM = 1,234,567"
    confidence: str = "high"  # high | medium | low


class SafetyCheck(BaseModel):
    """A single safety/validation check result."""

    check_name: str = ""  # "TrustGate", "Guardrail", "Schema Validation"
    passed: bool = True
    detail: str = ""  # human-readable result
    blocked_reasons: list[str] = Field(default_factory=list)
    requires_approval: bool = False
    approval_status: str | None = None  # pending | approved | rejected


class RecoveryRecord(BaseModel):
    """A failure recovery attempt — what went wrong and what was tried."""

    attempt: int = 0
    failure_layer: str = ""  # schema, semantic, sql_generation, execution...
    root_cause: str = ""  # "column account_id not found in orders"
    recovery_strategy: str = ""  # "describe orders table, rebuild query plan"
    retry_budget: int = 0
    outcome: str = ""  # "recovered" | "escalated_to_user" | "finalized_with_caveat"


class AgentRunCanvas(BaseModel):
    """Complete agent run visualization contract for the frontend.

    Five cards that the UI renders directly — no raw trace interpretation needed.
    """

    run_id: str = ""
    session_id: str = ""
    status: str = ""  # running | completed | failed | waiting_approval | waiting_user

    plan: PlanCard = Field(default_factory=PlanCard)
    task_lens: TaskLensCard = Field(default_factory=TaskLensCard)
    activity: list[ActivityStep] = Field(default_factory=list)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    safety: list[SafetyCheck] = Field(default_factory=list)
    recovery: list[RecoveryRecord] = Field(default_factory=list)

    # Convenience: summary for the canvas header
    question: str = ""
    answer_summary: str = ""
    total_latency_ms: int = 0
    step_count: int = 0

