from __future__ import annotations

from typing import Any

from engine.agent.types import AgentAnswer, AgentArtifact, AgentArtifactPresentation, ResultProfile


class AgentArtifactIdentity:
    def __init__(self, run_id: str | None = None):
        self.run_id = run_id
        self._counter = 0

    def next_id(self, semantic_id: str) -> str:
        if not self.run_id:
            return semantic_id
        self._counter += 1
        return f"agent/run/{self.run_id}/artifact/{self._counter:03d}/{semantic_id}"


def build_agent_artifacts(
    query_plan: dict[str, Any] | None,
    sql: str | None,
    safety: dict[str, Any] | None,
    execution: dict[str, Any] | None,
    chart_suggestion: dict[str, Any] | None,
    result_profile: ResultProfile | None,
    answer: AgentAnswer | None,
    error: str | None = None,
    identity: AgentArtifactIdentity | None = None,
) -> list[AgentArtifact]:
    artifacts: list[AgentArtifact] = []

    if query_plan:
        artifacts.append(build_query_plan_artifact(query_plan, identity=identity))

    if sql:
        artifacts.append(build_sql_artifact(sql, safety=safety, identity=identity))

    if safety:
        artifacts.append(build_safety_artifact(safety, identity=identity))

    if execution and execution.get("success"):
        artifacts.append(build_table_artifact(execution, safety=safety, identity=identity))

    if chart_suggestion and chart_suggestion.get("type") and chart_suggestion.get("type") != "table":
        artifacts.append(build_chart_artifact(chart_suggestion, safety=safety, identity=identity))

    if result_profile:
        artifacts.append(build_profile_artifact(result_profile, safety=safety, identity=identity))

    if answer and answer.recommendations:
        artifacts.append(build_recommendations_artifact(answer, identity=identity))

    if error:
        artifacts.append(build_error_artifact(error, safety=safety, execution=execution, identity=identity))

    return sorted(artifacts, key=lambda artifact: artifact.presentation.priority)


def build_query_plan_artifact(
    query_plan: dict[str, Any],
    *,
    identity: AgentArtifactIdentity | None = None,
) -> AgentArtifact:
    return _artifact(
        "query_plan",
        "query_plan",
        "Query plan",
        query_plan,
        mode="dock",
        priority=80,
        collapsed=True,
        identity=identity,
        produced_by_step="build_query_plan",
    )


def build_sql_artifact(
    sql: str,
    *,
    safety: dict[str, Any] | None,
    identity: AgentArtifactIdentity | None = None,
) -> AgentArtifact:
    return _artifact(
        "sql_candidate",
        "sql",
        "Validated SQL",
        {"sql": sql, "safety_state": _safety_state(safety)},
        mode="dock",
        priority=70,
        collapsed=True,
        identity=identity,
        produced_by_step="validate_sql",
        depends_on=["query_plan"],
    )


def build_safety_artifact(
    safety: dict[str, Any],
    *,
    identity: AgentArtifactIdentity | None = None,
) -> AgentArtifact:
    return _artifact(
        "safety_report",
        "safety",
        "Safety report",
        safety,
        mode="dock",
        priority=75,
        collapsed=True,
        identity=identity,
        produced_by_step="validate_sql",
        depends_on=["sql_candidate"],
    )


def build_table_artifact(
    execution: dict[str, Any],
    *,
    safety: dict[str, Any] | None,
    identity: AgentArtifactIdentity | None = None,
) -> AgentArtifact:
    return _artifact(
        "result_table",
        "table",
        "Result table",
        {
            "columns": execution.get("columns", []),
            "rows": execution.get("rows", []),
            "rowCount": execution.get("rowCount", len(execution.get("rows", []) or [])),
            "latencyMs": execution.get("latencyMs", 0),
            "safety_state": _safety_state(safety),
        },
        mode="both",
        priority=20,
        identity=identity,
        produced_by_step="execute_sql",
        depends_on=["sql_candidate", "safety_report"],
    )


def build_profile_artifact(
    result_profile: ResultProfile,
    *,
    safety: dict[str, Any] | None,
    identity: AgentArtifactIdentity | None = None,
) -> AgentArtifact:
    return _artifact(
        "result_profile",
        "insight",
        "Result profile",
        {**result_profile.model_dump(), "safety_state": _safety_state(safety)},
        mode="both",
        priority=10,
        identity=identity,
        produced_by_step="profile_result",
        depends_on=["result_table"],
    )


def build_chart_artifact(
    chart_suggestion: dict[str, Any],
    *,
    safety: dict[str, Any] | None,
    identity: AgentArtifactIdentity | None = None,
) -> AgentArtifact:
    return _artifact(
        "chart_suggestion",
        "chart",
        "Chart suggestion",
        {**chart_suggestion, "safety_state": _safety_state(safety)},
        mode="inline",
        priority=30,
        identity=identity,
        produced_by_step="suggest_chart",
        depends_on=["result_table"],
    )


def build_recommendations_artifact(
    answer: AgentAnswer,
    *,
    identity: AgentArtifactIdentity | None = None,
) -> AgentArtifact:
    return _artifact(
        "recommendations",
        "recommendation",
        "Recommended next steps",
        {"recommendations": answer.recommendations, "followUpQuestions": answer.follow_up_questions},
        mode="inline",
        priority=40,
        identity=identity,
        produced_by_step="answer_synthesizer",
        depends_on=["result_profile"],
    )


def build_error_artifact(
    error: str,
    *,
    safety: dict[str, Any] | None,
    execution: dict[str, Any] | None,
    identity: AgentArtifactIdentity | None = None,
) -> AgentArtifact:
    return _artifact(
        "agent_error",
        "error",
        "Agent stopped",
        {
            "error": error,
            "recovery_guidance": _recovery_guidance(error, safety, execution),
            "safety_state": _safety_state(safety),
        },
        mode="both",
        priority=1,
        identity=identity,
        produced_by_step="agent_finalize",
        depends_on=["safety_report"],
    )


def _safety_state(safety: dict[str, Any] | None) -> dict[str, Any]:
    if not safety:
        return {"available": False}
    return {
        "available": True,
        "passed": bool(safety.get("passed")),
        "can_execute": bool(safety.get("can_execute")),
        "requires_confirmation": bool(safety.get("requires_confirmation")),
        "guardrail_result": (safety.get("guardrail") or {}).get("result") if isinstance(safety.get("guardrail"), dict) else None,
        "schema_warnings_count": len(safety.get("schema_warnings") or []),
    }


def _recovery_guidance(
    error: str,
    safety: dict[str, Any] | None,
    execution: dict[str, Any] | None,
) -> str:
    if safety and safety.get("revise_suggestion"):
        return str(safety["revise_suggestion"])
    if execution and execution.get("revise_suggestion"):
        return str(execution["revise_suggestion"])
    if safety and safety.get("requires_confirmation"):
        return "Review the SQL and datasource environment, then rerun after manual confirmation."
    if "max_steps" in error:
        return "Increase max_steps or run a narrower question so the agent can finish validation and synthesis."
    return "Open the trace drawer, review the blocked SQL and safety report, then retry with a narrower question."


def _artifact(
    semantic_id: str,
    artifact_type: str,
    title: str,
    payload: dict[str, Any],
    mode: str,
    priority: int,
    collapsed: bool = False,
    identity: AgentArtifactIdentity | None = None,
    produced_by_step: str | None = None,
    depends_on: list[str] | None = None,
) -> AgentArtifact:
    return AgentArtifact(
        id=identity.next_id(semantic_id) if identity else semantic_id,
        semantic_id=semantic_id,
        type=artifact_type,  # type: ignore[arg-type]
        title=title,
        payload=payload,
        presentation=AgentArtifactPresentation(
            mode=mode,  # type: ignore[arg-type]
            priority=priority,
            collapsed=collapsed,
        ),
        produced_by_step=produced_by_step,
        depends_on=depends_on or [],
    )
