from __future__ import annotations

from typing import Any

from engine.agent_contracts.recommendations import recommendation_texts
from engine.agent_contracts.types import AgentAnswer, AnswerEvidence, FollowUpSuggestion, ResultProfile


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
    review_only = bool(safety and safety.get("can_execute") and not execution_success and execution and execution.get("reason"))
    facts: list[str] = []

    if execution_success:
        facts = list(result_profile.notable_facts if result_profile else [])
        lead = facts[0] if facts else "The query completed and returned data for the requested analysis."
        answer = f"{lead} I treated the returned rows as evidence for the question: {question}"
    elif review_only:
        answer = "I generated and validated the SQL, but execution was disabled for this review-only run. No result set was retrieved."
        # Do NOT include profile facts — they are misleading when no execution happened
        if result_profile:
            facts = []
    else:
        answer = "I do not have a successful result set to analyze yet."
        if result_profile and result_profile.detected_patterns and "execution_skipped" not in result_profile.detected_patterns:
            facts = list(result_profile.notable_facts if result_profile else [])

    caveats = list(result_profile.limitations if result_profile else [])
    if safety and safety.get("messages"):
        caveats.extend(str(message) for message in safety.get("messages", [])[:3])
    if result_profile and result_profile.anomalies and execution_success:
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
    execution_data = execution or {}
    execution_success = bool(execution_data.get("success"))
    if execution_success:
        evidence.append(
            AnswerEvidence(
                artifact_id="result_table",
                label="Rows returned",
                value=execution_data.get("rowCount", len(execution_data.get("rows", []) or [])),
            )
        )
    if result_profile:
        if execution_success:
            evidence.append(
                AnswerEvidence(
                    artifact_id="result_profile",
                    label="Result profile",
                    value=f"{result_profile.row_count} rows profiled",
                )
            )
        else:
            # execution skipped or failed — report truthfully, not misleading row counts
            evidence.append(
                AnswerEvidence(
                    artifact_id="result_profile",
                    label="Result profile",
                    value="execution was skipped; no result set available",
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
