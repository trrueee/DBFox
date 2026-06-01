from __future__ import annotations

from typing import Any

from engine.agent.recommendations import recommendation_texts
from engine.agent.types import AgentAnswer, AnswerEvidence, FollowUpSuggestion, ResultProfile


def synthesize_agent_answer(
    question: str,
    query_plan: dict[str, Any] | None,
    sql: str | None,
    safety: dict[str, Any] | None,
    execution: dict[str, Any] | None,
    result_profile: ResultProfile | None,
    suggestions: list[FollowUpSuggestion] | None = None,
    error: str | None = None,
) -> AgentAnswer:
    if error:
        return AgentAnswer(
            answer=f"I could not complete the analysis because: {error}",
            key_findings=[],
            evidence=_base_evidence(sql=sql, safety=safety, execution=execution, result_profile=result_profile),
            caveats=["No business conclusion was produced because the run did not complete successfully."],
            recommendations=recommendation_texts(suggestions or []),
            follow_up_questions=[suggestion.question for suggestion in (suggestions or [])],
        )

    execution_success = bool((execution or {}).get("success"))
    review_only = bool(safety and safety.get("can_execute") and execution and execution.get("reason"))
    facts = list(result_profile.notable_facts if result_profile else [])

    if execution_success:
        lead = facts[0] if facts else "The query completed and returned data for the requested analysis."
        answer = f"{lead} I treated the returned rows as evidence for the question: {question}"
    elif review_only:
        answer = "I generated and validated the SQL, but execution was disabled for this review-only run."
    else:
        answer = "I do not have a successful result set to analyze yet."

    caveats = list(result_profile.limitations if result_profile else [])
    if safety and safety.get("messages"):
        caveats.extend(str(message) for message in safety.get("messages", [])[:3])
    if result_profile and result_profile.anomalies:
        facts.extend(result_profile.anomalies[:2])

    return AgentAnswer(
        answer=answer,
        key_findings=facts[:5],
        evidence=_base_evidence(sql=sql, safety=safety, execution=execution, result_profile=result_profile),
        caveats=_dedupe(caveats)[:5],
        recommendations=recommendation_texts(suggestions or []),
        follow_up_questions=[suggestion.question for suggestion in (suggestions or [])],
    )


def _base_evidence(
    sql: str | None,
    safety: dict[str, Any] | None,
    execution: dict[str, Any] | None,
    result_profile: ResultProfile | None,
) -> list[AnswerEvidence]:
    evidence: list[AnswerEvidence] = []
    if execution and execution.get("success"):
        evidence.append(
            AnswerEvidence(
                artifact_id="result_table",
                label="Rows returned",
                value=execution.get("rowCount", len(execution.get("rows", []) or [])),
            )
        )
    if result_profile:
        evidence.append(
            AnswerEvidence(
                artifact_id="result_profile",
                label="Result profile",
                value=f"{result_profile.row_count} rows profiled",
            )
        )
    if sql:
        evidence.append(AnswerEvidence(artifact_id="sql_candidate", label="SQL", value="validated candidate"))
    if safety:
        evidence.append(
            AnswerEvidence(
                artifact_id="safety_report",
                label="Safety",
                value="passed" if safety.get("can_execute") else "blocked",
            )
        )
    return evidence


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
