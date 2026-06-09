from __future__ import annotations

from operator import add
from typing import Annotated, Any, Literal, TypedDict


KernelStatus = Literal[
    "running",
    "waiting_user",
    "waiting_approval",
    "paused",
    "completed",
    "failed",
]


class BaseKernelState(TypedDict, total=False):
    thread_id: str
    run_id: str
    datasource_id: str
    execute: bool

    status: KernelStatus
    messages: Annotated[list[dict[str, Any]], add]

    workspace_context: Any | None
    follow_up_context: Any | None

    goal: str | None
    plan: dict[str, Any] | None
    plan_events: Annotated[list[dict[str, Any]], add]

    tool_results: Annotated[list[dict[str, Any]], add]
    artifacts: Annotated[list[dict[str, Any]], add]
    trace_events: Annotated[list[dict[str, Any]], add]

    step_count: int
    max_steps: int

    api_key: str | None
    api_base: str | None
    model_name: str | None


class AgentLifecycleState(TypedDict, total=False):
    # Seven-step Agent lifecycle state. These fields make the graph's
    # understand/context/plan/act/observe/reflect/answer loop explicit and
    # inspectable without replacing the existing controller/tool runtime.
    agent_intent: dict[str, Any] | None
    agent_context: dict[str, Any] | None
    agent_lifecycle_plan: dict[str, Any] | None
    agent_observation: dict[str, Any] | None
    agent_reflection: dict[str, Any] | None
    agent_sql_critique: dict[str, Any] | None

    pending_decision: dict[str, Any] | None
    pending_tool_call: dict[str, Any] | None
    pending_approval: dict[str, Any] | None
    last_tool_name: str | None
    last_observation: dict[str, Any] | None


class SelfHealingState(TypedDict, total=False):
    # Structured self-healing state.
    last_failed_tool_call: dict[str, Any] | None
    last_error_telemetry: dict[str, Any] | None
    retry_counters: dict[str, int]
    retry_policy: dict[str, Any] | None


class SqlFlowState(TypedDict, total=False):
    followup_context: dict[str, Any] | None
    schema_context: dict[str, Any] | None
    query_plan: dict[str, Any] | None
    sql_candidate: dict[str, Any] | None
    sql: str | None
    safety: dict[str, Any] | None
    revision_attempted: bool
    revision_count: int


class ExecutionFlowState(TypedDict, total=False):
    execution: dict[str, Any] | None
    result_profile: dict[str, Any] | None
    chart_suggestion: dict[str, Any] | None
    suggestions: list[dict[str, Any]]


class AnswerFlowState(TypedDict, total=False):
    answer: dict[str, Any] | None
    final_answer: dict[str, Any] | None
    error: str | None


class KernelState(
    BaseKernelState,
    AgentLifecycleState,
    SelfHealingState,
    SqlFlowState,
    ExecutionFlowState,
    AnswerFlowState,
):
    pass


def latest_user_message(state: KernelState) -> str:
    for message in reversed(state.get("messages", [])):
        if message.get("role") == "user":
            return str(message.get("content") or "")
    return ""
