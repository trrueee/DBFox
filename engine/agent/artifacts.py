from __future__ import annotations

from typing import Any

from engine.agent.types import AgentAnswer, AgentArtifact, AgentArtifactPresentation, ResultProfile


def build_agent_artifacts(
    query_plan: dict[str, Any] | None,
    sql: str | None,
    safety: dict[str, Any] | None,
    execution: dict[str, Any] | None,
    chart_suggestion: dict[str, Any] | None,
    result_profile: ResultProfile | None,
    answer: AgentAnswer | None,
    error: str | None = None,
) -> list[AgentArtifact]:
    artifacts: list[AgentArtifact] = []

    if query_plan:
        artifacts.append(
            _artifact(
                "query_plan",
                "query_plan",
                "Query plan",
                query_plan,
                mode="dock",
                priority=80,
                collapsed=True,
            )
        )

    if sql:
        artifacts.append(
            _artifact(
                "sql_candidate",
                "sql",
                "Validated SQL",
                {"sql": sql, "safety_state": _safety_state(safety)},
                mode="dock",
                priority=70,
                collapsed=True,
            )
        )

    if safety:
        artifacts.append(
            _artifact(
                "safety_report",
                "safety",
                "Safety report",
                safety,
                mode="dock",
                priority=75,
                collapsed=True,
            )
        )

    if execution and execution.get("success"):
        artifacts.append(
            _artifact(
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
            )
        )

    if chart_suggestion and chart_suggestion.get("type") and chart_suggestion.get("type") != "table":
        artifacts.append(
            _artifact(
                "chart_suggestion",
                "chart",
                "Chart suggestion",
                {**chart_suggestion, "safety_state": _safety_state(safety)},
                mode="inline",
                priority=30,
            )
        )

    if result_profile:
        artifacts.append(
            _artifact(
                "result_profile",
                "insight",
                "Result profile",
                {**result_profile.model_dump(), "safety_state": _safety_state(safety)},
                mode="both",
                priority=10,
            )
        )

    if answer and answer.recommendations:
        artifacts.append(
            _artifact(
                "recommendations",
                "recommendation",
                "Recommended next steps",
                {"recommendations": answer.recommendations, "followUpQuestions": answer.follow_up_questions},
                mode="inline",
                priority=40,
            )
        )

    if error:
        artifacts.append(
            _artifact(
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
            )
        )

    return sorted(artifacts, key=lambda artifact: artifact.presentation.priority)


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
    artifact_id: str,
    artifact_type: str,
    title: str,
    payload: dict[str, Any],
    mode: str,
    priority: int,
    collapsed: bool = False,
) -> AgentArtifact:
    return AgentArtifact(
        id=artifact_id,
        type=artifact_type,  # type: ignore[arg-type]
        title=title,
        payload=payload,
        presentation=AgentArtifactPresentation(
            mode=mode,  # type: ignore[arg-type]
            priority=priority,
            collapsed=collapsed,
        ),
    )
